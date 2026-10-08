"""Regressoes deterministicas dos achados do SupervisorPortal.

Nenhum teste deste arquivo cria cliente Gemini: o no que chamaria o modelo e
substituido por um duble local.
"""

from datetime import datetime, timezone
from unittest.mock import MagicMock
from uuid import uuid4

import pytest

from app.contrato import ImovelSugerido, MensagemHistorico, PerfilLead, SlotOferecido, TurnoRequest
from app.lia import grafo, indice as indice_imoveis, prompts, qualificacao
from app.lia.grafo import SaidaLia, responder


class _DubleLLM:
    def __init__(self, saida: SaidaLia):
        self.saida = saida
        self.chamadas = 0

    def invoke(self, _mensagens):
        self.chamadas += 1
        return self.saida


def _saida(**alteracoes) -> SaidaLia:
    corpo = {
        "resposta": "Vou ajudar voce.",
        "intencao": "compra",
        "camposExtraidos": {},
        "proximaAcao": "continuar_conversa",
        "slotEscolhido": None,
    }
    corpo.update(alteracoes)
    return SaidaLia.model_validate(corpo)


@pytest.fixture
def ambiente(monkeypatch):
    llm = _DubleLLM(_saida())
    indice = MagicMock()
    indice.buscar.return_value = []
    monkeypatch.setattr(grafo, "_modelo", lambda: llm)
    monkeypatch.setattr(grafo, "_modelo_apresentacao", lambda: llm)
    monkeypatch.setattr(indice_imoveis, "atual", lambda: indice)
    return llm, indice


def _imovel(id_: str, bairro: str) -> ImovelSugerido:
    return ImovelSugerido(
        id=id_, tipo="apartamento", bairro=bairro, quartos=2, metragem=60,
        preco_venda=500000, preco_aluguel=None, motivo="combina com o pedido",
    )


def test_modalidade_conflitante_pede_esclarecimento_e_nao_busca(ambiente):
    llm, indice = ambiente
    llm.saida = _saida(proximaAcao="sugerir_imoveis")
    resposta = responder(
        TurnoRequest(
            conversa_id=uuid4(),
            mensagem="zona sul a partir de 300 mil",
            historico=[
                MensagemHistorico(
                    papel="lead",
                    texto="ola, gostaria de um apartamento para alugar",
                    em=datetime.now(timezone.utc),
                )
            ],
            perfil_lead=PerfilLead(intencao="aluguel"),
        )
    )

    assert resposta.intencao == "indefinida"
    assert resposta.proxima_acao == "continuar_conversa"
    assert "aluguel" in resposta.resposta
    assert "comprar" in resposta.resposta
    assert resposta.imoveis_sugeridos == []
    indice.buscar.assert_not_called()


def test_sequencia_de_conflito_e_escolha_atualiza_o_perfil_sem_repetir(ambiente):
    llm, indice = ambiente
    llm.saida = _saida(intencao="aluguel")
    primeiro = responder(
        TurnoRequest(conversa_id=uuid4(), mensagem="quero alugar")
    )
    perfil = PerfilLead(intencao=primeiro.intencao)
    historico = [
        MensagemHistorico(
            papel="lead", texto="quero alugar", em=datetime.now(timezone.utc)
        ),
        MensagemHistorico(
            papel="agente", texto=primeiro.resposta, em=datetime.now(timezone.utc)
        ),
    ]

    llm.saida = _saida(proximaAcao="sugerir_imoveis")
    ambiguo = responder(
        TurnoRequest(
            conversa_id=uuid4(),
            mensagem="zona sul a partir de 300 mil",
            historico=historico,
            perfil_lead=perfil,
        )
    )
    assert ambiguo.imoveis_sugeridos == []
    assert ambiguo.proxima_acao == "continuar_conversa"
    assert ambiguo.campos_extraidos.regiao == "zona sul"
    assert ambiguo.campos_extraidos.preco_min is None
    assert ambiguo.campos_extraidos.preco_max is None
    perfil_apos_ambiguo = qualificacao.fundir(
        perfil, ambiguo.intencao, ambiguo.campos_extraidos
    )
    assert perfil_apos_ambiguo.regiao == "zona sul"
    assert perfil_apos_ambiguo.preco_min is None
    assert perfil_apos_ambiguo.preco_max is None
    indice.buscar.assert_not_called()
    indice.reset_mock()
    historico += [
        MensagemHistorico(
            papel="lead",
            texto="zona sul a partir de 300 mil",
            em=datetime.now(timezone.utc),
        ),
        MensagemHistorico(
            papel="agente", texto=ambiguo.resposta, em=datetime.now(timezone.utc)
        ),
    ]

    llm.saida = _saida(
        resposta="Você quer alugar ou comprar?",
        proximaAcao="continuar_conversa",
    )
    indice.buscar.return_value = []
    resolvido = responder(
        TurnoRequest(
            conversa_id=uuid4(),
            mensagem="desculpe, eu quero comprar agora",
            historico=historico,
            perfil_lead=perfil_apos_ambiguo,
        )
    )
    perfil_resultante = qualificacao.fundir(
        perfil_apos_ambiguo, resolvido.intencao, resolvido.campos_extraidos
    )

    assert resolvido.intencao == "compra"
    assert perfil_resultante.intencao == "compra"
    assert perfil_resultante.regiao == "zona sul"
    assert perfil_resultante.preco_min == 300000
    assert perfil_resultante.preco_max is None
    assert "Você quer alugar ou comprar?" not in resolvido.resposta
    assert "região" not in resolvido.resposta
    assert "compra" in resolvido.resposta.lower()
    assert resolvido.imoveis_sugeridos == []
    assert indice.buscar.call_count == 1


