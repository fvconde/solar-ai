"""Fixtures compartilhadas dos testes do agente."""

import os
import time
from pathlib import Path

import pytest
from dotenv import load_dotenv

RAIZ = Path(__file__).resolve().parents[1]
PAUSA_ENTRE_CHAMADAS = 5.0

load_dotenv(RAIZ / ".env")


@pytest.fixture(scope="session")
def gemini_configurado() -> None:
    faltando = [
        nome
        for nome in ("GEMINI_API_KEY", "GEMINI_MODEL")
        if not os.getenv(nome, "").strip()
    ]

    if faltando:
        pytest.skip(f"ausente no ambiente: {', '.join(faltando)}")


@pytest.fixture(scope="session")
def _ritmo_da_sessao() -> dict[str, float]:
    return {"ultima": 0.0}


@pytest.fixture
def ritmo(gemini_configurado, _ritmo_da_sessao):
    """Serializa as chamadas ao Gemini com pausa, contra o limite por minuto."""
    espera = PAUSA_ENTRE_CHAMADAS - (time.monotonic() - _ritmo_da_sessao["ultima"])

    if espera > 0:
        time.sleep(espera)

    yield

    _ritmo_da_sessao["ultima"] = time.monotonic()
