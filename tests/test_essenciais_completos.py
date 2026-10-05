from unittest.mock import MagicMock
from uuid import uuid4

import pytest
from pydantic import ValidationError

from app.contrato import (
    CamposExtraidos,
    PerfilLead,
    TurnoRequest,
    TurnoResponse,
)
from app.lia import grafo
from app.lia import indice as indice_imoveis
from app.lia.grafo import (
    CamposExtraidosLLM,
    SaidaApresentacao,
    SaidaLia,
    responder,
)


class _DubleLLM:
    def __init__(self, *saidas):
        self.saidas = list(saidas)

    def invoke(self, mensagens):
        if not self.saidas:
            return SaidaLia.model_validate({
                "resposta": "Resposta padrao do duble.",
                "intencao": "compra",
                "camposExtraidos": {},
                "proximaAcao": "continuar_conversa",
                "slotEscolhido": None,
            })
        return self.saidas.pop(0)


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


def test_responder_perfil_incompleto_retorna_essenciais_completos_false(dublar):
    dublar(_saida_lia(intencao="compra", camposExtraidos={}))
    requisicao = TurnoRequest(
        conversa_id=uuid4(),
        mensagem="quero comprar",
        perfil_lead=PerfilLead(intencao="compra"),
    )

    resposta = responder(requisicao)

    assert resposta.essenciais_completos is False


def test_responder_perfil_fecha_com_extraidos_deste_turno_retorna_essenciais_completos_true(dublar):
    dublar(
        _saida_lia(
            intencao="compra",
            camposExtraidos={"precoMax": 750000},
        )
    )
    requisicao = TurnoRequest(
        conversa_id=uuid4(),
        mensagem="ate 750 mil",
        perfil_lead=PerfilLead(intencao="compra", regiao="Pinheiros"),
    )

    resposta = responder(requisicao)

    assert resposta.essenciais_completos is True


def test_responder_perfil_ja_completo_retorna_essenciais_completos_true(dublar):
    dublar(_saida_lia(intencao="compra", camposExtraidos={}))
    requisicao = TurnoRequest(
        conversa_id=uuid4(),
        mensagem="gostaria de agendar visita",
        perfil_lead=PerfilLead(intencao="compra", regiao="Pinheiros", preco_max=750000),
    )

    resposta = responder(requisicao)

    assert resposta.essenciais_completos is True


def test_responder_reengajamento_perfil_incompleto_retorna_essenciais_completos_false(dublar):
    dublar(_saida_lia(intencao="compra", camposExtraidos={}))
    requisicao = TurnoRequest(
        conversa_id=uuid4(),
        mensagem="[reengajar]",
        perfil_lead=PerfilLead(intencao="compra"),
    )

    resposta = responder(requisicao, reengajamento=True)

    assert resposta.essenciais_completos is False


def test_responder_reengajamento_perfil_fecha_com_extraidos_retorna_essenciais_completos_true(dublar):
    dublar(
        _saida_lia(
            intencao="compra",
            camposExtraidos={"precoMax": 800000},
        )
    )
    requisicao = TurnoRequest(
        conversa_id=uuid4(),
        mensagem="[reengajar]",
        perfil_lead=PerfilLead(intencao="compra", regiao="Moema"),
    )

    resposta = responder(requisicao, reengajamento=True)

    assert resposta.essenciais_completos is True


def test_responder_reengajamento_perfil_ja_completo_retorna_essenciais_completos_true(dublar):
    dublar(_saida_lia(intencao="compra", camposExtraidos={}))
    requisicao = TurnoRequest(
        conversa_id=uuid4(),
        mensagem="[reengajar]",
        perfil_lead=PerfilLead(intencao="compra", regiao="Moema", preco_max=800000),
    )

    resposta = responder(requisicao, reengajamento=True)

    assert resposta.essenciais_completos is True


def test_turno_response_model_dump_by_alias_contem_essenciais_completos_booleano():
    resposta_true = TurnoResponse(
        resposta="Tudo certo.",
        intencao="compra",
        campos_extraidos=CamposExtraidos(),
        proxima_acao="continuar_conversa",
        imoveis_sugeridos=[],
        slot_escolhido=None,
        essenciais_completos=True,
    )
    dados_true = resposta_true.model_dump(by_alias=True)
    assert dados_true["essenciaisCompletos"] is True
    assert "essenciais_completos" not in dados_true

    resposta_false = TurnoResponse(
        resposta="Tudo certo.",
        intencao="compra",
        campos_extraidos=CamposExtraidos(),
        proxima_acao="continuar_conversa",
        imoveis_sugeridos=[],
        slot_escolhido=None,
        essenciais_completos=False,
    )
    dados_false = resposta_false.model_dump(by_alias=True)
    assert dados_false["essenciaisCompletos"] is False
    assert "essenciais_completos" not in dados_false

    validado = TurnoResponse.model_validate({
        "resposta": "Tudo certo.",
        "intencao": "compra",
        "camposExtraidos": {},
        "proximaAcao": "continuar_conversa",
        "imoveisSugeridos": [],
        "slotEscolhido": None,
        "essenciaisCompletos": True,
    })
    assert validado.essenciais_completos is True


def test_turno_response_recusa_campo_desconhecido():
    with pytest.raises(ValidationError):
        TurnoResponse.model_validate({
            "resposta": "Tudo certo.",
            "intencao": "compra",
            "camposExtraidos": {},
            "proximaAcao": "continuar_conversa",
            "imoveisSugeridos": [],
            "slotEscolhido": None,
            "essenciaisCompletos": True,
            "campoDesconhecido": "valor",
        })


def test_turno_response_exige_essenciais_completos():
    with pytest.raises(ValidationError):
        TurnoResponse.model_validate({
            "resposta": "Tudo certo.",
            "intencao": "compra",
            "camposExtraidos": {},
            "proximaAcao": "continuar_conversa",
            "imoveisSugeridos": [],
            "slotEscolhido": None,
        })


def test_schema_saida_lia_e_saida_apresentacao_nao_contem_essenciais_completos():
    assert "essenciais_completos" not in SaidaLia.model_fields
    assert "essenciaisCompletos" not in SaidaLia.model_fields
    assert "essenciais_completos" not in SaidaLia.model_json_schema().get("properties", {})
    assert "essenciaisCompletos" not in SaidaLia.model_json_schema().get("properties", {})

    assert "essenciais_completos" not in SaidaApresentacao.model_fields
    assert "essenciaisCompletos" not in SaidaApresentacao.model_fields
    assert "essenciais_completos" not in SaidaApresentacao.model_json_schema().get("properties", {})
    assert "essenciaisCompletos" not in SaidaApresentacao.model_json_schema().get("properties", {})

    assert "essenciais_completos" not in CamposExtraidosLLM.model_fields
    assert "essenciaisCompletos" not in CamposExtraidosLLM.model_fields
    assert "essenciais_completos" not in CamposExtraidosLLM.model_json_schema().get("properties", {})
    assert "essenciaisCompletos" not in CamposExtraidosLLM.model_json_schema().get("properties", {})
