"""Página inicial: em que quadrante a economia está, e com que atraso se sabe.

A ordem da página é deliberada. O estado vem primeiro, a defasagem medida vem
logo em seguida, e só depois vêm os gráficos. Um painel que mostra o regime sem
mostrar o atraso do próprio sinal está vendendo precisão que não tem.
"""

from __future__ import annotations

import streamlit as st

from ... import artefatos as dados
from ... import formato
from ... import regime as regime_mod
from .. import componentes, graficos

MESES_NO_MAPA = 24


@componentes.protegido
def renderizar() -> None:
    componentes.titulo(
        "Regime macroeconômico",
        "Crescimento × inflação, classificado por regra determinística e "
        "confrontado com a datação oficial de recessões.",
    )

    info = dados.resumo_regime()
    if not info:
        st.warning("Nenhum mês classificado ainda.")
        return

    _estado(info)
    st.divider()
    _numeros(info)
    st.divider()
    _mapa()
    st.divider()
    _historia()
    st.divider()
    _agenda()


def _estado(info: dict) -> None:
    esquerda, direita = st.columns([3, 2])

    with esquerda:
        st.markdown(
            f"## {componentes.pilula(info['quadrante'])}", unsafe_allow_html=True)
        st.markdown(
            f"Desde **{formato.mes_ano(info['desde'])}** "
            f"({formato.meses(info['meses_no_quadrante'])}). "
            f"Último mês de referência: **{formato.mes_ano(info['referencia'])}**."
        )
        if info.get("pendente"):
            st.warning(
                f"**Virada pendente:** o sinal cru já aponta "
                f"*{info['pendente']}* há {formato.meses(info['meses_pendente'])}, "
                f"e a regra exige {regime_mod.MESES_PERSISTENCIA} meses seguidos "
                f"para confirmar. Enquanto isso, o quadrante vigente continua "
                f"sendo o que está acima.",
                icon="⏳",
            )
        else:
            st.caption(
                "Nenhuma virada pendente: o sinal cru concorda com o quadrante "
                "vigente neste mês."
            )

    with direita:
        st.markdown("**O que cada quadrante quer dizer**")
        st.markdown(
            "\n".join(
                f"- {componentes.pilula(nome)} &nbsp; {descricao}"
                for nome, descricao in (
                    ("Expansão", "cresce sem pressionar preços"),
                    ("Aquecimento", "cresce e pressiona preços"),
                    ("Desaceleração", "não cresce e não pressiona"),
                    ("Estagflação", "não cresce e pressiona"),
                )
            ),
            unsafe_allow_html=True,
        )


def _numeros(info: dict) -> None:
    config = dados.configuracao_vigente()

    a, b, c, d = st.columns(4)
    a.metric(
        "Crescimento",
        formato.numero(info["eixo_crescimento"], 1, sinal=True, sufixo="%"),
        delta=f"corte em {formato.numero(info['corte_crescimento'], 1)}",
        delta_color="off",
        delta_arrow="off",
        help="IBC-Br dessazonalizado, momentum 3m/3m anualizado. O corte é zero: "
             "a pergunta é se a atividade está encolhendo.",
    )
    b.metric(
        "Inflação",
        formato.numero(info["eixo_inflacao"], 1, sufixo="%"),
        delta=f"corte em {formato.numero(info['corte_inflacao'], 1)}",
        delta_color="off",
        delta_arrow="off",
        help="Núcleo do IPCA dessazonalizado por nós em janela expansiva, "
             "3 meses compostos e anualizados. O corte é a mediana do próprio "
             "histórico até aquele mês — não a meta.",
    )
    c.metric(
        "Trocas de quadrante",
        f"{info['trocas_com_persistencia']}",
        delta=f"{info['trocas_sem_persistencia']} sem a regra de persistência",
        delta_color="off",
        delta_arrow="off",
        help="A regra de persistência exige o novo sinal confirmado em cada eixo "
             "por 3 meses seguidos antes de trocar o quadrante.",
    )
    if config:
        d.metric(
            "Recessões acompanhadas",
            f"{int(config['recessoes_detectadas'])} de "
            f"{int(config['recessoes_avaliadas'])}",
            delta=f"sinal ligado em "
                  f"{formato.numero(config['fracao_da_janela_com_sinal'] * 100, 0)}% "
                  f"da janela",
            delta_color="off",
            delta_arrow="off",
            help="Medido contra a cronologia do CODACE. A fração da janela com o "
                 "sinal ligado está aqui de propósito: sem ela, 'detectou todas' "
                 "não informa nada.",
        )

    if config:
        st.info(
            f"**O sinal acompanha, não antecipa.** Nesta configuração — corte em "
            f"{config['corte_crescimento']}, persistência de "
            f"{formato.meses(int(config['persistencia']))} — ele entra em "
            f"contração com **{formato.defasagem(config['defasagem_pico_mediana'])}** "
            f"em relação ao início das recessões datadas, e sai com "
            f"**{formato.defasagem(config['defasagem_vale_mediana'])}**. "
            f"É o que uma regra de momentum consegue fazer sobre dado publicado "
            f"com 45 a 60 dias de defasagem. A medição inteira está na página "
            f"Validação.",
            icon="🎯",
        )


