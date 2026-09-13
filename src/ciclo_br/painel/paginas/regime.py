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

# O que cada nome quer dizer para quem não trabalha com isso. Fica aqui, e não
# só na metodologia, porque o título da página é uma dessas quatro palavras: o
# leitor encontra o termo antes de ter qualquer chance de procurar o que é.
#
# Cada frase responde às mesmas duas perguntas dos eixos, nessa ordem — cresce
# ou encolhe, preços acima ou abaixo do normal — para que a leitura do texto e a
# leitura do gráfico usem o mesmo par de perguntas.
SENTIDO = {
    "Expansão":
        "A economia **cresce** e os preços sobem **menos** que o normal "
        "histórico. É a combinação boa: crescer sem a conta da inflação.",
    "Aquecimento":
        "A economia **cresce**, mas os preços sobem **mais** que o normal. "
        "Crescimento com fatura: é quando se costuma discutir alta de juros.",
    "Desaceleração":
        "A atividade **encolhe** e a pressão de preços **cede**. Ruim para o "
        "emprego, e é o quadro que costuma abrir espaço para o juro cair.",
    "Estagflação":
        "A atividade **encolhe** e os preços sobem **acima** do normal. O pior "
        "dos quatro: o remédio para um lado piora o outro.",
}


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

    _glossario(info.get("quadrante"))


def _glossario(vigente: str | None) -> None:
    """Os quatro nomes explicados, lado a lado, com o vigente marcado.

    Lado a lado e não em lista: os quatro são combinações de duas perguntas, e
    ver os quatro juntos é o que mostra que são quatro respostas do mesmo par —
    e não quatro rótulos avulsos que o leitor teria que decorar.
    """
    st.markdown("**O que cada um desses nomes quer dizer**")
    for coluna, nome in zip(st.columns(4), graficos.ORDEM, strict=True):
        with coluna.container(border=True):
            marca = " &nbsp;·&nbsp; **agora**" if nome == vigente else ""
            st.markdown(
                f"{componentes.pilula(nome)}{marca}", unsafe_allow_html=True)
            st.caption(SENTIDO[nome])


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

    grafico, leitura = st.columns([5, 4])
    with grafico:
        st.altair_chart(
            graficos.mapa_de_quadrantes(reg, meses=MESES_NO_MAPA), width="stretch")
    with leitura:
        st.markdown(
            f"**Cada bolinha é um mês** — são os últimos {MESES_NO_MAPA}. A "
            f"linha liga cada mês ao seguinte, então ela é o caminho que a "
            f"economia fez, e o círculo escuro marca o mês mais recente. O "
            f"caminho conta mais que o ponto: dois meses na mesma faixa podem "
            f"estar indo em direções opostas.\n\n"
            f"**Os dois eixos são duas perguntas.** O de baixo pergunta *a "
            f"economia está crescendo?* — à direita da linha vertical, sim; à "
            f"esquerda, ela está encolhendo. O da lateral pergunta *os preços "
            f"estão subindo mais rápido que o normal?* — acima da linha "
            f"horizontal, sim; abaixo, não. Cada faixa colorida é uma das quatro "
            f"combinações possíveis dessas duas respostas, com o nome no canto.\n\n"
            f"**O anel em volta de alguns pontos.** A cor de dentro diz onde o "
            f"mês caiu; o anel diz qual regime ainda estava valendo. Os dois "
            f"discordam porque uma virada só é confirmada depois de "
            f"{regime_mod.MESES_PERSISTENCIA} meses seguidos do sinal novo — "
            f"então cada anel é um mês de atraso da regra, marcado no lugar onde "
            f"esse atraso aconteceu."
        )

    st.caption(
        "**Por que os eixos mostram a distância até o corte, e não o número do "
        "indicador.** O corte de inflação não é um número fixo: é a mediana do "
        "próprio histórico até aquele mês, e por isso ele se move. Com os "
        "valores crus, a fronteira entre os quadrantes seria uma linha que anda, "
        "e o leitor teria que adivinhar onde ela estava em cada mês. Medindo a "
        "distância até o corte, a fronteira é o zero em todos os meses: zero no "
        "eixo de baixo quer dizer *nem cresce nem encolhe*, e zero no eixo da "
        "lateral quer dizer *inflação exatamente no normal histórico*."
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
