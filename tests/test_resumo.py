"""Resumo para o corretor. Testes determinísticos: nunca chamam o Gemini."""

from unittest.mock import MagicMock

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.contrato import (
    ImovelSugerido,
    MensagemHistorico,
    PerfilLead,
    ResumoRequest,
    ResumoResponse,
)
from app.lia import grafo, prompts
from app.main import app


_app_contrato = FastAPI()


@_app_contrato.post("/resumo")
def _validar_contrato(requisicao: ResumoRequest) -> dict[str, bool]:
    return {"valido": bool(requisicao.historico)}


_cliente_contrato = TestClient(_app_contrato)
_cliente_endpoint = TestClient(app)


class _DubleResumo:
    def __init__(self, saida: ResumoResponse):
        self.saida = saida
        self.chamadas = []

    def invoke(self, mensagens):
        self.chamadas.append(mensagens)
        return self.saida


def _payload_resumo() -> dict:
    return {
        "perfilLead": {"intencao": "compra", "regiao": "Pinheiros"},
        "historico": [
            {
                "papel": "lead",
                "texto": "Quero morar em Pinheiros.",
                "em": "2026-09-13T20:00:00Z",
            }
        ],
        "imoveis": [],
    }


def test_prompt_resumo_inclui_perfil_historico_e_imoveis():
    perfil = PerfilLead(intencao="compra", regiao="Pinheiros", preco_max=900000)
    historico = [
        MensagemHistorico(
            papel="lead",
            texto="Quero morar em Pinheiros, mas não quero térreo.",
            em="2026-09-13T20:00:00Z",
        )
    ]
    imoveis = [
        ImovelSugerido(
            id="SOL-42",
            tipo="apartamento",
            bairro="Pinheiros",
            quartos=2,
            metragem=72,
            preco_venda=850000,
            motivo="Dentro da faixa e da região",
        )
    ]

    prompt = prompts.resumo(perfil, historico, imoveis)

    assert "intencao: compra" in prompt
    assert "regiao: Pinheiros" in prompt
    assert "não quero térreo" in prompt
    assert "SOL-42" in prompt
    assert "Dentro da faixa e da região" in prompt
    assert all(
        secao in prompt
        for secao in ("### perfil", "### orcamento", "### imoveis", "### objecoes", "### proximoPasso")
    )
    assert "Não narre a conversa" in prompt
    assert "devolva `null`" in prompt


def test_resumo_request_com_historico_vazio_da_422():
    payload = _payload_resumo()
    payload["historico"] = []

    resposta = _cliente_contrato.post("/resumo", json=payload)

    assert resposta.status_code == 422


def test_resumo_request_valido_aceita_aliases_em_camelcase():
    resposta = _cliente_contrato.post("/resumo", json=_payload_resumo())

    assert resposta.status_code == 200
    assert resposta.json() == {"valido": True}


def test_resumo_request_com_campo_desconhecido_da_422():
    payload = _payload_resumo()
    payload["canal"] = "web"

    resposta = _cliente_contrato.post("/resumo", json=payload)

    assert resposta.status_code == 422


def test_resumo_response_exige_as_cinco_secoes_mesmo_quando_nulas():
    resumo = ResumoResponse.model_validate(
        {
            "perfil": "Busca para moradia.",
            "orcamento": None,
            "imoveis": None,
            "objecoes": None,
            "proximoPasso": "Confirmar a faixa de preço.",
        }
    )

    assert resumo.model_dump(by_alias=True) == {
        "perfil": "Busca para moradia.",
        "orcamento": None,
        "imoveis": None,
        "objecoes": None,
        "proximoPasso": "Confirmar a faixa de preço.",
    }


def test_modelo_resumo_usa_saida_estruturada_por_json_schema(monkeypatch):
    cliente = MagicMock()
    monkeypatch.setattr(grafo, "_cliente", lambda: cliente)

    grafo._modelo_resumo.__wrapped__()

    cliente.with_structured_output.assert_called_once_with(
        ResumoResponse,
        method="json_schema",
    )


def test_endpoint_resumo_com_duble_preserva_nulos_e_mascara_pii(monkeypatch):
    payload = _payload_resumo()
    payload["historico"][0]["texto"] = (
        "Meu telefone é (11) 98765-4321. Quero Pinheiros, mas não quero térreo."
    )
    saida = ResumoResponse(
        perfil="Compra para moradia.",
        orcamento=None,
        imoveis=None,
        objecoes="Não quer imóvel no térreo.",
        proximo_passo="Confirmar a faixa de preço.",
    )
    duble = _DubleResumo(saida)
    monkeypatch.setattr(grafo, "_modelo_resumo", lambda: duble)

    resposta = _cliente_endpoint.post("/resumo", json=payload)

    assert resposta.status_code == 200
    assert resposta.json() == {
        "perfil": "Compra para moradia.",
        "orcamento": None,
        "imoveis": None,
        "objecoes": "Não quer imóvel no térreo.",
        "proximoPasso": "Confirmar a faixa de preço.",
    }
    assert len(duble.chamadas) == 1
    prompt_enviado = duble.chamadas[0][0].content
    assert "(11) 98765-4321" not in prompt_enviado
    assert "[TELEFONE_1]" in prompt_enviado
