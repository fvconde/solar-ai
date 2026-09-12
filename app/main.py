"""Esqueleto do agente Lia.

O agente e stateless por decisao de arquitetura: ele nunca abre conexao com o
Postgres. Quem e dono do estado e a API .NET. Por isso o /health daqui checa
apenas o proprio processo e a presenca da configuracao -- se um dia ele
precisar de banco para responder, a arquitetura quebrou antes do teste.
"""

import logging
import os
from contextlib import asynccontextmanager
from typing import Annotated, Literal

from fastapi import FastAPI, Header, HTTPException, Response
from pydantic import BaseModel

from app.contrato import TurnoRequest, TurnoResponse
from app.lia import IndiceIndisponivelError, LiaIndisponivelError, responder
from app.lia import indice as indice_imoveis

SERVICO = "solar-ai"
ESSENCIAIS = frozenset({"gemini_config"})
NIVEIS_DE_LOG = frozenset({"CRITICAL", "ERROR", "WARNING", "INFO", "DEBUG"})

_FORMATO_DE_LOG = "%(levelname)s %(name)s %(message)s"

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


def _checar_indice() -> CheckResult:
    try:
        indice = indice_imoveis.atual()
    except IndiceIndisponivelError as erro:
        return CheckResult(status="down", reason=_motivo(str(erro)))

    return CheckResult(
        status="up",
        reason=_motivo(
            f"{len(indice.imoveis)} imoveis em {indice.dimensao} dimensoes ({indice.origem})"
        ),
    )


def _agregar(checks: dict[str, CheckResult]) -> Status:
    falhos = [nome for nome, check in checks.items() if check.status != "up"]

    if not falhos:
        return "up"

    return "down" if any(nome in ESSENCIAIS for nome in falhos) else "degraded"


def configurar_log() -> str:
    """Liga os logs do `solar`, que o uvicorn nao configura por serem nossos."""
    bruto = os.getenv("SOLAR_LOG_LEVEL", "").strip().upper()
    nivel = bruto if bruto in NIVEIS_DE_LOG else "INFO"

    logging.basicConfig(level=nivel, format=_FORMATO_DE_LOG)
    logger.setLevel(nivel)

    if bruto and bruto != nivel:
        logger.warning("SOLAR_LOG_LEVEL=%r invalido; usando %s", bruto, nivel)

    return nivel


def _construir_indice() -> None:
    try:
        indice = indice_imoveis.construir()
    except IndiceIndisponivelError as erro:
        logger.error("Indice de imoveis nao subiu: %s", erro)
        return

    logger.info(
        "Indice de imoveis pronto: imoveis=%d dimensao=%d modelo=%s origem=%s",
        len(indice.imoveis),
        indice.dimensao,
        indice.modelo,
        indice.origem,
    )


@asynccontextmanager
async def _ciclo_de_vida(_: FastAPI):
    configurar_log()
    logger.info(
        "solar-ai versao=%s modelo=%s chave_carregada=%s",
        _versao(),
        os.getenv("GEMINI_MODEL"),
        bool(os.getenv("GEMINI_API_KEY")),
    )
    _construir_indice()
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
    checks = {
        "gemini_config": _checar_gemini_config(),
        "indice_imoveis": _checar_indice(),
    }
    status = _agregar(checks)

    if status == "down":
        response.status_code = 503

    return HealthResponse(
        service=SERVICO,
        status=status,
        version=_versao(),
        checks=checks,
    )


@app.post(
    "/turn",
    response_model=TurnoResponse,
    responses={503: {"description": "a Lia nao conseguiu responder este turno"}},
)
def turn(
    requisicao: TurnoRequest,
    x_solar_trigger: Annotated[str | None, Header(alias="X-Solar-Trigger")] = None,
) -> TurnoResponse:
    """Processa um turno de conversa pelo grafo da Lia."""
    try:
        return responder(requisicao, reengajamento=(x_solar_trigger == "follow-up"))
    except LiaIndisponivelError as erro:
        logger.error(
            "Turno da conversa %s falhou (cota=%s): %s",
            requisicao.conversa_id,
            erro.cota,
            erro,
        )
        raise HTTPException(
            status_code=503,
            detail=_motivo(str(erro)) or "a Lia nao conseguiu responder este turno",
        ) from erro
