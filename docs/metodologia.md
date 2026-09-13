# Metodologia

Documento vivo. Cada decisão metodológica entra aqui quando é tomada, com a
evidência que a sustenta. É desta página que a aba **Metodologia** do dashboard
é escrita.

---

## 1. O que o projeto afirma, e o que não afirma

O projeto classifica o estado do ciclo macroeconômico brasileiro em quatro
quadrantes de **crescimento × inflação**, e mede **surpresas** de divulgação
contra o consenso do Focus.

Ele **não** faz previsão, **não** dá recomendação de investimento, e **não**
usa modelo de linguagem para decidir nada: o LLM só verbaliza um conjunto de
fatos já calculados, sem acesso a nenhum número fora deles.

---

## 2. Definição dos eixos

| Eixo | Série | Transformação |
|---|---|---|
| Crescimento | IBC-Br com ajuste sazonal (SGS 24364) | variação % 3m/3m anualizada |
| Inflação | IPCA núcleo por médias aparadas com suavização (SGS 4466) | MM3M dessazonalizada e anualizada |

**Por que momentum e não nível.** "Crescimento alto" e "crescimento acelerando"
produzem classificações diferentes e às vezes opostas — em 2021 o Brasil teve
nível altíssimo por efeito-base de 2020 e momentum já em queda. Momentum reage
cedo e não fica refém da base de comparação.

**Por que núcleo e não IPCA cheio.** Um painel que lê choque de alimento ou
combustível como mudança de regime erra. O IPCA cheio e o acumulado em 12 meses
ficam no projeto para exibição, e deliberadamente não alimentam o classificador:
o acumulado em 12 meses vira de sinal muitos meses depois da virada real.

---

## 3. Auditoria da quebra metodológica dos núcleos (dez/2025)

**Problema.** O Banco Central alterou a metodologia dos núcleos do IPCA e
congelou as versões anteriores em códigos separados (29675, 29677–29682),
encerradas em nov/2025, enquanto os códigos canônicos (4466 entre eles) seguem
com a metodologia nova. Como o eixo de inflação atravessa 1996–2026, uma quebra
não tratada produziria um degrau artificial bem no trecho mais relevante.

**Teste** (executado em 12/09/2026, sobre o vintage corrente das duas séries):

| | |
|---|---|
| Cobertura de 4466 | jul/1994 – ago/2026 (386 meses) |
| Cobertura de 29675 | fev/1996 – nov/2025 (358 meses) |
| Meses sobrepostos | 358 |
| Meses divergentes | 3 |
| Maior diferença absoluta | 0,01 p.p. |

**Conclusão.** As duas séries são numericamente a mesma no trecho comum, a menos
de arredondamento. Isso indica que o BCB **recalculou o histórico** sob a nova
metodologia. Nenhuma emenda é aplicada; 4466 é usada inteira.

**Limitação desta auditoria.** O teste compara o *vintage atual* das duas
séries. Ele não demonstra que o valor publicado em, digamos, 2010 fosse igual ao
que a série mostra hoje para 2010 — isso exigiria vintages históricos, que não
existem publicamente para séries brasileiras (ver seção 4).

A série congelada permanece no projeto como evidência reproduzível da auditoria,
com papel `auditoria`, e não entra em nenhum cálculo.

---

## 4. Revisões, vintages e viés de look-ahead

**O que não existe.** Não há base de dados em tempo real pública para séries
macro brasileiras. A API do SGS entrega apenas a revisão corrente; o IPEAData não
tem dimensão de vintage; o Brasil está ausente dos compêndios internacionais de
fontes de dados em tempo real. O único vintage sistemático disponível é o do
lado das *expectativas*, via API do Focus, que é point-in-time por construção.

**Consequências declaradas.**

1. A classificação histórica é **ex-post**. Ela usa a série tal como revisada
   hoje, e portanto não simula a informação disponível em tempo real.
