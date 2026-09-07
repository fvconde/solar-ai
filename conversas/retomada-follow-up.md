# Conversa — retomada-follow-up

> Exemplo 3 do enunciado: o lead esfria, some e volta. Testa se a Lia retoma sem re-perguntar.

Modelo: `gemini-3.5-flash-lite`

## Turno 1

**Lead:** quero comprar um apto de 2 quartos no Tatuape, ate 500 mil

**Lia:** Tatuapé é uma ótima região e o orçamento está bem alinhado com o que busca. Você tem pressa para se mudar ou está pesquisando com calma?

- intencao: `compra` · proximaAcao: `continuar_conversa`
- extraiu: `{"precoMax": 500000, "quartos": 2, "regiao": "Tatuapé", "score": 75}`
- perfil apos o turno: `{"intencao": "compra", "precoMax": 500000, "quartos": 2, "regiao": "Tatuapé", "score": 75}`

## Turno 2

**Lead:** ainda nao sei quando, vou pensar melhor

**Lia:** Sem problemas, pesquise com calma. Como posso te chamar?

- intencao: `compra` · proximaAcao: `continuar_conversa`
- extraiu: `{"urgencia": "baixa", "score": 75}`
- perfil apos o turno: `{"intencao": "compra", "precoMax": 500000, "quartos": 2, "regiao": "Tatuapé", "score": 75, "urgencia": "baixa"}`

## Turno 3

**Lead:** oi, voltei. ainda tem alguma coisa naquela faixa?

**Lia:** Temos sim, continuei acompanhando os imóveis de 2 quartos no Tatuapé até 500 mil. Posso pedir para um corretor te enviar as melhores opções?

- intencao: `compra` · proximaAcao: `agendar_reuniao`
- extraiu: `{"score": 80}`
- perfil apos o turno: `{"intencao": "compra", "precoMax": 500000, "quartos": 2, "regiao": "Tatuapé", "score": 80, "urgencia": "baixa"}`

## Turno 4

**Lead:** consigo ver essa semana

**Lia:** Ótimo, vou pedir para um corretor separar as opções e entrar em contato com você ainda esta semana.

- intencao: `compra` · proximaAcao: `agendar_reuniao`
- extraiu: `{"urgencia": "alta", "score": 90}`
- perfil apos o turno: `{"intencao": "compra", "precoMax": 500000, "quartos": 2, "regiao": "Tatuapé", "score": 90, "urgencia": "alta"}`

