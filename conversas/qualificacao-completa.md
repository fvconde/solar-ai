# Conversa — qualificacao-completa

> Aceite do S-12: lead responde so o que e perguntado, e em 6 turnos o perfil fecha em 100.

Modelo: `gemini-3.5-flash-lite`

## Turno 1

**Lead:** boa tarde, quero comprar um apartamento pra morar

**Lia:** Boa tarde. Para começarmos, qual região você tem interesse em procurar?

- intencao: `compra` · proximaAcao: `continuar_conversa`
- extraiu: `{"score": 25}`
- perfil apos o turno: `{"intencao": "compra", "score": 25}`
- lacunas abertas: `regiao, faixa de preco, prazo, quartos, nome`

## Turno 2

**Lead:** na zona sul, de preferencia Vila Mariana

**Lia:** Entendido, Vila Mariana é uma ótima escolha. Qual faixa de preço você tem em mente para essa compra?

- intencao: `compra` · proximaAcao: `continuar_conversa`
- extraiu: `{"regiao": "zona sul, Vila Mariana", "score": 45}`
- perfil apos o turno: `{"intencao": "compra", "regiao": "zona sul, Vila Mariana", "score": 45}`
- lacunas abertas: `faixa de preco, prazo, quartos, nome`

## Turno 3

**Lead:** ate 700 mil

**Lia:** Perfeito, até 700 mil. E você tem preferência por quantos quartos nesse apartamento?

- intencao: `compra` · proximaAcao: `continuar_conversa`
- extraiu: `{"precoMax": 700000, "score": 65}`
- perfil apos o turno: `{"intencao": "compra", "precoMax": 700000, "regiao": "zona sul, Vila Mariana", "score": 65}`
- lacunas abertas: `prazo, quartos, nome`

## Turno 4

**Lead:** quero mudar ate o mes que vem

**Lia:** Entendido, urgência para o mês que vem. De quantos quartos você precisa nesse apartamento?

- intencao: `compra` · proximaAcao: `continuar_conversa`
- extraiu: `{"urgencia": "alta", "score": 80}`
- perfil apos o turno: `{"intencao": "compra", "precoMax": 700000, "regiao": "zona sul, Vila Mariana", "urgencia": "alta", "score": 80}`
- lacunas abertas: `quartos, nome`

## Turno 5

**Lead:** 2 quartos

**Lia:** Dois quartos, anotado. Como você se chama?

- intencao: `compra` · proximaAcao: `continuar_conversa`
- extraiu: `{"quartos": 2, "score": 90}`
- perfil apos o turno: `{"intencao": "compra", "precoMax": 700000, "quartos": 2, "regiao": "zona sul, Vila Mariana", "urgencia": "alta", "score": 90}`
- lacunas abertas: `nome`

## Turno 6

**Lead:** sou a Bia

**Lia:** Prazer, Bia. Vou separar as melhores opções na Vila Mariana e já passo para um corretor entrar em contato com você.

- intencao: `compra` · proximaAcao: `agendar_reuniao`
- extraiu: `{"nome": "Bia", "score": 100}`
- perfil apos o turno: `{"nome": "Bia", "intencao": "compra", "precoMax": 700000, "quartos": 2, "regiao": "zona sul, Vila Mariana", "urgencia": "alta", "score": 100}`
- lacunas abertas: `nenhuma`

