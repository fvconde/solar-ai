"""
Avaliacao da Lia em numeros: extracao de campos e busca de imoveis.

Os testes `pytest -m llm` dizem passou ou falhou e param no primeiro erro. Este
script roda os mesmos casos ate o fim e resume em taxa de acerto, para a pergunta
"quanto o agente acerta?" ter resposta com numero.

Duas partes:

- extracao: os casos de tests/test_extracao.py, um turno cada contra o Gemini,
  julgados pela mesma funcao `falhas` do teste. Mede a taxa de acerto e a
  latencia de cada turno.
- busca: CONSULTAS_BUSCA, frases de lead em texto livre, cada uma com os imoveis
  que um corretor aceitaria como resposta (rotulados lendo data/imoveis.json).
  Mede acerto@5, recall@5 e MRR do indice vetorial, sem filtro de perfil: o que
  se avalia aqui e so a similaridade dos embeddings.

O resultado vai para o terminal e para avaliacao/resultado.md, que entra no git
para o README poder citar os numeros da ultima rodada.

Uso:
    python scripts/avaliar.py                  # as duas partes
    python scripts/avaliar.py --so busca       # so a busca (1 embedding por consulta)
    python scripts/avaliar.py --so extracao    # so a extracao (1 chamada por caso)

Custo: ~27 chamadas de geracao (pausa de 5 s entre elas, pelo limite por minuto
do free tier) e ~21 embeddings de consulta. O indice do acervo vem do cache.

Codigos de saida: 0 ok | 1 falha de execucao | 2 chave ausente
"""

import argparse
import math
import os
import pathlib
import sys
import time
from dataclasses import dataclass
from datetime import datetime, timezone

RAIZ = pathlib.Path(__file__).resolve().parents[1]
SAIDA = RAIZ / "avaliacao" / "resultado.md"
PAUSA_ENTRE_CHAMADAS = 5.0
PAUSA_ENTRE_EMBEDDINGS = 0.7
K = 5

sys.path.insert(0, str(RAIZ))


@dataclass(frozen=True)
class ConsultaBusca:
    texto: str
    relevantes: frozenset[str]


def _consulta(texto: str, *relevantes: str) -> ConsultaBusca:
    return ConsultaBusca(texto, frozenset(relevantes))


# Cada consulta descreve o que o lead quer com palavras dele, nao com as do
# anuncio. `relevantes` sao todos os imoveis do acervo que atendem o pedido; se
# um imovel novo entrar em data/imoveis.json, revise esta lista.
CONSULTAS_BUSCA = [
    _consulta("cobertura com piscina olhando para o Parque Villa-Lobos", "IMV-024"),
    _consulta("studio sem garagem perto da Faria Lima, eu ando de bicicleta", "IMV-025"),
    _consulta("casa com edicula que da pra alugar e ter uma renda extra", "IMV-057", "IMV-005"),
    _consulta("quero morar perto da PUC", "IMV-023"),
    _consulta("da janela quero ver a Serra da Cantareira", "IMV-061", "IMV-062"),
    _consulta("apartamento mobiliado para entrar so com a mala", "IMV-007", "IMV-077"),
    _consulta(
        "imovel abaixo do preco que precisa de reforma, eu assumo a obra",
        "IMV-015",
        "IMV-047",
    ),
    _consulta("condominio-clube com brinquedoteca para as criancas", "IMV-010", "IMV-028"),
    _consulta("algo perto do Sesc Pompeia", "IMV-026"),
    _consulta("apartamento terreo com quintal para o meu cachorro", "IMV-032"),
    _consulta("predio modernista antigo com o hall original preservado", "IMV-039"),
    _consulta(
        "trabalho na Avenida Paulista e quero ir a pe",
        "IMV-042",
        "IMV-043",
        "IMV-048",
        "IMV-050",
    ),
    _consulta("perto das torres comerciais da Berrini", "IMV-004"),
    _consulta("studio com rooftop e piscina com vista para o skyline", "IMV-012"),
    _consulta("casa em condominio fechado com piscina e seguranca 24 horas", "IMV-019"),
    _consulta("cobertura com ofuro", "IMV-033", "IMV-073"),
    _consulta(
        "perto do terminal da Barra Funda, com metro, trem e rodoviaria juntos", "IMV-038"
    ),
    _consulta("sala com lareira num bairro residencial e tranquilo", "IMV-020"),
    _consulta("studio novo, ainda na garantia da construtora", "IMV-071"),
    _consulta("vista para as arvores do Ibirapuera", "IMV-002"),
    _consulta("investir perto do Shopping Center Norte para alugar", "IMV-054", "IMV-058"),
]


