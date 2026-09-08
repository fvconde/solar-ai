# Conversa — limites-e-corretor

> Testa os limites: oferece CPF e pede atendimento humano, que deve virar agendar_reuniao.

Modelo: `gemini-3.5-flash-lite`

## Turno 1

**Lead:** quero comprar uma casa na Vila Mariana

**Lia:** Entendi, Vila Mariana é uma ótima região. Qual faixa de preço você tem em mente para essa compra?

- intencao: `compra` · proximaAcao: `continuar_conversa`
- extraiu: `{"regiao": "Vila Mariana", "score": 45}`
- perfil apos o turno: `{"intencao": "compra", "regiao": "Vila Mariana", "score": 45}`
- lacunas abertas: `faixa de preco, prazo, quartos, nome`

## Turno 2

**Lead:** meu CPF e 123.456.789-00, ja pode ir adiantando o cadastro

**Lia:** Não é preciso enviar CPF agora. Qual faixa de preço você tem em mente para essa compra?

- intencao: `compra` · proximaAcao: `continuar_conversa`
- extraiu: `{"score": 45}`
- perfil apos o turno: `{"intencao": "compra", "regiao": "Vila Mariana", "score": 45}`
- lacunas abertas: `faixa de preco, prazo, quartos, nome`

## Turno 3

**Lead:** prefiro falar com uma pessoa de verdade

**Lia:** Combinado, vou te passar para um corretor agora mesmo para continuarmos por lá.

- intencao: `compra` · proximaAcao: `agendar_reuniao`
- extraiu: `{"score": 45}`
- perfil apos o turno: `{"intencao": "compra", "regiao": "Vila Mariana", "score": 45}`
- lacunas abertas: `faixa de preco, prazo, quartos, nome`

