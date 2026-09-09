"""Indice vetorial dos imoveis: embeddings em memoria, reconstruidos no boot."""

import hashlib
import json
import logging
import math
import os
import re
import unicodedata
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from langchain_google_genai import GoogleGenerativeAIEmbeddings

from app.contrato import LIMITE_IMOVEIS, Intencao, PerfilLead

logger = logging.getLogger("solar.lia")

DIMENSAO = 768
BASE = Path(__file__).resolve().parents[2] / "data" / "imoveis.json"
CACHE = Path(__file__).resolve().parents[2] / "data" / "embeddings.json"

_TAREFA_DOCUMENTO = "RETRIEVAL_DOCUMENT"
_TAREFA_CONSULTA = "RETRIEVAL_QUERY"
_LOTE = 100
_CASAS = 6

_indice: "Indice | None" = None


class IndiceIndisponivelError(RuntimeError):
    pass


@dataclass(frozen=True, slots=True)
class Imovel:
    id: str
    tipo: str
    bairro: str
    zona: str
    quartos: int
    banheiros: int
    vagas: int
    metragem: int
    preco_venda: int | None
    preco_aluguel: int | None
    condominio: int | None
    iptu: int | None
    descricao: str

    @property
    def texto(self) -> str:
        """O que vai para o embedding: cabecalho estruturado mais a descricao."""
        quartos = "1 quarto" if self.quartos == 1 else f"{self.quartos} quartos"
        vagas = "1 vaga" if self.vagas == 1 else f"{self.vagas} vagas"

        return (
            f"{self.tipo} de {quartos} e {vagas}, {self.metragem} m2, "
            f"no bairro {self.bairro}, zona {self.zona}.\n{self.descricao}"
        )


@dataclass(frozen=True, slots=True)
class Resultado:
    imovel: Imovel
    similaridade: float


@dataclass(frozen=True, slots=True)
class Filtro:
    """Recorte estruturado do perfil. Preco so filtra com a intencao conhecida."""

    intencao: Intencao | None = None
    preco_min: int | None = None
    preco_max: int | None = None
    quartos: int | None = None
    regiao: str | None = None
    tipo: str | None = None

    @classmethod
    def do_perfil(cls, perfil: PerfilLead, tipo: str | None = None) -> "Filtro":
        return cls(
            intencao=perfil.intencao,
            preco_min=perfil.preco_min,
            preco_max=perfil.preco_max,
            quartos=perfil.quartos,
            regiao=perfil.regiao,
            tipo=tipo,
        )

    def aceita(self, imovel: Imovel) -> bool:
        if self.tipo is not None and imovel.tipo != self.tipo:
            return False

        if self.quartos is not None and imovel.quartos < self.quartos:
            return False

        if self.regiao is not None and not _regiao_bate(self.regiao, imovel):
            return False

        return self._preco_bate(imovel)

    def _preco_bate(self, imovel: Imovel) -> bool:
        if self.preco_min is None and self.preco_max is None:
            return True

        preco = self._preco_do_imovel(imovel)

        if preco is None:
            return self.intencao is None or self.intencao == "indefinida"

        if self.preco_min is not None and preco < self.preco_min:
            return False

        return self.preco_max is None or preco <= self.preco_max

    def _preco_do_imovel(self, imovel: Imovel) -> int | None:
        if self.intencao == "aluguel":
            return imovel.preco_aluguel

        if self.intencao in ("compra", "investimento"):
            return imovel.preco_venda

        return None


SINONIMOS_DE_TIPO = {
    "apartamento": "apartamento",
    "apartamentos": "apartamento",
    "apto": "apartamento",
    "aptos": "apartamento",
    "ape": "apartamento",
    "apes": "apartamento",
    "casa": "casa",
    "casas": "casa",
    "sobrado": "casa",
    "sobrados": "casa",
    "cobertura": "cobertura",
    "coberturas": "cobertura",
    "studio": "studio",
    "studios": "studio",
    "estudio": "studio",
    "estudios": "studio",
    "kitnet": "studio",
    "quitinete": "studio",
}

