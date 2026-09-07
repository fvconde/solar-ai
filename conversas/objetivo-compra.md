# Conversa — objetivo-compra

> Lead decidido: da tudo rapido e quer agendar.

Modelo: `gemini-3.5-flash-lite`

## Turno 1

**Lead:** boa tarde, procuro apartamento pra comprar

**Lia:** Boa tarde. Qual região você tem interesse?

- intencao: `compra` · proximaAcao: `continuar_conversa`
- extraiu: `{"score": 30}`
- perfil apos o turno: `{"intencao": "compra", "score": 30}`

## Turno 2

**Lead:** seria no Butanta ou perto, ate 650 mil

**Lia:** Entendi, Butantã e arredores até esse valor. Quantos quartos você precisa?

- intencao: `compra` · proximaAcao: `continuar_conversa`
- extraiu: `{"precoMax": 650000, "regiao": "Butanta", "score": 50}`
- perfil apos o turno: `{"intencao": "compra", "score": 50, "precoMax": 650000, "regiao": "Butanta"}`

## Turno 3

**Lead:** 3 quartos, e preciso mudar ate o fim do ano

**Lia:** Entendi, três quartos e mudança até o fim do ano. Me diz seu nome, por favor?

- intencao: `compra` · proximaAcao: `continuar_conversa`
- extraiu: `{"quartos": 3, "urgencia": "media", "score": 75}`
- perfil apos o turno: `{"intencao": "compra", "score": 75, "precoMax": 650000, "regiao": "Butanta", "quartos": 3, "urgencia": "media"}`

## Turno 4

**Lead:** sou o Rafael. da pra marcar uma visita essa semana?

**Lia:** Prazer, Rafael. Vou separar as melhores opções no Butantã e peço para um corretor entrar em contato para agendarmos a visita.

- intencao: `compra` · proximaAcao: `agendar_reuniao`
- extraiu: `{"nome": "Rafael", "score": 90}`
- perfil apos o turno: `{"intencao": "compra", "score": 90, "precoMax": 650000, "regiao": "Butanta", "quartos": 3, "urgencia": "media", "nome": "Rafael"}`