2. O ajuste sazonal é feito em **janela expansiva**: para classificar um mês, o
   dessazonalizador roda apenas com dados até aquele mês. Isso elimina a parte do
   look-ahead que estava sob nosso controle. A parte que não está — a revisão do
   dado bruto, e o ajuste sazonal que a própria fonte aplica com amostra completa
   no IBC-Br e na produção industrial — permanece, e é declarada aqui.
3. A partir da primeira coleta, o projeto **constrói o próprio banco de
   vintages**: nada é sobrescrito, e cada observação é gravada com a data em que
   foi coletada. Revisões retroativas viram linhas novas, não correções
   silenciosas. Isso não recupera o passado, mas torna o futuro auditável.

---

## 4b. Camada derivada: ajuste sazonal recursivo e momentum

**Ajuste sazonal em janela expansiva.** Para obter o valor dessazonalizado de um
mês, o decompositor é reestimado usando **apenas os dados até aquele mês**. Isso
é verificado por teste: o valor dessazonalizado de um período tem que ser idêntico
quer a série termine ali, quer ela continue por mais dois anos. Se mudasse, o
passado estaria sendo reescrito com informação que não existia, e o backtest
viraria ficção.

Só duas séries são dessazonalizadas por nós — **taxa de desocupação** e **núcleo
do IPCA** — porque IBC-Br e produção industrial já vêm ajustados da fonte. O
ajuste move o núcleo em 0,08 p.p. na média.

**STL, não X-13ARIMA-SEATS.** O X-13 é o padrão de órgão estatístico, mas depende
de um binário do Census Bureau que não existe no runner do GitHub Actions nem no
Streamlit Cloud. O STL é Python puro e roda em qualquer lugar. O custo é
conhecido e aceito: o STL não trata efeito de calendário nem de dias úteis — o
que pesa pouco nas duas séries em questão, e pesaria muito na produção industrial,
que por sorte já vem ajustada da fonte.

**As duas transformações.**

| Eixo | Entrada | Transformação |
|---|---|---|
| Crescimento | IBC-Br dessazonalizado (nível) | média de 3 meses sobre os 3 anteriores, anualizada |
| Inflação | núcleo dessazonalizado (taxa % a.m.) | 3 meses **compostos** e anualizados |

A composição é multiplicativa, não média aritmética: 1% ao mês por três meses não
é 3% no trimestre, e para inflação essa diferença não é detalhe de arredondamento.

**Aderência a episódios conhecidos** (verificação feita em 12/09/2026):

| Episódio | Eixo de crescimento |
|---|---|
| Recessão de 2014-16 | 18 de 18 meses negativos, mínimo −10,1 |
| COVID (2020) | mínimo −38,2 e máximo +40,3 — o tombo e o repique |
| Crise de 2008-09 | 6 de 10 meses negativos, mínimo −20,5 |
| Choque de 2021-22 | eixo de inflação em 8,2% anualizado na média, pico de 13,4 |

**Limitação assumida.** O momentum 3m/3m sobre série mensal é volátil por
construção — em 2020 ele varia de −38 a +40. Isso é fidelidade ao dado, não
defeito, mas significa que uma regra de sinal aplicada cru produziria troca de
quadrante a cada oscilação em torno de zero. O tratamento disso é decisão da
camada de classificação, não desta.

---

## 4c. Classificador de regime

**Os quatro estados.** O par de sinais dos dois eixos define o quadrante:

| | Inflação abaixo do corte | Inflação acima do corte |
|---|---|---|
| **Crescimento acima do corte** | Expansão | Aquecimento |
| **Crescimento abaixo do corte** | Desaceleração | Estagflação |

**Os cortes são a mediana em janela expansiva de cada eixo.** O corte de um mês é
a mediana dos dados até aquele mês — nunca da amostra inteira. Isso não é detalhe
de implementação: a mediana de amostra cheia reintroduziria o viés de look-ahead
que o ajuste sazonal recursivo existe para eliminar, porque o corte de 2015
estaria usando dados de 2020. Há teste dedicado a essa propriedade.

