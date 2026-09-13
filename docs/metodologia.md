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

**Persistência de 3 meses, confirmada por eixo.** Aplicada crua, a regra trocaria
de quadrante 52 vezes em 277 meses, com um terço dos episódios durando dois meses
ou menos — ruído apresentado como mudança de regime. Uma troca só é confirmada
após três meses consecutivos do novo sinal, o que reduz as trocas para 33.
Enquanto não confirma, o estado anterior permanece vigente e o candidato fica
marcado como **pendente**, exibido no painel em vez de escondido.

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

O CODACE data **recessões**: queda disseminada do nível de atividade. O eixo de
crescimento deste projeto mede **momentum abaixo de um corte**. São objetos
diferentes, e o sinal fica abaixo do corte muito mais vezes do que a economia
entra em recessão.

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
recessão datada.

| Corte | Persistência | Recessões detectadas | Defasagem no pico (mediana) | Defasagem no vale | Trocas de quadrante | Episódios fora de recessão | Maior episódio | Fração da janela com sinal ligado |
|---|---|---|---|---|---|---|---|---|
| mediana | 1 (sem regra) | 3/3 | 0 | +2 | 52 | 8 | 44 m | 76% |
| mediana | 2 | 3/3 | +1 | +3 | 46 | 7 | 44 m | 77% |
| **mediana** | **3 (vigente)** | **3/3** | **−12** | **+4** | **33** | **4** | **54 m** | **81%** |
| mediana | 4 | 3/3 | −43 | +7 | 15 | 0 | 122 m | 91% |
| mediana | 5 | 3/3 | −36 | +8 | 13 | 0 | 116 m | 87% |
| mediana | 6 | 3/3 | −35 | +9 | 10 | 0 | 116 m | 87% |
| zero | 1 (sem regra) | 3/3 | +2 | +1 | 43 | 5 | 25 m | 40% |
| zero | 2 | 3/3 | +3 | +2 | 36 | 4 | 25 m | 38% |
| zero | **3** | 3/3 | +4 | +3 | 28 | 3 | 25 m | 36% |
| zero | 4 | 2/3 | +3,5 | +4 | 16 | 3 | 35 m | 36% |
| zero | 5 | 1/3 | +3 | +5 | 14 | 2 | 35 m | 32% |
| zero | 6 | 1/3 | +4 | +6 | 10 | 2 | 35 m | 32% |

A coluna "maior episódio" e a fração de meses com sinal ligado não são decoração.
Sem elas, a degeneração apareceria como o melhor resultado da tabela: um prazo de
confirmação longo demais faz o sinal virar um único bloco que cobre tudo, detecta
todas as recessões e não tem nenhum falso alarme, porque nunca desliga. É o que
acontece com a mediana e persistência 4, onde um único episódio de **122 meses**
engole as recessões de 2014-2016 e de 2020 e produz a "antecipação" de 112 meses
que aparece na tabela detalhada.

### 7.4 O que a tabela decide, e o que ela abre

**O prazo de persistência está decidido em 3, e por evidência.** Com o corte
vigente, 3 é o maior valor que ainda não degenera: em 4 o sinal vira um bloco
único. Com o corte alternativo, 3 é o maior valor que ainda detecta as três
recessões: em 4 uma delas é perdida. Os dois critérios, independentes, apontam o
mesmo número. Os valores 1 e 2 continuam disponíveis e custam 46 a 52 trocas de
quadrante — regime que muda quatro vezes por ano não é regime.

**A tabela abriu uma questão que não estava no roteiro: o corte de crescimento.**
Entre maio de 2008 e junho de 2020, o momentum brasileiro ficou abaixo da sua
própria mediana expansiva em **81% dos meses**. Nessa taxa base, "detectou 3 de 3
recessões" quase não informa: um sinal ligado em quatro de cada cinco meses acerta
todas por construção. A antecipação de 12 meses também não é antecipação de
verdade — é o sinal ligando cedo e ficando ligado.

Trocando apenas o corte de crescimento por **zero** — isto é, perguntando "a
atividade está encolhendo?" em vez de "está crescendo abaixo do padrão histórico?"
— o sinal passa a ficar ligado em 36% dos meses, o maior episódio cai de 54 para
25 meses, e a defasagem vira **+4 meses no pico e +3 no vale**. O sinal deixa de
antecipar e passa a acompanhar com atraso curto, que é o comportamento honesto de
uma regra de momentum sobre dados publicados com 45 a 60 dias de defasagem.

**Nada foi trocado.** O classificador continua usando a mediana expansiva, que é a
decisão registrada na seção 8. As duas versões são medidas lado a lado e
versionadas justamente para que a escolha possa ser revista com números em vez de
opinião — a troca custa uma linha, e a seção 4c diz qual.

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
| 2026-09-12 | Persistência confirmada por eixo, não pelo rótulo do quadrante | ruído no outro eixo travava a virada; episódio de 116 meses (seção 4c) |
| 2026-09-12 | Prazo de persistência fixado em 3 meses | maior valor que não degenera nem perde recessão, nos dois cortes (seção 7.4) |
| 2026-09-12 | Cronologia do CODACE transcrita à mão, com a imagem de origem versionada | a fonte não publica formato estruturado; transcrição precisa ser auditável (seção 7.1) |
| 2026-09-12 | Corte de crescimento mantido na mediana expansiva, com a alternativa medida ao lado | a decisão é do autor do projeto; a validação entrega o número, não a troca (seção 7.4) |
