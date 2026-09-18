"""Página das séries: o que entra no projeto, de onde vem e o que foi feito com ela.

A regra dura do projeto é que nenhuma série entra sem ficha completa — fonte,
código, unidade, periodicidade, tratamento sazonal, papel e transformação. Esta
página é a ficha na tela, porque uma regra que não é visível tende a virar
intenção.

A aba de revisões só existe por causa do armazenamento append-only. Em um painel
que sobrescreve, ela seria impossível de montar: o valor anterior teria sumido no
lugar do novo.
"""

from __future__ import annotations

import pandas as pd
import streamlit as st

from ... import artefatos as dados
from ... import formato
from ...config import catalogo
from .. import componentes, graficos


@componentes.protegido
def renderizar() -> None:
    componentes.titulo(
        "Séries",
        "Dezesseis séries oficiais, cada uma com ficha obrigatória em "
        "`config/series.yaml`. Nenhuma entra sem ela, e há teste verificando.",
    )

    catalogo_tab, bruta_tab, derivada_tab, revisao_tab = st.tabs(
        ["Catálogo", "Série bruta", "Camada derivada", "Revisões"]
    )
    with catalogo_tab:
        _catalogo()
    with bruta_tab:
        _bruta()
    with derivada_tab:
        _derivada()
    with revisao_tab:
        _revisoes()


def _catalogo() -> None:
    fichas = dados.fichas()

    a, b = st.columns(2)
    blocos = a.multiselect("Bloco", sorted(fichas["bloco"].unique()),
                           placeholder="todos")
    papeis = b.multiselect("Papel no projeto", sorted(fichas["papel"].unique()),
                           placeholder="todos")
    if blocos:
        fichas = fichas[fichas["bloco"].isin(blocos)]
    if papeis:
        fichas = fichas[fichas["papel"].isin(papeis)]

    st.dataframe(
        fichas.rename(columns={
            "id": "ID", "nome": "Nome", "bloco": "Bloco", "papel": "Papel",
            "fonte": "Fonte", "codigo": "Código", "unidade": "Unidade",
            "periodicidade": "Periodicidade", "ajuste_sazonal": "Ajuste sazonal",
            "transformacao": "Transformação", "notas": "Notas",
        }),
        hide_index=True, width="stretch",
        column_config={"Notas": st.column_config.TextColumn(width="large")},
    )
    st.caption(
        "**Ajuste sazonal** diz quem dessazonalizou: `origem` é a própria fonte, "
        "`proprio` somos nós em janela expansiva, `nao_aplicavel` é série que não "
        "pede ajuste. A distinção importa: o que a fonte ajusta, ela ajusta com a "
        "amostra completa, e essa parte do viés de look-ahead não está sob nosso "
        "controle. Está declarada na página de Metodologia."
    )


def _seletor(chave: str) -> str:
    fichas = catalogo()
    rotulos = {f"{s.nome}  ·  {sid}": sid for sid, s in fichas.items()}
    escolha = st.selectbox("Série", list(rotulos), key=chave)
    return rotulos[escolha]


def _bruta() -> None:
    serie_id = _seletor("serie_bruta")
    ficha = catalogo()[serie_id]
    observacoes = dados.serie_bruta(serie_id)

    if observacoes.empty:
        st.info(f"`{serie_id}` ainda não foi coletada. Rode `ciclo-ingest --serie "
                f"{serie_id} --backfill`.")
        return

    componentes.numeros([
        ("Observações", f"{len(observacoes)}", None),
        ("Primeira referência",
         formato.mes_curto(observacoes["data_referencia"].iloc[0]), None),
        ("Última referência",
         formato.mes_curto(observacoes["data_referencia"].iloc[-1]), None),
        ("Coletada pela última vez",
         formato.dia(observacoes["data_coleta"].max()), None),
    ])

    componentes.figura(
        graficos.serie_simples(
            observacoes, titulo=ficha.unidade,
            recessoes=dados.recessoes() if ficha.periodicidade != "diaria" else None,
        ),
        f"{ficha.nome}, série vigente como está gravada em "
        f"`data/raw/{serie_id}.parquet`. Unidade: {ficha.unidade}.",
        numerar=False,
    )

    st.markdown(
        f"**Fonte:** {ficha.fonte.upper()} · "
        f"**Código:** {ficha.referencia_na_fonte} · "
        f"**Unidade:** {ficha.unidade} · "
        f"**Periodicidade:** {ficha.periodicidade} · "
        f"**Ajuste sazonal:** {ficha.ajuste_sazonal} · "
        f"**Papel:** {ficha.papel}"
    )
    if ficha.transformacao:
        st.markdown(f"**Transformação aplicada:** {ficha.transformacao}")
    if ficha.notas:
        st.caption(" ".join(ficha.notas.split()))


