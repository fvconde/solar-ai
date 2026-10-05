"""Grafo da Lia.

Oito nos com supervisor central deterministico na entrada do turno:
`supervisor` avalia a natureza do turno (custo zero de LLM, sem modelo) e roteia
para o especialista adequado: `qualificador`, `consultor`, `agendador` ou `reengajador`.

Exatamente TRES nos chamam o LLM no grafo: `responder`, `reengajar` e `apresentar`.
Os nos `supervisor`, `qualificador`, `agendar`, `consultar` e `pontuar` sao funcoes
puras e deterministicas.

O custo por turno se mantem inalterado: 1 chamada no turno comum (qualificador comum,
agendador, reengajador ou consultor direto) e 2 chamadas no turno que atinge a regua
e sugere imoveis (qualificador com sugestao).
"""

import logging
import os
import re
import unicodedata
from functools import lru_cache
from typing import TypedDict, cast

from langchain_core.messages import BaseMessage, HumanMessage, SystemMessage
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
    ResumoRequest,
    ResumoResponse,
    SlotOferecido,
    TurnoRequest,
    TurnoResponse,
    Urgencia,
)
from app.lia import indice as indice_imoveis
from app.lia import prompts, qualificacao
from app.lia.indice import Filtro, IndiceIndisponivelError, Resultado
from app.lia.mascaramento import MascaradorPII
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
    slot_escolhido: int | None = None


