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

**Reprodutibilidade é numérica, não bit a bit.** O STL usa LOESS, que passa por
BLAS/LAPACK, e o backend numérico difere entre plataformas: a mesma entrada
produz valores que divergem nos últimos bits no Linux e no Windows. A CI compara
a camada derivada com tolerância, não por igualdade — sem isso o build reprovaria
só por ter rodado em outro sistema.

A tolerância precisa ser **maior que a granularidade da gravação**, e isso já
custou um falso negativo. Com os dois em 1e-6, um valor recalculado que se mexia
meio dígito na última casa mudava de arredondamento, a diferença gravada dava
exatamente 1e-6, e a comparação reprovava na fronteira — e a mediana expansiva do
classificador amplificava esse meio dígito até reprovar a camada de regime
inteira. Gravação em 6 casas, tolerância em 1e-5: uma ordem de grandeza de folga,
e ainda quatro ordens abaixo de qualquer diferença com significado econômico. Há
teste que trava a relação entre as duas constantes.

---

## 4c. Classificador de regime

**Os quatro estados.** O par de sinais dos dois eixos define o quadrante:

| | Inflação abaixo do corte | Inflação acima do corte |
|---|---|---|
| **Crescimento acima do corte** | Expansão | Aquecimento |
| **Crescimento abaixo do corte** | Desaceleração | Estagflação |

**Os dois cortes não são do mesmo tipo, e a diferença é deliberada.**

- **Crescimento: corte em zero.** Momentum negativo é atividade encolhendo. A
  pergunta vira "está caindo?", que é a mesma pergunta que a datação oficial de
  recessões responde — e por isso a validação da seção 7 tem sentido.
- **Inflação: mediana em janela expansiva.** Não existe zero natural para
  inflação; todo número positivo é alguma inflação. A referência é o próprio
  histórico, com o corte de um mês sendo a mediana dos dados até aquele mês —
  nunca da amostra inteira, o que reintroduziria o viés de look-ahead que o
  ajuste sazonal recursivo existe para eliminar. Há teste dedicado.

**O corte de crescimento já foi a mediana, e mudou por medição.** Até 12/09/2026
os dois eixos usavam a mediana do próprio histórico. A validação da seção 7
mostrou o custo: entre maio de 2008 e junho de 2020, o momentum ficou abaixo da
sua mediana expansiva em **81% dos meses**. Nessa taxa base, "detectou as três
recessões" quase não informa — um sinal ligado em quatro de cada cinco meses
acerta todas por construção — e a aparente antecipação de doze meses era só o
sinal ligando cedo e ficando ligado. Com corte em zero, fica ligado em 36% dos
meses e passa a acompanhar as recessões com atraso de três a quatro meses. A
tabela completa está na seção 7.3; a decisão está registrada na seção 9.

**Consequência que permanece, agora só do lado da inflação.** O eixo de inflação
mede desvio do passado brasileiro, não desvio da meta. Em junho de 2026 o núcleo
anualizado está em 4,2% — acima da meta de 3% — e ainda assim classificado como
"inflação baixa", porque a mediana histórica é 5,3%. É referência coerente e
verificável, mas responde "a inflação está baixa para os padrões do Brasil", não
"a inflação está dentro da meta". A alternativa — comparar contra a meta vigente
em cada mês — continua em aberto, e trocar exige apenas substituir a série de
corte, como foi feito do lado do crescimento.

**Classificação só a partir de maio de 2008**, 218 meses. Quem manda agora é o
corte de inflação: ele exige 60 meses de história, e o eixo começa em junho de
2003. O corte de crescimento em zero não exige nenhuma, mas o quadrante precisa
dos dois eixos, então vale o mais lento. As três recessões da janela de validação
ficam cobertas; os cinco primeiros anos da série, não.

