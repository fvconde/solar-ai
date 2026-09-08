"""Grafo da Lia.

Tres nos, uma chamada ao LLM: `qualificar` calcula as lacunas do perfil,
`responder` conversa com o Gemini e `pontuar` aplica a regua do score. O no de
busca (S-15) entra depois.
"""

import logging
import os
from functools import lru_cache
from typing import TypedDict

from langchain_core.messages import HumanMessage, SystemMessage
from langchain_google_genai import ChatGoogleGenerativeAI
from langgraph.graph import END, START, StateGraph
from pydantic import BaseModel, ConfigDict, Field
from pydantic.alias_generators import to_camel

from app.contrato import (
    LIMITE_EXPECTATIVA,
    CamposExtraidos,
    Intencao,
    ProximaAcao,
    TurnoRequest,
    TurnoResponse,
    Urgencia,
)
from app.lia import prompts, qualificacao
from app.lia.qualificacao import Sinal

logger = logging.getLogger("solar.lia")

_MARCAS_DE_COTA = ("429", "resource_exhausted", "quota", "rate limit")


class LiaIndisponivelError(RuntimeError):
    def __init__(self, mensagem: str, cota: bool = False) -> None:
        super().__init__(mensagem)
        self.cota = cota


class CamposExtraidosLLM(BaseModel):
    """CamposExtraidos sem `score`: desde o S-12 quem pontua e a regua."""

    model_config = ConfigDict(
        alias_generator=to_camel, populate_by_name=True, extra="forbid"
    )

    nome: str | None = None
    preco_min: int | None = None
    preco_max: int | None = None
    quartos: int | None = None
    regiao: str | None = None
    urgencia: Urgencia | None = None
    expectativa_retorno: str | None = Field(default=None, max_length=LIMITE_EXPECTATIVA)


class SaidaLia(BaseModel):
    model_config = ConfigDict(
        alias_generator=to_camel, populate_by_name=True, extra="forbid"
    )

    resposta: str = Field(min_length=1)
    intencao: Intencao
    campos_extraidos: CamposExtraidosLLM
    proxima_acao: ProximaAcao


class EstadoTurno(TypedDict):
    requisicao: TurnoRequest
    lacunas: tuple[Sinal, ...]
    desfecho: str | None
    saida: SaidaLia
    score: int


def _temperatura() -> dict[str, float]:
    bruto = os.getenv("GEMINI_TEMPERATURE", "").strip()

    if not bruto:
        return {}

    try:
        return {"temperature": float(bruto)}
    except ValueError:
        logger.warning("GEMINI_TEMPERATURE=%r invalida; ignorada", bruto)
        return {}


@lru_cache(maxsize=1)
def _modelo():
    chave = os.getenv("GEMINI_API_KEY", "").strip()
    nome = os.getenv("GEMINI_MODEL", "").strip()

    if not chave or not nome:
        raise LiaIndisponivelError("GEMINI_API_KEY ou GEMINI_MODEL ausente no ambiente")

    return ChatGoogleGenerativeAI(
        model=nome,
        google_api_key=chave,
        **_temperatura(),
    ).with_structured_output(SaidaLia, method="json_schema")


def _e_cota(texto: str) -> bool:
    minusculo = texto.lower()
    return any(marca in minusculo for marca in _MARCAS_DE_COTA)


def _qualificar(estado: EstadoTurno) -> EstadoTurno:
    perfil = estado["requisicao"].perfil_lead

    return {
        "lacunas": qualificacao.lacunas(perfil),
        "desfecho": qualificacao.desfecho_da_trilha(perfil),
    }


def _responder(estado: EstadoTurno) -> EstadoTurno:
    requisicao = estado["requisicao"]

    mensagens = [
        SystemMessage(content=prompts.persona()),
        HumanMessage(
            content=prompts.turno(
                requisicao.perfil_lead,
                requisicao.historico,
                requisicao.mensagem,
                estado["lacunas"],
                estado["desfecho"],
            )
        ),
    ]

    try:
        saida = _modelo().invoke(mensagens)
    except LiaIndisponivelError:
        raise
    except Exception as erro:
        texto = f"{type(erro).__name__}: {erro}"
        raise LiaIndisponivelError(texto, cota=_e_cota(texto)) from erro

    if not isinstance(saida, SaidaLia):
        raise LiaIndisponivelError(
            f"o modelo devolveu {type(saida).__name__} em vez da saida estruturada"
        )

    return {"saida": saida}


def _pontuar(estado: EstadoTurno) -> EstadoTurno:
    requisicao = estado["requisicao"]
    saida = estado["saida"]

    perfil = qualificacao.fundir(
        requisicao.perfil_lead, saida.intencao, saida.campos_extraidos
    )

    return {"score": qualificacao.pontuar(perfil)}


@lru_cache(maxsize=1)
def _grafo():
    grafo = StateGraph(EstadoTurno)
    grafo.add_node("qualificar", _qualificar)
    grafo.add_node("responder", _responder)
    grafo.add_node("pontuar", _pontuar)
    grafo.add_edge(START, "qualificar")
    grafo.add_edge("qualificar", "responder")
    grafo.add_edge("responder", "pontuar")
    grafo.add_edge("pontuar", END)

    return grafo.compile()


def responder(requisicao: TurnoRequest) -> TurnoResponse:
    estado = _grafo().invoke({"requisicao": requisicao})
    saida: SaidaLia = estado["saida"]

    return TurnoResponse(
        resposta=saida.resposta,
        intencao=saida.intencao,
        campos_extraidos=CamposExtraidos(
            **saida.campos_extraidos.model_dump(), score=estado["score"]
        ),
        proxima_acao=saida.proxima_acao,
        imoveis_sugeridos=[],
    )
