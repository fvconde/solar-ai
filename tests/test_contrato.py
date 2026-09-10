"""Contrato do /turn e montagem dos prompts. Nao chama o Gemini."""

from datetime import datetime, timezone

import pytest
from pydantic import ValidationError

from app.contrato import (
    LIMITE_EXPECTATIVA,
    LIMITE_HISTORICO,
    CamposExtraidos,
    MensagemHistorico,
    PerfilLead,
    SlotOferecido,
    TurnoRequest,
)
from app.lia import prompts
from app.lia.grafo import SaidaLia
from app.lia.qualificacao import INVESTIMENTO, MORADIA

CONVERSA = "0f0d4f6c-2b3a-4f1e-9a77-5c1e2b8d4a10"


def _mensagem(papel: str, texto: str) -> dict:
    return {"papel": papel, "texto": texto, "em": datetime.now(timezone.utc).isoformat()}


def _saida(**alteracoes) -> dict:
    corpo = {
        "resposta": "Claro, posso ajudar.",
        "intencao": "compra",
        "camposExtraidos": {},
        "proximaAcao": "continuar_conversa",
        "slotEscolhido": None,
    }
    corpo.update(alteracoes)
    return corpo


class TestCamposExtraidos:
    def test_tudo_nulo_e_valido(self):
        campos = CamposExtraidos()

        assert campos.preco_max is None
        assert campos.regiao is None
        assert campos.score is None

    def test_aceita_camelcase_e_snake_case(self):
        assert CamposExtraidos.model_validate({"precoMax": 650000}).preco_max == 650000
        assert CamposExtraidos.model_validate({"preco_max": 650000}).preco_max == 650000

    def test_recusa_campo_desconhecido(self):
        with pytest.raises(ValidationError):
            CamposExtraidos.model_validate({"precoMedio": 500000})

    def test_recusa_urgencia_fora_do_enum(self):
        with pytest.raises(ValidationError):
            CamposExtraidos.model_validate({"urgencia": "urgentissima"})

    @pytest.mark.parametrize("score", [-1, 101])
    def test_recusa_score_fora_da_faixa(self, score: int):
        with pytest.raises(ValidationError):
            CamposExtraidos.model_validate({"score": score})

    def test_recusa_expectativa_longa_demais(self):
        with pytest.raises(ValidationError):
            CamposExtraidos.model_validate({"expectativaRetorno": "x" * (LIMITE_EXPECTATIVA + 1)})


class TestTurnoRequest:
    def test_perfil_e_historico_sao_opcionais(self):
        requisicao = TurnoRequest.model_validate({"conversaId": CONVERSA, "mensagem": "oi"})

        assert requisicao.historico == []
        assert requisicao.perfil_lead == PerfilLead()
        assert requisicao.agenda == []

    def test_aceita_agenda_em_camelcase(self):
        inicio = datetime(2026, 9, 10, 15, 0, tzinfo=timezone.utc)

        requisicao = TurnoRequest.model_validate(
            {
                "conversaId": CONVERSA,
                "mensagem": "quinta de tarde",
                "agenda": [
                    {
                        "id": 42,
                        "inicio": inicio.isoformat(),
                        "fim": inicio.replace(hour=16).isoformat(),
                    }
                ],
            }
        )

        assert requisicao.agenda == [
            SlotOferecido(id=42, inicio=inicio, fim=inicio.replace(hour=16))
        ]

    def test_recusa_mensagem_vazia(self):
        with pytest.raises(ValidationError):
            TurnoRequest.model_validate({"conversaId": CONVERSA, "mensagem": ""})

    def test_recusa_campo_desconhecido(self):
        with pytest.raises(ValidationError):
            TurnoRequest.model_validate({"conversaId": CONVERSA, "mensagem": "oi", "canal": "web"})

    def test_recusa_historico_acima_do_limite(self):
        historico = [_mensagem("lead", "oi") for _ in range(LIMITE_HISTORICO + 1)]

        with pytest.raises(ValidationError):
            TurnoRequest.model_validate(
                {"conversaId": CONVERSA, "mensagem": "oi", "historico": historico}
            )


class TestSaidaLia:
    def test_aceita_a_forma_esperada(self):
        assert SaidaLia.model_validate(_saida()).proxima_acao == "continuar_conversa"

    def test_recusa_resposta_vazia(self):
        with pytest.raises(ValidationError):
            SaidaLia.model_validate(_saida(resposta=""))

    def test_recusa_intencao_fora_do_enum(self):
        with pytest.raises(ValidationError):
            SaidaLia.model_validate(_saida(intencao="locacao"))

    def test_recusa_proxima_acao_removida_do_contrato(self):
        with pytest.raises(ValidationError):
            SaidaLia.model_validate(_saida(proximaAcao="escalar_humano"))

    def test_recusa_campo_desconhecido(self):
        with pytest.raises(ValidationError):
            SaidaLia.model_validate(_saida(imoveisSugeridos=[]))

    def test_nao_carrega_campo_que_o_contrato_nao_tem(self):
        assert set(SaidaLia.model_fields) == {
            "resposta",
            "intencao",
            "campos_extraidos",
            "proxima_acao",
            "slot_escolhido",
        }