**Persistência de 3 meses, confirmada por eixo.** Aplicada crua, a regra trocaria
de quadrante 43 vezes em 218 meses classificados, com episódios de dois meses ou
menos apresentados como mudança de regime. Uma troca só é confirmada após três
meses consecutivos do novo sinal, o que reduz as trocas para 28. Enquanto não
confirma, o estado anterior permanece vigente e o candidato fica marcado como
**pendente**, exibido no painel em vez de escondido.

A confirmação corre **em cada eixo separadamente**, e não no rótulo de quatro
estados. A primeira versão contava meses do quadrante inteiro, e a validação da
seção 7 mostrou que isso trava: com o crescimento firme acima do corte, alternar
entre "Expansão" e "Aquecimento" — que diferem apenas no eixo de inflação — zerava
o contador todo mês, e a virada do crescimento nunca confirmava. Na série real
isso produziu um episódio de contração de **116 meses**. O quadrante é a leitura
conjunta de duas afirmações independentes, e cada uma precisa do seu próprio prazo
de confirmação. Há teste de regressão nomeado.

O custo da persistência é atraso, e atraso é exatamente o que a seção 7 mede. O
prazo de três meses deixou de ser escolha de gosto: é o resultado da varredura
registrada lá.

**Episódios de contração do sinal** — os dez blocos contíguos em que o
crescimento confirmado está abaixo de zero, em 218 meses classificados
(verificação de 12/09/2026):

| Episódio | Duração | Recessão datada pelo CODACE |
|---|---|---|
| dez/2008 – mai/2009 | 6 m | set–dez/2008 |
| jan/2012 – jun/2012 | 6 m | — |
| mai/2014 – nov/2014 | 7 m | abr/2014 – dez/2016 |
| mar/2015 – mar/2017 | 25 m | abr/2014 – dez/2016 |
| jun/2018 – set/2018 | 4 m | — |
| mai/2019 – jul/2019 | 3 m | — |
| mai/2020 – set/2020 | 5 m | jan–jun/2020 |
| mai/2021 – set/2021 | 5 m | (fora da janela avaliável) |
| set/2023 – nov/2023 | 3 m | (fora da janela avaliável) |
| set/2025 – nov/2025 | 3 m | (fora da janela avaliável) |

A recessão de 2014-2016 aparece em dois blocos, com um respiro de três meses no
início de 2015 — é por isso que a seção 7.3 publica duas leituras da defasagem
no pico daquela recessão.

**Aderência dentro das recessões datadas:**

| Recessão | Quadrantes atribuídos |
|---|---|
| set–dez/2008 | Expansão 3, Desaceleração 1 |
| abr/2014 – dez/2016 | Estagflação 29, Aquecimento 4 |
| jan–jun/2020 | Expansão 4, Desaceleração 2 |

Os dois primeiros meses de cada recessão costumam ficar do lado errado, e isso é o
atraso de três a quatro meses medido na seção 7 aparecendo como rótulo. A recessão
de 2008 tem só quatro meses na datação mensal do CODACE, então o atraso consome
quase toda ela.

**A sequência de 2021-22** foi Expansão 4m → Desaceleração 4m → Estagflação 1m →
Aquecimento 15m, que reproduz a narrativa real: retomada, tropeço no meio de 2021,
e depois crescimento com inflação alta até o fim de 2022.

---

## 5. Medida de surpresa

**Definição.** Surpresa = valor realizado − mediana do Focus vigente na véspera da
divulgação. A unidade é a mesma do indicador (p.p.), o que torna a medida
interpretável sem normalização.

**Por que surpresa e não outlier estatístico.** Um detector de outlier responde
"esse número é raro" — e o IPCA de janeiro é sempre alto, então ele gritaria todo
janeiro. A pergunta que uma mesa faz é outra: o número foi diferente do que o
mercado esperava? Só a segunda tem conteúdo econômico.

### 5.1 As três peças

