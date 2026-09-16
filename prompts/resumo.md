# Resumo para o corretor

Leia nesta ordem: perfil estruturado, conversa completa e imóveis mostrados.

{perfil}

{historico}

{imoveis}

## Objetivo

Entregue um resumo curto e escaneável para um corretor que tem cerca de trinta
segundos para entender o atendimento. Não narre a conversa, não reproduza falas
em sequência e não escreva texto corrido.

## Regras obrigatórias

- Use somente fatos presentes nos insumos acima. Nunca complete lacunas por
  plausibilidade.
- Cada seção deve ser uma frase curta ou uma lista compacta em texto puro.
- Se uma seção não tiver conteúdo comprovado, devolva `null`. Não invente nada
  para preencher uma seção vazia.
- Preserve em `objecoes` o que o lead rejeitou ou excluiu, mesmo quando essa
  informação não aparece no perfil estruturado.
- Não inclua telefone, e-mail, CPF, CEP ou outro dado de contato no resumo.

## O que devolver

### perfil

Perfil e intenção do lead, apenas com o que já se sabe.

### orcamento

Orçamento e região desejados. Use `null` se nenhum dos dois foi informado.

### imoveis

Imóveis efetivamente mostrados ao lead. Use `null` quando a lista recebida
estiver vazia.

### objecoes

Objeções, recusas e restrições ditas pelo lead. Use `null` quando não houver
nenhuma.

### proximoPasso

Próximo passo sugerido a partir da conversa. Use `null` quando a transcrição não
der base para sugerir uma ação.
