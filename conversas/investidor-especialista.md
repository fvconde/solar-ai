# Conversa — investidor-especialista

> Exemplo 2 do enunciado: ticket e expectativa de retorno ate direcionar_especialista.

Modelo: `gemini-3.5-flash-lite`

## Turno 1

**Lead:** to procurando imovel pra investir e alugar depois

**Lia:** Entendi, buscar um imóvel para investir é uma ótima estratégia. Qual faixa de preço você tem em mente para essa aplicação?

- intencao: `investimento` · proximaAcao: `continuar_conversa`
- extraiu: `{"score": 25}`
- perfil apos o turno: `{"intencao": "investimento", "score": 25}`
- lacunas abertas: `ticket, expectativa de retorno, regiao, prazo, nome`

## Turno 2

**Lead:** qual regiao ta rendendo mais aluguel hoje?

**Lia:** As regiões mais centrais e próximas ao metrô costumam ter uma procura constante por aluguel. Para termos uma ideia melhor do investimento, quanto você planeja aplicar?

- intencao: `investimento` · proximaAcao: `continuar_conversa`
- extraiu: `{"score": 25}`
- perfil apos o turno: `{"intencao": "investimento", "score": 25}`
- lacunas abertas: `ticket, expectativa de retorno, regiao, prazo, nome`

## Turno 3

**Lead:** entendi. tenho ate 400 mil pra aplicar

**Lia:** Entendido, com esse valor já dá para buscar boas opções. E que tipo de retorno você espera ter com esse investimento?

- intencao: `investimento` · proximaAcao: `continuar_conversa`
- extraiu: `{"precoMax": 400000, "score": 45}`
- perfil apos o turno: `{"intencao": "investimento", "precoMax": 400000, "score": 45}`
- lacunas abertas: `expectativa de retorno, regiao, prazo, nome`

## Turno 4

**Lead:** espero uns 0,7% ao mes de aluguel liquido

**Lia:** Com essa expectativa de retorno bem definida, vou direcionar você para um dos nossos especialistas em investimentos. Ele vai entrar em contato para apresentar as melhores opções.

- intencao: `investimento` · proximaAcao: `direcionar_especialista`
- extraiu: `{"expectativaRetorno": "0,7% ao mes de aluguel liquido", "score": 65}`
- perfil apos o turno: `{"intencao": "investimento", "precoMax": 400000, "expectativaRetorno": "0,7% ao mes de aluguel liquido", "score": 65}`
- lacunas abertas: `regiao, prazo, nome`

