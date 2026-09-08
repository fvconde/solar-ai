# Conversa — aluguel-urgente

> Aluguel com prazo curto. Testa se preco e lido como mensal.

Modelo: `gemini-3.5-flash-lite`

## Turno 1

**Lead:** preciso alugar um apto rapido, saio do atual dia 30

**Lia:** Entendo a pressa, dia 30 está logo aí. Em qual região ou bairro você está procurando?

- intencao: `aluguel` · proximaAcao: `continuar_conversa`
- extraiu: `{"urgencia": "alta", "score": 40}`
- perfil apos o turno: `{"intencao": "aluguel", "urgencia": "alta", "score": 40}`
- lacunas abertas: `regiao, faixa de preco, quartos, nome`

## Turno 2

**Lead:** ate 3 mil de aluguel, 2 quartos

**Lia:** Perfeito, dois quartos e até três mil. E em qual região você prefere?

- intencao: `aluguel` · proximaAcao: `continuar_conversa`
- extraiu: `{"precoMax": 3000, "quartos": 2, "score": 70}`
- perfil apos o turno: `{"intencao": "aluguel", "precoMax": 3000, "quartos": 2, "urgencia": "alta", "score": 70}`
- lacunas abertas: `regiao, nome`

## Turno 3

**Lead:** Pinheiros ou Perdizes

**Lia:** Pinheiros e Perdizes são excelentes opções por lá. Como você se chama?

- intencao: `aluguel` · proximaAcao: `continuar_conversa`
- extraiu: `{"regiao": "Pinheiros ou Perdizes", "score": 90}`
- perfil apos o turno: `{"intencao": "aluguel", "precoMax": 3000, "quartos": 2, "regiao": "Pinheiros ou Perdizes", "urgencia": "alta", "score": 90}`
- lacunas abertas: `nome`

