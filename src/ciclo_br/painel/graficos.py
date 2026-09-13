"""Gráficos do painel, em Altair.

Altair e não uma biblioteca nova: ela já vem com o Streamlit, então o painel não
acrescenta dependência para desenhar. Duas escolhas de desenho merecem
explicação, porque não são estéticas:

**Os dois eixos não dividem a mesma escala.** O momentum de crescimento foi de
−38 a +40 na covid; o eixo de inflação vive entre 0 e 13. Num gráfico só, a
inflação vira uma linha reta. Por isso são dois painéis empilhados com o eixo do
tempo compartilhado.

**O mapa de quadrantes plota distância ao corte, não o valor do eixo.** O corte
de inflação se move — é a mediana expansiva do próprio histórico. Com valores
crus, a fronteira do quadrante seria uma linha que anda e o leitor teria que
adivinhar onde ela estava em cada mês; com a distância, a fronteira é o zero em
todos os meses e o quadrante que se vê é o que o classificador diz.
"""

from __future__ import annotations

import altair as alt
import pandas as pd

# Cores dos quadrantes. Verde e vermelho nos extremos (Expansão e Estagflação),
# âmbar e azul nos estados mistos — a leitura de "bom, ruim, morno" sai antes
# da legenda.
PALETA = {
    "Expansão": "#2a9d8f",
    "Aquecimento": "#e9c46a",
    "Estagflação": "#c1444f",
    "Desaceleração": "#4a6fa5",
}

ORDEM = ("Expansão", "Aquecimento", "Desaceleração", "Estagflação")

COR_RECESSAO = "#6b7280"
COR_CORTE = "#9aa0a6"


def _escala_quadrante() -> alt.Scale:
    return alt.Scale(domain=list(ORDEM), range=[PALETA[q] for q in ORDEM])


def recortar(recessoes: pd.DataFrame, inicio, fim) -> pd.DataFrame:
    """Recessões que tocam a janela do gráfico, com as bordas aparadas nela.

    Sem isso, a série de 2003 em diante herdaria o eixo do tempo da cronologia
    do CODACE, que começa em 1980: metade do gráfico seria faixa cinza sobre
    espaço vazio, e o período com dado ficaria espremido na direita.
    """
    if recessoes.empty:
        return recessoes
    dentro = recessoes[(recessoes["fim"] > inicio) & (recessoes["inicio"] < fim)].copy()
    dentro["inicio"] = dentro["inicio"].clip(lower=inicio)
    dentro["fim"] = dentro["fim"].clip(upper=fim)
    return dentro


def _sombra_recessao(recessoes: pd.DataFrame) -> alt.Chart:
    """As recessões datadas pelo CODACE, ao fundo de tudo."""
    return alt.Chart(recessoes).mark_rect(
        color=COR_RECESSAO, opacity=0.16,
    ).encode(
        x=alt.X("inicio:T"),
        x2=alt.X2("fim:T"),
        tooltip=[
            alt.Tooltip("recessao_id:N", title="Recessão (CODACE)"),
            alt.Tooltip("duracao:Q", title="Duração (meses)"),
            alt.Tooltip("granularidade:N", title="Datação"),
        ],
    )


def eixo_no_tempo(
    reg: pd.DataFrame,
    recessoes: pd.DataFrame,
    *,
    coluna: str,
    corte: str,
    titulo: str,
    altura: int = 190,
    eixo_do_tempo: bool = True,
) -> alt.LayerChart:
    """Um eixo, seu corte e as recessões oficiais ao fundo.

    `eixo_do_tempo` esconde os rótulos de ano: num empilhamento com escala de
    tempo compartilhada, três réguas idênticas só ocupam espaço — a de baixo
    serve os três painéis.

    Note que o eixo é **escondido**, não removido: `axis=None` num dos painéis
    de um `vconcat` com escala compartilhada quebra a resolução de escala do
    Vega-Lite e o gráfico inteiro deixa de desenhar, com erro só no console do
    navegador. Um teste de renderização em Python não pega isso, porque o erro
    é do lado do JavaScript.
    """
    base = alt.Chart(reg)

    regua = (alt.Axis(format="%Y") if eixo_do_tempo
             else alt.Axis(labels=False, ticks=False, domain=False, title=None))
    linha = base.mark_line(color="#1f2933", strokeWidth=1.6).encode(
        x=alt.X("data:T", title=None, axis=regua),
        y=alt.Y(f"{coluna}:Q", title=titulo),
        tooltip=[
            alt.Tooltip("data:T", title="Mês", format="%m/%Y"),
            alt.Tooltip(f"{coluna}:Q", title=titulo, format=".2f"),
            alt.Tooltip(f"{corte}:Q", title="Corte", format=".2f"),
            alt.Tooltip("quadrante:N", title="Quadrante"),
        ],
    )
    limite = base.mark_line(
        color=COR_CORTE, strokeDash=[5, 3], strokeWidth=1.4,
    ).encode(x=alt.X("data:T"), y=alt.Y(f"{corte}:Q"))

    return alt.layer(_sombra_recessao(recessoes), limite, linha).properties(height=altura)