1. **O consenso é point-in-time por construção.** Cada linha da API de
   Expectativas traz `Data` (a apuração, diária) e `DataReferencia` (o período
   projetado). O armazenamento append-only guarda a trajetória inteira sem
   sobrescrever nada.
2. **A data de divulgação vem do calendário do IBGE**, que devolve o período de
   referência de cada evento. Sem ela não existe "véspera".
3. **O realizado carrega a data em que foi coletado**, o que permite distinguir
   primeira leitura de valor já revisado.

**A janela começa em 2017, e quem manda é o calendário.** A API de calendário do
IBGE responde vazio antes de 2017 — verificado produto a produto em 12/09/2026.
Estimar a data de divulgação a partir do mês de referência daria mais cobertura e
seria pior: o ganho viria de um número inventado.

### 5.2 Os pares

Só entram pares em que as duas pontas medem a mesma coisa na mesma unidade.

| Par | Realizado | Consenso | Divulgações medidas | Desde |
|---|---|---|---|---|
| IPCA | `ipca`, % ao mês | Focus IPCA mensal | 117 | jan/2017 |
| Desocupação | `desocupacao`, % da força de trabalho | Focus desocupação mensal | 60 | out/2021 |
| PIB | `pib_yoy`, % interanual | Focus PIB trimestral | 39 | mar/2017 |

**O câmbio ficou de fora de propósito.** A PTAX é preço de mercado contínuo, não
tem data de divulgação, e "surpresa" ali não seria surpresa de divulgação.

**O PIB exigiu amarrar a definição antes de parear.** A expectativa de "PIB Total"
do Focus é interanual — visível nos valores: −10,54% para o 2º tri de 2020 e
+12,76% para o 2º tri de 2021. Do lado do realizado, o BCB não publica o nome das
séries do SGS por API, então a definição da série 22099 foi estabelecida por
conferência e não por leitura de rótulo. A variação interanual calculada a partir
dela reproduz o número cheio do IBGE nos dois trimestres mais distintivos da
amostra (2T2020: −10,1%; 2T2021: +12,4%) e é a que mais se aproxima da mediana do
Focus ao longo de 94 trimestres — desvio padrão 0,62 p.p., contra 0,70 da série
22109 e 1,62 da 22110. A conferência está registrada na própria ficha, em
`config/series.yaml`.

### 5.3 Decisões de apuração

- **`baseCalculo` fixado em 0**, nunca misturado com 1. São janelas de apuração
  diferentes, com números de respondentes diferentes (140 contra 41 numa amostra
  de setembro de 2026); alternar entre elas compararia populações distintas.
- **Consenso da véspera é estrito.** Uma apuração feita no próprio dia da
  divulgação não estava disponível para quem operava antes de o número sair.
- **Mediana repetida não gera linha nova.** Se o consenso não mudou, não houve
  notícia. Isso tem uma consequência que a tabela expõe em vez de esconder: a
  coluna `dias_sem_mudanca` mede há quantos dias o consenso estava parado quando
  o número saiu — **não** há quantos dias ele estava desatualizado. Média de 6
  dias no IPCA e 15 na desocupação, que é série que o mercado revisita pouco.
- **Guardamos apenas os períodos de referência a até um mês da coleta** (seis, no
  trimestral). A API devolve 25 meses de projeção por coleta, mas o projeto só usa
  o consenso do período prestes a ser divulgado.

### 5.4 O resultado, e o viés que ele revela

Versionado em [`data/derivado/surpresa.csv`](../data/derivado/surpresa.csv),
216 divulgações, reverificado na CI.

| Par | n | Surpresa média | Desvio padrão | Dias sem mudança (média) |
|---|---|---|---|---|
| IPCA | 117 | **+0,01 p.p.** | 0,10 | 6 |
| PIB | 39 | **+0,41 p.p.** | 0,49 | 9 |
| Desocupação | 60 | **−0,17 p.p.** | 0,19 | 15 |

