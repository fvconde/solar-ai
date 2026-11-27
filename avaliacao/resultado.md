# Avaliacao da Lia

Rodada de 2026-11-27 05:46 UTC com `python scripts/avaliar.py`.

**Extracao** (modelo `gemini-3.5-flash-lite`)

| Metrica | Valor |
| --- | --- |
| Casos certos | 25 de 27 (93%) |
| Latencia media do turno | 808 ms |
| Latencia p95 do turno | 920 ms |

Casos errados:

- `intencao-investimento-disfarcada-de-compra`: intencao: esperava 'investimento', veio 'indefinida'
- `expectativa-de-retorno-verbatim`: intencao: esperava 'investimento', veio 'indefinida'; o score nao veio da regua

**Busca (RAG)** (embedding `gemini-embedding-001`, acervo de 80 imoveis, 21 consultas rotuladas)

| Metrica | Valor |
| --- | --- |
| Acerto@5 (algum imovel certo no top 5) | 100% |
| Recall@5 (fracao dos certos no top 5) | 0.95 |
| MRR (posicao do primeiro certo) | 0.92 |

Todas as consultas trouxeram um imovel certo no top 5.
