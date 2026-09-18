"""Página de investimento e consumo do governo, as duas como % do PIB.

**Por que esta página é sobretudo texto em volta de um gráfico.** Duas linhas que
sobem e descem juntas produzem, sozinhas, uma conclusão causal na cabeça de quem
olha — aqui, a de que gasto público desloca investimento privado. O gráfico não
sustenta essa conclusão e não tem como sustentá-la: as duas séries dividem o
mesmo denominador, então quando o PIB cai as duas razões sobem sem que ninguém
tenha decidido nada. A página existe para mostrar o fato e chegar antes da
inferência errada, nessa ordem.

**Por que as duas dividem o mesmo eixo**, ao contrário dos eixos de regime: são
percentuais do mesmo denominador, no mesmo trimestre, na mesma faixa da escala.
A comparação de nível entre elas é a informação, e empilhá-las a destruiria.

O argumento empírico mais forte da página é a assimetria de amplitude, e ele
aparece nos números antes do gráfico de propósito: em trinta anos o investimento
andou 6,4 pontos do PIB e o consumo do governo andou 2,2. Uma é cíclica, a outra
é quase um platô — e qualquer leitura de "uma empurrou a outra" tem que explicar
primeiro por que a série supostamente empurradora mal se mexe.
"""

from __future__ import annotations

import pandas as pd
import streamlit as st

from ... import artefatos as dados
from ... import formato
from .. import componentes, graficos

# Do id da camada derivada para o rótulo que aparece na legenda e no texto. O
# rótulo entra na coluna `serie` antes de o gráfico ser montado: o Vega imprime o
# domínio cru na legenda, e renomear na camada de desenho criaria um segundo
# lugar onde o nome vive.
ROTULOS = {
    "taxa_investimento": "Taxa de investimento",
    "consumo_governo_pib": "Consumo do governo",
}


@componentes.protegido
def renderizar() -> None:
    componentes.titulo(
        "Investimento e governo",
        "Formação bruta de capital fixo e despesa de consumo da administração "
        "pública, as duas como % do PIB a preços correntes, em soma móvel de "
        "quatro trimestres.",
    )

    tabela = _tabela()
    _onde_estamos(tabela)
    _no_tempo(tabela)
    _como_ler(tabela)
    _o_que_nao_prova()


def _tabela() -> pd.DataFrame:
    """As duas séries derivadas em formato longo, já com o rótulo de exibição."""
    derivado = dados.derivado()
    tabela = derivado[derivado["serie_id"].isin(ROTULOS)].copy()
    tabela["serie"] = tabela["serie_id"].map(ROTULOS)
    # Ordem de aparição: é ela que o gráfico usa na legenda, e o investimento é a
    # série que o texto discute primeiro.
    ordem = {rotulo: i for i, rotulo in enumerate(ROTULOS.values())}
    tabela["_ordem"] = tabela["serie"].map(ordem)
    tabela = tabela.sort_values(["_ordem", "data_referencia"])
    return tabela[["data_referencia", "serie", "valor"]].reset_index(drop=True)


def _serie(tabela: pd.DataFrame, rotulo: str) -> pd.Series:
    linhas = tabela[tabela["serie"] == rotulo]
    return pd.Series(linhas["valor"].to_numpy(), index=list(linhas["data_referencia"]))


def _onde_estamos(tabela: pd.DataFrame) -> None:
    investimento = _serie(tabela, ROTULOS["taxa_investimento"])
    governo = _serie(tabela, ROTULOS["consumo_governo_pib"])
    if investimento.empty or governo.empty:
        st.info("Camada derivada sem as razões. Rode `ciclo-transformar`.")
        return

    referencia = formato.mes_ano(investimento.index[-1])
    # Quatro trimestres atrás, que é a comparação homóloga desta série.
    variacao = (investimento.iloc[-1] - investimento.iloc[-5]
                if len(investimento) > 4 else None)

    componentes.numeros([
        ("Taxa de investimento",
         formato.numero(investimento.iloc[-1], 1, sufixo="% do PIB"),
         f"referência {referencia} · soma de 4 trimestres"),
        ("Consumo do governo",
         formato.numero(governo.iloc[-1], 1, sufixo="% do PIB"),
         f"referência {referencia} · soma de 4 trimestres"),
        ("Investimento, em 4 trimestres",
         formato.numero(variacao, 1, sinal=True, sufixo=" p.p."),
         "contra o mesmo trimestre do ano anterior"),
        ("Amplitude desde 1996",
         f"{formato.numero(investimento.min(), 1)} a "
         f"{formato.numero(investimento.max(), 1)}%",
         f"o governo variou {formato.numero(governo.min(), 1)} a "
         f"{formato.numero(governo.max(), 1)}%"),
    ])


