"""Página de validação: o classificador confrontado com a datação oficial.

A métrica principal é a **defasagem**, não a taxa de acerto, e a página existe em
boa parte para justificar isso. O CODACE data recessões — queda disseminada do
nível de atividade, avaliada por um comitê olhando um conjunto amplo de
indicadores. O eixo de crescimento daqui é o momentum de uma série só contra um
corte. São objetos diferentes, e taxa de acerto puniria o sinal por fazer
exatamente aquilo para que foi construído.

A página também mostra a varredura inteira, e não só a configuração escolhida.
Uma tabela que mostra apenas a opção vencedora é propaganda; o que torna a
escolha verificável é o custo das outras estar visível ao lado.
"""

from __future__ import annotations

import pandas as pd
import streamlit as st

from ... import artefatos as dados
from ... import formato
from .. import componentes, graficos


@componentes.protegido
def renderizar() -> None:
    componentes.titulo(
        "Validação contra o CODACE",
        "Quantos meses o sinal se atrasa em relação às recessões datadas pelo "
        "Comitê de Datação de Ciclos Econômicos da FGV/IBRE.",
    )

    _o_que_se_compara()
    st.divider()
    _cronologia()
    st.divider()
    _resultado()
    st.divider()
    _varredura()
    st.divider()
    _limites()


def _o_que_se_compara() -> None:
    esquerda, direita = st.columns(2)
    esquerda.markdown(
        "**O que está sendo comparado**\n\n"
        "O CODACE data recessões: queda disseminada do nível de atividade, "
        "julgada por um comitê sobre um conjunto amplo de indicadores. O eixo de "
        "crescimento deste projeto é o momentum de **uma** série comparado a um "
        "corte. São objetos diferentes, e o sinal fica abaixo do corte bem mais "
        "vezes do que a economia entra em recessão."
    )
    direita.markdown(
        "**Por que defasagem e não taxa de acerto**\n\n"
        "Taxa de acerto penalizaria o sinal por fazer o que foi construído para "
        "fazer. Pior: com o sinal ligado na maior parte do tempo, \"detectou "
        "todas as recessões\" é quase tautologia. Por isso a tabela abaixo "
        "sempre traz junto **a fração da janela com o sinal ligado** e **o maior "
        "episódio** — as duas colunas que expõem um sinal que acerta tudo porque "
        "nunca desliga."
    )

    st.info(
        "**Convenção de datação.** O pico é o último mês de expansão e o vale é "
        "o último mês de recessão, como o próprio CODACE define. Logo a recessão "
        "ocupa `pico`+1 até `vale`. Defasagem **negativa é antecipação** e "
        "**positiva é atraso** — e antecipar não é necessariamente melhor: um "
        "sinal que se antecipa sempre também grita em falso.",
        icon="📐",
    )


def _cronologia() -> None:
    st.subheader("A cronologia oficial, transcrita à mão")
    crono = dados.cronologia()

    st.dataframe(
        pd.DataFrame({
            "Recessão": crono["recessao_id"],
            "Pico": crono["pico"].astype(str),
            "Vale": crono["vale"].astype(str),
            "Duração (meses)": crono["duracao"],
            "Datação": crono["granularidade"],
            "Fonte": crono["fonte"],
            "Observação": crono["observacao"],
        }),
        hide_index=True, width="stretch",
        column_config={"Observação": st.column_config.TextColumn(width="large")},
    )
    st.caption(
        "O CODACE não publica a cronologia em formato estruturado: a datação "
        "mensal existe como imagem e a trimestral, dentro de PDFs de comunicado. "
        "A transcrição está versionada em `config/codace_cronologia.csv`, e a "
        "imagem de origem em `docs/fontes/` — para que a transcrição possa ser "
        "conferida, não apenas acreditada. A leitura revalida tudo: pico antes do "
        "vale, ordem cronológica e ausência de sobreposição."
    )


def _resultado() -> None:
    st.subheader("O resultado, recessão por recessão")
    config = dados.configuracao_vigente()
    tabela = dados.defasagens_vigentes()

    if config:
        st.markdown(
            f"Configuração em uso: corte de crescimento em **{config['corte_crescimento']}**, "
            f"persistência de **{formato.meses(int(config['persistencia']))}**."
        )

    st.dataframe(
        pd.DataFrame({
            "Recessão": tabela["recessao_id"],
            "Datação": tabela["granularidade"],
            "Pico": tabela["pico"],
            "Vale": tabela["vale"],
            "Episódio do sinal": [
                f"{i} – {f}" if i else "—"
                for i, f in zip(tabela["episodio_inicio"].fillna(""),
                                tabela["episodio_fim"].fillna(""), strict=True)
            ],
            "Defasagem no pico": [formato.defasagem(v) for v in tabela["defasagem_pico"]],
            "No vale": [formato.defasagem(v) for v in tabela["defasagem_vale"]],
            "Meses sobrepostos": tabela["meses_sobrepostos"],
            "Cobertura da recessão": tabela["cobertura_da_recessao"],
        }),
        hide_index=True, width="stretch",
    )

    if config:
        a, b, c = st.columns(3)
        a.metric("Defasagem mediana no pico",
                 formato.numero(config["defasagem_pico_mediana"], 1, sinal=True))
        b.metric("Defasagem mediana no vale",
                 formato.numero(config["defasagem_vale_mediana"], 1, sinal=True))
        c.metric("Sinal ligado na janela",
                 formato.numero(config["fracao_da_janela_com_sinal"] * 100, 0,
                                sufixo="%"))

    st.caption(
        "**A coluna de cobertura merece leitura.** A recessão de 2008 tem só "
        "quatro meses na datação mensal, então um sinal que entra com três meses "
        "de atraso pega o último deles — e isso aparece como cobertura de 1 em 4, "
        "não como sucesso. Em 2014-2016 o sinal liga, desliga e religa dentro da "
        "mesma recessão; a regra associa o maior bloco, mas o primeiro bloco a "
        "tocar a recessão está na coluna `defasagem_pico_primeiro` do CSV "
        "versionado, porque é outra leitura legítima da mesma coisa."
    )