def faixa_de_quadrantes(episodios: pd.DataFrame, *, altura: int = 42) -> alt.Chart:
    """Uma tarja colorida por episódio — a leitura de regime em um relance."""
    return alt.Chart(episodios).mark_rect().encode(
        x=alt.X("inicio:T", title=None, axis=alt.Axis(format="%Y")),
        x2=alt.X2("fim:T"),
        color=alt.Color(
            "quadrante:N", scale=_escala_quadrante(),
            legend=alt.Legend(title=None, orient="bottom", columns=4),
        ),
        tooltip=[
            alt.Tooltip("quadrante:N", title="Quadrante"),
            alt.Tooltip("inicio:T", title="De", format="%m/%Y"),
            alt.Tooltip("meses:Q", title="Duração (meses)"),
        ],
    ).properties(height=altura)


def historia_do_regime(
    reg: pd.DataFrame, episodios: pd.DataFrame, recessoes: pd.DataFrame
) -> alt.VConcatChart:
    """Os dois eixos e a faixa de quadrantes, com o tempo compartilhado."""
    janela = recortar(recessoes, reg["data"].min(), reg["data"].max())
    return alt.vconcat(
        eixo_no_tempo(reg, janela, coluna="eixo_crescimento",
                      corte="corte_crescimento", titulo="Crescimento (% anualizado)",
                      eixo_do_tempo=False),
        eixo_no_tempo(reg, janela, coluna="eixo_inflacao",
                      corte="corte_inflacao", titulo="Inflação (% anualizado)",
                      altura=160, eixo_do_tempo=False),
        faixa_de_quadrantes(episodios),
        spacing=6,
    ).resolve_scale(x="shared", color="independent")


def _dominio(valores: pd.Series, *, folga: float = 0.12) -> list[float]:
    """Intervalo que cobre os dados **e** o zero, com folga para as etiquetas."""
    baixo = min(float(valores.min()), 0.0)
    alto = max(float(valores.max()), 0.0)
    margem = max((alto - baixo) * folga, 0.1)
    return [baixo - margem, alto + margem]


def _cantos(limite_x: list[float], limite_y: list[float],
            *, recuo: float = 0.14) -> pd.DataFrame:
    """Os quatro nomes de quadrante, recuados para dentro dos cantos.

    Vega-Lite não aceita `align`/`baseline` como canal de codificação, então o
    recuo é feito na posição: cada nome entra um pouco no seu canto e a
    ancoragem padrão (centro) resolve o resto.
    """
    largura = (limite_x[1] - limite_x[0]) * recuo
    altura = (limite_y[1] - limite_y[0]) * recuo
    esquerda, direita = limite_x[0] + largura, limite_x[1] - largura
    baixo, cima = limite_y[0] + altura, limite_y[1] - altura
    return pd.DataFrame([
        {"x": direita, "y": cima, "quadrante": "Aquecimento"},
        {"x": direita, "y": baixo, "quadrante": "Expansão"},
        {"x": esquerda, "y": cima, "quadrante": "Estagflação"},
        {"x": esquerda, "y": baixo, "quadrante": "Desaceleração"},
    ])