def _no_tempo(tabela: pd.DataFrame) -> None:
    componentes.secao("As duas séries no tempo")
    componentes.figura(
        graficos.series_comparadas(
            tabela,
            titulo="% do PIB",
            recessoes=dados.recessoes(),
            cores=graficos.CORES_INVESTIMENTO,
        ),
        "Formação bruta de capital fixo e despesa de consumo da administração "
        "pública, as duas sobre o PIB, tudo a preços correntes e em soma móvel de "
        "quatro trimestres. Ao fundo, as recessões datadas pelo CODACE.",
    )


def _como_ler(tabela: pd.DataFrame) -> None:
    investimento = _serie(tabela, ROTULOS["taxa_investimento"])
    governo = _serie(tabela, ROTULOS["consumo_governo_pib"])
    if investimento.empty or governo.empty:
        return

    st.markdown(
        "**O que salta aos olhos é a diferença de amplitude.** Em trinta anos a "
        f"taxa de investimento andou {formato.numero(investimento.max() - investimento.min(), 1)} "
        f"pontos do PIB, de {formato.numero(investimento.min(), 1)}% no pior "
        f"momento a {formato.numero(investimento.max(), 1)}% no melhor. O consumo "
        f"do governo andou {formato.numero(governo.max() - governo.min(), 1)} "
        f"pontos, entre {formato.numero(governo.min(), 1)}% e "
        f"{formato.numero(governo.max(), 1)}%, e passa a maior parte do tempo "
        "dentro de uma faixa estreita. As duas linhas não se movem na mesma "
        "escala: uma é cíclica, a outra é quase um platô. Qualquer leitura de "
        "*uma empurrou a outra* tem que explicar primeiro por que a série "
        "supostamente empurradora mal se mexe."
    )


def _o_que_nao_prova() -> None:
    componentes.secao("O que este gráfico não permite concluir")
    st.markdown(
        "- **Ele não mostra causalidade.** São duas contas do mesmo bolo, "
        "dividindo o mesmo denominador. Quando o PIB cai, as duas razões sobem "
        "sem que nada tenha sido decidido — e é exatamente o que acontece em 2020 "
        "e em 2015-16, dentro das faixas cinza. Movimento simultâneo aqui é "
        "aritmética antes de ser economia.\n"
        "- **Ele não demonstra *crowding out*.** A tese de que gasto público "
        "desloca investimento privado é sobre o canal — juro real, crédito, "
        "câmbio, expectativa —, não sobre o sinal de duas linhas num gráfico. "
        "Testá-la exige identificação, e este projeto não a tem.\n"
        "- **Consumo do governo não é gasto público.** A série é a despesa de "
        "consumo da administração pública: remuneração de servidores e consumo "
        "intermediário. Fora dela ficam as transferências — Previdência, Bolsa "
        "Família —, os juros da dívida e o investimento público. Quem procura o "
        "tamanho do Estado está vendo talvez metade dele.\n"
        "- **E o investimento público está na outra linha.** A formação bruta de "
        "capital fixo soma o que o setor público e o privado investem. Uma obra "
        "federal sobe a linha do investimento, não a do governo — o que desfaz a "
        "leitura de uma cor contra a outra que o gráfico convida.\n"
        "- **A soma móvel de quatro trimestres atrasa a virada.** Ela existe para "
        "tirar a sazonalidade sem dessazonalizador, e o preço é que cada trimestre "
        "novo entra com peso de um quarto: uma inflexão real aparece aqui com dois "
        "a três trimestres de atraso em relação ao dado bruto.\n"
        "- **Preços correntes, e é de propósito.** Numerador e denominador são do "
        "mesmo período, então não há deflator escolhido por ninguém. Em "
        "compensação, mudança de **preço relativo** aparece como mudança de taxa: "
        "quando bem de capital encarece mais que o resto do PIB, a taxa de "
        "investimento sobe sem que um tijolo a mais tenha sido assentado. Parte da "
        "queda brasileira desde 2014 é preço relativo, não volume."
    )
    st.caption(
        "Fonte: IBGE, Contas Nacionais Trimestrais (tabela 1846, valores a preços "
        "correntes). A seção correspondente da Metodologia traz a definição "
        "completa e a conferência dos números."
    )
