"""Resumo para o corretor. Testes determinísticos: nunca chamam o Gemini."""

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.contrato import (
    ImovelSugerido,
    MensagemHistorico,
    PerfilLead,
    ResumoRequest,
    ResumoResponse,
)
from app.lia import prompts


_app_contrato = FastAPI()


@_app_contrato.post("/resumo")
def _validar_contrato(requisicao: ResumoRequest) -> dict[str, bool]:
    return {"valido": bool(requisicao.historico)}


_cliente_contrato = TestClient(_app_contrato)


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
