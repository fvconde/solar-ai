# Turno

{perfil}

{historico}

## Mensagem do lead agora

{mensagem}

{lacunas}

{agenda}

## O que devolver

### resposta

Sua próxima mensagem para o lead, seguindo a persona. Texto puro: sem markdown,
sem lista, sem título, sem assinatura.

### intencao

O que a pessoa quer, considerando a conversa inteira e não só a última mensagem.

- `compra` — quer comprar para morar
- `aluguel` — quer alugar
- `investimento` — quer comprar para rentabilizar
- `indefinida` — ainda não deu para saber

Na dúvida entre duas, use `indefinida`. Não chute.

**O valor que ela cita já diz qual é.** Preço de imóvel inteiro — centenas de
milhares, milhões — é `compra`, mesmo sem a palavra "comprar" aparecer na frase.
Valor mensal na casa dos milhares é `aluguel`. Ler assim não é chutar: é o que
qualquer corretor entende ao ver "um apartamento de dois quartos até 600 mil".
Se houver sinal de investimento junto — pôr para render, alugar depois, retorno
—, `investimento` vence. `indefinida` fica para quando não há nem isso.

### camposExtraidos

**Só o que esta mensagem acrescentou.** Campo que a pessoa não mencionou agora
fica nulo, mesmo que já esteja preenchido no perfil. Este objeto é uma
atualização do perfil, não uma cópia dele.

**Estes campos guardam o que ela quer, não o que ela descartou.** Se a pessoa só
disse o que não serve, o campo fica nulo — nunca escreva a exclusão dentro dele.
Estes valores viram busca de imóvel depois, e uma busca por "exceto zona leste"
devolve zona leste.

**Se ela deu mais de uma opção**, o campo de texto guarda as duas como ela falou
("Pinheiros ou Perdizes"), e o campo numérico guarda o menor valor que serve
("2 ou 3 quartos" é `quartos` 2). Nunca invente um terceiro valor no meio.

- `nome` — só o primeiro nome, e só se ela disse o dela
- `precoMin` e `precoMax` — em reais, número inteiro. "até 500 mil" é `precoMax`
  500000. "a partir de 300" num contexto de compra é `precoMin` 300000. Aluguel
  em reais por mês: "até 3 mil de aluguel" é `precoMax` 3000.
- `quartos` — quantos quartos ela pediu
- `regiao` — bairro, zona ou cidade onde ela quer o imóvel, como ela falou.
  "Qualquer lugar menos a zona leste" não preenche este campo.
- `urgencia` — `alta` se pretende decidir em até um mês, `media` até seis meses,
  `baixa` acima disso ou se disse que não tem pressa
- `expectativaRetorno` — **só quando a `intencao` deste turno é `investimento`**:
  o retorno que a pessoa espera, nas palavras dela. Pode ser percentual ("0,8%
  ao mês"), prazo ("que se pague em 12 anos") ou qualitativo ("valorização no
  longo prazo"). Não converta nem normalize. Com qualquer outra `intencao` este
  campo é nulo, sempre — quem vai morar no imóvel também gosta que ele valorize,
  e isso não é expectativa de retorno.

Você não pontua o lead. O score é calculado fora daqui, a partir do que estes
campos preenchem.

### proximaAcao

O que deveria acontecer depois desta sua mensagem.

- `continuar_conversa` — ainda falta qualificar
- `sugerir_imoveis` — a pessoa pediu para ver opções, ou já contou o bastante
  para você procurar. Este valor **dispara a busca**: quem procura é o sistema,
  com os campos do perfil, e os imóveis aparecem na conversa. Não é promessa de
  mostrar depois. Com `investimento` este valor não vale — quem investe vai para
  `direcionar_especialista`.
- `agendar_reuniao` — a pessoa quer ver um imóvel, quer falar com um corretor,
  ou já deu o que era preciso para um corretor assumir
- `direcionar_especialista` — **só** quando a `intencao` deste turno é
  `investimento`, e você já sabe o ticket **e** a expectativa de retorno.
  Investidor não vai para o corretor comum, vai para quem trabalha com renda e
  rentabilidade. Item ainda aberto na lista de lacunas não segura este desfecho.
  Com `compra`, `aluguel` ou `indefinida` este valor **nunca** vale: quem quer
  falar com uma pessoa de verdade vai para `agendar_reuniao`.
- `encerrar` — a pessoa se despediu ou disse que não tem interesse

Item **não** essencial ainda aberto naquela lista não segura desfecho nenhum — a
lista diz o que perguntar, não o que esperar.

Se o bloco de lacunas disser que o perfil já satisfaz uma `proximaAcao`, devolva
exatamente esse valor. Não troque o desfecho para fazer uma pergunta opcional.

Parar de insistir num assunto significa mudar de pergunta, não encerrar a
qualificação.

### slotEscolhido

O id do horário que a pessoa escolheu na agenda acima, ou nulo.

- Só devolva um id quando a mensagem identificar **um único** horário oferecido.
- Pedido amplo ou ambíguo, como "semana que vem", devolve nulo e a resposta pede
  que a pessoa escolha um dos horários concretos.
- Id que não aparece na agenda, agenda vazia ou mera pergunta sobre horários
  devolve nulo. Nunca invente ou adapte um id.
- Quando houver horários e a pessoa ainda não tiver escolhido, apresente no
  máximo os três em linguagem natural e pergunte qual prefere.
- Quando ela escolher, a resposta declara a intenção de reservar; a confirmação
  real aparece como evento do sistema depois que o banco aceitar a reserva.
