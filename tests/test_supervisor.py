"""Testes do no supervisor e roteamento multiagente entre especialistas — card S-23.

Nenhum teste aqui chama o Gemini: o LLM entra por duble e a busca por indice
mockado, entao todas as assercoes sao deterministicas e gratuitas.
"""

import logging
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock
from uuid import UUID, uuid4

import pytest

from app.contrato import MensagemHistorico, PerfilLead, SlotOferecido, TurnoRequest
from app.lia import grafo, prompts
from app.lia import indice as indice_imoveis
from app.lia.grafo import (
    ROTA_AGENDADOR,
    ROTA_CONSULTOR,
    ROTA_QUALIFICADOR,
    ROTA_REENGAJADOR,
    ROTAS_ESPECIALISTAS,
    MotivoDoImovel,
    SaidaApresentacao,
    SaidaLia,
    _grafo,
    responder,
)
from app.lia.indice import Embutidor, Filtro, Resultado


class _DubleLLM:
    def __init__(self, *saidas):
        self.saidas = list(saidas)
        self.mensagens = []

    def invoke(self, mensagens):
        self.mensagens.append(mensagens)
        if not self.saidas:
            return SaidaLia.model_validate({
                "resposta": "Resposta padrao do duble.",
                "intencao": "compra",
                "camposExtraidos": {},
                "proximaAcao": "continuar_conversa",
                "slotEscolhido": None,
            })
        saida = self.saidas.pop(0)
        if isinstance(saida, Exception):
            raise saida
        return saida

    @property
    def chamadas(self) -> int:
        return len(self.mensagens)


@pytest.fixture(autouse=True)
def indice_mockado(monkeypatch):
    mock_indice = MagicMock()
    mock_indice.buscar.return_value = []
    monkeypatch.setattr(indice_imoveis, "atual", lambda: mock_indice)
    return mock_indice


@pytest.fixture
def dublar(monkeypatch):
    def _dublar(*saidas) -> _DubleLLM:
        duble = _DubleLLM(*saidas)
        monkeypatch.setattr(grafo, "_modelo", lambda: duble)
        monkeypatch.setattr(grafo, "_modelo_apresentacao", lambda: duble)
        return duble

    return _dublar


def _saida_lia(**alteracoes) -> SaidaLia:
    corpo = {
        "resposta": "Entendi, vou ajudar voce.",
        "intencao": "compra",
        "camposExtraidos": {},
        "proximaAcao": "continuar_conversa",
        "slotEscolhido": None,
    }
    corpo.update(alteracoes)
    return SaidaLia.model_validate(corpo)


def _saida_apresentacao(*ids: str) -> SaidaApresentacao:
    return SaidaApresentacao(
        resposta="Encontrei estas opcoes perfeitas para voce.",
        motivos=[MotivoDoImovel(id=i, motivo=f"combina com seu perfil {i}") for i in ids],
    )


class TestTopologiaDoGrafo:
    def test_grafo_contem_no_supervisor_e_os_quatro_especialistas(self):
        g = _grafo()
        nomes_dos_nos = set(g.nodes.keys())

        assert "supervisor" in nomes_dos_nos
        assert "qualificador" in nomes_dos_nos
        assert "agendador" in nomes_dos_nos
        assert "consultor" in nomes_dos_nos
        assert "reengajador" in nomes_dos_nos
        assert "responder" in nomes_dos_nos
        assert "pontuar" in nomes_dos_nos
        assert "apresentar" in nomes_dos_nos

    def test_rotas_especialistas_sao_quatro(self):
        assert ROTAS_ESPECIALISTAS == {
            "reengajador",
            "agendador",
            "consultor",
            "qualificador",
        }


