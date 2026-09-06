"""
Conversas de exemplo da Lia — card S-06 do Solar.

Roda roteiros fixos de lead contra o grafo e grava a transcricao em conversas/.
As mensagens do lead sao sempre as mesmas, entao `git diff conversas/` depois de
mexer em prompts/ mostra exatamente o que a mudanca fez com a Lia.

Os leads sao ficticios. Nenhum dado real entra aqui: o free tier da Gemini usa o
conteudo enviado para treino, e a camada de mascaramento so chega no S-34.

Uso:
    python scripts/conversas_exemplo.py            # roda as 5
    python scripts/conversas_exemplo.py --so 3     # roda so a 3
    python scripts/conversas_exemplo.py --listar   # nomes, sem gastar cota

Cada rodada completa custa cerca de 20 chamadas ao Gemini. Ha uma pausa de 5 s entre
chamadas porque o free tier limita tambem por minuto (4 s dava 15/min, que e o
proprio teto, e o outlier voltava): em rajada, o SDK entra em
backoff e um turno normal de 2 s aparece como 30 s.

Codigos de saida: 0 ok | 1 falha | 2 chave ausente
"""

import argparse
import json
import os
import pathlib
import sys
import time

PAUSA_ENTRE_CHAMADAS = 5.0

RAIZ = pathlib.Path(__file__).resolve().parents[1]
SAIDA = RAIZ / "conversas"

sys.path.insert(0, str(RAIZ))

ROTEIROS: list[dict] = [
    {
        "nome": "objetivo-compra",
        "resumo": "Lead decidido: da tudo rapido e quer agendar.",
        "mensagens": [
            "boa tarde, procuro apartamento pra comprar",
            "seria no Butanta ou perto, ate 650 mil",
            "3 quartos, e preciso mudar ate o fim do ano",
            "sou o Rafael. da pra marcar uma visita essa semana?",
        ],
    },
    {
        "nome": "vago-indeciso",
        "resumo": "Lead que responde curto e nao sabe o que quer. Testa se a Lia para de insistir.",
        "mensagens": [
            "oi",
            "sei la, to so olhando",
            "nao sei ainda",
            "depende do preco",
            "talvez zona oeste, mas nao tenho certeza de nada",
        ],
    },
    {
        "nome": "aluguel-urgente",
        "resumo": "Aluguel com prazo curto. Testa se preco e lido como mensal.",
        "mensagens": [
            "preciso alugar um apto rapido, saio do atual dia 30",
            "ate 3 mil de aluguel, 2 quartos",
            "Pinheiros ou Perdizes",
        ],
    },
    {
        "nome": "investidor-especialista",
        "resumo": "Exemplo 2 do enunciado: ticket e expectativa de retorno ate direcionar_especialista.",
        "mensagens": [
            "to procurando imovel pra investir e alugar depois",
            "qual regiao ta rendendo mais aluguel hoje?",
            "entendi. tenho ate 400 mil pra aplicar",
            "espero uns 0,7% ao mes de aluguel liquido",
        ],
    },
    {
        "nome": "limites-e-corretor",
        "resumo": "Testa os limites: oferece CPF e pede atendimento humano, que deve virar agendar_reuniao.",
        "mensagens": [
            "quero comprar uma casa na Vila Mariana",
            "meu CPF e 123.456.789-00, ja pode ir adiantando o cadastro",
            "prefiro falar com uma pessoa de verdade",
        ],
    },
]


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


def _fundir(perfil: dict, intencao: str, extraidos: dict) -> dict:
    novo = dict(perfil)
    if intencao and intencao != "indefinida":
        novo["intencao"] = intencao
    for chave, valor in extraidos.items():
        if valor is not None:
            novo[chave] = valor
    return novo