O IPCA é o teste da construção inteira, e ele passa: surpresa média de +0,01 p.p.
em 117 divulgações é o que se espera de um consenso não enviesado. Se a montagem
estivesse errada — consenso da referência trocada, data de divulgação deslocada —
essa média não seria zero.

**Os outros dois não têm média zero, e o motivo mais provável é revisão.** O
realizado gravado para 2017-2026 é o valor *vigente hoje*, não o primeiro print: o
backfill trouxe a série já revisada. O IPCA praticamente não é revisado, e sua
média é zero. O PIB é revisado para cima, e sua média é +0,41 p.p. A ordem dos
fatos é coerente com a explicação.

Na desocupação as duas explicações competem e os dados **não** decidem entre elas:
a janela começa no fim de 2021 e é quase toda de desemprego em queda, e projetar
uma tendência longa sempre fica atrás dela. Revisão da PNADC e conservadorismo do
consenso produziriam o mesmo sinal. Fica declarado como indeterminado.

**A coluna `primeira_leitura`** marca quais linhas o pipeline observou ao vivo —
coleta até quatro dias depois da divulgação. Hoje é uma só, a do IPCA de agosto de
2026. Ela vira verdadeira sozinha conforme o projeto roda, e é o que vai permitir,
daqui a alguns anos, medir a surpresa contra o primeiro print em vez do valor
revisado. É o mesmo argumento do banco de vintages da seção 4: o projeto não tem
como consertar o passado, mas pode parar de estragar o futuro.

### 5.5 Cobertura, com a limitação medida

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
escolha de desenho.

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

## 7. Validação contra a datação do CODACE

### 7.1 A cronologia, e por que ela deu trabalho

O CODACE (FGV/IBRE) é o comitê que data oficialmente os ciclos de negócios
brasileiros — o equivalente ao comitê do NBER nos Estados Unidos. Ele **não
publica a cronologia em formato estruturado**. A datação trimestral existe dentro
do texto de comunicados em PDF; a datação **mensal**, que é a que interessa aqui,
existe apenas como uma tabela em imagem.

A transcrição está em [`config/codace_cronologia.csv`](../config/codace_cronologia.csv),
com a proveniência de cada linha no cabeçalho do arquivo. A imagem de origem está
versionada em [`docs/fontes/codace_cronologia_mensal.png`](fontes/codace_cronologia_mensal.png),
tal como baixada, para que a transcrição possa ser conferida a olho.

**Convenção de datação.** O comunicado de 30/10/2017 define explicitamente, para
os trimestres: o pico "equivale ao final de um período de expansão, que será
seguido, no trimestre seguinte, pelo início de uma recessão"; o vale "equivale ao
trimestre final de uma recessão". A mesma convenção foi aplicada aos meses — a
recessão ocupa `pico`+1 até `vale`.

**A convenção é verificável, e foi verificada.** Pela datação mensal, a recessão
de 2014-2016 vai de abril de 2014 a dezembro de 2016: 33 meses. Pela datação
trimestral do comunicado de 2017, do 2º tri de 2014 ao 4º tri de 2016: 11
trimestres, também 33 meses. As duas fontes, publicadas em documentos diferentes,
fecham exatamente. Há teste que quebra se a transcrição escorregar um mês.

**Duas irregularidades da fonte, registradas em vez de alisadas:**

- Para 2008, a datação mensal põe o vale em dezembro de 2008 e a trimestral põe no
  1º trimestre de 2009. É divergência da própria fonte, não erro de transcrição.
- A recessão da covid **nunca foi datada em meses**. O CODACE publicou apenas
  pico no 4º tri de 2019 e vale no 2º tri de 2020 (comunicado de 31/01/2023). Os
  meses usados aqui são o último mês de cada trimestre, derivados por nós, e a
  linha está marcada como `granularidade = trimestral`. A defasagem medida contra
  essa recessão carrega a imprecisão de até um trimestre.

### 7.2 O que está sendo comparado — e o que não está

