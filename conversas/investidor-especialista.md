# Conversa — investidor-especialista

> Exemplo 2 do enunciado: ticket e expectativa de retorno ate direcionar_especialista.

Modelo: `gemini-3.5-flash-lite`

## Turno 1

**Lead:** to procurando imovel pra investir e alugar depois

**Lia:** Entendi, focar em rentabilidade é um ótimo caminho. Quanto você espera de retorno com esse imóvel?

- intencao: `investimento` · proximaAcao: `continuar_conversa`
- extraiu: `{"score": 30}`
- perfil apos o turno: `{"intencao": "investimento", "score": 30}`

## Turno 2

**Lead:** qual regiao ta rendendo mais aluguel hoje?

**Lia:** As regiões centrais e próximas a universidades costumam ter uma procura forte por locação. Para eu afunilar as opções, quanto você tem disponível para investir?

- intencao: `investimento` · proximaAcao: `continuar_conversa`
- extraiu: `{"score": 35}`
- perfil apos o turno: `{"intencao": "investimento", "score": 35}`

## Turno 3

**Lead:** entendi. tenho ate 400 mil pra aplicar

**Lia:** Com esse valor dá para encontrar boas opções com liquidez rápida. Qual faixa de retorno mensal você espera obter com o aluguel?

- intencao: `investimento` · proximaAcao: `continuar_conversa`
- extraiu: `{"precoMax": 400000, "score": 50}`
- perfil apos o turno: `{"intencao": "investimento", "score": 50, "precoMax": 400000}`

## Turno 4

**Lead:** espero uns 0,7% ao mes de aluguel liquido

**Lia:** Uma expectativa bem realista para o mercado atual. Vou separar os imóveis que entregam esse perfil de renda para você conversar com o nosso especialista em investimentos.

- intencao: `investimento` · proximaAcao: `direcionar_especialista`
- extraiu: `{"expectativaRetorno": "0,7% ao mes de aluguel liquido", "score": 90}`
- perfil apos o turno: `{"intencao": "investimento", "score": 90, "precoMax": 400000, "expectativaRetorno": "0,7% ao mes de aluguel liquido"}`