def mapa_de_quadrantes(reg: pd.DataFrame, *, meses: int = 24) -> alt.LayerChart:
    """Os últimos meses no plano crescimento × inflação, em distância ao corte.

    O caminho importa mais que o ponto: dois meses no mesmo quadrante podem estar
    indo em direções opostas, e é a trajetória que mostra isso.
    """
    recorte = reg[reg["quadrante"].notna()].tail(meses).copy()
    recorte["rotulo"] = recorte["data"].dt.strftime("%m/%Y")
    ultimo = recorte.tail(1)

    # O domínio é forçado a conter o zero nos dois eixos. Sem isso, um período em
    # que a economia não cruza uma das fronteiras produziria um "mapa de
    # quadrantes" sem a fronteira à vista — e o leitor teria que acreditar na
    # legenda em vez de ver a posição.
    limite_x = _dominio(recorte["distancia_crescimento"])
    limite_y = _dominio(recorte["distancia_inflacao"])

    fundo = alt.Chart(_cantos(limite_x, limite_y)).mark_text(
        fontSize=12, opacity=0.5, fontWeight="bold",
    ).encode(
        x=alt.X("x:Q"), y=alt.Y("y:Q"),
        text=alt.Text("quadrante:N"),
        color=alt.Color("quadrante:N", scale=_escala_quadrante(), legend=None),
    )

    eixo_x = alt.Chart(pd.DataFrame({"v": [0.0]})).mark_rule(
        color=COR_CORTE, strokeDash=[4, 4]).encode(y=alt.Y("v:Q"))
    eixo_y = alt.Chart(pd.DataFrame({"v": [0.0]})).mark_rule(
        color=COR_CORTE, strokeDash=[4, 4]).encode(x=alt.X("v:Q"))

    caminho = alt.Chart(recorte).mark_line(
        color="#1f2933", strokeWidth=1, opacity=0.45,
    ).encode(
        x=alt.X("distancia_crescimento:Q"),
        y=alt.Y("distancia_inflacao:Q"),
        order=alt.Order("data:T"),
    )

    pontos = alt.Chart(recorte).mark_circle(size=95).encode(
        x=alt.X("distancia_crescimento:Q",
                title="Crescimento − corte (p.p. anualizados)",
                scale=alt.Scale(domain=limite_x, nice=False)),
        y=alt.Y("distancia_inflacao:Q",
                title="Inflação − corte (p.p. anualizados)",
                scale=alt.Scale(domain=limite_y, nice=False)),
        color=alt.Color("quadrante:N", scale=_escala_quadrante(), legend=None),
        opacity=alt.Opacity("data:T", legend=None, scale=alt.Scale(range=[0.3, 1])),
        tooltip=[
            alt.Tooltip("rotulo:N", title="Mês"),
            alt.Tooltip("quadrante:N", title="Quadrante"),
            alt.Tooltip("eixo_crescimento:Q", title="Crescimento", format=".2f"),
            alt.Tooltip("eixo_inflacao:Q", title="Inflação", format=".2f"),
            alt.Tooltip("corte_inflacao:Q", title="Corte de inflação", format=".2f"),
        ],
    )

    destaque = alt.Chart(ultimo).mark_point(
        size=260, filled=False, strokeWidth=2, color="#1f2933",
    ).encode(x=alt.X("distancia_crescimento:Q"), y=alt.Y("distancia_inflacao:Q"))

    etiqueta = alt.Chart(ultimo).mark_text(
        dx=12, dy=-12, fontSize=12, fontWeight="bold", color="#1f2933", align="left",
    ).encode(
        x=alt.X("distancia_crescimento:Q"),
        y=alt.Y("distancia_inflacao:Q"),
        text=alt.Text("rotulo:N"),
    )

    return alt.layer(
        fundo, eixo_x, eixo_y, caminho, pontos, destaque, etiqueta
    ).properties(height=420)


def historico_de_surpresa(tabela: pd.DataFrame, *, desvio: float) -> alt.LayerChart:
    """Surpresas de um par ao longo do tempo, com a faixa de ±1 desvio padrão.

    A faixa é o que transforma "0,15 p.p." em informação: dentro dela a
    divulgação foi rotina, fora dela foi notícia.
    """
    faixa = alt.Chart(
        pd.DataFrame({"baixo": [-desvio], "alto": [desvio]})
    ).mark_rect(color=COR_RECESSAO, opacity=0.12).encode(
        y=alt.Y("baixo:Q"), y2=alt.Y2("alto:Q"))

    zero = alt.Chart(pd.DataFrame({"v": [0.0]})).mark_rule(
        color="#1f2933", strokeWidth=1).encode(y=alt.Y("v:Q"))

    barras = alt.Chart(tabela).mark_bar(size=6).encode(
        x=alt.X("data_divulgacao:T", title=None),
        y=alt.Y("surpresa:Q", title="Surpresa (p.p.)"),
        color=alt.condition(
            alt.datum.surpresa >= 0,
            alt.value(PALETA["Estagflação"]), alt.value(PALETA["Desaceleração"]),
        ),
        tooltip=[
            alt.Tooltip("data_divulgacao:T", title="Divulgação", format="%d/%m/%Y"),
            alt.Tooltip("data_referencia:T", title="Referência", format="%m/%Y"),
            alt.Tooltip("realizado:Q", title="Realizado", format=".2f"),
            alt.Tooltip("consenso:Q", title="Consenso", format=".2f"),
            alt.Tooltip("surpresa:Q", title="Surpresa", format="+.2f"),
            alt.Tooltip("dias_sem_mudanca:Q", title="Dias sem mudança no consenso"),
        ],
    )
    return alt.layer(faixa, zero, barras).properties(height=260)