O CODACE data **recessões**: queda disseminada do nível de atividade, avaliada
por um comitê que olha um conjunto amplo de indicadores e se reúne quando quer. O
eixo de crescimento deste projeto é o momentum de **uma** série, comparado a um
corte, calculado todo mês. São objetos diferentes, e o sinal fica abaixo do corte
mais vezes do que a economia entra em recessão.

Por isso a métrica principal é a **defasagem** — quantos meses o sinal se antecipa
ou atrasa em cada ponta — e não taxa de acerto. Taxa de acerto penalizaria o sinal
por fazer exatamente aquilo para que foi construído.

- defasagem no pico = mês de entrada em contração − (`pico` + 1)
- defasagem no vale = mês de saída da contração − (`vale` + 1)

Negativo é antecipação, positivo é atraso. Antecipar não é automaticamente melhor:
um sinal que se antecipa sempre é um sinal que também grita em falso, e os dois
números só fazem sentido lidos junto com a fração de meses em que o sinal está
ligado.

**Janela de validação: três recessões** (2008, 2014-2016 e 2020). A classificação
começa em maio de 2008 e a datação do CODACE termina no vale do 2º tri de 2020.
Com três eventos, qualquer modelo com parâmetros estimados estaria sendo ajustado
ao ruído — é esta a razão de o classificador ser uma regra de sinal.

**Assimetrias declaradas:**

- O CODACE anuncia com anos de atraso: o vale de 2020 só foi datado em janeiro de
  2023. Se o classificador "ganhar" do comitê, isso **não é mérito** — ele tem a
  série completa e o comitê, na época, não tinha.
- Depois do último vale datado, a ausência de um novo pico não significa ausência
  de recessão. Episódios do sinal nessa ponta são contados à parte, como não
  avaliáveis.
- A recessão de 2008 começa quatro meses depois do início da classificação. Não há
  pista suficiente antes dela, e a linha está marcada como cobertura `parcial`: o
  truncamento só encurta a antecipação aparente, nunca a alonga.

### 7.3 O resultado

Gerado por `ciclo-validar`, versionado em
[`data/derivado/validacao_resumo.csv`](../data/derivado/validacao_resumo.csv) e
[`data/derivado/validacao_defasagens.csv`](../data/derivado/validacao_defasagens.csv),
e reverificado na CI. A janela avaliável tem 146 meses, dos quais 43 são de
recessão datada. A linha em negrito é a configuração em uso.

| Corte | Persistência | Recessões detectadas | Defasagem no pico (mediana) | Defasagem no vale | Trocas de quadrante | Episódios fora de recessão | Maior episódio | Fração da janela com sinal ligado |
|---|---|---|---|---|---|---|---|---|
| zero | 1 (sem regra) | 3/3 | +2 | +1 | 43 | 5 | 25 m | 40% |
| zero | 2 | 3/3 | +3 | +2 | 36 | 4 | 25 m | 38% |
| **zero** | **3** | **3/3** | **+4** | **+3** | **28** | **3** | **25 m** | **36%** |
| zero | 4 | 2/3 | +3,5 | +4 | 16 | 3 | 35 m | 36% |
| zero | 5 | 1/3 | +3 | +5 | 14 | 2 | 35 m | 32% |
| zero | 6 | 1/3 | +4 | +6 | 10 | 2 | 35 m | 32% |
| mediana | 1 (sem regra) | 3/3 | 0 | +2 | 52 | 8 | 44 m | 76% |
| mediana | 2 | 3/3 | +1 | +3 | 46 | 7 | 44 m | 77% |
| mediana | 3 | 3/3 | −12 | +4 | 33 | 4 | 54 m | 81% |
| mediana | 4 | 3/3 | −43 | +7 | 15 | 0 | 122 m | 91% |
| mediana | 5 | 3/3 | −36 | +8 | 13 | 0 | 116 m | 87% |
| mediana | 6 | 3/3 | −35 | +9 | 10 | 0 | 116 m | 87% |

