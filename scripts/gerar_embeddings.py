"""
Gerador do cache de embeddings dos imoveis — card S-14 do Solar.

Le data/imoveis.json, chama a API de embedding uma vez por imovel e grava os
vetores em data/embeddings.json. O boot do agente le esse arquivo: se o modelo,
a dimensao e o sha256 do corpus conferem, sobe sem rede e sem cota.

Rode este script sempre que mudar data/imoveis.json ou o texto que vai para o
embedding (Imovel.texto). Sem isso o cache e recusado e o boot volta a gastar
cota — o log do agente diz o motivo da recusa.

Custo: 1 unidade de cota por imovel, e a cota de embedding do free tier e de
100 por minuto por modelo e por projeto (metrica EmbedContentRequestsPerMinute,
que conta conteudo, nao requisicao HTTP). Com 80 imoveis, duas geracoes no
mesmo minuto dao 429.

Uso:
    python scripts/gerar_embeddings.py             # gera se a base mudou
    python scripts/gerar_embeddings.py --forcar    # gera de novo de qualquer jeito
    python scripts/gerar_embeddings.py --conferir  # so diz se o cache confere, sem gastar cota

Codigos de saida: 0 ok | 1 falha | 2 chave ou modelo ausente | 3 cache desatualizado (--conferir)
"""

import argparse
import os
import pathlib
import sys
import time

RAIZ = pathlib.Path(__file__).resolve().parents[1]

sys.path.insert(0, str(RAIZ))

from dotenv import load_dotenv  # noqa: E402

load_dotenv(RAIZ / ".env")

from app.lia import indice as ix  # noqa: E402


def _argumentos() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Gera o cache de embeddings dos imoveis.")
    parser.add_argument("--forcar", action="store_true", help="regera mesmo com cache valido")
    parser.add_argument("--conferir", action="store_true", help="so confere, sem chamar a API")

    return parser.parse_args()


def main() -> int:
    argumentos = _argumentos()

    try:
        imoveis = ix.carregar()
    except ix.IndiceIndisponivelError as erro:
        print(f"falha: {erro}", file=sys.stderr)
        return 1

    modelo = os.getenv("GEMINI_EMBEDDING_MODEL", "").strip()

    if not modelo:
        print("falha: GEMINI_EMBEDDING_MODEL ausente no ambiente", file=sys.stderr)
        return 2

    print(f"base: {len(imoveis)} imoveis, corpus {ix.impressao(imoveis)[:12]}")

    valido = ix.ler_cache(imoveis, modelo) is not None

    if argumentos.conferir:
        print(f"cache: {'confere' if valido else 'DESATUALIZADO'} em {ix.CACHE}")
        return 0 if valido else 3

    if valido and not argumentos.forcar:
        print(f"cache ja confere em {ix.CACHE}; nada a fazer (use --forcar para regerar)")
        return 0

    if not os.getenv("GEMINI_API_KEY", "").strip():
        print("falha: GEMINI_API_KEY ausente no ambiente", file=sys.stderr)
        return 2

    print(f"gerando {len(imoveis)} embeddings com {modelo}...")
    inicio = time.monotonic()

    try:
        indice = ix.construir(cache=False)
        destino = ix.escrever_cache(imoveis, indice.vetores, modelo)
    except ix.IndiceIndisponivelError as erro:
        print(f"falha: {erro}", file=sys.stderr)
        return 1

    tamanho = destino.stat().st_size / 1024

    print(
        f"gravado {destino} — {len(imoveis)} vetores de {indice.dimensao} dimensoes, "
        f"{tamanho:.0f} KB, {time.monotonic() - inicio:.1f}s"
    )

    return 0


if __name__ == "__main__":
    sys.exit(main())