class TestPrompts:
    def test_persona_e_turno_saem_do_disco(self):
        assert "Lia" in prompts.persona()
        assert "camposExtraidos" in prompts._ler("turno.md")

    def test_turno_substitui_todos_os_marcadores(self):
        texto = prompts.turno(PerfilLead(), [], "quero comprar", MORADIA)

        assert "{perfil}" not in texto
        assert "{historico}" not in texto
        assert "{mensagem}" not in texto
        assert "{lacunas}" not in texto
        assert "{agenda}" not in texto
        assert "quero comprar" in texto

    def test_turno_lista_so_os_horarios_recebidos(self):
        inicio = datetime(2026, 9, 10, 18, 0, tzinfo=timezone.utc)
        agenda = [SlotOferecido(id=42, inicio=inicio, fim=inicio.replace(hour=19))]

        texto = prompts.turno(PerfilLead(), [], "quinta de tarde", agenda=agenda)

        assert "id `42`" in texto
        assert "15:00 as 16:00" in texto
        assert "id `43`" not in texto

    def test_lacunas_saem_na_ordem_recebida(self):
        bloco = self._bloco(prompts.turno(PerfilLead(), [], "oi", MORADIA))

        assert bloco.index(MORADIA[0].pergunta) < bloco.index(MORADIA[1].pergunta)

    def test_perfil_completo_diz_que_nao_falta_nada(self):
        texto = prompts.turno(PerfilLead(), [], "oi", ())

        assert "perfil esta completo" in texto

    def test_lacuna_essencial_aberta_aparece_no_bloco(self):
        bloco = self._bloco(prompts.turno(PerfilLead(), [], "oi", MORADIA))

        assert "essencial para um corretor assumir: intencao, regiao, faixa de preco" in bloco
        assert "montada sem a mensagem de agora" in bloco

    def test_piso_atendido_nao_menciona_essencial(self):
        opcionais = tuple(sinal for sinal in MORADIA if not sinal.essencial)
        bloco = self._bloco(prompts.turno(PerfilLead(), [], "oi", opcionais))

        assert "essencial" not in bloco
        assert opcionais[0].pergunta in bloco

    def test_o_bloco_devolve_a_decisao_para_a_proxima_acao(self):
        bloco = self._bloco(prompts.turno(PerfilLead(), [], "oi", MORADIA))

        assert "`proximaAcao` decide se ha proxima pergunta" in bloco

    def test_desfecho_satisfeito_e_declarado_como_fato(self):
        opcionais = tuple(sinal for sinal in INVESTIMENTO if not sinal.essencial)
        bloco = self._bloco(
            prompts.turno(PerfilLead(), [], "oi", opcionais, "direcionar_especialista")
        )

        assert "satisfaz a regra de `direcionar_especialista`" in bloco
        assert opcionais[0].pergunta in bloco

    def test_piso_aberto_nao_declara_desfecho_satisfeito(self):
        bloco = self._bloco(
            prompts.turno(PerfilLead(), [], "oi", INVESTIMENTO, "direcionar_especialista")
        )

        assert "satisfaz a regra" not in bloco
        assert "faltava essencial" in bloco

    def test_moradia_nunca_declara_desfecho_satisfeito(self):
        opcionais = tuple(sinal for sinal in MORADIA if not sinal.essencial)
        bloco = self._bloco(prompts.turno(PerfilLead(), [], "oi", opcionais, None))

        assert "satisfaz a regra" not in bloco
        assert "None" not in bloco

    def test_o_bloco_nao_enumera_como_checklist(self):
        bloco = self._bloco(prompts.turno(PerfilLead(), [], "oi", MORADIA))

        assert "1. " not in bloco

    @staticmethod
    def _bloco(texto: str) -> str:
        return texto.split(prompts.TITULO)[1].split("## O que devolver")[0]

    def test_perfil_vazio_diz_que_e_o_primeiro_contato(self):
        assert "primeiro contato" in prompts.turno(PerfilLead(), [], "oi")

    def test_perfil_omite_campo_nulo(self):
        texto = prompts.turno(PerfilLead(regiao="Butanta"), [], "oi")

        assert "regiao: Butanta" in texto
        assert "quartos" not in texto.split("## Conversa ate agora")[0]

    def test_rotulos_cobrem_todo_campo_do_perfil(self):
        campos = set(PerfilLead().model_dump(by_alias=True))

        assert campos <= set(prompts.ROTULOS)

    def test_historico_nomeia_os_dois_papeis(self):
        historico = [
            MensagemHistorico.model_validate(_mensagem("lead", "quero alugar")),
            MensagemHistorico.model_validate(_mensagem("agente", "Em que regiao?")),
        ]

        texto = prompts.turno(PerfilLead(), historico, "Pinheiros")

        assert "Lead: quero alugar" in texto
        assert "Lia: Em que regiao?" in texto