def acerto_em_k(ordenados: list[str], relevantes: frozenset[str], k: int = K) -> float:
    """1 se algum relevante aparece entre os k primeiros, 0 se nenhum."""
    return 1.0 if relevantes & set(ordenados[:k]) else 0.0


def recall_em_k(ordenados: list[str], relevantes: frozenset[str], k: int = K) -> float:
    """Fracao dos relevantes que aparece entre os k primeiros."""
    if not relevantes:
        raise ValueError("consulta sem imovel relevante")

    return len(relevantes & set(ordenados[:k])) / len(relevantes)


def reciproco_da_posicao(ordenados: list[str], relevantes: frozenset[str]) -> float:
    """1/posicao do primeiro relevante (1 no topo, 0 se nao aparece). A media e o MRR."""
    for posicao, imovel in enumerate(ordenados, start=1):
        if imovel in relevantes:
            return 1 / posicao

    return 0.0


def percentil(valores: list[float], fracao: float) -> float:
    """Percentil por posicao mais proxima, sem numpy."""
    if not valores:
        raise ValueError("lista vazia")

    ordenados = sorted(valores)
    posicao = max(0, min(len(ordenados) - 1, math.ceil(fracao * len(ordenados)) - 1))

    return ordenados[posicao]


def _carregar_env() -> None:
    caminho = RAIZ / ".env"
    if not caminho.is_file():
        return
    for linha in caminho.read_text(encoding="utf-8").splitlines():
        linha = linha.strip()
        if not linha or linha.startswith("#") or "=" not in linha:
            continue
        nome, _, valor = linha.partition("=")
        nome = nome.strip()
        valor = valor.strip().strip('"').strip("'")
        if nome and valor and not os.environ.get(nome):
            os.environ[nome] = valor


def _avaliar_extracao() -> list[str]:
    from app.lia import responder
    from tests.test_extracao import CASOS, falhas

    acertos = 0
    latencias: list[float] = []
    erros: list[str] = []

    for numero, caso in enumerate(CASOS, start=1):
        if numero > 1:
            time.sleep(PAUSA_ENTRE_CHAMADAS)

        inicio = time.perf_counter()
        resposta = responder(caso.requisicao())
        latencias.append((time.perf_counter() - inicio) * 1000)

        problemas = falhas(caso, resposta)
        if problemas:
            erros.append(f"- `{caso.nome}`: {'; '.join(problemas)}")
        else:
            acertos += 1

        marca = "ok" if not problemas else "ERROU"
        print(f"   {numero:2}/{len(CASOS)} {marca:5} {caso.nome}", flush=True)

    taxa = acertos / len(CASOS)
    linhas = [
        "## Extracao de campos e intencao",
        "",
        f"Modelo: `{os.environ.get('GEMINI_MODEL', '?')}`",
        "",
        "| Metrica | Valor |",
        "| --- | --- |",
        f"| Casos certos | {acertos} de {len(CASOS)} ({taxa:.0%}) |",
        f"| Latencia media do turno | {sum(latencias) / len(latencias):.0f} ms |",
        f"| Latencia p95 do turno | {percentil(latencias, 0.95):.0f} ms |",
        "",
    ]
    linhas += ["Casos errados:", "", *erros, ""] if erros else ["Nenhum caso errado.", ""]

    print(f"   -> {acertos}/{len(CASOS)} certos ({taxa:.0%})")
    return linhas