def realizado_contra_consenso(tabela: pd.DataFrame) -> alt.LayerChart:
    """As duas linhas lado a lado — o que se esperava e o que saiu."""
    longo = tabela.melt(
        id_vars=["data_referencia"], value_vars=["realizado", "consenso"],
        var_name="serie", value_name="valor",
    )
    return alt.layer(
        alt.Chart(longo).mark_line(strokeWidth=1.6).encode(
            x=alt.X("data_referencia:T", title=None),
            y=alt.Y("valor:Q", title=None, scale=alt.Scale(zero=False)),
            color=alt.Color(
                "serie:N",
                scale=alt.Scale(domain=["realizado", "consenso"],
                                range=["#1f2933", PALETA["Aquecimento"]]),
                legend=alt.Legend(title=None, orient="bottom"),
            ),
            tooltip=[
                alt.Tooltip("data_referencia:T", title="Referência", format="%m/%Y"),
                alt.Tooltip("serie:N", title=None),
                alt.Tooltip("valor:Q", title="Valor", format=".2f"),
            ],
        )
    ).properties(height=240)


def serie_simples(
    serie: pd.DataFrame, *, titulo: str, recessoes: pd.DataFrame | None = None
) -> alt.LayerChart:
    """Uma série qualquer no tempo, com as recessões oficiais ao fundo."""
    linha = alt.Chart(serie).mark_line(color="#1f2933", strokeWidth=1.6).encode(
        x=alt.X("data_referencia:T", title=None),
        y=alt.Y("valor:Q", title=titulo, scale=alt.Scale(zero=False)),
        tooltip=[
            alt.Tooltip("data_referencia:T", title="Referência", format="%m/%Y"),
            alt.Tooltip("valor:Q", title="Valor", format=".3f"),
        ],
    )
    if recessoes is None or serie.empty:
        return alt.layer(linha).properties(height=300)

    janela = recortar(recessoes, serie["data_referencia"].min(),
                      serie["data_referencia"].max())
    return alt.layer(_sombra_recessao(janela), linha).properties(height=300)


def varredura(resumo: pd.DataFrame, *, vigente: dict) -> alt.LayerChart:
    """O custo de cada configuração: atraso no pico contra fração do tempo ligado.

    É o gráfico que mostra por que o corte mudou. Um ponto no canto inferior
    direito parece ótimo — pouco atraso — e está ligado quase sempre: detecta
    tudo porque nunca desliga.
    """
    tabela = resumo.copy()
    tabela["percentual_ligado"] = tabela["fracao_da_janela_com_sinal"] * 100
    tabela["escolhida"] = (
        (tabela["corte_crescimento"] == vigente.get("corte_crescimento"))
        & (tabela["persistencia"] == vigente.get("persistencia"))
    )

    pontos = alt.Chart(tabela).mark_point(size=130, filled=True).encode(
        x=alt.X("percentual_ligado:Q", title="Fração da janela com o sinal ligado (%)",
                scale=alt.Scale(zero=False)),
        y=alt.Y("defasagem_pico_mediana:Q", title="Defasagem mediana no pico (meses)"),
        color=alt.Color(
            "corte_crescimento:N", title="Corte de crescimento",
            scale=alt.Scale(domain=["zero", "mediana"],
                            range=[PALETA["Expansão"], PALETA["Estagflação"]]),
            legend=alt.Legend(orient="bottom"),
        ),
        size=alt.Size("maior_episodio_meses:Q", title="Maior episódio (meses)",
                      scale=alt.Scale(range=[60, 600]), legend=alt.Legend(orient="bottom")),
        tooltip=[
            alt.Tooltip("corte_crescimento:N", title="Corte"),
            alt.Tooltip("persistencia:Q", title="Persistência (meses)"),
            alt.Tooltip("recessoes_detectadas:Q", title="Recessões detectadas"),
            alt.Tooltip("defasagem_pico_mediana:Q", title="Defasagem no pico", format="+.1f"),
            alt.Tooltip("defasagem_vale_mediana:Q", title="Defasagem no vale", format="+.1f"),
            alt.Tooltip("maior_episodio_meses:Q", title="Maior episódio (meses)"),
            alt.Tooltip("percentual_ligado:Q", title="Janela ligada (%)", format=".0f"),
            alt.Tooltip("episodios_fora_de_recessao:Q", title="Episódios fora de recessão"),
        ],
    )

    escolhida = alt.Chart(tabela[tabela["escolhida"]]).mark_point(
        size=420, filled=False, strokeWidth=2.5, color="#1f2933",
    ).encode(x=alt.X("percentual_ligado:Q"), y=alt.Y("defasagem_pico_mediana:Q"))

    return alt.layer(pontos, escolhida).properties(height=380)
