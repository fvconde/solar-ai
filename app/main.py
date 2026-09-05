"""Esqueleto do agente Lia.

O agente e stateless por decisao de arquitetura: ele nunca abre conexao com o
Postgres. Quem e dono do estado e a API .NET. Por isso o /health daqui checa
apenas o proprio processo e a presenca da configuracao -- se um dia ele
precisar de banco para responder, a arquitetura quebrou antes do teste.
"""

import os

from fastapi import FastAPI

app = FastAPI(title="solar-ai", version="0.1.0")


@app.get("/")
def raiz():
    return {"service": "solar-ai", "status": "up"}


@app.get("/health")
def health():
    # Nunca expor o valor da chave -- apenas se ela foi carregada.
    return {
        "service": "solar-ai",
        "status": "up",
        "modelo": os.getenv("GEMINI_MODEL"),
        "chave_carregada": bool(os.getenv("GEMINI_API_KEY")),
    }
