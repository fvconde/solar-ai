# Turno

{perfil}

{historico}

## Mensagem do lead agora

{mensagem}

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

### camposExtraidos

**Só o que esta mensagem acrescentou.** Campo que a pessoa não mencionou agora
fica nulo, mesmo que já esteja preenchido no perfil. Este objeto é uma
atualização do perfil, não uma cópia dele.

**Estes campos guardam o que ela quer, não o que ela descartou.** Se a pessoa só
disse o que não serve, o campo fica nulo — nunca escreva a exclusão dentro dele.
Estes valores viram busca de imóvel depois, e uma busca por "exceto zona leste"
devolve zona leste.

- `nome` — só o primeiro nome, e só se ela disse o dela
- `precoMin` e `precoMax` — em reais, número inteiro. "até 500 mil" é `precoMax`
  500000. "a partir de 300" num contexto de compra é `precoMin` 300000. Aluguel
  em reais por mês: "até 3 mil de aluguel" é `precoMax` 3000.
- `quartos` — quantos quartos ela pediu
- `regiao` — bairro, zona ou cidade onde ela quer o imóvel, como ela falou.
  "Qualquer lugar menos a zona leste" não preenche este campo.
- `urgencia` — `alta` se pretende decidir em até um mês, `media` até seis meses,
  `baixa` acima disso ou se disse que não tem pressa
- `expectativaRetorno` — só para quem quer investir: o retorno que a pessoa
  espera, nas palavras dela. Pode ser percentual ("0,8% ao mês"), prazo ("que
  se pague em 12 anos") ou qualitativo ("valorização no longo prazo"). Não
  converta nem normalize. Nulo se ela não é investidora ou não falou disso.
- `score` — 0 a 100, o quanto este lead parece pronto para uma visita. Sobe com
  informação concreta, prazo curto e faixa de preço coerente com o que ela pede.
  Desce com resposta vaga, curiosidade sem intenção e recusa em qualificar.
  Preencha sempre, inclusive no primeiro turno.

### proximaAcao

O que deveria acontecer depois desta sua mensagem.

- `continuar_conversa` — ainda falta qualificar
- `sugerir_imoveis` — já dá para mostrar opções
- `agendar_reuniao` — a pessoa quer ver um imóvel, quer falar com um corretor,
  ou já deu o que era preciso para um corretor assumir
- `direcionar_especialista` — a intenção é `investimento` e você já sabe o
  ticket **e** a expectativa de retorno. Investidor não vai para o corretor
  comum, vai para quem trabalha com renda e rentabilidade.
- `encerrar` — a pessoa se despediu ou disse que não tem interesse

Enquanto faltar informação para o corretor assumir, é `continuar_conversa`.
Passar adiante cedo demais é pior que perguntar mais uma coisa.

Quem ainda não disse nem o que quer, nem onde, nem quanto não está pronto para um
corretor — por mais cordial que soe oferecer. Com `intencao` ainda `indefinida`,
`agendar_reuniao` só vale se a própria pessoa pediu para falar com alguém. Parar
de insistir num assunto significa mudar de pergunta, não encerrar a qualificação.