class TestSupervisorRoteamento:
    def test_supervisor_nao_gasta_chamada_llm(self, monkeypatch):
        mock_modelo = MagicMock()
        monkeypatch.setattr(grafo, "_modelo", lambda: mock_modelo)
        monkeypatch.setattr(grafo, "_modelo_apresentacao", lambda: mock_modelo)

        req = TurnoRequest(
            conversa_id=uuid4(),
            mensagem="ola",
            perfil_lead=PerfilLead(),
        )

        estado_inicial = {
            "requisicao": req,
            "mascarador": grafo.MascaradorPII(),
            "reengajamento": False,
        }

        delta = grafo._supervisor(estado_inicial)

        assert delta["rota"] == ROTA_QUALIFICADOR
        assert mock_modelo.invoke.call_count == 0

    def test_roteamento_reengajador_com_flag_ativa(self, caplog, dublar):
        dublar(_saida_lia(resposta="Oi! Vi que voce procurava imoveis."))
        cid = uuid4()
        req = TurnoRequest(
            conversa_id=cid,
            mensagem="[reengajar]",
            perfil_lead=PerfilLead(regiao="Pinheiros", preco_max=800000),
        )

        with caplog.at_level(logging.INFO, logger="solar"):
            resp = responder(req, reengajamento=True)

        assert resp.resposta
        assert f"Supervisor roteou conversa {cid} para o no reengajador" in caplog.text

    def test_roteamento_agendador_quando_ha_agenda_recebida(self, caplog, dublar):
        dublar(_saida_lia(resposta="Horario confirmado para as 15h.", slotEscolhido=10))
        cid = uuid4()
        agora = datetime.now(timezone.utc)
        req = TurnoRequest(
            conversa_id=cid,
            mensagem="quinta-feira as tres da tarde",
            perfil_lead=PerfilLead(nome="Marina", intencao="compra"),
            agenda=[
                SlotOferecido(id=10, inicio=agora, fim=agora + timedelta(hours=1))
            ],
        )

        with caplog.at_level(logging.INFO, logger="solar"):
            resp = responder(req)

        assert resp.slot_escolhido == 10
        assert f"Supervisor roteou conversa {cid} para o no agendador" in caplog.text

    def test_roteamento_consultor_quando_lead_qualificado_busca_imoveis(self, caplog, dublar, monkeypatch):
        dublar(_saida_apresentacao("IMV-001"))
        cid = uuid4()

        # Perfil completo sem lacunas essenciais
        perfil_completo = PerfilLead(
            intencao="compra",
            regiao="zona sul",
            preco_max=600000,
            quartos=2,
        )

        req = TurnoRequest(
            conversa_id=cid,
            mensagem="quais opcoes de imoveis voce tem disponiveis?",
            perfil_lead=perfil_completo,
        )

        with caplog.at_level(logging.INFO, logger="solar"):
            resp = responder(req)

        assert resp.resposta
        assert f"Supervisor roteou conversa {cid} para o no consultor" in caplog.text

    def test_roteamento_qualificador_quando_ha_lacunas_essenciais(self, caplog, dublar):
        dublar(_saida_lia(resposta="Qual regiao voce prefere?"))
        cid = uuid4()
        req = TurnoRequest(
            conversa_id=cid,
            mensagem="quero comprar um imovel",
            perfil_lead=PerfilLead(intencao="compra"),
        )

        with caplog.at_level(logging.INFO, logger="solar"):
            resp = responder(req)

        assert resp.resposta
        assert f"Supervisor roteou conversa {cid} para o no qualificador" in caplog.text

    def test_quatro_turnos_de_naturezas_diferentes_produzem_quatro_rotas_distintas_no_log(
        self, caplog, dublar
    ):
        """Criterio de aceite literal: quatro turnos de naturezas diferentes produzem

        quatro rotas diferentes no log com o guid da conversa e o no escolhido.
        """
        dublar(
            _saida_lia(resposta="Reengajamento"),
            _saida_lia(resposta="Agendamento", slotEscolhido=1),
            _saida_apresentacao("IMV-001"),
            _saida_lia(resposta="Qualificacao"),
        )

        agora = datetime.now(timezone.utc)
        guid_reengajar = uuid4()
        guid_agendar = uuid4()
        guid_consultar = uuid4()
        guid_qualificar = uuid4()

        # 1. Turno de reengajamento
        req_reengajar = TurnoRequest(
            conversa_id=guid_reengajar,
            mensagem="[reengajar]",
            perfil_lead=PerfilLead(regiao="Tatuape"),
        )

        # 2. Turno de agendamento
        req_agendar = TurnoRequest(
            conversa_id=guid_agendar,
            mensagem="pode ser amanha as 10h",
            perfil_lead=PerfilLead(nome="Carlos"),
            agenda=[SlotOferecido(id=1, inicio=agora, fim=agora + timedelta(hours=1))],
        )

        # 3. Turno de consulta direta de imoveis (lead ja qualificado)
        req_consultar = TurnoRequest(
            conversa_id=guid_consultar,
            mensagem="mostrar opcoes de apartamentos disponiveis",
            perfil_lead=PerfilLead(
                intencao="compra",
                regiao="zona sul",
                preco_max=700000,
                quartos=2,
            ),
        )

        # 4. Turno de qualificacao comum
        req_qualificar = TurnoRequest(
            conversa_id=guid_qualificar,
            mensagem="ola, procuro algo para morar",
            perfil_lead=PerfilLead(),
        )

        with caplog.at_level(logging.INFO, logger="solar"):
            responder(req_reengajar, reengajamento=True)
            responder(req_agendar)
            responder(req_consultar)
            responder(req_qualificar)

        log_completo = caplog.text

        # As quatro rotas distintas aparecem, cada uma com o guid da sua conversa
        assert f"Supervisor roteou conversa {guid_reengajar} para o no reengajador" in log_completo
        assert f"Supervisor roteou conversa {guid_agendar} para o no agendador" in log_completo
        assert f"Supervisor roteou conversa {guid_consultar} para o no consultor" in log_completo
        assert f"Supervisor roteou conversa {guid_qualificar} para o no qualificador" in log_completo


