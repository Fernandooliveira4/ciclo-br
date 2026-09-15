# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

O projeto inteiro — código, docstrings, commits, nomes de função e colunas — está
em **português do Brasil**. Escreva assim também.

## Comandos

Ambiente (as mesmas versões que a CI e o Streamlit Cloud rodam):

```bash
pip install -r requirements-ci.txt && pip install -e . --no-deps
```

Verificação:

```bash
ruff check .
pytest -q
pytest tests/test_regime.py::test_ruido_no_outro_eixo_nao_trava_a_virada   # um teste só
```

Painel (`.venv/Scripts/python.exe -m streamlit run app.py`, ou `scripts/abrir-painel.cmd` no Windows):

```bash
streamlit run app.py
```

Pipeline, na ordem de dependência:

```bash
ciclo-ingest --backfill      # carga inicial; sem a flag é o modo incremental diário
ciclo-calendario             # datas de divulgação do IBGE (auxiliar; falha não derruba nada)
ciclo-transformar            # eixos: ajuste sazonal recursivo + momentum
ciclo-regime                 # classifica o quadrante
ciclo-validar                # defasagem contra a cronologia do CODACE
ciclo-surpresa               # realizado × consenso do Focus da véspera
ciclo-briefing               # publica o briefing, se os fatos mudaram
ciclo-qualidade              # portões de qualidade do dado (código 1 reprova)
```

`ciclo-transformar`, `ciclo-regime`, `ciclo-validar` e `ciclo-surpresa` aceitam
`--verificar`: não gravam nada e devolvem código 1 se o artefato versionado
estiver desatualizado. É assim que a CI confere. `ciclo-briefing --auditar` refaz
a verificação de todos os briefings publicados. Esses cinco, mais `ruff`,
`pytest` e `ciclo-qualidade`, são os **oito portões de CI** (`.github/workflows/ci.yml`).

`ciclo-briefing` também tem `--replay AAAA-MM-DD` (reconstrói e imprime, sem
publicar), `--sem-llm` e `--forcar`.

## Arquitetura

```
ingestion/ ──► data/raw/*.parquet ──► transformacao ──► regime ──┬─► validacao ──► data/derivado/validacao_*.csv
 (única                append-only        derivado/      derivado/│
  camada                                  series.parquet regime.  └─► surpresa ──► data/derivado/surpresa.csv
  com rede)                                              parquet
                                                              │
                              artefatos.py (leitura única) ◄───┴──► briefing/ ──► data/briefings/*.md + .json
                                     │                                  │
                                     └──────────► painel/ ◄─────────────┘
```

**O repositório é o banco de dados.** Um Parquet por série em `data/raw/`,
versionado no Git; o histórico de commits é o histórico de coletas. Toda saída de
pipeline (`data/derivado/`, `data/briefings/`, `data/calendario.parquet`) também
é versionada. Não existe arquivo DuckDB binário — DuckDB é só motor de consulta
sobre os Parquet (`storage.conectar()` expõe as visões `obs_bruto`, `obs`,
`revisoes`).

### Invariantes que o código existe para sustentar

Cada uma tem teste e/ou portão de CI. Quebrá-las é o principal risco de qualquer
mudança aqui.

1. **Nada é sobrescrito** (`storage.py`). Chave `(serie_id, data_referencia,
   data_coleta)`; revisão da fonte vira linha nova. `anexar()` só grava o que é
   inédito ou mudou de valor, senão o arquivo cresceria a cada execução diária.
   No Focus, `data_coleta` vem na entrada e faz parte da identidade da observação
   (o consenso de terça e o de quarta são fatos distintos); no SGS ela é "agora"
   e a diferença de valor significa revisão.
2. **O painel só lê arquivo** (`painel/__init__.py`). Nenhum módulo de `painel/`
   nem `artefatos.py` pode importar `ciclo_br.ingestion`, `requests`, `urllib`,
   `http`, `socket` ou `ciclo_br.briefing.llm`. Dois testes em `tests/test_painel.py`
   travam isso — um lendo a AST do código-fonte, outro em tempo de execução.
   É por isso que `CAMINHO_SURPRESA` e `CAMINHO_CALENDARIO` moram em `config.py`
   e não no módulo que os escreve.
