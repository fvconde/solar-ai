# Conversa — aluguel-urgente

> Aluguel com prazo curto. Testa se preco e lido como mensal.

Modelo: `gemini-3.5-flash-lite`

## Turno 1

**Lead:** preciso alugar um apto rapido, saio do atual dia 30

**Lia:** Entendo a pressa com a mudança. Em qual região você está procurando apartamento?

- intencao: `aluguel` · proximaAcao: `continuar_conversa`
- extraiu: `{"urgencia": "alta", "score": 40}`
- perfil apos o turno: `{"intencao": "aluguel", "urgencia": "alta", "score": 40}`

## Turno 2

**Lead:** ate 3 mil de aluguel, 2 quartos

**Lia:** Entendido. Em qual bairro ou região você prefere buscar?

- intencao: `aluguel` · proximaAcao: `continuar_conversa`
- extraiu: `{"precoMax": 3000, "quartos": 2, "score": 60}`
- perfil apos o turno: `{"intencao": "aluguel", "urgencia": "alta", "score": 60, "precoMax": 3000, "quartos": 2}`

## Turno 3

**Lead:** Pinheiros ou Perdizes

**Lia:** Ótima escolha de bairros. Qual é o seu primeiro nome?

- intencao: `aluguel` · proximaAcao: `continuar_conversa`
- extraiu: `{"regiao": "Pinheiros ou Perdizes", "score": 70}`
- perfil apos o turno: `{"intencao": "aluguel", "urgencia": "alta", "score": 70, "precoMax": 3000, "quartos": 2, "regiao": "Pinheiros ou Perdizes"}`

