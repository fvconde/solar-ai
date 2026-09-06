# Conversa — investidor-especialista

> Exemplo 2 do enunciado: ticket e expectativa de retorno ate direcionar_especialista.

Modelo: `gemini-3.5-flash-lite`

## Turno 1

**Lead:** to procurando imovel pra investir e alugar depois

**Lia:** Para investimento, o foco é a rentabilidade. Quanto você pretende aplicar e qual retorno espera ter com o aluguel?

- intencao: `investimento` · proximaAcao: `continuar_conversa`
- extraiu: `{"score": 30}`
- perfil apos o turno: `{"intencao": "investimento", "score": 30}`

## Turno 2

**Lead:** qual regiao ta rendendo mais aluguel hoje?

**Lia:** As regiões centrais e próximas a universidades costumam ter uma procura constante por aluguel. Para eu te indicar os melhores pontos, quanto você pretende aplicar?

- intencao: `investimento` · proximaAcao: `continuar_conversa`
- extraiu: `{"score": 35}`
- perfil apos o turno: `{"intencao": "investimento", "score": 35}`

## Turno 3

**Lead:** entendi. tenho ate 400 mil pra aplicar

**Lia:** Com esse valor dá para encontrar opções bem interessantes. E qual retorno você espera ter com o aluguel?

- intencao: `investimento` · proximaAcao: `continuar_conversa`
- extraiu: `{"precoMax": 400000, "score": 50}`
- perfil apos o turno: `{"intencao": "investimento", "score": 50, "precoMax": 400000}`

## Turno 4

**Lead:** espero uns 0,7% ao mes de aluguel liquido

**Lia:** Entendido. Vou separar as melhores opções para esse perfil de rentabilidade e um especialista vai entrar em contato com você.

- intencao: `investimento` · proximaAcao: `direcionar_especialista`
- extraiu: `{"expectativaRetorno": "0,7% ao mes de aluguel liquido", "score": 85}`
- perfil apos o turno: `{"intencao": "investimento", "score": 85, "precoMax": 400000, "expectativaRetorno": "0,7% ao mes de aluguel liquido"}`

