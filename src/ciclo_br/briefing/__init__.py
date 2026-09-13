"""Briefing por divulgação: a estatística decide, o texto apenas descreve.

O pacote está partido em quatro por causa de uma separação que é o argumento
inteiro do projeto:

- `fatos.py` monta um **JSON fechado** a partir dos artefatos versionados. Todo
  valor citável já sai dali formatado como string em português, e o conjunto de
  números que o texto pode usar é derivado desse mesmo JSON.
- `modelo.py` escreve o briefing de forma determinística. É o gerador padrão
  quando não há chave de API, e é a rede de segurança quando o texto do modelo
  de linguagem é recusado.
- `llm.py` pede o texto ao Haiku 4.5 e **confere o resultado**: todo número
  escrito precisa estar no conjunto permitido, e há termos que o briefing não
  pode conter. Texto reprovado é descartado, não corrigido.
- `publicacao.py` grava o par `.md` + `.json` e mantém o índice.

**Por que o texto não pode inventar número.** Um modelo de linguagem escrevendo
sobre macroeconomia produz frases plausíveis com números plausíveis, e um número
plausível errado é pior que nenhum texto. Aqui ele não tem acesso a nada além do
JSON de fatos, e a verificação é automática: se aparecer um número que não está
lá, o texto inteiro é descartado e o gerador determinístico assume. O rodapé do
briefing diz quem escreveu e, quando houve recusa, por quê.

`llm.py` é o único módulo daqui que fala com a rede, e nenhum outro o importa —
por isso o painel consegue montar um briefing de demonstração sem sair do
arquivo.
"""