def _derivada() -> None:
    receitas = dados.receitas()
    tabela = dados.derivado()

    rotulos = {
        f"{linha['serie_id']}  ·  {linha['descricao'][:60]}": linha["serie_id"]
        for _, linha in receitas.iterrows()
    }
    escolha = st.selectbox("Série derivada", list(rotulos))
    serie_id = rotulos[escolha]
    receita = receitas[receitas["serie_id"] == serie_id].iloc[0]
    serie = tabela[tabela["serie_id"] == serie_id]

    st.markdown(
        f"**Origem:** `{receita['origem']}` → **{receita['descricao']}** "
        f"({receita['unidade']})"
    )
    componentes.figura(
        graficos.serie_simples(serie, titulo=receita["unidade"],
                               recessoes=dados.recessoes()),
        f"{receita['descricao']} ({receita['unidade']}), calculada a partir de "
        f"`{receita['origem']}`.",
        numerar=False,
    )

    componentes.numeros([
        ("Observações", f"{len(serie)}", None),
        ("De", formato.mes_curto(serie["data_referencia"].iloc[0]), None),
        ("Até", formato.mes_curto(serie["data_referencia"].iloc[-1]), None),
    ])

    st.caption(
        "As séries que este projeto dessazonaliza são tratadas em **janela "
        "expansiva**: o valor de março de 2015 é estimado usando apenas dados até "
        "março de 2015. O resultado é mais feio que o de um ajuste com a amostra "
        "inteira, e é esse o ponto — o backtest do outro jeito fica bonito por "
        "construção."
    )
    with st.expander("Todas as receitas da camada derivada"):
        st.dataframe(
            receitas.rename(columns={
                "serie_id": "Série", "origem": "Origem", "papel": "Papel",
                "descricao": "Como é calculada", "unidade": "Unidade"}),
            hide_index=True, width="stretch",
        )


def _revisoes() -> None:
    serie_id = _seletor("serie_revisao")
    ficha = catalogo()[serie_id]
    alteracoes = dados.revisoes(serie_id)

    # Focus e SGS produzem a mesma forma no arquivo e significam coisas
    # diferentes: no SGS, um valor novo para uma referência antiga é revisão do
    # dado; no Focus, é a apuração do dia seguinte. Chamar os dois de "revisão"
    # seria errado, e é uma confusão fácil de cometer.
    consenso = ficha.fonte == "focus"
    if consenso:
        st.info(
            "Esta é uma série de **expectativa**, não de realizado. Cada linha "
            "nova para o mesmo período de referência é uma apuração posterior do "
            "Focus — a trajetória do consenso, não revisão de dado. É exatamente "
            "essa trajetória que permite recuperar o que o mercado esperava na "
            "véspera de cada divulgação.",
            icon="📈",
        )

    if alteracoes.empty:
        st.success(
            f"Nenhuma revisão observada em `{serie_id}` desde o início da coleta.",
            icon="✅",
        )
        st.caption(
            "O banco de vintages começa vazio por construção: ele registra o que "
            "a fonte mudar **a partir** da primeira coleta, e não tem como "
            "reconstruir o que ela mudou antes disso. Não existe base pública de "
            "vintages para séries brasileiras — é por isso que o projeto constrói "
            "a sua, e é por isso que ela leva tempo para ter conteúdo."
        )
        return

    rotulo = "apurações posteriores" if consenso else "revisões"
    componentes.numeros([(f"Total de {rotulo}", f"{len(alteracoes)}", None)])
    st.dataframe(
        pd.DataFrame({
            "Referência": [formato.mes_curto(d) for d in alteracoes["data_referencia"]],
            "Valor anterior": alteracoes["valor_anterior"],
            "Valor novo": alteracoes["valor"],
            "Diferença": alteracoes["diferenca"],
            "Observado em": [formato.dia(d) for d in alteracoes["revisado_em"]],
        }).head(200),
        hide_index=True, width="stretch",
    )
    if len(alteracoes) > 200:
        st.caption(f"Mostrando as 200 mais recentes de {len(alteracoes)}.")
