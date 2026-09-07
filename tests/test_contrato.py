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
    TurnoRequest,
)
from app.lia import prompts
from app.lia.grafo import SaidaLia

CONVERSA = "0f0d4f6c-2b3a-4f1e-9a77-5c1e2b8d4a10"


def _mensagem(papel: str, texto: str) -> dict:
    return {"papel": papel, "texto": texto, "em": datetime.now(timezone.utc).isoformat()}


def _saida(**alteracoes) -> dict:
    corpo = {
        "resposta": "Claro, posso ajudar.",
        "intencao": "compra",
        "camposExtraidos": {},
        "proximaAcao": "continuar_conversa",
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
        }


class TestPrompts:
    def test_persona_e_turno_saem_do_disco(self):
        assert "Lia" in prompts.persona()
        assert "camposExtraidos" in prompts._ler("turno.md")

    def test_turno_substitui_os_tres_marcadores(self):
        texto = prompts.turno(PerfilLead(), [], "quero comprar")

        assert "{perfil}" not in texto
        assert "{historico}" not in texto
        assert "{mensagem}" not in texto
        assert "quero comprar" in texto

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