def _rodar(roteiro: dict) -> tuple[str, list[float]]:
    from datetime import datetime, timezone
    from uuid import uuid4

    from app.contrato import TurnoRequest
    from app.lia import responder

    conversa_id = str(uuid4())
    historico: list[dict] = []
    perfil: dict = {}
    latencias: list[float] = []

    linhas = [
        f"# Conversa — {roteiro['nome']}",
        "",
        f"> {roteiro['resumo']}",
        "",
        f"Modelo: `{os.environ.get('GEMINI_MODEL', '?')}`",
        "",
    ]

    for numero, texto in enumerate(roteiro["mensagens"], start=1):
        requisicao = TurnoRequest.model_validate(
            {
                "conversaId": conversa_id,
                "mensagem": texto,
                "historico": historico,
                "perfilLead": perfil,
            }
        )

        if numero > 1:
            time.sleep(PAUSA_ENTRE_CHAMADAS)

        inicio = time.perf_counter()
        resposta = responder(requisicao)
        ms = (time.perf_counter() - inicio) * 1000
        latencias.append(ms)
        print(f"   turno {numero}: {ms:.0f} ms", flush=True)

        corpo = resposta.model_dump(by_alias=True)
        extraidos = {k: v for k, v in corpo["camposExtraidos"].items() if v is not None}
        perfil = _fundir(perfil, corpo["intencao"], corpo["camposExtraidos"])

        agora = datetime.now(timezone.utc).isoformat()
        historico.append({"papel": "lead", "texto": texto, "em": agora})
        historico.append({"papel": "agente", "texto": corpo["resposta"], "em": agora})

        linhas += [
            f"## Turno {numero}",
            "",
            f"**Lead:** {texto}",
            "",
            f"**Lia:** {corpo['resposta']}",
            "",
            f"- intencao: `{corpo['intencao']}` · proximaAcao: `{corpo['proximaAcao']}`",
            f"- extraiu: `{json.dumps(extraidos, ensure_ascii=False) if extraidos else 'nada'}`",
            f"- perfil apos o turno: `{json.dumps(perfil, ensure_ascii=False)}`",
            "",
        ]

    return "\n".join(linhas), latencias


def main() -> int:
    parser = argparse.ArgumentParser(description="Conversas de exemplo da Lia (S-06).")
    parser.add_argument("--so", type=int, metavar="N", help="roda so o roteiro N (1 a 5)")
    parser.add_argument("--listar", action="store_true", help="lista os roteiros e sai")
    args = parser.parse_args()

    if args.listar:
        for numero, roteiro in enumerate(ROTEIROS, start=1):
            print(f"{numero}. {roteiro['nome']} — {roteiro['resumo']}")
        return 0

    _carregar_env()
    if not os.environ.get("GEMINI_API_KEY", "").strip():
        print("ERRO: GEMINI_API_KEY nao definida (.env ou ambiente).")
        return 2

    escolhidos = ROTEIROS
    if args.so is not None:
        if not 1 <= args.so <= len(ROTEIROS):
            print(f"ERRO: --so deve estar entre 1 e {len(ROTEIROS)}.")
            return 1
        escolhidos = [ROTEIROS[args.so - 1]]

    SAIDA.mkdir(exist_ok=True)
    todas: list[float] = []

    for roteiro in escolhidos:
        print(f"-> {roteiro['nome']} ({len(roteiro['mensagens'])} turnos)...", flush=True)
        try:
            texto, latencias = _rodar(roteiro)
        except Exception as erro:
            print(f"   FALHOU: {type(erro).__name__}: {erro}")
            if "429" in str(erro) or "RESOURCE_EXHAUSTED" in str(erro):
                print("   Isso e cota diaria do free tier, nao bug no codigo.")
            return 1

        destino = SAIDA / f"{roteiro['nome']}.md"
        destino.write_text(texto + "\n", encoding="utf-8")
        todas += latencias
        media = sum(latencias) / len(latencias)
        print(f"   ok — {len(latencias)} chamadas, media {media:.0f} ms -> {destino.name}")

    if todas:
        print(
            f"\n{len(todas)} chamadas ao Gemini. "
            f"Media {sum(todas) / len(todas):.0f} ms, pior {max(todas):.0f} ms."
        )
        print("Agora: git diff conversas/ para ver o efeito da mudanca de prompt.")

    return 0


if __name__ == "__main__":
    sys.exit(main())