A coluna "maior episódio" e a fração de meses com sinal ligado não são decoração.
Sem elas, a degeneração apareceria como o melhor resultado da tabela: um prazo de
confirmação longo demais faz o sinal virar um único bloco que cobre tudo, detecta
todas as recessões e não tem nenhum falso alarme, porque nunca desliga. É o que
acontece com a mediana e persistência 4, onde um único episódio de **122 meses**
engole as recessões de 2014-2016 e de 2020 e produz a "antecipação" de 112 meses
que aparece na tabela detalhada.

**Recessão a recessão, na configuração em uso:**

| Recessão | Datação | Episódio do sinal | Defasagem no pico | No vale | Cobertura |
|---|---|---|---|---|---|
| 2008 | set–dez/2008 (mensal) | dez/2008 – mai/2009 | +3 | +5 | 1 de 4 meses |
| 2014-2016 | abr/2014 – dez/2016 (mensal) | mar/2015 – mar/2017 | +11 (ou +1) | +3 | 22 de 33 meses |
| 2020 | jan–jun/2020 (trimestral) | mai–set/2020 | +4 | +3 | 2 de 6 meses |

**As duas defasagens de 2014.** O sinal ligou em maio de 2014, um mês depois do
início da recessão, desligou por três meses no começo de 2015 e religou. A regra
de associação escolhe o bloco de maior sobreposição, que é o segundo — daí +11. A
leitura pelo primeiro bloco a tocar a recessão dá +1. As duas estão na coluna
`defasagem_pico` e `defasagem_pico_primeiro` do CSV, em vez de uma delas virar
nota de rodapé conveniente.

**A recessão de 2008 é o pior caso, e por um motivo estrutural.** A datação mensal
do CODACE lhe dá quatro meses. Com atraso de três meses, o sinal pega só o último.
Uma regra de momentum sobre dado publicado com 45 a 60 dias de defasagem não tem
como fazer melhor numa recessão tão curta — e isso é limite do método, não ajuste
pendente.

### 7.4 O que a tabela decidiu

**O corte do eixo de crescimento passou da mediana histórica para zero.** Era a
escolha original do projeto, e a medição a derrubou. Com a mediana, o sinal ficava
ligado em 81% dos meses da janela: nessa taxa base, "detectou 3 de 3 recessões" é
quase tautologia, e a antecipação de doze meses era o sinal ligando cedo e ficando
ligado, não previsão. Com corte em zero, fica ligado em 36% dos meses, o maior
episódio cai de 54 para 25 meses, e a defasagem vira +4 no pico e +3 no vale.

O sinal deixou de "antecipar" e passou a acompanhar com atraso curto. Isso é
piora aparente e melhora real: acompanhar com três a quatro meses de atraso é o
comportamento honesto de uma regra de momentum sobre dado publicado com 45 a 60
dias de defasagem, enquanto antecipar doze meses era artefato da taxa base.

**O prazo de persistência está fixado em 3, e por evidência.** Com corte em zero,
3 é o maior valor que ainda detecta as três recessões — em 4 uma delas é perdida.
Com o corte anterior, 3 era o maior valor que ainda não degenerava em bloco único.
Os dois critérios, em dois cortes diferentes, apontam o mesmo número. Os valores 1
e 2 continuam disponíveis e custam 36 a 43 trocas de quadrante em 218 meses —
regime que muda duas vezes por ano não é regime.

**O que continua aberto.** O corte do eixo de inflação segue sendo a mediana
expansiva, pelo motivo da seção 4c: não há zero natural para inflação. A
alternativa seria comparar contra a meta vigente em cada mês, o que exigiria
versionar a série histórica de metas do CMN. Não está feito, e a consequência
— núcleo a 4,2% classificado como "inflação baixa" porque a mediana é 5,3% —
está declarada em vez de escondida.