_NEGACOES = frozenset({"nao", "nem", "exceto", "menos", "sem", "nada"})
_JANELA_DA_NEGACAO = 3


def tipo_pedido(mensagem: str, historico: Sequence | None = None) -> str | None:
    """O tipo de imovel que o lead nomeou, da fala mais recente para a mais antiga.

    Existe porque `tipo` nao esta no `PerfilLead`, e o contrato do `POST /turn`
    esta congelado desde o S-05: mexer nele custa commit coordenado em dois repos
    e uma migration. Enquanto isso, "quero apartamento" e restricao dura tanto
    quanto "2 quartos" -- devolver uma casa para quem pediu apartamento derruba a
    confianca na busca inteira.

    Palavra precedida de negacao nao conta: e a mesma armadilha do bug de negacao
    do S-11, e aqui ela viraria filtro em vez de campo.
    """
    falas = [mensagem]

    for anterior in reversed(list(historico or ())):
        if getattr(anterior, "papel", None) == "lead":
            falas.append(anterior.texto)

    for fala in falas:
        tipo = _tipo_na_fala(fala)

        if tipo is not None:
            return tipo

    return None


def _tipo_na_fala(fala: str) -> str | None:
    palavras = re.findall(r"[a-z0-9]+", _sem_acento(fala))

    for posicao, palavra in enumerate(palavras):
        tipo = SINONIMOS_DE_TIPO.get(palavra)

        if tipo is None:
            continue

        anteriores = palavras[max(0, posicao - _JANELA_DA_NEGACAO) : posicao]

        if not _NEGACOES.intersection(anteriores):
            return tipo

    return None


_INTENCAO_NA_CONSULTA = {
    "compra": "para comprar",
    "aluguel": "para alugar",
    "investimento": "para investir",
}


def texto_da_consulta(mensagem: str, perfil: PerfilLead) -> str:
    """O lado da consulta do embedding, espelho do `Imovel.texto`.

    A mensagem vem primeiro porque e onde o desejo aparece em linguagem natural.
    O perfil vem depois e sustenta a busca quando a mensagem sozinha nao descreve
    imovel nenhum -- "pode ser", "manda o que voce achar". Preco fica de fora de
    proposito: ele ja e restricao dura no `Filtro`, e numero em texto embutido
    aproxima por semelhanca de digito, nao de imovel.
    """
    partes = []

    if perfil.quartos is not None:
        quartos = "1 quarto" if perfil.quartos == 1 else f"{perfil.quartos} quartos"
        partes.append(f"de {quartos}")

    if perfil.regiao:
        partes.append(f"na regiao {perfil.regiao}")

    if perfil.intencao in _INTENCAO_NA_CONSULTA:
        partes.append(_INTENCAO_NA_CONSULTA[perfil.intencao])

    if not partes:
        return mensagem

    return f"{mensagem}\n\nImovel {' '.join(partes)}."


@dataclass(frozen=True, slots=True)
class Embutidor:
    documentos: Callable[[list[str]], list[Sequence[float]]]
    consulta: Callable[[str], Sequence[float]]


@dataclass(frozen=True, slots=True)
class Indice:
    imoveis: tuple[Imovel, ...]
    vetores: tuple[tuple[float, ...], ...]
    embutidor: Embutidor
    modelo: str
    origem: str

    @property
    def dimensao(self) -> int:
        return len(self.vetores[0])

    def buscar(
        self,
        texto: str,
        k: int = LIMITE_IMOVEIS,
        filtro: Filtro | None = None,
    ) -> list[Resultado]:
        """Ordena por similaridade os imoveis que o filtro aceita.

        Lista vazia significa que a base nao tem o que o lead pediu -- e um fato
        para a Lia dizer, nunca para ela trocar por um imovel qualquer.
        """
        consulta = _normalizar(_chamar(self.embutidor.consulta, texto))

        if len(consulta) != self.dimensao:
            raise IndiceIndisponivelError(
                f"consulta em {len(consulta)} dimensoes contra indice de {self.dimensao}"
            )

        resultados = [
            Resultado(imovel, _produto(consulta, self.vetores[posicao]))
            for posicao, imovel in enumerate(self.imoveis)
            if filtro is None or filtro.aceita(imovel)
        ]
        resultados.sort(key=lambda resultado: resultado.similaridade, reverse=True)

        return resultados[:k]


