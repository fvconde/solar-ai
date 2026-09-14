"""Resumo para o corretor: testes gratuitos e aceite ao vivo isolado."""

import json
import time
from unittest.mock import MagicMock

import pytest
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


@pytest.mark.llm
def test_resumos_ao_vivo_distinguem_perfis_e_preservam_exclusao(ritmo):
    cenarios = {
        "compra_sem_objecao": {
            "perfilLead": {
                "intencao": "compra",
                "regiao": "Pinheiros",
                "precoMax": 900000,
                "quartos": 2,
            },
            "historico": [
                {
                    "papel": "lead",
                    "texto": (
                        "Quero comprar um apartamento em Pinheiros para morar, "
                        "com dois quartos e orcamento de ate 900 mil reais."
                    ),
                    "em": "2026-09-13T20:00:00Z",
                }
            ],
            "imoveis": [],
        },
        "investimento": {
            "perfilLead": {
                "intencao": "investimento",
                "regiao": "Vila Mariana",
                "precoMax": 700000,
                "expectativaRetorno": "Renda mensal de aluguel e valorizacao no longo prazo",
            },
            "historico": [
                {
                    "papel": "lead",
                    "texto": (
                        "Busco um imovel na Vila Mariana como investimento, ate "
                        "700 mil reais, priorizando renda de aluguel e valorizacao."
                    ),
                    "em": "2026-09-13T20:05:00Z",
                }
            ],
            "imoveis": [],
        },
        "somente_exclusao": {
            "perfilLead": {},
            "historico": [
                {
                    "papel": "lead",
                    "texto": "Nao quero imoveis na Zona Leste.",
                    "em": "2026-09-13T20:10:00Z",
                }
            ],
            "imoveis": [],
        },
    }

    respostas = {}
    for indice, (rotulo, payload) in enumerate(cenarios.items()):
        if indice:
            time.sleep(5.0)
        resposta = _cliente_endpoint.post("/resumo", json=payload)
        respostas[rotulo] = resposta
        print(f"\n{rotulo}={json.dumps(resposta.json(), ensure_ascii=False)}")

    assert {rotulo: resposta.status_code for rotulo, resposta in respostas.items()} == {
        rotulo: 200 for rotulo in cenarios
    }

    compra = ResumoResponse.model_validate(respostas["compra_sem_objecao"].json())
    investimento = ResumoResponse.model_validate(respostas["investimento"].json())
    exclusao = ResumoResponse.model_validate(respostas["somente_exclusao"].json())

    texto_compra = " ".join(
        parte for parte in compra.model_dump().values() if parte is not None
    ).lower()
    texto_investimento = " ".join(
        parte for parte in investimento.model_dump().values() if parte is not None
    ).lower()

    assert compra.objecoes is None
    assert compra.imoveis is None
    assert any(termo in texto_compra for termo in ("compra", "moradia", "pinheiros"))
    assert investimento.imoveis is None
    assert any(
        termo in texto_investimento
        for termo in ("investimento", "investidor", "renda", "retorno")
    )
    assert compra.model_dump() != investimento.model_dump()
    assert exclusao.objecoes is not None
    assert "leste" in exclusao.objecoes.lower()