def test_resposta_vaga_mantem_esclarecimento_pendente(ambiente):
    llm, indice = ambiente
    llm.saida = _saida(proximaAcao="sugerir_imoveis")
    resposta = responder(
        TurnoRequest(
            conversa_id=uuid4(),
            mensagem="não sei",
            historico=[
                MensagemHistorico(
                    papel="agente",
                    texto="Você quer alugar ou comprar? Esse valor é mensal ou o preço total do imóvel?",
                    em=datetime.now(timezone.utc),
                )
            ],
            perfil_lead=PerfilLead(intencao="aluguel"),
        )
    )

    assert resposta.intencao == "indefinida"
    assert resposta.proxima_acao == "continuar_conversa"
    assert "Você quer alugar ou comprar?" in resposta.resposta
    assert resposta.imoveis_sugeridos == []
    indice.buscar.assert_not_called()


def test_primeira_opcao_preserva_cartao_e_nao_cria_nova_vitrine(ambiente):
    llm, indice = ambiente
    llm.saida = _saida(resposta="A segunda opcao parece melhor.", proximaAcao="sugerir_imoveis")
    resposta = responder(
        TurnoRequest(
            conversa_id=uuid4(),
            mensagem="gostei da primeira opção",
            historico=[
                MensagemHistorico(
                    papel="agente",
                    texto="Encontrei estas opções.",
                    em=datetime.now(timezone.utc),
                    imoveis_sugeridos=[_imovel("IMV-1", "Santo Amaro"), _imovel("IMV-2", "Jabaquara")],
                )
            ],
            perfil_lead=PerfilLead(intencao="compra", regiao="zona sul", preco_max=600000),
            agenda=[SlotOferecido(id=1, inicio=datetime.now(timezone.utc), fim=datetime.now(timezone.utc))],
        )
    )

    assert "Santo Amaro" in resposta.resposta
    assert "Jabaquara" not in resposta.resposta
    assert resposta.proxima_acao == "agendar_reuniao"
    assert resposta.imoveis_sugeridos == []
    indice.buscar.assert_not_called()


def test_prompt_preserva_ordem_dos_cartoes_no_historico():
    historico = [
        MensagemHistorico(
            papel="agente",
            texto="Encontrei estas opções.",
            em=datetime.now(timezone.utc),
            imoveis_sugeridos=[_imovel("IMV-1", "Santo Amaro"), _imovel("IMV-2", "Jabaquara")],
        )
    ]

    texto = prompts._historico(historico)

    assert "1. IMV-1 — Santo Amaro; 2. IMV-2 — Jabaquara" in texto


def test_visita_confirmada_bloqueia_nova_vitrine(ambiente):
    llm, indice = ambiente
    llm.saida = _saida(resposta="Vou mostrar novas opções.", proximaAcao="sugerir_imoveis")
    resposta = responder(
        TurnoRequest(
            conversa_id=uuid4(),
            mensagem="tem mais algum?",
            perfil_lead=PerfilLead(intencao="compra", regiao="zona sul", preco_max=600000),
            visita_confirmada=True,
            contato_informado=True,
        )
    )

    assert resposta.proxima_acao == "agendar_reuniao"
    assert (
        resposta.resposta
        == "Sua reunião já está confirmada e o corretor dará continuidade ao atendimento."
    )
    assert resposta.imoveis_sugeridos == []
    indice.buscar.assert_not_called()


def test_handoff_sem_contato_pede_contato_sem_prometer_retorno(ambiente):
    llm, _indice = ambiente
    llm.saida = _saida(
        resposta="Já vou pedir para um corretor entrar em contato.",
        proximaAcao="agendar_reuniao",
    )
    resposta = responder(
        TurnoRequest(
            conversa_id=uuid4(),
            mensagem="quero falar com um corretor",
            perfil_lead=PerfilLead(intencao="compra", regiao="zona sul", preco_max=600000),
        )
    )

    assert "informe seu telefone ou e-mail" in resposta.resposta
    assert "já vou pedir" not in resposta.resposta.lower()


def test_pergunta_de_regiao_tem_acentuacao():
    from app.lia.qualificacao import MORADIA

    assert "região ou bairro" in MORADIA[1].pergunta
