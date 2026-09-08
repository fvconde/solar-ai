"""Carga dos prompts da Lia a partir de prompts/."""

from pathlib import Path

from app.contrato import MensagemHistorico, PerfilLead
from app.lia.qualificacao import Sinal

PASTA = Path(__file__).resolve().parents[2] / "prompts"

ROTULOS = {
    "nome": "nome",
    "intencao": "intencao",
    "precoMin": "preco minimo",
    "precoMax": "preco maximo",
    "quartos": "quartos",
    "regiao": "regiao",
    "urgencia": "urgencia",
    "expectativaRetorno": "expectativa de retorno",
    "score": "score",
}


def _ler(arquivo: str) -> str:
    caminho = PASTA / arquivo
    if not caminho.is_file():
        raise FileNotFoundError(f"prompt ausente: {caminho}")
    return caminho.read_text(encoding="utf-8")


def persona() -> str:
    return _ler("persona.md")


def _perfil(perfil: PerfilLead) -> str:
    conhecido = {
        chave: valor
        for chave, valor in perfil.model_dump(by_alias=True).items()
        if valor is not None
    }

    if not conhecido:
        return "## Perfil do lead\n\nNada ainda. Este e o primeiro contato."

    linhas = "\n".join(
        f"- {ROTULOS.get(chave, chave)}: {valor}" for chave, valor in conhecido.items()
    )

    return f"## Perfil do lead\n\n{linhas}"


def _historico(historico: list[MensagemHistorico]) -> str:
    if not historico:
        return "## Conversa ate agora\n\nEsta e a primeira mensagem da conversa."

    linhas = "\n".join(
        f"{'Lead' if mensagem.papel == 'lead' else 'Lia'}: {mensagem.texto}"
        for mensagem in historico
    )

    return f"## Conversa ate agora\n\n{linhas}"


TITULO = "## O que ainda falta descobrir"

COMPLETO = "Nada — o perfil esta completo."

ABERTAS = (
    "Em ordem de importancia: {perguntas}.\n\n"
    "Se voce for perguntar alguma coisa neste turno, pergunte a primeira que "
    "ainda fizer sentido depois da mensagem dela. A regra de `proximaAcao` "
    "decide se ha proxima pergunta; esta lista so decide qual seria."
)

PISO_ABERTO = (
    "\n\nAntes desta mensagem, faltava essencial para um corretor assumir: "
    "{essenciais}. Esta lista foi montada sem a mensagem de agora — se ela fechar "
    "o que faltava, o essencial esta fechado."
)

DESFECHO_SATISFEITO = (
    "\n\nEste perfil ja satisfaz a regra de `{desfecho}`, e nenhum item da lista "
    "acima segura esse desfecho."
)


def _lacunas(lacunas: tuple[Sinal, ...], desfecho: str | None) -> str:
    if not lacunas:
        return f"{TITULO}\n\n{COMPLETO}"

    bloco = ABERTAS.format(perguntas="; ".join(sinal.pergunta for sinal in lacunas))
    essenciais = [sinal.rotulo for sinal in lacunas if sinal.essencial]

    if essenciais:
        bloco += PISO_ABERTO.format(essenciais=", ".join(essenciais))
    elif desfecho is not None:
        bloco += DESFECHO_SATISFEITO.format(desfecho=desfecho)

    return f"{TITULO}\n\n{bloco}"


def turno(
    perfil: PerfilLead,
    historico: list[MensagemHistorico],
    mensagem: str,
    lacunas: tuple[Sinal, ...] = (),
    desfecho: str | None = None,
) -> str:
    return (
        _ler("turno.md")
        .replace("{perfil}", _perfil(perfil))
        .replace("{historico}", _historico(historico))
        .replace("{mensagem}", mensagem)
        .replace("{lacunas}", _lacunas(lacunas, desfecho))
    )
