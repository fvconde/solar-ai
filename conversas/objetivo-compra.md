# Conversa — objetivo-compra

> Lead decidido: da tudo rapido e quer agendar.

Modelo: `gemini-3.5-flash-lite`

## Turno 1

**Lead:** boa tarde, procuro apartamento pra comprar

**Lia:** Boa tarde. Para começarmos, em qual região ou bairro você prefere procurar?

- intencao: `compra` · proximaAcao: `continuar_conversa`
- extraiu: `{"score": 25}`
- perfil apos o turno: `{"intencao": "compra", "score": 25}`
- lacunas abertas: `regiao, faixa de preco, prazo, quartos, nome`

## Turno 2

**Lead:** seria no Butanta ou perto, ate 650 mil

**Lia:** Entendido, no Butantã ou perto e até 650 mil. Quando você pretende se mudar?

- intencao: `compra` · proximaAcao: `continuar_conversa`
- extraiu: `{"precoMax": 650000, "regiao": "Butantã", "score": 65}`
- perfil apos o turno: `{"intencao": "compra", "precoMax": 650000, "regiao": "Butantã", "score": 65}`
- lacunas abertas: `prazo, quartos, nome`

## Turno 3

**Lead:** 3 quartos, e preciso mudar ate o fim do ano

**Lia:** Entendido, 3 quartos e mudança até o fim do ano. Como você se chama?

- intencao: `compra` · proximaAcao: `continuar_conversa`
- extraiu: `{"quartos": 3, "urgencia": "alta", "score": 90}`
- perfil apos o turno: `{"intencao": "compra", "precoMax": 650000, "quartos": 3, "regiao": "Butantã", "urgencia": "alta", "score": 90}`
- lacunas abertas: `nome`

## Turno 4

**Lead:** sou o Rafael. da pra marcar uma visita essa semana?

**Lia:** Prazer, Rafael. Vou separar as melhores opções para você e já passo para um corretor organizar a sua visita.

- intencao: `compra` · proximaAcao: `agendar_reuniao`
- extraiu: `{"nome": "Rafael", "score": 100}`
- perfil apos o turno: `{"nome": "Rafael", "intencao": "compra", "precoMax": 650000, "quartos": 3, "regiao": "Butantã", "urgencia": "alta", "score": 100}`
- lacunas abertas: `nenhuma`