def _mapa() -> None:
    st.subheader("Onde a economia está, e para onde estava indo")
    reg = dados.regime_mensal()

    grafico, leitura = st.columns([3, 2])
    with grafico:
        st.altair_chart(
            graficos.mapa_de_quadrantes(reg, meses=MESES_NO_MAPA), width="stretch")
    with leitura:
        st.markdown(
            f"**Como ler.** Os eixos mostram a **distância até o corte**, não o "
            f"valor bruto do indicador. O corte de inflação se move — é a mediana "
            f"expansiva do histórico — então, em valores crus, a fronteira do "
            f"quadrante seria uma linha que anda e o leitor teria que adivinhar "
            f"onde ela estava em cada mês. Plotando a distância, a fronteira é o "
            f"zero em todos os meses.\n\n"
            f"São os últimos {MESES_NO_MAPA} meses classificados. O círculo "
            f"aberto é o mês mais recente; a linha é o caminho até ele, e é ela "
            f"que informa: dois meses no mesmo quadrante podem estar indo em "
            f"direções opostas."
        )


def _historia() -> None:
    st.subheader("A série inteira")
    st.caption(
        "As faixas cinzas são as recessões datadas pelo CODACE. A linha "
        "tracejada em cada painel é o corte daquele eixo — reta no zero para "
        "crescimento, móvel para inflação. A tarja embaixo é o quadrante "
        "vigente, já com a regra de persistência aplicada."
    )
    reg = dados.regime_mensal()
    episodios = dados.episodios(reg)
    st.altair_chart(
        graficos.historia_do_regime(reg, episodios, dados.recessoes()),
        width="stretch",
    )

    with st.expander("Os episódios, um a um"):
        tabela = episodios.copy()
        tabela["Período"] = [
            f"{formato.mes_curto(i)} – {formato.mes_curto(u)}"
            for i, u in zip(tabela["inicio"], tabela["ultimo"], strict=True)
        ]
        st.dataframe(
            tabela[["Período", "quadrante", "meses"]].rename(
                columns={"quadrante": "Quadrante", "meses": "Duração (meses)"}),
            hide_index=True, width="stretch",
        )


def _agenda() -> None:
    st.subheader("Próximas divulgações")
    proximas = dados.proximas_divulgacoes(limite=6)
    if proximas.empty:
        st.caption("Nenhuma divulgação futura no calendário versionado.")
        return

    tabela = proximas.assign(
        Divulgação=proximas["data_divulgacao"].dt.strftime("%d/%m/%Y"),
        Referência=[formato.mes_curto(d) for d in proximas["data_referencia"]],
    )
    st.dataframe(
        tabela[["Divulgação", "Referência", "titulo", "series_ids"]].rename(
            columns={"titulo": "Pesquisa", "series_ids": "Séries que alimenta"}),
        hide_index=True, width="stretch",
    )
    st.caption(
        "Vem do calendário do IBGE, versionado em `data/calendario.parquet`. "
        "É a mesma tabela que fornece a data de divulgação usada para medir "
        "surpresa — sem ela não existe 'véspera'."
    )