**As duas versões continuam sendo medidas lado a lado.** A varredura não foi
apagada depois da decisão: `ciclo-validar` recalcula as doze combinações a cada
execução e a CI reprova se a tabela sair de sincronia com o classificador. Uma
decisão tomada por medição precisa continuar medível, ou vira folclore de
repositório.

---

## 8. O painel

Cinco páginas: **Regime**, **Séries**, **Surpresas**, **Validação** e
**Metodologia**. A última não é apêndice — é o motivo de as outras quatro terem
o direito de existir. Um painel macro que mostra um classificador sem mostrar
contra o que ele foi validado, com que atraso ele responde e o que ele não
consegue afirmar está vendendo confiança que não construiu.

### 8.1 A regra: o painel só lê arquivo

Nenhum módulo do painel importa a camada de ingestão nem um cliente HTTP. Tudo o
que aparece na tela saiu de um arquivo versionado no repositório:
`data/derivado/regime.parquet`, `validacao_defasagens.csv`,
`validacao_resumo.csv`, `surpresa.csv`, `data/calendario.parquet`, os Parquet de
série bruta, `config/series.yaml`, `config/codace_cronologia.csv` e este próprio
documento.

A regra é verificada por **dois testes**, e não por disciplina:

1. Um lê o código-fonte de cada módulo do painel e reprova qualquer import de
   `requests`, `urllib`, `http`, `socket` ou `ciclo_br.ingestion`.
2. O outro importa o painel com os módulos de ingestão retirados de
   `sys.modules` e confere que nenhum voltou — o que pega o caminho indireto,
   em que um módulo do painel importasse `ciclo_br.surpresa` e arrastasse a
   ingestão junto sem nunca escrever a palavra.

Dois caminhos de artefato (`surpresa.csv` e `calendario.parquet`) foram movidos
para `config.py` justamente por isso: eram declarados em módulos que falam com
a rede, e o painel precisava conhecê-los sem passar por lá.

**Três coisas dependem dessa regra.** A tela não pode divergir do pipeline, já
que ela não recalcula nada e os portões de CI conferem os arquivos. O painel
abre sem rede e sem credencial, inclusive offline. E, como o estado inteiro do
projeto está em arquivo versionado, voltar o repositório a um commit anterior faz
o painel mostrar o que ele mostrava naquele dia — sem nenhum modo especial.

### 8.2 O que o painel não tem, de propósito

**Não há seletor de "como estava em março de 2015".** Reconstruir aquela tela com
o dado revisado de hoje seria o mesmo viés de look-ahead que o ajuste sazonal
recursivo existe para eliminar, e sairia mais bonito do que a verdade permite. A
única volta ao passado honesta é a do parágrafo acima: o commit daquele dia.

**Não há cache.** As tabelas têm centenas de linhas e a leitura custa
milissegundos; em troca, some a classe de bug mais irritante de um painel de
dados, que é a tela continuar mostrando o número velho depois de o pipeline
rodar.

**Não há número calculado na tela.** O resumo do regime exibido é o mesmo objeto
que o comando `ciclo-regime` imprime no log — há teste comparando os dois. O
painel escolhe a linha da varredura que corresponde ao classificador em uso, em
vez de assumir; sem isso, ele poderia exibir a defasagem de uma configuração que
não é a que gerou os quadrantes ao lado.

### 8.3 Três decisões de gráfico que não são estéticas

**O mapa de quadrantes plota distância ao corte, não o valor do eixo.** O corte
de inflação se move — é a mediana expansiva do próprio histórico. Com valores
crus, a fronteira do quadrante seria uma linha que anda e o leitor teria que
adivinhar onde ela estava em cada mês. Plotando a distância, a fronteira é o zero
em todos os meses, e o quadrante que se vê é exatamente o que o classificador
diz. O domínio é forçado a conter o zero nos dois eixos, para que a fronteira
esteja sempre à vista.