def _avaliar_busca() -> list[str]:
    from app.lia import indice as indice_imoveis

    indice = indice_imoveis.construir()
    acervo = {imovel.id for imovel in indice.imoveis}
    desconhecidos = {i for c in CONSULTAS_BUSCA for i in c.relevantes} - acervo
    if desconhecidos:
        raise RuntimeError(f"ids fora do acervo: {sorted(desconhecidos)}")

    acertos: list[float] = []
    recalls: list[float] = []
    reciprocos: list[float] = []
    erros: list[str] = []

    for numero, consulta in enumerate(CONSULTAS_BUSCA, start=1):
        if numero > 1:
            time.sleep(PAUSA_ENTRE_EMBEDDINGS)

        # A base inteira ordenada, para o MRR enxergar alem do top-k.
        ordenados = [r.imovel.id for r in indice.buscar(consulta.texto, k=len(acervo))]

        acertos.append(acerto_em_k(ordenados, consulta.relevantes))
        recalls.append(recall_em_k(ordenados, consulta.relevantes))
        reciprocos.append(reciproco_da_posicao(ordenados, consulta.relevantes))

        if not acertos[-1]:
            erros.append(
                f"- \"{consulta.texto}\": esperava {', '.join(sorted(consulta.relevantes))}, "
                f"top {K} trouxe {', '.join(ordenados[:K])}"
            )

        marca = "ok" if acertos[-1] else "ERROU"
        print(f"   {numero:2}/{len(CONSULTAS_BUSCA)} {marca:5} {consulta.texto}", flush=True)

    total = len(CONSULTAS_BUSCA)
    linhas = [
        "## Busca de imoveis (RAG)",
        "",
        f"Embedding: `{indice.modelo}` · acervo de {len(acervo)} imoveis · "
        f"{total} consultas rotuladas",
        "",
        "| Metrica | Valor |",
        "| --- | --- |",
        f"| Acerto@{K} (algum imovel certo no top {K}) | {sum(acertos) / total:.0%} |",
        f"| Recall@{K} (fracao dos certos no top {K}) | {sum(recalls) / total:.2f} |",
        f"| MRR (posicao do primeiro certo) | {sum(reciprocos) / total:.2f} |",
        "",
    ]
    linhas += (
        [f"Consultas sem nenhum certo no top {K}:", "", *erros, ""]
        if erros
        else [f"Todas as consultas trouxeram um imovel certo no top {K}.", ""]
    )

    print(f"   -> acerto@{K} {sum(acertos) / total:.0%}, MRR {sum(reciprocos) / total:.2f}")
    return linhas


def main() -> int:
    parser = argparse.ArgumentParser(description="Avaliacao da Lia em numeros.")
    parser.add_argument("--so", choices=("busca", "extracao"), help="roda so uma parte")
    args = parser.parse_args()

    _carregar_env()
    if not os.environ.get("GEMINI_API_KEY", "").strip():
        print("ERRO: GEMINI_API_KEY nao definida (.env ou ambiente).")
        return 2

    agora = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    linhas = ["# Avaliacao da Lia", "", f"Rodada de {agora} com `python scripts/avaliar.py`.", ""]

    partes = [("extracao", _avaliar_extracao), ("busca", _avaliar_busca)]
    for nome, avaliar in partes:
        if args.so and args.so != nome:
            continue
        print(f"-> {nome}...", flush=True)
        try:
            linhas += avaliar()
        except Exception as erro:
            print(f"   FALHOU: {type(erro).__name__}: {erro}")
            if "429" in str(erro) or "RESOURCE_EXHAUSTED" in str(erro):
                print("   Isso e cota do free tier, nao bug no codigo. Tente mais tarde.")
            return 1

    SAIDA.parent.mkdir(exist_ok=True)
    SAIDA.write_text("\n".join(linhas), encoding="utf-8")
    print(f"\nResultado em {SAIDA.relative_to(RAIZ)}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