class TestCustoDeChamadasNaoSobe:
    def test_turno_reengajamento_custa_uma_chamada(self, dublar):
        duble = dublar(_saida_lia(resposta="Oi!"))
        req = TurnoRequest(conversa_id=uuid4(), mensagem="[reengajar]", perfil_lead=PerfilLead())
        responder(req, reengajamento=True)
        assert duble.chamadas == 1

    def test_turno_agendamento_custa_uma_chamada(self, dublar):
        duble = dublar(_saida_lia(resposta="Marcado."))
        agora = datetime.now(timezone.utc)
        req = TurnoRequest(
            conversa_id=uuid4(),
            mensagem="horario 1",
            perfil_lead=PerfilLead(),
            agenda=[SlotOferecido(id=1, inicio=agora, fim=agora + timedelta(hours=1))],
        )
        responder(req)
        assert duble.chamadas == 1

    def test_turno_qualificacao_comum_custa_uma_chamada(self, dublar):
        duble = dublar(_saida_lia(resposta="Qual regiao?"))
        req = TurnoRequest(conversa_id=uuid4(), mensagem="oi", perfil_lead=PerfilLead())
        responder(req)
        assert duble.chamadas == 1

    def test_turno_consultor_direto_custa_uma_chamada(self, dublar):
        duble = dublar(_saida_apresentacao("IMV-001"))
        req = TurnoRequest(
            conversa_id=uuid4(),
            mensagem="buscar imoveis",
            perfil_lead=PerfilLead(intencao="compra", regiao="sul", preco_max=500000, quartos=2),
        )
        responder(req)
        assert duble.chamadas == 1

    def test_turno_qualificacao_que_sugere_imoveis_custa_duas_chamadas(self, dublar):
        duble = dublar(
            _saida_lia(proximaAcao="sugerir_imoveis"),
            _saida_apresentacao("IMV-001", "IMV-002"),
        )
        req = TurnoRequest(
            conversa_id=uuid4(),
            mensagem="quero apartamento de 2 quartos",
            perfil_lead=PerfilLead(intencao="compra"),
        )
        responder(req)
        assert duble.chamadas == 2
