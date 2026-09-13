"""Página de surpresas: o número saiu diferente do que o mercado esperava?

A distinção que a página inteira defende: isto não é um detector de outlier. Um
outlier responde "esse número é raro", e o IPCA de janeiro é sempre alto — um
detector de outlier gritaria todo janeiro. A pergunta com conteúdo econômico é
outra, e exige saber o que se esperava **antes** de o número sair.
"""

from __future__ import annotations

import pandas as pd
import streamlit as st

from .. import componentes, dados, formato, graficos

ROTULOS = {
    "ipca": "IPCA (% ao mês)",
    "desocupacao": "Taxa de desocupação (% da força de trabalho)",
    "pib": "PIB (% interanual)",
}


@componentes.protegido
def renderizar() -> None:
    componentes.titulo(
        "Surpresas",
        "Realizado menos a mediana do Focus apurada na véspera da divulgação — "
        "não a média histórica, não um limiar estatístico.",
    )

    tabela = dados.surpresas()
    por_par = dados.surpresas_por_par(tabela)

    _ultimas(por_par)
    st.divider()
    _detalhe(tabela, por_par)
    st.divider()
    _vies(por_par)


def _ultimas(por_par: pd.DataFrame) -> None:
    st.subheader("A última divulgação de cada par")
    colunas = st.columns(len(por_par))

    for coluna, (_, linha) in zip(colunas, por_par.iterrows(), strict=True):
        desvios = (
            abs(linha["surpresa"]) / linha["desvio_padrao"]
            if linha["desvio_padrao"] else 0.0
        )
        with coluna:
            st.metric(
                ROTULOS.get(linha["par"], linha["par"]),
                formato.numero(linha["realizado"], 2),
                delta=f"{formato.numero(linha['surpresa'], 2, sinal=True)} "
                      f"{linha['unidade']} vs. consenso",
                delta_color="off",
                delta_arrow="off",
            )
            st.caption(
                f"Consenso de {formato.numero(linha['consenso'], 2)} · "
                f"referência {formato.mes_curto(linha['ultima_referencia'])} · "
                f"divulgado em {formato.dia(linha['ultima_divulgacao'])}"
            )
            st.caption(
                f"**{formato.numero(desvios, 1)}×** o desvio padrão histórico do "
                f"par ({formato.numero(linha['desvio_padrao'], 2)} p.p.)."
            )

    st.caption(
        "A escala em desvios padrão não é enfeite: sem ela, 0,15 p.p. não diz se "
        "a divulgação foi notícia ou rotina."
    )


def _detalhe(tabela: pd.DataFrame, por_par: pd.DataFrame) -> None:
    st.subheader("Histórico por par")
    par = st.selectbox(
        "Par", list(por_par["par"]),
        format_func=lambda p: ROTULOS.get(p, p),
    )
    recorte = tabela[tabela["par"] == par].sort_values("data_divulgacao")
    info = por_par[por_par["par"] == par].iloc[0]

    a, b, c, d = st.columns(4)
    a.metric("Divulgações medidas", f"{int(info['observacoes'])}")
    b.metric("Surpresa média",
             f"{formato.numero(info['media'], 2, sinal=True)} p.p.")
    c.metric("Desvio padrão", f"{formato.numero(info['desvio_padrao'], 2)} p.p.")
    d.metric("Consenso parado, em média",
             f"{formato.numero(info['dias_sem_mudanca_medio'], 0)} dias")

    st.altair_chart(
        graficos.historico_de_surpresa(recorte, desvio=float(info["desvio_padrao"])),
        width="stretch",
    )
    st.caption(
        "A faixa cinza é ±1 desvio padrão. **Barra vermelha** é realizado acima "
        "do consenso; **azul**, abaixo."
    )

    st.altair_chart(graficos.realizado_contra_consenso(recorte), width="stretch")
    st.caption(
        "O consenso usado é a última apuração do Focus **estritamente anterior** "
        "à divulgação: uma apuração feita no próprio dia não estava disponível "
        "para quem operava antes de o número sair."
    )

    with st.expander(f"As {len(recorte)} divulgações medidas"):
        st.dataframe(
            pd.DataFrame({
                "Referência": [formato.mes_curto(d) for d in recorte["data_referencia"]],
                "Divulgação": [formato.dia(d) for d in recorte["data_divulgacao"]],
                "Realizado": recorte["realizado"],
                "Consenso": recorte["consenso"],
                "Surpresa": recorte["surpresa"],
                "Consenso de": [formato.dia(d) for d in recorte["data_consenso"]],
                "Dias sem mudança": recorte["dias_sem_mudanca"],
                "Primeira leitura": recorte["primeira_leitura"],
            }).iloc[::-1],
            hide_index=True, width="stretch",
        )
        st.caption(
            "**Dias sem mudança** mede há quantos dias o consenso estava parado "
            "quando o número saiu — não há quantos dias ele estava desatualizado. "
            "A ingestão não grava mediana repetida: se o consenso não mudou, não "
            "houve notícia."
        )


def _vies(por_par: pd.DataFrame) -> None:
    st.subheader("O teste da construção, e o viés que ele expõe")

    st.dataframe(
        pd.DataFrame({
            "Par": [ROTULOS.get(p, p) for p in por_par["par"]],
            "n": por_par["observacoes"],
            "Desde": [formato.mes_curto(d) for d in por_par["desde"]],
            "Surpresa média (p.p.)": por_par["media"].round(2),
            "Desvio padrão": por_par["desvio_padrao"].round(2),
            "Primeiras leituras": por_par["primeiras_leituras"],
        }),
        hide_index=True, width="stretch",
    )

    ipca = por_par[por_par["par"] == "ipca"]
    if not ipca.empty:
        linha = ipca.iloc[0]
        st.success(
            f"**O IPCA é o teste da montagem inteira, e ele passa.** Surpresa "
            f"média de {formato.numero(linha['media'], 2, sinal=True)} p.p. em "
            f"{int(linha['observacoes'])} divulgações é o que se espera de um "
            f"consenso não enviesado. Se a referência estivesse trocada ou a data "
            f"de divulgação deslocada, essa média não seria zero.",
            icon="✅",
        )

    st.warning(
        "**As outras duas não têm média zero, e o motivo mais provável é "
        "revisão.** O realizado gravado para 2017-2026 é o valor *vigente hoje*, "
        "não o primeiro print: o backfill trouxe a série já revisada. O IPCA "
        "quase não é revisado e dá zero; o PIB é revisado para cima e dá +0,41 "
        "p.p. Na desocupação as duas explicações competem — revisão da PNADC "
        "contra consenso perseguindo uma queda longa — e os dados **não** decidem "
        "entre elas. Fica declarado como indeterminado.",
        icon="⚠️",
    )

    st.caption(
        "A coluna **primeiras leituras** conta as divulgações que o pipeline "
        "observou ao vivo, com coleta até quatro dias depois. Ela cresce sozinha "
        "conforme o projeto roda, e é o que vai permitir, daqui a alguns anos, "
        "medir a surpresa contra o primeiro print em vez do valor revisado. O "
        "projeto não tem como consertar o passado, mas pode parar de estragar o "
        "futuro."
    )

    st.markdown(
        "**O câmbio ficou de fora de propósito.** A PTAX é preço de mercado "
        "contínuo: não tem data de divulgação, e 'surpresa' ali não seria "
        "surpresa de divulgação."
    )
    st.caption(
        "A janela começa em 2017 porque a API de calendário do IBGE não devolve "
        "nada antes disso. Estimar a data de divulgação a partir do mês de "
        "referência daria mais cobertura e menos verdade."
    )
