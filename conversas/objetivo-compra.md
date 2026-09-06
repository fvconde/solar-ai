# Conversa — objetivo-compra

> Lead decidido: da tudo rapido e quer agendar.

Modelo: `gemini-3.5-flash-lite`

## Turno 1

**Lead:** boa tarde, procuro apartamento pra comprar

**Lia:** Boa tarde. Para qual região você está olhando?

- intencao: `compra` · proximaAcao: `continuar_conversa`
- extraiu: `{"score": 20}`
- perfil apos o turno: `{"intencao": "compra", "score": 20}`

## Turno 2

**Lead:** seria no Butanta ou perto, ate 650 mil

**Lia:** Entendi, Butantã e arredores até esse valor. Quantos quartos você precisa?

- intencao: `compra` · proximaAcao: `continuar_conversa`
- extraiu: `{"precoMax": 650000, "regiao": "Butanta", "score": 40}`
- perfil apos o turno: `{"intencao": "compra", "score": 40, "precoMax": 650000, "regiao": "Butanta"}`

## Turno 3

**Lead:** 3 quartos, e preciso mudar ate o fim do ano

**Lia:** Prazo anotado, até o fim do ano. Qual é o seu nome?

- intencao: `compra` · proximaAcao: `continuar_conversa`
- extraiu: `{"quartos": 3, "urgencia": "alta", "score": 75}`
- perfil apos o turno: `{"intencao": "compra", "score": 75, "precoMax": 650000, "regiao": "Butanta", "quartos": 3, "urgencia": "alta"}`

## Turno 4

**Lead:** sou o Rafael. da pra marcar uma visita essa semana?

**Lia:** Com certeza, Rafael. Vou passar suas informações para um corretor e ele entra em contato para agendar a visita.

- intencao: `compra` · proximaAcao: `agendar_reuniao`
- extraiu: `{"nome": "Rafael", "score": 90}`
- perfil apos o turno: `{"intencao": "compra", "score": 90, "precoMax": 650000, "regiao": "Butanta", "quartos": 3, "urgencia": "alta", "nome": "Rafael"}`

