"""Regua de qualificacao do lead: score e proxima lacuna.

Uma tabela de sinais por trilha responde as duas perguntas do S-12 -- quanto
vale este lead e sobre o que perguntar agora. Deterministica, sem LLM.
"""

from dataclasses import dataclass

from pydantic import BaseModel

from app.contrato import Intencao, PerfilLead

@dataclass(frozen=True)
class Sinal:
    """Um sinal de qualificacao: o que vale e como se pergunta por ele."""

    campo: str
    peso: int
    rotulo: str
    pergunta: str
    essencial: bool = False
    graduacao: dict[str, int] | None = None


MORADIA = (
    Sinal("intencao", 25, "intencao", "se ela quer comprar ou alugar", essencial=True),
    Sinal(
        "regiao",
        20,
        "regiao",
        "em que regiao ou bairro ela quer o imovel",
        essencial=True,
    ),
    Sinal(
        "preco",
        20,
        "faixa de preco",
        "que faixa de preco ela tem em mente",
        essencial=True,
    ),
    Sinal(
        "urgencia",
        15,
        "prazo",
        "quando ela pretende se mudar ou decidir",
        graduacao={"alta": 15, "media": 9, "baixa": 5},
    ),
    Sinal("quartos", 10, "quartos", "de quantos quartos ela precisa"),
    Sinal("nome", 10, "nome", "como ela se chama"),
)

INVESTIMENTO = (
    Sinal("intencao", 25, "intencao", "se e para investir ou para morar", essencial=True),
    Sinal("preco", 20, "ticket", "quanto ela tem para aplicar", essencial=True),
    Sinal(
        "expectativa_retorno",
        20,
        "expectativa de retorno",
        "que retorno ela espera, em percentual, prazo ou nas palavras dela",
        essencial=True,
    ),
    Sinal("regiao", 15, "regiao", "em que regiao ela quer investir"),
    Sinal(
        "urgencia",
        10,
        "prazo",
        "em quanto tempo ela pretende decidir",
        graduacao={"alta": 10, "media": 6, "baixa": 3},
    ),
    Sinal("nome", 10, "nome", "como ela se chama"),
)


DESFECHO_DA_TRILHA = {"investimento": "direcionar_especialista"}


def trilha(perfil: PerfilLead) -> tuple[Sinal, ...]:
    return INVESTIMENTO if perfil.intencao == "investimento" else MORADIA


def _preenchido(perfil: PerfilLead, campo: str) -> bool:
    if campo == "intencao":
        return perfil.intencao is not None and perfil.intencao != "indefinida"

    if campo == "preco":
        return perfil.preco_min is not None or perfil.preco_max is not None

    return getattr(perfil, campo) is not None


def _pontos(perfil: PerfilLead, sinal: Sinal) -> int:
    if sinal.graduacao is None:
        return sinal.peso

    return sinal.graduacao[getattr(perfil, sinal.campo)]


def pontuar(perfil: PerfilLead) -> int:
    """Soma os sinais preenchidos do perfil, de 0 a 100."""
    total = sum(
        _pontos(perfil, sinal)
        for sinal in trilha(perfil)
        if _preenchido(perfil, sinal.campo)
    )

    return min(total, 100)


def lacunas(perfil: PerfilLead) -> tuple[Sinal, ...]:
    """O que falta no perfil, do sinal que mais vale para o que menos vale."""
    return tuple(
        sinal for sinal in trilha(perfil) if not _preenchido(perfil, sinal.campo)
    )


def lacunas_essenciais(perfil: PerfilLead) -> tuple[Sinal, ...]:
    """Piso do handoff: sem isto, nenhum humano assume o lead."""
    return tuple(sinal for sinal in lacunas(perfil) if sinal.essencial)


def desfecho_da_trilha(perfil: PerfilLead) -> str | None:
    """A `proximaAcao` que os essenciais desta trilha disparam, se houver uma.

    So a trilha de investimento tem: e a regra congelada do
    `direcionar_especialista`. Em moradia o essencial e piso, nao gatilho.
    """
    return DESFECHO_DA_TRILHA.get(perfil.intencao)


def fundir(perfil: PerfilLead, intencao: Intencao, extraidos: BaseModel) -> PerfilLead:
    """Espelha Lead.Fundir do solar-ai-api: nulo nao apaga, indefinida nao apaga."""
    fundido = perfil.model_copy(update=extraidos.model_dump(exclude_none=True))

    if intencao != "indefinida":
        fundido.intencao = intencao

    return fundido
