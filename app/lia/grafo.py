"""Grafo da Lia.

Cinco nos e uma chamada ao LLM no turno comum: `qualificar` calcula as lacunas
do perfil, `responder` conversa com o Gemini e `pontuar` aplica a regua do score.

Quando o proprio modelo diz que e hora de mostrar opcoes, o turno segue por mais
dois nos: `consultar` busca no indice com o perfil ja fundido -- e por isso a
busca do S-15 vem depois do LLM, e nao antes: o filtro duro precisa do que o lead
acabou de dizer -- e `apresentar` gasta uma segunda chamada para escrever a fala
com os imoveis na mao. Turno que sugere custa 2 chamadas e 1 embedding; turno
comum continua custando 1 chamada e nenhum embedding.
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
    ImovelSugerido,
    Intencao,
    PerfilLead,
    ProximaAcao,
    TurnoRequest,
    TurnoResponse,
    Urgencia,
)
from app.lia import indice as indice_imoveis
from app.lia import prompts, qualificacao
from app.lia.indice import Filtro, IndiceIndisponivelError, Resultado
from app.lia.qualificacao import Sinal

logger = logging.getLogger("solar.lia")

IMOVEIS_POR_SUGESTAO = 3
GATILHO_DA_BUSCA: ProximaAcao = "sugerir_imoveis"

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


class MotivoDoImovel(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    motivo: str = Field(min_length=1)


class SaidaApresentacao(BaseModel):
    """Segunda chamada: a fala com os imoveis na mao e o motivo de cada um."""

    model_config = ConfigDict(extra="forbid")

    resposta: str = Field(min_length=1)
    motivos: list[MotivoDoImovel] = Field(default_factory=list)


class EstadoTurno(TypedDict):
    requisicao: TurnoRequest
    lacunas: tuple[Sinal, ...]
    desfecho: str | None
    saida: SaidaLia
    score: int
    perfil: PerfilLead
    filtro: Filtro
    resultados: list[Resultado] | None
    apresentacao: SaidaApresentacao | None


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
def _cliente():
    chave = os.getenv("GEMINI_API_KEY", "").strip()
    nome = os.getenv("GEMINI_MODEL", "").strip()

    if not chave or not nome:
        raise LiaIndisponivelError("GEMINI_API_KEY ou GEMINI_MODEL ausente no ambiente")

    return ChatGoogleGenerativeAI(
        model=nome,
        google_api_key=chave,
        **_temperatura(),
    )


@lru_cache(maxsize=1)
def _modelo():
    return _cliente().with_structured_output(SaidaLia, method="json_schema")


@lru_cache(maxsize=1)
def _modelo_apresentacao():
    return _cliente().with_structured_output(SaidaApresentacao, method="json_schema")


def _e_cota(texto: str) -> bool:
    minusculo = texto.lower()
    return any(marca in minusculo for marca in _MARCAS_DE_COTA)


def _qualificar(estado: EstadoTurno) -> EstadoTurno:
    perfil = estado["requisicao"].perfil_lead

    return {
        "lacunas": qualificacao.lacunas(perfil),
        "desfecho": qualificacao.desfecho_da_trilha(perfil),
    }


def _invocar(modelo, mensagens: list, esperado: type[BaseModel]) -> BaseModel:
    try:
        saida = modelo.invoke(mensagens)
    except LiaIndisponivelError:
        raise
    except Exception as erro:
        texto = f"{type(erro).__name__}: {erro}"
        raise LiaIndisponivelError(texto, cota=_e_cota(texto)) from erro

    if not isinstance(saida, esperado):
        raise LiaIndisponivelError(
            f"o modelo devolveu {type(saida).__name__} em vez da saida estruturada"
        )

    return saida


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

    return {"saida": _invocar(_modelo(), mensagens, SaidaLia)}


def _pontuar(estado: EstadoTurno) -> EstadoTurno:
    requisicao = estado["requisicao"]
    saida = estado["saida"]

    perfil = qualificacao.fundir(
        requisicao.perfil_lead, saida.intencao, saida.campos_extraidos
    )

    return {"perfil": perfil, "score": qualificacao.pontuar(perfil)}


def _consultar(estado: EstadoTurno) -> EstadoTurno:
    """Busca no indice com o perfil ja fundido. Indice fora do ar nao derruba o turno."""
    requisicao = estado["requisicao"]
    perfil = estado["perfil"]
    filtro = Filtro.do_perfil(
        perfil, indice_imoveis.tipo_pedido(requisicao.mensagem, requisicao.historico)
    )

    try:
        resultados = indice_imoveis.atual().buscar(
            indice_imoveis.texto_da_consulta(requisicao.mensagem, perfil),
            k=IMOVEIS_POR_SUGESTAO,
            filtro=filtro,
        )
    except IndiceIndisponivelError as erro:
        logger.warning(
            "Busca de imoveis da conversa %s nao aconteceu: %s",
            requisicao.conversa_id,
            erro,
        )
        return {"filtro": filtro, "resultados": None}

    # Nunca logar o texto da consulta: ele carrega a mensagem do lead.
    logger.info(
        "Busca de imoveis da conversa %s: %d resultado(s) %s",
        requisicao.conversa_id,
        len(resultados),
        [resultado.imovel.id for resultado in resultados],
    )

    return {"filtro": filtro, "resultados": resultados}


def _apresentar(estado: EstadoTurno) -> EstadoTurno:
    """Segunda chamada ao LLM. Falhar aqui devolve o turno sem imoveis, nao um 503.

    O lead ja tem resposta escrita pelo no `responder`; trocar uma conversa que
    funciona por um erro porque a vitrine falhou seria pior do que entregar a
    conversa sem a vitrine.
    """
    requisicao = estado["requisicao"]

    mensagens = [
        SystemMessage(content=prompts.persona()),
        HumanMessage(
            content=prompts.apresentacao(
                estado["perfil"],
                requisicao.historico,
                requisicao.mensagem,
                estado["resultados"],
                estado["filtro"],
            )
        ),
    ]

    try:
        apresentacao = _invocar(_modelo_apresentacao(), mensagens, SaidaApresentacao)
    except LiaIndisponivelError as erro:
        logger.warning(
            "Apresentacao de imoveis da conversa %s falhou (cota=%s): %s",
            requisicao.conversa_id,
            erro.cota,
            erro,
        )
        return {"apresentacao": None}

    return {"apresentacao": apresentacao}


def _fechou_os_essenciais_agora(estado: EstadoTurno) -> bool:
    """O turno em que o perfil deixou de ter essencial em aberto.

    Existe por causa do achado do S-12: o no qualificador monta as lacunas antes
    da mensagem do turno, entao o turno que **fecha** o piso sempre o ve aberto, e
    o modelo pede mais uma pergunta em vez de mostrar imovel. Quem sabe que o piso
    fechou e a regua, depois de fundir -- e ela decide sozinha, sem chamada extra.

    So o instante da virada dispara. Turno seguinte volta a depender do modelo
    dizer `sugerir_imoveis`, senao toda conversa qualificada passaria a custar
    duas chamadas e um embedding por mensagem.
    """
    antes = qualificacao.lacunas_essenciais(estado["requisicao"].perfil_lead)

    return bool(antes) and not qualificacao.lacunas_essenciais(estado["perfil"])


def _apos_pontuar(estado: EstadoTurno) -> str:
    proxima_acao = estado["saida"].proxima_acao

    if proxima_acao == GATILHO_DA_BUSCA:
        return "consultar"

    # Desfecho que o modelo declarou ganha da regua: encaminhar para gente de
    # verdade e encerrar sao decisoes da conversa, nao do perfil.
    if proxima_acao != "continuar_conversa":
        return END

    return "consultar" if _fechou_os_essenciais_agora(estado) else END


def _apos_consultar(estado: EstadoTurno) -> str:
    """Lista vazia ainda vai para o LLM: negociar criterio e trabalho de fala.

    `None` e outra coisa -- o indice nao respondeu, e a Lia nao pode afirmar que
    a base nao tem o que ela nunca chegou a procurar.
    """
    return END if estado["resultados"] is None else "apresentar"


@lru_cache(maxsize=1)
def _grafo():
    grafo = StateGraph(EstadoTurno)
    grafo.add_node("qualificar", _qualificar)
    grafo.add_node("responder", _responder)
    grafo.add_node("pontuar", _pontuar)
    grafo.add_node("consultar", _consultar)
    grafo.add_node("apresentar", _apresentar)
    grafo.add_edge(START, "qualificar")
    grafo.add_edge("qualificar", "responder")
    grafo.add_edge("responder", "pontuar")
    grafo.add_conditional_edges("pontuar", _apos_pontuar, {"consultar": "consultar", END: END})
    grafo.add_conditional_edges(
        "consultar", _apos_consultar, {"apresentar": "apresentar", END: END}
    )
    grafo.add_edge("apresentar", END)

    return grafo.compile()


def _sugeridos(
    resultados: list[Resultado] | None,
    apresentacao: SaidaApresentacao | None,
) -> list[ImovelSugerido]:
    """So entra no cartao o imovel que a busca achou **e** o LLM justificou.

    O `motivo` e texto do LLM por decisao do card: uma frase montada pela regua
    diria a mesma coisa em todos os cartoes. Sem motivo, o imovel fica de fora --
    inventar a justificativa aqui seria fabricar a parte que o lead le.
    """
    if not resultados or apresentacao is None:
        return []

    motivos = {motivo.id: motivo.motivo for motivo in apresentacao.motivos}
    sugeridos = []

    for resultado in resultados:
        motivo = motivos.get(resultado.imovel.id)

        if motivo is None:
            continue

        imovel = resultado.imovel
        sugeridos.append(
            ImovelSugerido(
                id=imovel.id,
                tipo=imovel.tipo,
                bairro=imovel.bairro,
                quartos=imovel.quartos,
                metragem=imovel.metragem,
                preco_venda=imovel.preco_venda,
                preco_aluguel=imovel.preco_aluguel,
                motivo=motivo,
            )
        )

    return sugeridos


def _proxima_acao(saida: SaidaLia, imoveis: list[ImovelSugerido]) -> ProximaAcao:
    """Este campo descreve o que aconteceu, nao o que o modelo pretendia.

    Quem o le depois -- a trilha do front, o painel do corretor -- precisa poder
    confiar nele. Entao ele desce quando a busca nao trouxe nada (vazia ou indice
    fora do ar) e sobe quando a regua disparou a busca e o lead recebeu imoveis
    num turno que o modelo tinha marcado como `continuar_conversa`.
    """
    if imoveis:
        return GATILHO_DA_BUSCA

    if saida.proxima_acao == GATILHO_DA_BUSCA:
        return "continuar_conversa"

    return saida.proxima_acao


def responder(requisicao: TurnoRequest) -> TurnoResponse:
    estado = _grafo().invoke({"requisicao": requisicao})
    saida: SaidaLia = estado["saida"]
    apresentacao: SaidaApresentacao | None = estado.get("apresentacao")
    imoveis = _sugeridos(estado.get("resultados"), apresentacao)

    return TurnoResponse(
        resposta=apresentacao.resposta if apresentacao else saida.resposta,
        intencao=saida.intencao,
        campos_extraidos=CamposExtraidos(
            **saida.campos_extraidos.model_dump(), score=estado["score"]
        ),
        proxima_acao=_proxima_acao(saida, imoveis),
        imoveis_sugeridos=imoveis,
    )
