from unittest.mock import MagicMock, patch
from uuid import uuid4

import pytest

from fastapi.testclient import TestClient

from app.contrato import MensagemHistorico, PerfilLead, TurnoRequest
from app.lia import prompts
from app.lia.grafo import SaidaLia, responder
from app.main import app


def test_prompt_reengajamento_inclui_perfil_e_historico():
    perfil = PerfilLead(regiao="Tatuape", preco_max=500000, quartos=2, intencao="compra")
    historico = [
        MensagemHistorico(papel="lead", texto="quero um apto no Tatuape ate 500 mil", em="2026-09-11T12:00:00Z"),
        MensagemHistorico(papel="agente", texto="Tatuapé é uma boa região. Você tem alguma urgência?", em="2026-09-11T12:00:05Z"),
    ]

    prompt = prompts.reengajamento(perfil, historico)

    assert "Tatuape" in prompt
    assert "500.000" in prompt or "500000" in prompt
    assert "compra" in prompt
    assert "quero um apto no Tatuape" in prompt
    assert "Tatuapé é uma boa região" in prompt
    assert "NUNCA envie mensagens genericas como" in prompt


def test_responder_com_reengajamento_chama_no_reengajar(monkeypatch):
    perfil = PerfilLead(regiao="Pinheiros", preco_max=800000, score=70)
    requisicao = TurnoRequest(
        conversa_id=uuid4(),
        mensagem="[reengajar]",
        perfil_lead=perfil,
        historico=[
            MensagemHistorico(papel="lead", texto="procuro em Pinheiros", em="2026-09-11T10:00:00Z"),
            MensagemHistorico(papel="agente", texto="Pinheiros tem excelentes opções.", em="2026-09-11T10:00:05Z"),
        ],
    )

    saida_mock = SaidaLia.model_validate({
        "resposta": "Oi! Vi que você estava procurando imóveis em Pinheiros até 800 mil. Surgiram algumas novidades na região, quer dar uma olhada?",
        "intencao": "compra",
        "camposExtraidos": {},
        "proximaAcao": "continuar_conversa",
        "slotEscolhido": None,
    })

    monkeypatch.setattr("app.lia.grafo._modelo", lambda: MagicMock())
    with patch("app.lia.grafo._invocar", return_value=saida_mock) as mock_invocar:
        resposta = responder(requisicao, reengajamento=True)

        assert mock_invocar.call_count == 1
        assert resposta.proxima_acao == "continuar_conversa"
        assert resposta.slot_escolhido is None
        assert resposta.imoveis_sugeridos == []
        assert "Pinheiros" in resposta.resposta
        assert resposta.campos_extraidos.score == 65


def test_endpoint_turn_aciona_reengajamento_com_header(monkeypatch):
    client = TestClient(app)
    conversa_id = str(uuid4())

    saida_mock = SaidaLia.model_validate({
        "resposta": "Continuamos com opções no Tatuapé na faixa até 500 mil. Quer avaliar?",
        "intencao": "compra",
        "camposExtraidos": {},
        "proximaAcao": "continuar_conversa",
        "slotEscolhido": None,
    })

    payload = {
        "conversaId": conversa_id,
        "mensagem": "[reengajar]",
        "perfilLead": {"regiao": "Tatuape", "precoMax": 500000, "intencao": "compra"},
        "historico": [],
        "agenda": [],
    }

    monkeypatch.setattr("app.lia.grafo._modelo", lambda: MagicMock())
    with patch("app.lia.grafo._invocar", return_value=saida_mock):
        resp = client.post("/turn", json=payload, headers={"X-Solar-Trigger": "follow-up"})

        assert resp.status_code == 200
        dados = resp.json()
        assert dados["proximaAcao"] == "continuar_conversa"
        assert "Tatuapé" in dados["resposta"]


def test_endpoint_turn_sem_header_nao_aciona_reengajamento_mesmo_com_mensagem_sentinela(monkeypatch):
    client = TestClient(app)
    conversa_id = str(uuid4())

    saida_mock = SaidaLia.model_validate({
        "resposta": "Entendi que você digitou [reengajar]. Como posso te ajudar com a busca de imóveis?",
        "intencao": "indefinida",
        "camposExtraidos": {},
        "proximaAcao": "continuar_conversa",
        "slotEscolhido": None,
    })

    payload = {
        "conversaId": conversa_id,
        "mensagem": "[reengajar]",
        "perfilLead": {},
        "historico": [],
        "agenda": [],
    }

    monkeypatch.setattr("app.lia.grafo._modelo", lambda: MagicMock())
    with patch("app.lia.grafo._invocar", return_value=saida_mock) as mock_invocar:
        resp = client.post("/turn", json=payload)

        assert resp.status_code == 200
        assert mock_invocar.call_count == 1
        chamada_mensagens = mock_invocar.call_args[0][1]
        assert any("Mensagem do lead agora" in m.content for m in chamada_mensagens if hasattr(m, "content"))


@pytest.mark.llm
def test_reengajamento_live_com_gemini(ritmo):
    conversa_id = uuid4()
    perfil = PerfilLead(
        nome="Lucas",
        regiao="Tatuape",
        preco_max=500000,
        intencao="compra",
    )
    historico = [
        MensagemHistorico(papel="lead", texto="procuro um apto no Tatuape ate 500 mil", em="2026-09-11T10:00:00Z"),
        MensagemHistorico(papel="agente", texto="Tatuapé é uma boa região nessa faixa. Quantos quartos prefere?", em="2026-09-11T10:00:05Z"),
    ]
    requisicao = TurnoRequest(
        conversa_id=conversa_id,
        mensagem="[reengajar]",
        perfil_lead=perfil,
        historico=historico,
    )

    resposta = responder(requisicao, reengajamento=True)

    print(f"\n>>> MENSAGEM REAL GERADA PELA LIA: {resposta.resposta}")
    assert resposta.proxima_acao in ("continuar_conversa", "sugerir_imoveis")
    texto_baixo = resposta.resposta.lower()
    assert "tatuap" in texto_baixo
    assert "500" in texto_baixo