def _varredura() -> None:
    st.subheader("O que cada configuração custa")
    st.markdown(
        "Duas escolhas existem no classificador: contra o que o eixo de "
        "crescimento é comparado, e por quantos meses o novo sinal precisa se "
        "manter para a virada valer. A varredura mede as doze combinações com a "
        "mesma régua. **O círculo aberto é a configuração em uso.**"
    )

    resumo = dados.validacao_resumo()
    grafico, nota = st.columns([3, 2])
    with grafico:
        st.altair_chart(
            graficos.varredura(resumo, vigente=dados.configuracao_vigente()),
            width="stretch",
        )
    with nota:
        st.markdown(
            "**O tamanho do ponto é o maior episódio contínuo de contração.** "
            "Um ponto grande no alto à direita é o retrato da degeneração: o "
            "sinal vira um bloco só, detecta todas as recessões e não tem falso "
            "alarme porque nunca desliga.\n\n"
            "Os pontos vermelhos são a mediana expansiva; os verdes, o corte em "
            "zero. A separação horizontal entre os dois grupos é a medida do "
            "problema que derrubou a mediana: ela deixava o sinal ligado o dobro "
            "do tempo."
        )

    st.dataframe(
        pd.DataFrame({
            "Corte": resumo["corte_crescimento"],
            "Persistência": resumo["persistencia"],
            "Recessões detectadas": [
                f"{int(d)}/{int(a)}" for d, a in
                zip(resumo["recessoes_detectadas"], resumo["recessoes_avaliadas"],
                    strict=True)
            ],
            "Defasagem no pico": resumo["defasagem_pico_mediana"],
            "No vale": resumo["defasagem_vale_mediana"],
            "Trocas de quadrante": resumo["trocas_de_quadrante"],
            "Episódios fora de recessão": resumo["episodios_fora_de_recessao"],
            "Maior episódio (meses)": resumo["maior_episodio_meses"],
            # Em percentual, e não em fração: a ProgressColumn formata o valor
            # cru, então 0,36 com formato de porcentagem apareceria como "0%".
            "Janela com sinal ligado": resumo["fracao_da_janela_com_sinal"] * 100,
        }),
        hide_index=True, width="stretch",
        column_config={
            "Janela com sinal ligado": st.column_config.ProgressColumn(
                format="%.0f%%", min_value=0, max_value=100),
        },
    )

    st.markdown(
        "**O que esta tabela decidiu, duas vezes.**\n\n"
        "Primeiro, o corte. Com a mediana expansiva, o sinal fica ligado em cerca "
        "de 80% dos meses da janela, e a aparente antecipação de doze meses em "
        "persistência 3 é o sinal ligando cedo e ficando ligado; em persistência "
        "4 ele degenera num único episódio de 122 meses, que a tabela mostraria "
        "como 3/3 recessões e zero falsos alarmes. Com corte em zero, o sinal "
        "fica ligado em cerca de um terço dos meses e passa a acompanhar as "
        "recessões com atraso de três a quatro meses — o comportamento honesto de "
        "uma regra de momentum sobre dado publicado com 45 a 60 dias de "
        "defasagem.\n\n"
        "Depois, a persistência. Três é o maior prazo que não degenera sob a "
        "mediana **e** não perde recessão sob o zero. Dois critérios "
        "independentes, a mesma resposta — e é isso que torna o parâmetro "
        "escolhido contra evidência em vez de no olho."
    )


def _limites() -> None:
    st.subheader("O que esta validação não prova")
    st.markdown(
        "- **A janela tem três recessões.** É a razão de o classificador ser uma "
        "regra de sinal e não um modelo com parâmetros estimados: com três "
        "eventos, qualquer modelo com muitos parâmetros estaria sendo ajustado ao "
        "ruído.\n"
        "- **A covid nunca foi datada em meses.** O CODACE datou o episódio de "
        "2020 apenas em trimestres; os meses usados aqui são derivados deles, e a "
        "linha está marcada como `trimestral` na tabela acima.\n"
        "- **A classificação histórica é ex-post.** Não existem vintages públicos "
        "de séries brasileiras, então ela não simula a informação disponível em "
        "tempo real. O que estava sob controle — o ajuste sazonal, feito em "
        "janela expansiva — foi corrigido; o que não estava está declarado.\n"
        "- **O comitê anuncia com anos de atraso.** O vale de 2020 só foi datado "
        "em janeiro de 2023. Se o classificador 'ganhar' do comitê, isso não é "
        "mérito: ele tem a série completa, e o comitê, na época, não tinha.\n"
        "- **Episódios após o último vale datado não são avaliáveis.** Ausência "
        "de um pico novo não significa ausência de recessão; significa que o "
        "comitê ainda não se pronunciou. Eles são contados à parte."
    )
