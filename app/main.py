"""Esqueleto do agente Lia.

O agente e stateless por decisao de arquitetura: ele nunca abre conexao com o
Postgres. Quem e dono do estado e a API .NET. Por isso o /health daqui checa
apenas o proprio processo e a presenca da configuracao -- se um dia ele
precisar de banco para responder, a arquitetura quebrou antes do teste.
"""

import logging
import os
from contextlib import asynccontextmanager
from typing import Literal

from fastapi import FastAPI, Response
from pydantic import BaseModel

from app.contrato import CamposExtraidos, TurnoRequest, TurnoResponse

SERVICO = "solar-ai"
ESSENCIAIS = frozenset({"gemini_config"})

logger = logging.getLogger("solar")

Status = Literal["up", "degraded", "down"]


class CheckResult(BaseModel):
    status: Status
    reason: str | None = None


class HealthResponse(BaseModel):
    service: str
    status: Status
    version: str
    checks: dict[str, CheckResult]


def _producao() -> bool:
    return os.getenv("SOLAR_ENV", "production").lower() != "development"


def _motivo(detalhe: str) -> str | None:
    return None if _producao() else detalhe[:200]


def _versao() -> str:
    return os.getenv("SOLAR_VERSION") or "dev"


def _checar_gemini_config() -> CheckResult:
    # Nunca expor o valor da chave -- apenas se ela foi carregada.
    ausentes = [nome for nome in ("GEMINI_API_KEY", "GEMINI_MODEL") if not os.getenv(nome)]

    if not ausentes:
        return CheckResult(status="up")

    detalhe = f"variaveis ausentes no ambiente: {', '.join(ausentes)}"
    logger.error("Health check de configuracao da Gemini falhou: %s", detalhe)

    return CheckResult(status="down", reason=_motivo(detalhe))


def _agregar(checks: dict[str, CheckResult]) -> Status:
    falhos = [nome for nome, check in checks.items() if check.status != "up"]

    if not falhos:
        return "up"

    return "down" if any(nome in ESSENCIAIS for nome in falhos) else "degraded"


@asynccontextmanager
async def _ciclo_de_vida(_: FastAPI):
    logger.info(
        "solar-ai versao=%s modelo=%s chave_carregada=%s",
        _versao(),
        os.getenv("GEMINI_MODEL"),
        bool(os.getenv("GEMINI_API_KEY")),
    )
    yield


app = FastAPI(
    title=SERVICO,
    version="0.1.0",
    description="Agente conversacional Lia. Stateless: nunca acessa o banco.",
    lifespan=_ciclo_de_vida,
)


@app.get("/")
def raiz():
    return {"service": SERVICO}


@app.get(
    "/health",
    response_model=HealthResponse,
    response_model_exclude_none=True,
    responses={503: {"model": HealthResponse, "description": "status down"}},
)
def health(response: Response) -> HealthResponse:
    checks = {"gemini_config": _checar_gemini_config()}
    status = _agregar(checks)

    if status == "down":
        response.status_code = 503

    return HealthResponse(
        service=SERVICO,
        status=status,
        version=_versao(),
        checks=checks,
    )


@app.post("/turn", response_model=TurnoResponse)
def turn(requisicao: TurnoRequest) -> TurnoResponse:
    """Processa um turno de conversa. Eco ate o grafo da Lia entrar no S-06."""
    return TurnoResponse(
        resposta=f"Eco: {requisicao.mensagem}",
        intencao=requisicao.perfil_lead.intencao or "indefinida",
        campos_extraidos=CamposExtraidos(),
        proxima_acao="continuar_conversa",
        imoveis_sugeridos=[],
    )