**Consequência assumida da escolha de corte.** Usar a mediana do próprio histórico
significa que o eixo mede desvio do passado brasileiro, não desvio da meta de
inflação. Em setembro de 2026, por exemplo, o núcleo anualizado está em 4,2% — 
acima da meta de 3%, e ainda assim classificado como "inflação baixa", porque a
mediana histórica é 5,3%. É uma referência coerente e verificável, mas responde
"a inflação está baixa para os padrões do Brasil", não "a inflação está dentro da
meta". A alternativa — comparar contra a meta vigente em cada mês — foi
considerada e descartada; trocar exige apenas substituir a série de corte.

**Classificação só a partir de maio de 2008.** O corte expansivo exige 60 meses de
história e o eixo de crescimento começa em junho de 2003. As três recessões da
janela de validação (2008-09, 2014-16 e 2020) ficam cobertas, mas os cinco
primeiros anos da série não são classificados.

**Persistência de 3 meses.** Aplicada crua, a regra trocaria de quadrante 52 vezes
em 277 meses, com um terço dos episódios durando dois meses ou menos — ruído
apresentado como mudança de regime. Uma troca só é confirmada após três meses
consecutivos do novo sinal, o que reduz as trocas para 24. Enquanto não confirma,
o estado anterior permanece vigente e o candidato fica marcado como **pendente**,
exibido no painel em vez de escondido.

O custo da persistência é atraso, e atraso é exatamente o que a validação da
seção 7 mede. Por isso a camada guarda também o quadrante **sem** persistência: a
defasagem contra a cronologia do CODACE será medida nas duas versões, e o
parâmetro deixa de ser escolhido por gosto para ser escolhido contra evidência.

**Aderência a episódios conhecidos** (verificação de 12/09/2026):

| Episódio | Classificação |
|---|---|
| 2015-16 | Estagflação em 18 de 18 meses |
| COVID (2020) | Desaceleração, 6 meses |
| 2021-22 | Aquecimento 6m → Estagflação 4m → Desaceleração 3m |
| 2008-09 | Desaceleração, 8 meses |

A sequência de 2021-22 reproduz a narrativa real do período: repique com inflação,
depois o crescimento morre e a inflação permanece.

---

## 5. Medida de surpresa

**Definição.** Surpresa = valor realizado − mediana do Focus vigente na véspera da
divulgação. A unidade é a mesma do indicador (p.p. para inflação), o que torna a
medida interpretável sem normalização.

**Por que surpresa e não outlier estatístico.** Um detector de outlier responde
"esse número é raro" — e o IPCA de janeiro é sempre alto, então ele gritaria todo
janeiro. A pergunta que uma mesa faz é outra: o número foi diferente do que o
mercado esperava? Só a segunda tem conteúdo econômico.

**Como o consenso da véspera é reconstruído.** A API de Expectativas do Banco
Central é point-in-time por construção: cada linha traz `Data` (a data da
apuração, diária) e `DataReferencia` (o período projetado). O consenso relevante é
a última mediana apurada **antes** da data de divulgação. O armazenamento
append-only guarda essa trajetória sem sobrescrever nada, e a consulta é um
`ORDER BY data_coleta DESC LIMIT 1` com corte na data do release.

**Decisões de apuração.**

- `baseCalculo` fixado em **0** e nunca misturado com 1. São janelas de apuração
  diferentes, com números de respondentes diferentes (140 contra 41 numa amostra
  de setembro de 2026); alternar entre elas compararia populações distintas.
- Guardamos apenas os períodos de referência a até um mês da coleta (seis meses,
  no trimestral). A API devolve 25 meses de projeção por coleta, mas o projeto só
  usa o consenso do período prestes a ser divulgado; o resto seriam ~160 mil
  linhas por indicador que nenhuma parte do sistema consulta.
