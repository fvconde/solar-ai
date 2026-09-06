"""Grafo da Lia.

Um no: le persona e contexto do turno, chama o Gemini com saida estruturada e
devolve os campos do contrato. Nos especializados de qualificacao (S-12) e
busca (S-15) entram depois.
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
    CamposExtraidos,
    Intencao,
    ProximaAcao,
    TurnoRequest,
    TurnoResponse,
)
from app.lia import prompts

logger = logging.getLogger("solar.lia")

_MARCAS_DE_COTA = ("429", "resource_exhausted", "quota", "rate limit")


class LiaIndisponivelError(RuntimeError):
    def __init__(self, mensagem: str, cota: bool = False) -> None:
        super().__init__(mensagem)
        self.cota = cota


class SaidaLia(BaseModel):
    model_config = ConfigDict(
        alias_generator=to_camel, populate_by_name=True, extra="forbid"
    )

    resposta: str = Field(min_length=1)
    intencao: Intencao
    campos_extraidos: CamposExtraidos
    proxima_acao: ProximaAcao


class EstadoTurno(TypedDict):
    requisicao: TurnoRequest
    saida: SaidaLia


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


def _responder(estado: EstadoTurno) -> EstadoTurno:
    requisicao = estado["requisicao"]

    mensagens = [
        SystemMessage(content=prompts.persona()),
        HumanMessage(
            content=prompts.turno(
                requisicao.perfil_lead, requisicao.historico, requisicao.mensagem
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


@lru_cache(maxsize=1)
def _grafo():
    grafo = StateGraph(EstadoTurno)
    grafo.add_node("responder", _responder)
    grafo.add_edge(START, "responder")
    grafo.add_edge("responder", END)

    return grafo.compile()


def responder(requisicao: TurnoRequest) -> TurnoResponse:
    estado = _grafo().invoke({"requisicao": requisicao})
    saida: SaidaLia = estado["saida"]

    return TurnoResponse(
        resposta=saida.resposta,
        intencao=saida.intencao,
        campos_extraidos=saida.campos_extraidos,
        proxima_acao=saida.proxima_acao,
        imoveis_sugeridos=[],
    )
