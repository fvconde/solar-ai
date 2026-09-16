"""Nivel de log do agente. Nao chama o Gemini.

A linha de boot existia desde o S-02 e nunca apareceu em container: o uvicorn
configura os loggers dele, nao os da aplicacao, e `solar` ficava em WARNING.
"""

import logging

import pytest
from fastapi import HTTPException

from app.contrato import TurnoRequest
from app.lia import grafo
from app.main import NIVEIS_DE_LOG, configurar_log, turn


@pytest.fixture(autouse=True)
def nivel_restaurado():
    logger = logging.getLogger("solar")
    anterior = logger.level
    yield
    logger.setLevel(anterior)


class TestConfigurarLog:
    def test_padrao_e_info(self, monkeypatch):
        monkeypatch.delenv("SOLAR_LOG_LEVEL", raising=False)

        assert configurar_log() == "INFO"
        assert logging.getLogger("solar").isEnabledFor(logging.INFO)

    @pytest.mark.parametrize("nivel", sorted(NIVEIS_DE_LOG))
    def test_aceita_os_niveis_conhecidos(self, monkeypatch, nivel):
        monkeypatch.setenv("SOLAR_LOG_LEVEL", nivel.lower())

        assert configurar_log() == nivel

    def test_nivel_invalido_cai_para_info(self, monkeypatch):
        monkeypatch.setenv("SOLAR_LOG_LEVEL", "VERBOSO")

        assert configurar_log() == "INFO"

    def test_a_linha_de_boot_sai_no_nivel_padrao(self, monkeypatch, caplog):
        monkeypatch.delenv("SOLAR_LOG_LEVEL", raising=False)
        configurar_log()

        with caplog.at_level(logging.INFO, logger="solar"):
            logging.getLogger("solar").info("Indice de imoveis pronto: imoveis=%d", 80)

        assert "Indice de imoveis pronto: imoveis=80" in caplog.text


def test_falha_do_modelo_nao_grava_pii_do_payload(monkeypatch, caplog):
    cpf = "111.222.333-44"
    telefone = "(11) 90000-0000"

    class ModeloQueEcoaPayloadNoErro:
        def invoke(self, mensagens):
            conteudo = "\n".join(
                mensagem.content
                for mensagem in mensagens
                if isinstance(mensagem.content, str)
            )
            raise RuntimeError(conteudo)

    monkeypatch.setattr(grafo, "_modelo", lambda: ModeloQueEcoaPayloadNoErro())
    requisicao = TurnoRequest.model_validate(
        {
            "conversaId": "0f0d4f6c-2b3a-4f1e-9a77-5c1e2b8d4a10",
            "mensagem": f"CPF {cpf}, telefone {telefone}",
        }
    )

    with caplog.at_level(logging.ERROR, logger="solar"):
        with pytest.raises(HTTPException):
            turn(requisicao)

    assert cpf not in caplog.text
    assert telefone not in caplog.text
    assert "[CPF_1]" in caplog.text
    assert "[TELEFONE_1]" in caplog.text