3. **`artefatos.py` é a única camada de leitura**, para painel e briefing. Toda
   leitura de artefato passa por `_caminho()`, que levanta `ArtefatoAusente`
   carregando o comando que gera o arquivo — o painel transforma isso em
   instrução na tela (`componentes.protegido`), não em traceback. Artefato novo
   precisa entrar no dicionário `ARTEFATOS`.
4. **Sem look-ahead no que está sob controle.** `transformacao.dessazonalizar_recursivo`
   reestima o STL a cada ponto com janela expansiva; o corte do eixo de inflação
   em `regime.py` é mediana expansiva. Calcular qualquer um deles sobre a amostra
   inteira reintroduz o viés que o projeto existe para evitar.
5. **A estatística decide, o LLM só descreve.** `briefing/llm.py` é o único módulo
   que fala com um modelo, recebe um JSON fechado de fatos (todo valor já
   formatado como string) e **verifica a saída**: número fora de
   `numeros_permitidos` reprova o texto inteiro, que é descartado, não corrigido —
   `briefing/modelo.py` (determinístico) assume e o rodapé diz por quê. O caminho
   do LLM está desligado hoje; ele depende de `ANTHROPIC_API_KEY` e do extra
   `pip install -e ".[llm]"`.

### Detalhes que já custaram bug

- **Tolerância numérica na camada derivada.** O STL passa por BLAS/LAPACK e
  diverge nos últimos bits entre Linux e Windows, então a comparação usa
  `TOLERANCIA = 1e-5` contra `CASAS_DECIMAIS = 6` na gravação. A tolerância
  precisa ficar uma ordem de grandeza acima da granularidade da gravação; há
  teste travando a relação. Use `transformacao.equivalente()`, nunca `==`.
- **Persistência do regime é por eixo, não pelo rótulo.** Contar meses do
  quadrante inteiro trava a confirmação (um episódio chegou a 116 meses). Cada
  eixo tem seu próprio contador de `MESES_PERSISTENCIA`.
- **`CORTE_CRESCIMENTO = "zero"`**, não mediana — decisão tomada pela validação,
  não por gosto. `CORTES_CRESCIMENTO` mantém a alternativa viva só para a
  varredura de `validacao.py` medir as duas lado a lado. Mudar o classificador
  exige rodar `ciclo-validar` e versionar a nova medição.
- **SGS**: cada consulta cobre no máximo 10 anos (o backfill fatia em janelas de
  9) e ausência de dado volta como HTTP 404, que precisa ser distinguido de falha
  real.
- **A surpresa começa em 2017** porque o calendário do IBGE não devolve nada
  antes disso; o consenso usado é a última apuração do Focus **estritamente
  anterior** à data de divulgação.

## Convenções

- **Nenhuma série entra sem ficha completa em `config/series.yaml`** — fonte,
  código, unidade, periodicidade, ajuste sazonal, papel e transformação.
  `config._validar` rejeita ficha incompleta e há teste sobre a regra.
- **Versões fixas em `requirements.txt` / `requirements-ci.txt`**, não faixas do
  `pyproject`. O job de ingestão roda com `contents: write` e dá push de volta;
  e a CI precisa testar exatamente o que o Streamlit Cloud instala. Subir uma
  versão é um commit que passa pelos oito portões.
- **Mexeu no dado bruto ou no cálculo, regere e versione o artefato derivado** no
  mesmo commit. Os portões `--verificar` reprovam o build justamente nesse caso.
- **Docstrings de módulo explicam *por que*, não *o que***: a decisão, a
  alternativa descartada e o custo. É o estilo dominante do repositório; siga-o
  ao criar módulo novo.
- **Mensagens de commit**: português, minúsculas, prefixo de escopo —
  `painel: explica os quatro quadrantes`, `regime: corte do eixo de crescimento
  passa da mediana histórica para zero`.
- `docs/metodologia.md` é o documento que o painel não pode contradizer. Mudança
  metodológica atualiza o código, o artefato versionado e a seção correspondente
  da metodologia.
- Ruff: `line-length = 100`, alvo `py311`, regras `E, F, I, UP, B`. Python de
  execução é 3.12 (CI, devcontainer, `runtime.txt`).