**Os dois eixos não dividem a mesma escala.** O momentum de crescimento foi de
−38 a +40 na covid; o eixo de inflação vive entre 0 e 13. Num gráfico só, a
inflação viraria uma linha reta. São dois painéis empilhados com o eixo do tempo
compartilhado, e a tarja de quadrantes embaixo.

**As faixas de recessão são aparadas na janela do gráfico.** A cronologia do
CODACE começa em 1980 e o eixo de crescimento, em 2003. Sem o recorte, metade do
gráfico seria faixa cinza sobre espaço vazio e o período com dado ficaria
espremido na direita.

### 8.4 Procedência na tela

A página de Metodologia abre com a lista de todo arquivo que o painel leu, com
tamanho, data de geração e o comando que o produz. É a resposta literal a "de
onde vem esse número", e é também o lugar onde a **ausência** de um artefato
aparece como informação: falta de arquivo vira instrução com o comando que o
gera, não traceback. Quem clona o repositório e ainda não rodou o pipeline
descobre isso pela tela.

O documento renderizado nessa página é este arquivo, e não um resumo dele. Duas
versões do mesmo argumento divergiriam na primeira mudança, e a que ficaria
desatualizada seria justamente a que o leitor vê.

---

## 9. Registro de decisões

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
| 2026-09-12 | Persistência confirmada por eixo, não pelo rótulo do quadrante | ruído no outro eixo travava a virada; episódio de 116 meses (seção 4c) |
| 2026-09-12 | Prazo de persistência fixado em 3 meses | maior valor que não degenera nem perde recessão, nos dois cortes (seção 7.4) |
| 2026-09-12 | Cronologia do CODACE transcrita à mão, com a imagem de origem versionada | a fonte não publica formato estruturado; transcrição precisa ser auditável (seção 7.1) |
| 2026-09-12 | Corte do eixo de crescimento trocado da mediana expansiva para zero | com a mediana o sinal ficava ligado em 81% dos meses; a taxa base tornava a detecção vazia (seção 7.4) |
| 2026-09-12 | Corte do eixo de inflação mantido na mediana expansiva | não há zero natural para inflação; a alternativa exigiria versionar a série de metas do CMN (seção 7.4) |
| 2026-09-12 | Calendário do IBGE promovido a fonte das datas de divulgação, com backfill desde 2017 | sem a data em que o número saiu não existe consenso da véspera (seção 5.1) |
| 2026-09-12 | Janela da surpresa começa em 2017 em vez de estimar datas de divulgação | cobertura maior viria de data inventada (seção 5.1) |
| 2026-09-12 | PIB entra pela série SGS 22099, com a definição estabelecida por conferência | o BCB não publica nome de série por API; a ficha registra o que foi testado (seção 5.2) |
| 2026-09-12 | Câmbio fora da medida de surpresa | PTAX é preço contínuo, não tem divulgação com hora marcada (seção 5.2) |
| 2026-09-12 | Tolerância de comparação uma ordem acima da granularidade de gravação | iguais, o arredondamento criava diferença de exatamente 1e-6 e reprovava a CI (seção 4b) |
| 2026-09-13 | Painel só lê arquivo versionado, sem importar a ingestão | a tela não pode divergir do pipeline, e é o que torna o replay por commit possível (seção 8.1) |
| 2026-09-13 | Sem seletor de "como estava em data X" no painel | reconstruir o passado com dado revisado de hoje é o viés que a camada derivada existe para evitar (seção 8.2) |
| 2026-09-13 | Página de Metodologia renderiza `docs/metodologia.md`, não um resumo | duas versões do mesmo argumento divergem, e a desatualizada seria a que o leitor vê (seção 8.4) |
| 2026-09-13 | Mapa de quadrantes em distância ao corte, não em valor do eixo | o corte de inflação se move; em valores crus a fronteira seria uma linha que anda (seção 8.3) |
