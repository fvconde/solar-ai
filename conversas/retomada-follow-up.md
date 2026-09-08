# Conversa — retomada-follow-up

> Exemplo 3 do enunciado: o lead esfria, some e volta. Testa se a Lia retoma sem re-perguntar.

Modelo: `gemini-3.5-flash-lite`

## Turno 1

**Lead:** quero comprar um apto de 2 quartos no Tatuape, ate 500 mil

**Lia:** Tatuapé é uma boa região. Você tem alguma urgência para essa mudança ou está pesquisando com calma?

- intencao: `compra` · proximaAcao: `continuar_conversa`
- extraiu: `{"precoMax": 500000, "quartos": 2, "regiao": "Tatuape", "score": 75}`
- perfil apos o turno: `{"intencao": "compra", "precoMax": 500000, "quartos": 2, "regiao": "Tatuape", "score": 75}`
- lacunas abertas: `prazo, nome`

## Turno 2

**Lead:** ainda nao sei quando, vou pensar melhor

**Lia:** Sem pressa, então. Como você se chama?

- intencao: `compra` · proximaAcao: `continuar_conversa`
- extraiu: `{"urgencia": "baixa", "score": 80}`
- perfil apos o turno: `{"intencao": "compra", "precoMax": 500000, "quartos": 2, "regiao": "Tatuape", "urgencia": "baixa", "score": 80}`
- lacunas abertas: `nome`

## Turno 3

**Lead:** oi, voltei. ainda tem alguma coisa naquela faixa?

**Lia:** Sim, temos opções naquela faixa sim. Como você se chama?

- intencao: `compra` · proximaAcao: `continuar_conversa`
- extraiu: `{"score": 80}`
- perfil apos o turno: `{"intencao": "compra", "precoMax": 500000, "quartos": 2, "regiao": "Tatuape", "urgencia": "baixa", "score": 80}`
- lacunas abertas: `nome`

## Turno 4

**Lead:** consigo ver essa semana

**Lia:** Entendi, então a urgência mudou e você quer ver algo logo. Como você se chama?

- intencao: `compra` · proximaAcao: `continuar_conversa`
- extraiu: `{"urgencia": "alta", "score": 90}`
- perfil apos o turno: `{"intencao": "compra", "precoMax": 500000, "quartos": 2, "regiao": "Tatuape", "urgencia": "alta", "score": 90}`
- lacunas abertas: `nome`