def carregar(caminho: Path | None = None) -> tuple[Imovel, ...]:
    origem = caminho or BASE

    try:
        bruto = json.loads(origem.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as erro:
        raise IndiceIndisponivelError(
            f"base de imoveis ilegivel em {origem}: {erro}"
        ) from erro

    if not bruto:
        raise IndiceIndisponivelError(f"base de imoveis vazia em {origem}")

    return tuple(
        Imovel(
            id=registro["id"],
            tipo=registro["tipo"],
            bairro=registro["bairro"],
            zona=registro["zona"],
            quartos=registro["quartos"],
            banheiros=registro["banheiros"],
            vagas=registro["vagas"],
            metragem=registro["metragem"],
            preco_venda=registro.get("precoVenda"),
            preco_aluguel=registro.get("precoAluguel"),
            condominio=registro.get("condominio"),
            iptu=registro.get("iptu"),
            descricao=registro["descricao"],
        )
        for registro in bruto
    )


def construir(
    embutidor: Embutidor | None = None,
    caminho: Path | None = None,
    cache: Path | bool | None = None,
) -> Indice:
    """Monta o indice: cache de vetores quando ele confere, API quando nao.

    `cache=False` ignora o cache e vai direto na API.
    """
    global _indice

    imoveis = carregar(caminho)
    injetado = embutidor is not None
    escolhido = embutidor or _gemini()
    modelo = "injetado" if injetado else _nome_do_modelo()

    consultar_cache = not injetado and cache is not False
    vetores = ler_cache(imoveis, modelo, cache or None) if consultar_cache else None
    origem = "cache"

    if vetores is None:
        origem = "injetado" if injetado else "api"
        vetores = _chamar(escolhido.documentos, [imovel.texto for imovel in imoveis])

    if len(vetores) != len(imoveis):
        raise IndiceIndisponivelError(f"{len(vetores)} vetores para {len(imoveis)} imoveis")

    dimensoes = {len(vetor) for vetor in vetores}

    if len(dimensoes) != 1:
        raise IndiceIndisponivelError(f"vetores com dimensoes diferentes: {sorted(dimensoes)}")

    _indice = Indice(
        imoveis=imoveis,
        vetores=tuple(_normalizar(vetor) for vetor in vetores),
        embutidor=escolhido,
        modelo=modelo,
        origem=origem,
    )

    return _indice


def impressao(imoveis: Sequence[Imovel]) -> str:
    """sha256 do texto que vai para o embedding, na ordem da base."""
    digestor = hashlib.sha256()

    for imovel in imoveis:
        digestor.update(imovel.texto.encode("utf-8"))
        digestor.update(b"\x00")

    return digestor.hexdigest()


def ler_cache(
    imoveis: Sequence[Imovel],
    modelo: str,
    caminho: Path | None = None,
) -> tuple[tuple[float, ...], ...] | None:
    origem = caminho or CACHE

    if not origem.exists():
        logger.info("Sem cache de embeddings em %s; os vetores virao da API", origem)
        return None

    try:
        guardado = json.loads(origem.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as erro:
        logger.warning("Cache de embeddings ilegivel em %s: %s", origem, erro)
        return None

    recusa = _recusa_do_cache(guardado, imoveis, modelo)

    if recusa:
        logger.warning("Cache de embeddings ignorado (%s); rode scripts/gerar_embeddings.py", recusa)
        return None

    return tuple(tuple(guardado["vetores"][imovel.id]) for imovel in imoveis)


def escrever_cache(
    imoveis: Sequence[Imovel],
    vetores: Sequence[Sequence[float]],
    modelo: str,
    caminho: Path | None = None,
) -> Path:
    destino = caminho or CACHE
    conteudo = {
        "modelo": modelo,
        "dimensao": len(vetores[0]),
        "corpus": impressao(imoveis),
        "gerado_em": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "vetores": {
            imovel.id: [round(valor, _CASAS) for valor in _normalizar(vetor)]
            for imovel, vetor in zip(imoveis, vetores)
        },
    }
    destino.write_text(json.dumps(conteudo, ensure_ascii=False), encoding="utf-8")

    return destino


def _recusa_do_cache(guardado: dict, imoveis: Sequence[Imovel], modelo: str) -> str | None:
    if not isinstance(guardado, dict) or not isinstance(guardado.get("vetores"), dict):
        return "formato desconhecido"

    if guardado.get("modelo") != modelo:
        return f"gerado com {guardado.get('modelo')!r} e o ambiente pede {modelo!r}"

    if guardado.get("dimensao") != DIMENSAO:
        return f"dimensao {guardado.get('dimensao')} em vez de {DIMENSAO}"

    if guardado.get("corpus") != impressao(imoveis):
        return "a base de imoveis mudou desde a geracao"

    faltando = [imovel.id for imovel in imoveis if imovel.id not in guardado["vetores"]]

    if faltando:
        return f"sem vetor para {len(faltando)} imoveis, a comecar por {faltando[0]}"

    return None


def atual() -> Indice:
    if _indice is None:
        raise IndiceIndisponivelError("indice de imoveis nao foi construido no boot")

    return _indice


def descartar() -> None:
    global _indice
    _indice = None


def _nome_do_modelo() -> str:
    nome = os.getenv("GEMINI_EMBEDDING_MODEL", "").strip()

    if not nome:
        raise IndiceIndisponivelError("GEMINI_EMBEDDING_MODEL ausente no ambiente")

    return nome


def _gemini() -> Embutidor:
    chave = os.getenv("GEMINI_API_KEY", "").strip()

    if not chave:
        raise IndiceIndisponivelError("GEMINI_API_KEY ausente no ambiente")

    cliente = GoogleGenerativeAIEmbeddings(model=_nome_do_modelo(), google_api_key=chave)

    return Embutidor(
        documentos=lambda textos: cliente.embed_documents(
            textos,
            batch_size=_LOTE,
            task_type=_TAREFA_DOCUMENTO,
            output_dimensionality=DIMENSAO,
        ),
        consulta=lambda texto: cliente.embed_query(
            texto,
            task_type=_TAREFA_CONSULTA,
            output_dimensionality=DIMENSAO,
        ),
    )


def _chamar(funcao, argumento):
    try:
        return funcao(argumento)
    except IndiceIndisponivelError:
        raise
    except Exception as erro:
        raise IndiceIndisponivelError(f"{type(erro).__name__}: {erro}") from erro


def _normalizar(vetor: Sequence[float]) -> tuple[float, ...]:
    norma = math.sqrt(sum(valor * valor for valor in vetor))

    if not norma:
        raise IndiceIndisponivelError("vetor de norma zero no indice")

    return tuple(valor / norma for valor in vetor)


def _produto(a: Sequence[float], b: Sequence[float]) -> float:
    return sum(x * y for x, y in zip(a, b))


def _sem_acento(texto: str) -> str:
    decomposto = unicodedata.normalize("NFKD", texto.lower())

    return "".join(letra for letra in decomposto if not unicodedata.combining(letra))


def _regiao_bate(regiao: str, imovel: Imovel) -> bool:
    alvo = _sem_acento(regiao)

    if _sem_acento(imovel.bairro) in alvo:
        return True

    return _sem_acento(imovel.zona) in set(re.findall(r"[a-z0-9]+", alvo))
