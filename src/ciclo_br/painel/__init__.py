"""Painel Streamlit do ciclo-br.

**A regra desta camada: ela só lê arquivo.** Nenhum módulo aqui importa a
ingestão nem fala com API alguma. Tudo que o painel mostra saiu de um arquivo
versionado no repositório — `data/derivado/regime.parquet`,
`validacao_*.csv`, `surpresa.csv`, `data/calendario.parquet` e os Parquet de
série bruta.

Isso não é preciosismo de arquitetura, é o que sustenta três coisas:

1. **O painel não pode divergir do pipeline.** Se ele recalculasse qualquer
   número por conta própria, existiriam duas versões da verdade e a da tela
   seria a não testada. Os portões de CI conferem os arquivos; o painel apenas
   os desenha.
2. **Ele abre sem rede e sem credencial.** Qualquer pessoa que clonar o
   repositório vê exatamente o que está publicado, inclusive offline.
3. **Ele é reproduzível no tempo.** Como o estado inteiro do projeto está em
   arquivos versionados, voltar o repositório a um commit anterior faz o painel
   mostrar o que ele mostrava naquele dia — sem nenhum modo especial. É disso
   que o modo replay da S8 vai viver.

O que o painel deliberadamente **não** tem é um seletor de "como estava em
março de 2015". Reconstruir aquela tela com o dado revisado de hoje seria
exatamente o viés de look-ahead que a camada derivada existe para evitar, e sair
mais bonito do que a verdade permite. Há teste travando a regra de importação.
"""