- Mediana repetida não gera linha nova: se o consenso não mudou, não houve
  notícia.

**Cobertura, com a limitação medida.**

| Série de expectativa | Coletas desde |
|---|---|
| IPCA mensal | jan/2003 |
| Câmbio mensal | jan/2003 |
| PIB total trimestral | jan/2003 |
| Taxa de desocupação mensal | **set/2021** |

A desocupação é a única variável cíclica com consenso mensal — não existe Focus
para o IBC-Br — e ela só passou a ser pesquisada em 2021. Na prática, o pilar de
surpresa é forte do lado da inflação e curto do lado da atividade, onde se apoia
em cinco anos de desocupação mais o PIB trimestral. Isso é limitação de fonte, não
escolha de desenho, e está declarado aqui em vez de escondido atrás de um gráfico.

---

## 6. Detecção de divulgação

O gatilho é o **diff da própria série**: a cada execução as APIs são reconsultadas
sobre uma janela recente e comparadas com o que já está gravado. Observação
inédita ou valor alterado disparam; caso contrário o pipeline não escreve nada.

Duas consequências desse desenho:

1. **Revisão retroativa é capturada de graça.** O mesmo mecanismo que detecta dado
   novo detecta o Banco Central mexendo num mês antigo — um evento que interessa a
   economista e que praticamente nenhum painel registra.
2. **Não há dependência crítica de calendário.** O calendário do IBGE é consultado,
   mas só alimenta o painel de próximas divulgações e adensa a frequência de
   consulta. Se ele sair do ar, a ingestão continua. O calendário do Banco Central
   existe, porém é endpoint interno do site, sem contrato público, e por isso ficou
   de fora.

---

## 7. Validação

A cronologia oficial de ciclos do CODACE (FGV/IBRE) não é publicada em formato
estruturado — é imagem e comunicados em PDF — e será transcrita à mão para um CSV
versionado, com citação do comunicado de origem.

A janela de sobreposição entre o IBC-Br (desde 2003) e a datação do CODACE (que
termina no vale do 2º tri/2020) contém **três recessões**: 2008-09, 2014-16 e
2020.

**É por isso que o classificador é uma regra de sinal e não um modelo
estimado.** Com três eventos de validação, qualquer modelo com muitos parâmetros
estaria sendo ajustado ao ruído. A métrica principal não é taxa de acerto e sim
**defasagem**: quantos meses antes ou depois o sinal vira em relação à data
oficial. Um classificador que acerta todas as recessões cinco meses atrasado é
inútil, e a matriz de confusão sozinha não mostra isso.

**Assimetria a declarar:** o CODACE anuncia com muitos meses de atraso. Se o
classificador "ganhar" do comitê, isso não é mérito — ele tem a série completa e
o comitê, na época, não tinha.

---

## 8. Registro de decisões

| Data | Decisão | Motivo |
|---|---|---|
| 2026-09-12 | Eixos por momentum, não por nível | efeito-base contamina o nível |
| 2026-09-12 | Núcleo 4466 no eixo de inflação | choque de oferta não é mudança de regime |
| 2026-09-12 | Armazenamento append-only em Parquet versionado no Git | revisão vira evento observável; constrói vintages próprios |
| 2026-09-12 | Sem emenda na quebra dos núcleos | auditoria mostrou histórico recalculado (seção 3) |
| 2026-09-12 | Surpresa vs. Focus em vez de outlier estatístico | outlier não tem conteúdo econômico |
| 2026-09-12 | `baseCalculo` 0, nunca misturado com 1 | são amostras de respondentes diferentes |
| 2026-09-12 | Guardar só a janela útil de referência do Focus | 90% do volume é projeção que o projeto não usa |
| 2026-09-12 | Diff da série como único gatilho; calendário auxiliar | evita ponto único de falha e captura revisão de graça |
| 2026-09-12 | Portões de qualidade reprovam o build | pipeline que quebra alto vale mais que um que grava lixo em silêncio |
