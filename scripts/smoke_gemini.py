"""
Smoke test da Gemini API — card S-00 do Solar.

Objetivo: provar com uma chamada real que a chave funciona, descobrir quais
modelos o free tier libera e medir latencia. Sem dependencias externas:
usa so a biblioteca padrao, para rodar em qualquer maquina.

Le o .env da raiz do repo automaticamente. Variaveis de ambiente ja
definidas tem precedencia sobre o .env.

Se GEMINI_MODEL estiver preenchido, o script usa exatamente esse modelo e
nao escolhe nada sozinho -- e isso que se quer a partir do S-00, porque
alias como 'gemini-flash-lite-latest' e ponteiro movel: o Google troca o
modelo por tras dele sem aviso, e o comportamento dos prompts da Lia muda
sem que uma linha de codigo tenha mudado.

Uso:
    python scripts/smoke_gemini.py              # le o .env
    python scripts/smoke_gemini.py --sugerir    # ignora GEMINI_MODEL e sugere um

Codigos de saida: 0 ok | 1 falha | 2 chave ausente | 3 modelo fixado invalido
"""

import json
import os
import sys
import time
import urllib.error
import urllib.request

BASE = "https://generativelanguage.googleapis.com/v1beta"

# Ordem de preferencia: o mais barato que atende. Flash-Lite primeiro porque
# o Solar faz muitas chamadas curtas de roteamento/qualificacao.
PREFERENCIA = ("flash-lite", "flash")

PROMPT = (
    "Voce e a Lia, agente de atendimento de uma imobiliaria. "
    "Responda em uma frase, em portugues do Brasil: "
    "um lead disse 'procuro apartamento de 2 quartos ate 500 mil na zona sul'. "
    "Qual a proxima pergunta que voce faria para qualificar?"
)


def _carregar_env():
    """Le o .env da raiz do repo. Nao sobrescreve variaveis ja definidas."""
    caminho = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), ".env")
    if not os.path.isfile(caminho):
        return False
    with open(caminho, encoding="utf-8") as f:
        for linha in f:
            linha = linha.strip()
            if not linha or linha.startswith("#") or "=" not in linha:
                continue
            nome, _, valor = linha.partition("=")
            nome = nome.strip()
            valor = valor.strip().strip('"').strip("'")
            if nome and valor and not os.environ.get(nome):
                os.environ[nome] = valor
    return True


def _get(url, chave):
    req = urllib.request.Request(url, headers={"x-goog-api-key": chave})
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.loads(r.read().decode("utf-8"))


def _post(url, chave, corpo):
    req = urllib.request.Request(
        url,
        data=json.dumps(corpo).encode("utf-8"),
        headers={"x-goog-api-key": chave, "Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=60) as r:
        return json.loads(r.read().decode("utf-8"))


def _erro(e):
    if isinstance(e, urllib.error.HTTPError):
        try:
            detalhe = json.loads(e.read().decode("utf-8"))
            msg = detalhe.get("error", {}).get("message", "")
            status = detalhe.get("error", {}).get("status", "")
            return f"HTTP {e.code} {status} - {msg}"
        except Exception:
            return f"HTTP {e.code}"
    return f"{type(e).__name__}: {e}"


def main():
    sugerir = "--sugerir" in sys.argv
    if _carregar_env():
        print("Config lida de .env")
    chave = os.environ.get("GEMINI_API_KEY", "").strip()
    if not chave:
        print("ERRO: variavel de ambiente GEMINI_API_KEY nao definida.")
        return 2
    print(f"Chave carregada: {chave[:6]}...{chave[-4:]} ({len(chave)} chars)\n")

    # 1. Descoberta: quais modelos esta chave enxerga.
    print("[1/2] Listando modelos disponiveis para esta chave...")
    try:
        dados = _get(f"{BASE}/models?pageSize=200", chave)
    except Exception as e:
        print(f"  FALHOU: {_erro(e)}")
        return 1

    gerativos = [
        m for m in dados.get("models", [])
        if "generateContent" in m.get("supportedGenerationMethods", [])
    ]
    nomes = sorted(m["name"].removeprefix("models/") for m in gerativos)
    print(f"  {len(nomes)} modelos com generateContent:")
    for n in nomes:
        print(f"    - {n}")

    fixado = "" if sugerir else os.environ.get("GEMINI_MODEL", "").strip()
    if fixado:
        if fixado not in nomes:
            print(f"\n  FALHOU: GEMINI_MODEL='{fixado}' nao aparece entre os modelos")
            print("  visiveis para esta chave. Corrija o .env ou rode com --sugerir.")
            return 3
        escolhido = fixado
        print(f"\n  Modelo fixado no .env: {escolhido}")
        return _chamada_real(escolhido, chave, len(nomes), fixado=True)

    escolhido = None
    for termo in PREFERENCIA:
        candidatos = [n for n in nomes if termo in n and "preview" not in n]
        if not candidatos:
            candidatos = [n for n in nomes if termo in n]
        if candidatos:
            escolhido = sorted(candidatos)[-1]
            break
    if not escolhido and nomes:
        escolhido = nomes[0]
    if not escolhido:
        print("  FALHOU: nenhum modelo generativo disponivel.")
        return 1
    print(f"\n  GEMINI_MODEL vazio -- sugestao automatica: {escolhido}")
    print("  Fixe um modelo no .env antes de comecar o S-06. Alias muda sozinho.")
    return _chamada_real(escolhido, chave, len(nomes), fixado=False)


def _chamada_real(escolhido, chave, total_modelos, fixado):
    # 2. Chamada real.
    print(f"\n[2/2] Chamada real em '{escolhido}'...")
    corpo = {
        "contents": [{"parts": [{"text": PROMPT}]}],
        "generationConfig": {"temperature": 0.4, "maxOutputTokens": 200},
    }
    inicio = time.perf_counter()
    try:
        resp = _post(f"{BASE}/models/{escolhido}:generateContent", chave, corpo)
    except Exception as e:
        print(f"  FALHOU: {_erro(e)}")
        return 1
    ms = (time.perf_counter() - inicio) * 1000

    try:
        texto = resp["candidates"][0]["content"]["parts"][0]["text"].strip()
    except (KeyError, IndexError):
        print(f"  Resposta em formato inesperado:\n{json.dumps(resp, indent=2)[:1500]}")
        return 1

    uso = resp.get("usageMetadata", {})
    print(f"  Latencia: {ms:.0f} ms")
    print(
        "  Tokens: "
        f"prompt={uso.get('promptTokenCount', '?')} "
        f"saida={uso.get('candidatesTokenCount', '?')} "
        f"total={uso.get('totalTokenCount', '?')}"
    )
    print(f"  Resposta da Lia: {texto}")

    print("\nOK - chave valida e chamada real bem-sucedida.")
    origem = "fixado no .env" if fixado else "SUGERIDO, ainda nao fixado"
    print(f"Anotar no ESTADO.md: modelo '{escolhido}' ({origem}), "
          f"{ms:.0f} ms, {total_modelos} modelos visiveis.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