class MotivoDoImovel(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    motivo: str = Field(min_length=1)


class SaidaApresentacao(BaseModel):
    """Segunda chamada: a fala com os imoveis na mao e o motivo de cada um."""

    model_config = ConfigDict(extra="forbid")

    resposta: str = Field(min_length=1)
    motivos: list[MotivoDoImovel] = Field(default_factory=list)


class EstadoTurno(TypedDict, total=False):
    requisicao: TurnoRequest
    mascarador: MascaradorPII
    reengajamento: bool
    rota: str
    lacunas: tuple[Sinal, ...]
    desfecho: str | None
    agenda: list[SlotOferecido]
    saida: SaidaLia
    score: int
    perfil: PerfilLead
    filtro: Filtro
    resultados: list[Resultado] | None
    apresentacao: SaidaApresentacao | None


def _sem_acento(texto: str) -> str:
    decomposto = unicodedata.normalize("NFKD", texto.lower())
    return "".join(letra for letra in decomposto if not unicodedata.combining(letra))


def _modalidade_mencionada(texto: str) -> Intencao | None:
    normalizado = _sem_acento(texto)
    aluguel = bool(re.search(r"\b(alug|locac|mensal|por mes)\w*", normalizado))
    compra = bool(re.search(r"\b(compr|vend|aquisic)\w*", normalizado))

    for numero, escala in re.findall(
        r"\b(\d+(?:[.,]\d+)?)\s*(milhoes?|milhao|mil)\b", normalizado
    ):
        valor = float(numero.replace(",", "."))
        if escala.startswith("milh"):
            valor *= 1_000_000
        elif escala.startswith("mil"):
            valor *= 1_000
        if valor >= 100_000:
            compra = True

    if aluguel and compra:
        return "indefinida"
    if aluguel:
        return "aluguel"
    if compra:
        return "compra"
    return None


def _regiao_mencionada(texto: str) -> str | None:
    normalizado = _sem_acento(texto)
    match = re.search(r"\b(zona\s+(?:norte|sul|leste|oeste|central))\b", normalizado)
    return match.group(1) if match else None


def _orcamento_mencionado(texto: str) -> tuple[int | None, int | None]:
    normalizado = _sem_acento(texto)
    precos = re.findall(
        r"\b(\d+(?:[.,]\d+)?)\s*(milhoes?|milhao|mil)\b", normalizado
    )
    if not precos:
        return None, None

    numero, escala = precos[-1]
    valor = float(numero.replace(",", "."))
    if escala.startswith("milh"):
        valor *= 1_000_000
    else:
        valor *= 1_000
    valor = int(valor)
    inicio = normalizado.rfind(numero)
    prefixo = normalizado[max(0, inicio - 24) : inicio]
    if re.search(r"(a partir de|acima de|no minimo)\s*$", prefixo):
        return valor, None
    return None, valor


def _preco_confirmado(requisicao: TurnoRequest) -> tuple[int | None, int | None]:
    textos = [requisicao.mensagem]
    textos.extend(
        mensagem.texto
        for mensagem in reversed(requisicao.historico)
        if mensagem.papel == "lead"
    )
    for texto in textos:
        minimo, maximo = _orcamento_mencionado(texto)
        if minimo is not None or maximo is not None:
            return minimo, maximo
    return None, None


def _aguarda_esclarecimento_modalidade(requisicao: TurnoRequest) -> bool:
    for mensagem in reversed(requisicao.historico):
        if mensagem.papel != "agente":
            continue
        texto = _sem_acento(mensagem.texto)
        tem_modalidades = bool(re.search(r"\b(alug\w*|compr\w*)\b", texto))
        tem_pergunta_de_valor = "mensal" in texto or "preco total" in texto
        return (
            "alugar ou comprar" in texto
            or "aluguel ou compra" in texto
            or (tem_modalidades and tem_pergunta_de_valor)
        )
    return False


def _modalidade_resolvida(requisicao: TurnoRequest) -> Intencao | None:
    if not _aguarda_esclarecimento_modalidade(requisicao):
        return None
    modalidade = _modalidade_mencionada(requisicao.mensagem)
    return modalidade if modalidade in ("aluguel", "compra") else None


def _conflito_modalidade(requisicao: TurnoRequest) -> bool:
    atual = _modalidade_mencionada(requisicao.mensagem)
    if _modalidade_resolvida(requisicao) is not None:
        return False
    if _aguarda_esclarecimento_modalidade(requisicao):
        return True
    if atual == "indefinida":
        return True
    if atual is None:
        return False

    anterior = requisicao.perfil_lead.intencao
    if anterior in ("aluguel", "compra") and anterior != atual:
        return True

    for mensagem in reversed(requisicao.historico):
        if mensagem.papel != "lead":
            continue
        mencionada = _modalidade_mencionada(mensagem.texto)
        if mencionada == "indefinida":
            return True
        if mencionada in ("aluguel", "compra"):
            return mencionada != atual
    return False


def _pergunta_depois_da_modalidade(perfil: PerfilLead) -> str:
    perguntas = {
        "regiao": "Em qual região ou bairro você está procurando?",
        "preco": "Qual faixa de preço você tem em mente?",
        "urgencia": "Quando você pretende se mudar ou decidir?",
        "quartos": "De quantos quartos você precisa?",
        "nome": "Como você se chama?",
    }
    lacunas = qualificacao.lacunas(perfil)
    return perguntas.get(lacunas[0].campo, "O que mais você gostaria de considerar?") if lacunas else "Como posso ajudar você a avançar?"


def _imovel_referenciado(requisicao: TurnoRequest) -> ImovelSugerido | None:
    texto = _sem_acento(requisicao.mensagem)
    ordinal = None
    if re.search(r"\b(primeir\w*|1a|1o|opcao\s*(?:numero\s*)?1)\b", texto):
        ordinal = 0
    elif re.search(r"\b(segund\w*|2a|2o|opcao\s*(?:numero\s*)?2)\b", texto):
        ordinal = 1
    elif re.search(r"\b(terceir\w*|3a|3o|opcao\s*(?:numero\s*)?3)\b", texto):
        ordinal = 2

    if ordinal is None:
        return None

    for mensagem in reversed(requisicao.historico):
        if mensagem.papel == "agente" and mensagem.imoveis_sugeridos:
            return (
                mensagem.imoveis_sugeridos[ordinal]
                if ordinal < len(mensagem.imoveis_sugeridos)
                else None
            )
    return None


def _resposta_de_handoff(
    saida: SaidaLia,
    requisicao: TurnoRequest,
    imovel: ImovelSugerido | None = None,
) -> SaidaLia:
    if imovel is not None:
        if requisicao.agenda:
            resposta = (
                f"Vamos seguir com o imóvel de {imovel.bairro}. "
                "Qual dos horários oferecidos funciona para você?"
            )
        else:
            resposta = (
                f"Vamos seguir com o imóvel de {imovel.bairro}. "
                "Vou confirmar a visita com o corretor."
            )
        proxima_acao: ProximaAcao = "agendar_reuniao"
    elif requisicao.visita_confirmada:
        resposta = "Sua visita já está confirmada e o corretor dará continuidade ao atendimento."
        proxima_acao = "agendar_reuniao"
    elif saida.proxima_acao in ("agendar_reuniao", "direcionar_especialista"):
        resposta = (
            "Posso encaminhar sua conversa para um corretor."
            if not requisicao.contato_informado
            else saida.resposta
        )
        proxima_acao = saida.proxima_acao
    else:
        return saida

    if not requisicao.contato_informado and "informe seu telefone ou e-mail" not in resposta:
        resposta += " Para o corretor entrar em contato, informe seu telefone ou e-mail."
    return saida.model_copy(update={"resposta": resposta, "proxima_acao": proxima_acao})


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


@lru_cache(maxsize=1)
def _modelo_resumo():
    return _cliente().with_structured_output(ResumoResponse, method="json_schema")


def _e_cota(texto: str) -> bool:
    minusculo = texto.lower()
    return any(marca in minusculo for marca in _MARCAS_DE_COTA)


def _qualificar(estado: EstadoTurno) -> EstadoTurno:
    perfil = estado["requisicao"].perfil_lead

    return {
        "lacunas": qualificacao.lacunas(perfil),
        "desfecho": qualificacao.desfecho_da_trilha(perfil),
        "agenda": [],
    }


def _agendar(estado: EstadoTurno) -> EstadoTurno:
    """No puro: leva ao prompt apenas os horarios recebidos da API dona do banco."""
    return {
        "agenda": estado["requisicao"].agenda,
        "lacunas": (),
        "desfecho": None,
    }


def _mensagens_mascaradas(
    mensagens: list[BaseMessage], mascarador: MascaradorPII
) -> list[BaseMessage]:
    """Ultima barreira antes da geracao: nenhum texto cru atravessa daqui."""
    def proteger(conteudo):
        if isinstance(conteudo, str):
            return mascarador.mascarar(conteudo)
        if isinstance(conteudo, list):
            return [proteger(item) for item in conteudo]
        if isinstance(conteudo, dict):
            return {chave: proteger(valor) for chave, valor in conteudo.items()}
        return conteudo

    return [
        mensagem.model_copy(update={"content": proteger(mensagem.content)})
        for mensagem in mensagens
    ]


def _desmascarar_saida(saida: BaseModel, mascarador: MascaradorPII) -> BaseModel:
    def restaurar(valor):
        if isinstance(valor, str):
            return mascarador.desmascarar(valor)
        if isinstance(valor, list):
            return [restaurar(item) for item in valor]
        if isinstance(valor, dict):
            return {chave: restaurar(item) for chave, item in valor.items()}
        return valor

    return type(saida).model_validate(restaurar(saida.model_dump()))


def _invocar(
    modelo,
    mensagens: list[BaseMessage],
    esperado: type[BaseModel],
    mascarador: MascaradorPII,
    *,
    restaurar_pii: bool = True,
) -> BaseModel:
    try:
        saida = modelo.invoke(_mensagens_mascaradas(mensagens, mascarador))
    except LiaIndisponivelError:
        raise
    except Exception as erro:
        texto = f"{type(erro).__name__}: {erro}"
        raise LiaIndisponivelError(texto, cota=_e_cota(texto)) from erro

    if not isinstance(saida, esperado):
        raise LiaIndisponivelError(
            f"o modelo devolveu {type(saida).__name__} em vez da saida estruturada"
        )

    return _desmascarar_saida(saida, mascarador) if restaurar_pii else saida


def _responder(estado: EstadoTurno) -> EstadoTurno:
    requisicao = estado["requisicao"]

    mensagens = [
        SystemMessage(content=prompts.persona()),
        HumanMessage(
            content=prompts.turno(
                requisicao.perfil_lead,
                requisicao.historico,
                requisicao.mensagem,
                estado.get("lacunas", ()),
                estado.get("desfecho"),
                estado.get("agenda", []),
                requisicao.contato_informado,
                requisicao.visita_confirmada,
            )
        ),
    ]

    return {
        "saida": _invocar(_modelo(), mensagens, SaidaLia, estado["mascarador"])
    }


def _reengajar(estado: EstadoTurno) -> EstadoTurno:
    requisicao = estado["requisicao"]

    mensagens = [
        SystemMessage(content=prompts.persona()),
        HumanMessage(
            content=prompts.reengajamento(
                requisicao.perfil_lead,
                requisicao.historico,
            )
        ),
    ]

    return {
        "saida": _invocar(_modelo(), mensagens, SaidaLia, estado["mascarador"]),
        "lacunas": (),
        "desfecho": None,
        "agenda": [],
    }


def _pontuar(estado: EstadoTurno) -> EstadoTurno:
    requisicao = estado["requisicao"]
    saida = estado["saida"]
    modalidade_resolvida = _modalidade_resolvida(requisicao)

    if modalidade_resolvida is not None:
        campos = saida.campos_extraidos
        preco_min, preco_max = _preco_confirmado(requisicao)
        if preco_min is not None or preco_max is not None:
            campos = campos.model_copy(
                update={"preco_min": preco_min, "preco_max": preco_max}
            )
        perfil = qualificacao.fundir(
            requisicao.perfil_lead,
            modalidade_resolvida,
            campos,
        )
        saida = saida.model_copy(
            update={
                "resposta": (
                    f"Entendi, vamos considerar {modalidade_resolvida}. "
                    f"{_pergunta_depois_da_modalidade(perfil)}"
                ),
                "intencao": modalidade_resolvida,
                "campos_extraidos": campos,
                "proxima_acao": "continuar_conversa",
                "slot_escolhido": None,
            }
        )
        return {
            "saida": saida,
            "perfil": perfil,
            "score": qualificacao.pontuar(perfil),
        }

    if _conflito_modalidade(requisicao):
        campos = saida.campos_extraidos
        regiao = _regiao_mencionada(requisicao.mensagem)
        if regiao is not None:
            campos = campos.model_copy(update={"regiao": regiao})
        campos = campos.model_copy(update={"preco_min": None, "preco_max": None})
        saida = saida.model_copy(
            update={
                "resposta": (
                    "Entendi que você falou em aluguel e agora mencionou um valor "
                    "de compra. Você quer alugar ou comprar? Esse valor é mensal "
                    "ou o preço total do imóvel?"
                ),
                "intencao": "indefinida",
                "campos_extraidos": campos,
                "proxima_acao": "continuar_conversa",
                "slot_escolhido": None,
            }
        )
        return {
            "saida": saida,
            "perfil": requisicao.perfil_lead,
            "score": qualificacao.pontuar(requisicao.perfil_lead),
        }

    imovel = _imovel_referenciado(requisicao)
    if imovel is not None or requisicao.visita_confirmada:
        saida = _resposta_de_handoff(saida, requisicao, imovel)

    perfil = qualificacao.fundir(
        requisicao.perfil_lead, saida.intencao, saida.campos_extraidos
    )

    if (
        imovel is None
        and not requisicao.visita_confirmada
        and saida.proxima_acao in ("agendar_reuniao", "direcionar_especialista")
    ):
        saida = _resposta_de_handoff(saida, requisicao)

    return {"saida": saida, "perfil": perfil, "score": qualificacao.pontuar(perfil)}


def _consultar(estado: EstadoTurno) -> EstadoTurno:
    """Busca no indice com o perfil ja fundido. Indice fora do ar nao derruba o turno."""
    requisicao = estado["requisicao"]
    perfil = estado.get("perfil") or requisicao.perfil_lead
    filtro = Filtro.do_perfil(
        perfil, indice_imoveis.tipo_pedido(requisicao.mensagem, requisicao.historico)
    )

    resultado_dict: EstadoTurno = {"filtro": filtro, "perfil": perfil}
    if estado.get("score") is None:
        resultado_dict["score"] = qualificacao.pontuar(perfil)
    if estado.get("saida") is None:
        resultado_dict["saida"] = SaidaLia(
            resposta="Separei algumas opcoes de imoveis para voce.",
            intencao=perfil.intencao or "indefinida",
            campos_extraidos=CamposExtraidosLLM(),
            proxima_acao="sugerir_imoveis",
            slot_escolhido=None,
        )

    try:
        texto = indice_imoveis.texto_da_consulta(requisicao.mensagem, perfil)
        resultados = indice_imoveis.atual().buscar(
            texto,
            k=IMOVEIS_POR_SUGESTAO,
            filtro=filtro,
            mascarador=estado["mascarador"],
        )
    except IndiceIndisponivelError as erro:
        logger.warning(
            "Busca de imoveis da conversa %s nao aconteceu: %s",
            requisicao.conversa_id,
            erro,
        )
        resultado_dict["resultados"] = None
        return resultado_dict

    # Nunca logar o texto da consulta: ele carrega a mensagem do lead.
    logger.info(
        "Busca de imoveis da conversa %s: %d resultado(s) %s",
        requisicao.conversa_id,
        len(resultados),
        [resultado.imovel.id for resultado in resultados],
    )

    resultado_dict["resultados"] = resultados
    return resultado_dict


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
        apresentacao = _invocar(
            _modelo_apresentacao(),
            mensagens,
            SaidaApresentacao,
            estado["mascarador"],
        )
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


ROTA_REENGAJADOR = "reengajador"
ROTA_AGENDADOR = "agendador"
ROTA_CONSULTOR = "consultor"
ROTA_QUALIFICADOR = "qualificador"

ROTAS_ESPECIALISTAS = frozenset({
    ROTA_REENGAJADOR,
    ROTA_AGENDADOR,
    ROTA_CONSULTOR,
    ROTA_QUALIFICADOR,
})

_PALAVRAS_BUSCA = frozenset({
    "buscar", "busca", "imoveis", "imovel", "opcoes", "opcao",
    "mostrar", "mostra", "catalogo", "vitrine", "ver", "listar",
    "disponivel", "disponiveis", "sugestoes", "sugestao",
})


def _e_consulta_imoveis(requisicao: TurnoRequest) -> bool:
    msg = requisicao.mensagem.strip().lower()
    if msg == "[consultar]":
        return True

    # Se o perfil ja tem essenciais preenchidos e a mensagem busca imoveis
    if not qualificacao.lacunas_essenciais(requisicao.perfil_lead):
        decomposto = unicodedata.normalize("NFKD", msg)
        sem_acento = "".join(letra for letra in decomposto if not unicodedata.combining(letra))
        palavras = set(re.findall(r"[a-z0-9]+", sem_acento))
        if palavras & _PALAVRAS_BUSCA:
            return True
        if indice_imoveis.tipo_pedido(requisicao.mensagem, requisicao.historico) is not None:
            return True

    return False


def _decidir_rota(estado: EstadoTurno) -> str:
    if estado.get("reengajamento"):
        return ROTA_REENGAJADOR

    requisicao = estado["requisicao"]

    if (
        requisicao.visita_confirmada
        or _imovel_referenciado(requisicao) is not None
        or _conflito_modalidade(requisicao)
    ):
        return ROTA_AGENDADOR if requisicao.agenda else ROTA_QUALIFICADOR

    if requisicao.agenda:
        return ROTA_AGENDADOR

    if _e_consulta_imoveis(requisicao):
        return ROTA_CONSULTOR

    return ROTA_QUALIFICADOR


def _supervisor(estado: EstadoTurno) -> EstadoTurno:
    """No supervisor deterministico: avalia a natureza do turno e roteia para o especialista.

    Custo zero de LLM. Roteamento centralizado na entrada do turno e observavel no log.
    """
    rota = _decidir_rota(estado)
    requisicao = estado["requisicao"]

    logger.info(
        "Supervisor roteou conversa %s para o no %s",
        requisicao.conversa_id,
        rota,
    )

    return {"rota": rota}


def _rotear_supervisor(estado: EstadoTurno) -> str:
    return estado["rota"]


def _apos_pontuar(estado: EstadoTurno) -> str:
    requisicao = estado["requisicao"]
    if (
        _conflito_modalidade(requisicao)
        or requisicao.visita_confirmada
        or _imovel_referenciado(requisicao) is not None
    ):
        return END

    proxima_acao = estado["saida"].proxima_acao

    if proxima_acao == GATILHO_DA_BUSCA:
        return "consultor"

    # Desfecho que o modelo declarou ganha da regua: encaminhar para gente de
    # verdade e encerrar sao decisoes da conversa, nao do perfil.
    if proxima_acao != "continuar_conversa":
        return END

    return "consultor" if _fechou_os_essenciais_agora(estado) else END


def _apos_consultar(estado: EstadoTurno) -> str:
    """Lista vazia ainda vai para o LLM: negociar criterio e trabalho de fala.

    `None` e outra coisa -- o indice nao respondeu, e a Lia nao pode afirmar que
    a base nao tem o que ela nunca chegou a procurar.
    """
    return END if estado.get("resultados") is None else "apresentar"


@lru_cache(maxsize=1)
def _grafo():
    grafo = StateGraph(EstadoTurno)
    grafo.add_node("supervisor", _supervisor)
    grafo.add_node("qualificador", _qualificar)
    grafo.add_node("agendador", _agendar)
    grafo.add_node("consultor", _consultar)
    grafo.add_node("reengajador", _reengajar)
    grafo.add_node("responder", _responder)
    grafo.add_node("pontuar", _pontuar)
    grafo.add_node("apresentar", _apresentar)

    grafo.add_edge(START, "supervisor")
    grafo.add_conditional_edges(
        "supervisor",
        _rotear_supervisor,
        {
            ROTA_REENGAJADOR: "reengajador",
            ROTA_AGENDADOR: "agendador",
            ROTA_CONSULTOR: "consultor",
            ROTA_QUALIFICADOR: "qualificador",
        },
    )
    grafo.add_edge("qualificador", "responder")
    grafo.add_edge("agendador", "responder")
    grafo.add_edge("responder", "pontuar")
    grafo.add_edge("reengajador", "pontuar")
    grafo.add_conditional_edges("pontuar", _apos_pontuar, {"consultor": "consultor", END: END})
    grafo.add_conditional_edges(
        "consultor", _apos_consultar, {"apresentar": "apresentar", END: END}
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


def _proxima_acao(
    saida: SaidaLia,
    imoveis: list[ImovelSugerido],
    lacunas: tuple[Sinal, ...],
    desfecho: str | None,
) -> ProximaAcao:
    """Este campo descreve o que aconteceu, nao o que o modelo pretendia.

    Quem o le depois -- a trilha do front, o painel do corretor -- precisa poder
    confiar nele. Entao ele desce quando a busca nao trouxe nada (vazia ou indice
    fora do ar) e sobe quando a regua disparou a busca e o lead recebeu imoveis
    num turno que o modelo tinha marcado como `continuar_conversa`. O desfecho
    deterministico de uma trilha ja fechada tambem corrige a tentativa do modelo
    de prolongar a qualificacao; encerramento e acoes explicitas continuam
    prevalecendo.
    """
    if imoveis:
        return GATILHO_DA_BUSCA

    if saida.proxima_acao == GATILHO_DA_BUSCA:
        return "continuar_conversa"

    if (
        saida.proxima_acao == "continuar_conversa"
        and desfecho is not None
        and not any(sinal.essencial for sinal in lacunas)
    ):
        return cast(ProximaAcao, desfecho)

    return saida.proxima_acao


def _slot_escolhido(saida: SaidaLia, agenda: list[SlotOferecido]) -> int | None:
    """Gate estrutural: id que nao veio do banco nunca atravessa a fronteira."""
    oferecidos = {slot.id for slot in agenda}
    return saida.slot_escolhido if saida.slot_escolhido in oferecidos else None


def responder(requisicao: TurnoRequest, reengajamento: bool = False) -> TurnoResponse:
    estado = _grafo().invoke(
        {
            "requisicao": requisicao,
            "mascarador": MascaradorPII(),
            "reengajamento": reengajamento,
        }
    )
    saida: SaidaLia = estado["saida"]
    apresentacao: SaidaApresentacao | None = estado.get("apresentacao")
    imoveis = _sugeridos(estado.get("resultados"), apresentacao)
    perfil_fundido = qualificacao.fundir(
        requisicao.perfil_lead, saida.intencao, saida.campos_extraidos
    )

    return TurnoResponse(
        resposta=apresentacao.resposta if apresentacao else saida.resposta,
        intencao=saida.intencao,
        campos_extraidos=CamposExtraidos(
            **saida.campos_extraidos.model_dump(), score=estado["score"]
        ),
        proxima_acao=_proxima_acao(
            saida,
            imoveis,
            estado.get("lacunas", ()),
            estado.get("desfecho"),
        ),
        imoveis_sugeridos=imoveis,
        slot_escolhido=_slot_escolhido(saida, requisicao.agenda),
        essenciais_completos=not qualificacao.lacunas_essenciais(perfil_fundido),
    )


def resumir(requisicao: ResumoRequest) -> ResumoResponse:
    """Gera as cinco secoes sem permitir que PII volte ao texto do resumo."""
    mensagens = [
        HumanMessage(
            content=prompts.resumo(
                requisicao.perfil_lead,
                requisicao.historico,
                requisicao.imoveis,
            )
        )
    ]
    saida = _invocar(
        _modelo_resumo(),
        mensagens,
        ResumoResponse,
        MascaradorPII(),
        restaurar_pii=False,
    )
    return cast(ResumoResponse, saida)
