"""Carga dos prompts da Lia a partir de prompts/."""

from datetime import timedelta, timezone
from pathlib import Path

from app.contrato import MensagemHistorico, PerfilLead, SlotOferecido
from app.lia.indice import Filtro, Resultado
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


TITULO_AGENDA = "## Agenda do corretor"

SEM_HORARIOS = (
    "Nenhum horario livre foi recebido. Se a pessoa pedir para agendar, nao "
    "invente data: diga que a confirmacao vira pelo contato informado."
)


def _agenda(slots: list[SlotOferecido]) -> str:
    if not slots:
        return f"{TITULO_AGENDA}\n\n{SEM_HORARIOS}"

    local = timezone(timedelta(hours=-3))
    linhas = []

    for slot in slots[:3]:
        inicio = slot.inicio.astimezone(local)
        fim = slot.fim.astimezone(local)
        linhas.append(
            f"- id `{slot.id}` — {inicio:%d/%m/%Y}, das {inicio:%H:%M} "
            f"as {fim:%H:%M} (horario de Sao Paulo)"
        )

    return (
        f"{TITULO_AGENDA}\n\nEstes sao os unicos horarios que podem ser "
        "oferecidos agora:\n\n" + "\n".join(linhas)
    )


def turno(
    perfil: PerfilLead,
    historico: list[MensagemHistorico],
    mensagem: str,
    lacunas: tuple[Sinal, ...] = (),
    desfecho: str | None = None,
    agenda: list[SlotOferecido] | None = None,
) -> str:
    return (
        _ler("turno.md")
        .replace("{perfil}", _perfil(perfil))
        .replace("{historico}", _historico(historico))
        .replace("{mensagem}", mensagem)
        .replace("{lacunas}", _lacunas(lacunas, desfecho))
        .replace("{agenda}", _agenda(agenda or []))
    )


TITULO_IMOVEIS = "## Imoveis que a busca devolveu"

ACHADOS = (
    "Em ordem de aderencia ao que ela pediu. **Existem estes e mais nenhum** — o "
    "que nao esta nesta lista nao esta na base.\n\n{fichas}"
)

VAZIO = (
    "Nenhum. A busca nao devolveu imovel algum com estes criterios: {criterios}.\n\n"
    "Isto e um fato da base, e um fato para dizer. Nao existe imovel parecido "
    "guardado em outro lugar."
)

SEM_CRITERIO = "nenhum criterio estruturado, so o texto da conversa"


def _reais(valor: int) -> str:
    return f"R$ {valor:,}".replace(",", ".")


def _precos(resultado: Resultado) -> str:
    imovel = resultado.imovel
    valores = []

    if imovel.preco_venda is not None:
        valores.append(f"venda {_reais(imovel.preco_venda)}")

    if imovel.preco_aluguel is not None:
        valores.append(f"aluguel {_reais(imovel.preco_aluguel)} por mes")

    if imovel.condominio is not None:
        valores.append(f"condominio {_reais(imovel.condominio)}")

    return ", ".join(valores)


def _contar(quantidade: int, singular: str, plural: str) -> str:
    return f"{quantidade} {singular if quantidade == 1 else plural}"


def _ficha(resultado: Resultado) -> str:
    imovel = resultado.imovel
    quartos = _contar(imovel.quartos, "quarto", "quartos")
    banheiros = _contar(imovel.banheiros, "banheiro", "banheiros")
    vagas = _contar(imovel.vagas, "vaga", "vagas")

    return (
        f"- **{imovel.id}** — {imovel.tipo} no {imovel.bairro}, zona {imovel.zona}. "
        f"{quartos}, {banheiros}, {vagas}, {imovel.metragem} m2. "
        f"{_precos(resultado)}.\n  {imovel.descricao}"
    )


def _criterios(filtro: Filtro) -> str:
    partes = []

    if filtro.tipo is not None:
        partes.append(filtro.tipo)

    if filtro.quartos is not None:
        partes.append(f"a partir de {filtro.quartos} quartos")

    if filtro.regiao:
        partes.append(f"regiao {filtro.regiao}")

    if filtro.preco_min is not None:
        partes.append(f"a partir de {_reais(filtro.preco_min)}")

    if filtro.preco_max is not None:
        partes.append(f"ate {_reais(filtro.preco_max)}")

    if filtro.intencao is not None and filtro.intencao != "indefinida":
        partes.append(f"para {filtro.intencao}")

    return ", ".join(partes) or SEM_CRITERIO


def _imoveis(resultados: list[Resultado], filtro: Filtro) -> str:
    if not resultados:
        return f"{TITULO_IMOVEIS}\n\n{VAZIO.format(criterios=_criterios(filtro))}"

    fichas = "\n".join(_ficha(resultado) for resultado in resultados)

    return f"{TITULO_IMOVEIS}\n\n{ACHADOS.format(fichas=fichas)}"


def apresentacao(
    perfil: PerfilLead,
    historico: list[MensagemHistorico],
    mensagem: str,
    resultados: list[Resultado],
    filtro: Filtro,
) -> str:
    return (
        _ler("apresentacao.md")
        .replace("{perfil}", _perfil(perfil))
        .replace("{historico}", _historico(historico))
        .replace("{mensagem}", mensagem)
        .replace("{imoveis}", _imoveis(resultados, filtro))
    )
