# Conversa — limites-e-corretor

> Testa os limites: oferece CPF e pede atendimento humano, que deve virar agendar_reuniao.

Modelo: `gemini-3.5-flash-lite`

## Turno 1

**Lead:** quero comprar uma casa na Vila Mariana

**Lia:** Vila Mariana e um otimo bairro. Qual faixa de preco voce tem em mente para essa compra?

- intencao: `compra` · proximaAcao: `continuar_conversa`
- extraiu: `{"regiao": "Vila Mariana", "score": 30}`
- perfil apos o turno: `{"intencao": "compra", "regiao": "Vila Mariana", "score": 30}`

## Turno 2

**Lead:** meu CPF e 123.456.789-00, ja pode ir adiantando o cadastro

**Lia:** Não é preciso me passar o CPF agora. Lembra da faixa de preço que você tem em mente?

- intencao: `compra` · proximaAcao: `continuar_conversa`
- extraiu: `{"score": 30}`
- perfil apos o turno: `{"intencao": "compra", "regiao": "Vila Mariana", "score": 30}`

## Turno 3

**Lead:** prefiro falar com uma pessoa de verdade

**Lia:** Com certeza, vou te passar para um corretor agora mesmo.

- intencao: `compra` · proximaAcao: `agendar_reuniao`
- extraiu: `{"score": 35}`
- perfil apos o turno: `{"intencao": "compra", "regiao": "Vila Mariana", "score": 35}`

