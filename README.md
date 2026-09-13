# ciclo-br

**Classificador de regime macroeconômico brasileiro, com pipeline reprodutível e
briefing automatizado por divulgação.**

O projeto coleta séries oficiais do Banco Central, classifica o estado do ciclo
em quadrantes de crescimento × inflação, mede a surpresa de cada divulgação
contra o consenso do Focus, e publica um briefing — mas só quando há dado novo.

![CI](https://github.com/Fernandooliveira4/ciclo-br/actions/workflows/ci.yml/badge.svg)
![Ingestão](https://github.com/Fernandooliveira4/ciclo-br/actions/workflows/ingest.yml/badge.svg)

> **Status:** em construção. Semanas 1 a 5 de 8 concluídas — ingestão, armazenamento,
> expectativas do Focus, agendamento automático, o classificador de regime e a
> validação contra a datação oficial do CODACE.
> O roteiro completo está em [Roadmap](#roadmap).

---

## Por que este projeto é diferente de um painel de indicadores

A maior parte dos dashboards macro de portfólio empilha gráficos e detecta
outliers estatísticos. Três decisões afastam este daqui disso:

**1. A estatística decide, o modelo de linguagem apenas descreve.**
A classificação de regime e a medida de surpresa são calculadas de forma
determinística. O LLM recebe um JSON de fatos já apurados e não tem acesso a
nenhum número fora dele — por construção, ele não pode inventar um dado. Se a
API falhar, um gerador de texto determinístico assume, e o rodapé do briefing diz
qual dos dois escreveu.

**2. O classificador é validado contra uma datação oficial.**
A série de quadrantes é confrontada com a cronologia de ciclos do CODACE
(FGV/IBRE), e a métrica principal é a **defasagem** do sinal, não a taxa de
acerto. A janela de validação contém três recessões, e é exatamente por isso que
o classificador é uma regra de sinal e não um modelo com parâmetros estimados.

A validação não é um selo: ela mudou o projeto. Encontrou um travamento na regra
de persistência que produzia um episódio de contração de 116 meses, fixou o prazo
de confirmação em três meses contra evidência em vez de gosto, e mostrou que o
corte de crescimento em uso deixa o sinal ligado em 81% dos meses da janela. O
resultado inteiro está em [`data/derivado/validacao_resumo.csv`](data/derivado/validacao_resumo.csv)
e o raciocínio na [seção 7 da metodologia](docs/metodologia.md).

**3. Nenhum dado é sobrescrito.**
Não existe base de vintages pública para séries brasileiras. Este projeto
constrói a sua: cada observação é gravada com a data em que foi coletada, e uma
revisão retroativa do Banco Central vira uma linha nova em vez de apagar a
anterior. O histórico de commits é o histórico de coletas.

O que o projeto **não** faz: previsão, recomendação de investimento, ou qualquer
julgamento delegado a um modelo de linguagem.

---

## Arquitetura

```
  SGS/BCB  ──┐
             ├──►  ingestão  ──►  Parquet append-only  ──►  DuckDB  ──┬──►  classificador de regime  ──┐
  Focus/BCB ─┤       (retry,        (serie, data_ref,      (consulta) │         (quadrante)           ├──►  briefing  ──►  dashboard
             │      fatiamento)      data_coleta)                     └──►  surpresa vs. Focus  ───────┘    (markdown)      (Streamlit)
  Calendário ┘                                                                                                  ▲
   IBGE                                                                                              LLM ou template
```

**O repositório é o banco de dados.** Um arquivo Parquet por série, versionado no
Git. Arquivo DuckDB binário foi descartado de propósito: não versiona bem, e o
objetivo é que cada commit automático mostre exatamente o que mudou.

**A cadência é por divulgação, não diária.** O job roda todo dia, compara o que a
API devolve com o que já está gravado, e só escreve briefing quando há observação
nova ou revisão. Na maior parte dos dias ele fica calado — um sistema que sabe
não falar é mais útil que um que parafraseia estabilidade.

---

## Dados

15 séries, todas com ficha obrigatória em [`config/series.yaml`](config/series.yaml)
declarando fonte, código, unidade, periodicidade, tratamento sazonal, papel no
projeto e transformação aplicada. **Nenhuma série entra sem ficha completa** — e
a regra é verificada por teste, não por disciplina.

| Bloco | Séries |
|---|---|
| Atividade | IBC-Br (com e sem ajuste), desocupação PNADC, produção industrial (com e sem ajuste) |
| Inflação | IPCA mensal, IPCA 12m, núcleo por médias aparadas, núcleo versão congelada (auditoria) |
| Política | Meta Selic, câmbio PTAX |
| Expectativas | Focus: IPCA, desocupação e câmbio mensais; PIB trimestral |

Duas particularidades da API do SGS ditam o desenho do cliente: cada consulta
cobre no máximo 10 anos (o backfill é fatiado em janelas de 9), e a ausência de
dado num intervalo volta como HTTP 404, que precisa ser distinguido de falha real.

---

## Como rodar

```bash
python -m venv .venv && .venv/Scripts/activate   # Windows
pip install -e ".[dev]"
```

```bash
ciclo-ingest --backfill          # carga inicial, desde o início de cada série
ciclo-ingest                     # incremental: o modo do agendamento diário
ciclo-ingest --fonte focus       # só as expectativas
ciclo-ingest --serie ipca        # uma série só
ciclo-calendario                 # próximas divulgações do IBGE
ciclo-transformar                # recalcula eixos (ajuste sazonal + momentum)
ciclo-regime                     # classifica o quadrante de regime
ciclo-validar                    # mede a defasagem contra a datação do CODACE
ciclo-qualidade                  # portões de qualidade (código 1 reprova)
pytest                           # suíte de testes
```

Consulta:

```python
from ciclo_br import storage
con = storage.conectar()
con.execute("SELECT * FROM obs WHERE serie_id = 'ibcbr_sa' ORDER BY data_referencia DESC LIMIT 12").df()
con.execute("SELECT * FROM revisoes ORDER BY revisado_em DESC").df()   # o que o BCB revisou
```

Três visões: `obs_bruto` (tudo, inclusive versões superadas — é o banco de
vintages), `obs` (a versão vigente de cada observação) e `revisoes` (apenas o
que a fonte alterou depois de publicar).

---

## Limitações declaradas

Estão detalhadas em [docs/metodologia.md](docs/metodologia.md). As principais:

- A classificação histórica é **ex-post**: não existem vintages públicos de séries
  brasileiras, então ela não simula a informação disponível em tempo real. O que
  estava sob controle — o ajuste sazonal, feito em janela expansiva — foi corrigido;
  o que não estava está declarado.
- A validação tem **três recessões**. Essa é a razão de não haver modelo estimado.
- Não há consenso do Focus para o IBC-Br. A surpresa do lado da atividade é medida
  pela **taxa de desocupação** (mensal) e pelo **PIB** (trimestral) — e o Focus só
  passou a pesquisar desocupação em **agosto de 2021**, então essa metade tem cinco
  anos de história, não vinte.
- O CODACE anuncia com anos de atraso — o vale de 2020 só foi datado em janeiro de
  2023. Se o classificador "ganhar" do comitê, isso não é mérito: ele tem a série
  completa e o comitê, na época, não tinha.
- A recessão da covid **nunca foi datada em meses** pelo CODACE. Os meses usados na
  validação são derivados dos trimestres publicados, e a linha está marcada como tal.
- O corte de crescimento em uso é a mediana do próprio histórico, o que deixa o
  sinal ligado em 81% dos meses entre 2008 e 2020. A alternativa está medida lado a
  lado no mesmo arquivo, em vez de argumentada em prosa.

---

## Roadmap

| Semana | Entrega | Status |
|---|---|---|
| 1 | Fichas das séries, cliente SGS, armazenamento append-only, backfill | ✅ concluída |
| 2 | Cliente Focus, calendário IBGE, GitHub Actions em cron, portões de qualidade | ✅ concluída |
| 3 | Ajuste sazonal recursivo, momentum, auditoria da quebra dos núcleos | ✅ concluída |
| 4 | Classificador de quadrante | ✅ concluída |
| 5 | Transcrição do CODACE e medição de defasagem | ✅ concluída |
| 6 | Surpresas realizado × Focus | — |
| 7 | Dashboard Streamlit (5 páginas, com Metodologia) | — |
| 8 | Briefing com LLM, modo replay para demonstração, publicação | — |

**Ordem de sacrifício**, se o prazo apertar: o LLM cai primeiro (o template
cobre), depois as surpresas de subgrupos, depois páginas do dashboard, depois as
séries de contexto. O núcleo inegociável é ingestão com data de coleta, CI verde,
quadrante histórico, validação contra o CODACE e a página de Metodologia.

---

## Licença

MIT.
