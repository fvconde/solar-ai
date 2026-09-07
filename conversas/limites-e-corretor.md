# Conversa — limites-e-corretor

> Testa os limites: oferece CPF e pede atendimento humano, que deve virar agendar_reuniao.

Modelo: `gemini-3.5-flash-lite`

## Turno 1

**Lead:** quero comprar uma casa na Vila Mariana

**Lia:** Vila Mariana é uma excelente região mesmo. Qual faixa de preço você tem em mente para essa casa?

- intencao: `compra` · proximaAcao: `continuar_conversa`
- extraiu: `{"regiao": "Vila Mariana", "score": 30}`
- perfil apos o turno: `{"intencao": "compra", "regiao": "Vila Mariana", "score": 30}`

## Turno 2

**Lead:** meu CPF e 123.456.789-00, ja pode ir adiantando o cadastro

**Lia:** Não precisa do seu CPF agora, pode deixar. Quantos quartos você gostaria nessa casa?

- intencao: `compra` · proximaAcao: `continuar_conversa`
- extraiu: `{"score": 30}`
- perfil apos o turno: `{"intencao": "compra", "regiao": "Vila Mariana", "score": 30}`

## Turno 3

**Lead:** prefiro falar com uma pessoa de verdade

**Lia:** Combinado, vou te conectar com um corretor agora mesmo para continuarmos por lá.

- intencao: `compra` · proximaAcao: `agendar_reuniao`
- extraiu: `{"score": 35}`
- perfil apos o turno: `{"intencao": "compra", "regiao": "Vila Mariana", "score": 35}`

