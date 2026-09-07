"""Carga dos prompts da Lia a partir de prompts/."""

from pathlib import Path

from app.contrato import MensagemHistorico, PerfilLead

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


def turno(perfil: PerfilLead, historico: list[MensagemHistorico], mensagem: str) -> str:
    return (
        _ler("turno.md")
        .replace("{perfil}", _perfil(perfil))
        .replace("{historico}", _historico(historico))
        .replace("{mensagem}", mensagem)
    )
