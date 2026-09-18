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
todos os meses e a posição do ponto diz, sozinha, em que quadrante o mês caiu.

**No mapa, a cor do ponto vem da posição, e não do regime vigente.** As duas
discordam enquanto a regra de persistência não confirma uma virada, e pintar
pelo vigente colocava pontos verdes dentro da faixa amarela: a cor
contradizendo o eixo, que é o que o olho lê primeiro. O regime em vigor voltou
como anel em volta do ponto, só nos meses em que há discordância.
"""

from __future__ import annotations

import altair as alt
import pandas as pd

from .tema import COR_CORTE, COR_RECESSAO, ORDEM, PALETA, PALETA_FORTE, TINTA
from .tema import escala_quadrante as _escala_quadrante

# Reexportados para quem já importava daqui: a cor passou a ser declarada em
# `tema.py`, junto com a derivação e o teste de contraste que a sustenta, mas
# este continua sendo o módulo onde o desenho mora.
__all__ = [
    "COR_CORTE", "COR_RECESSAO", "ORDEM", "PALETA", "PALETA_FORTE",
    "CORES_INVESTIMENTO",
    "eixo_no_tempo", "faixa_de_quadrantes", "historia_do_regime",
    "historico_de_surpresa", "mapa_de_quadrantes", "realizado_contra_consenso",
    "recortar", "serie_simples", "series_comparadas", "varredura",
]

# Azul e âmbar, e não o par verde/vermelho dos quadrantes: é o que tem a maior
# folga de luminosidade da paleta e o que sobrevive a deuteranopia. Mora aqui,
# junto das outras cores, para que o teste de paleta alcance.
CORES_INVESTIMENTO = {
    "Taxa de investimento": PALETA["Desaceleração"],
    "Consumo do governo": PALETA["Aquecimento"],
}


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
    linha = base.mark_line(color=TINTA, strokeWidth=1.6).encode(
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


def _regioes(limite_x: list[float], limite_y: list[float]) -> pd.DataFrame:
    """Os quatro quadrantes como área, não como duas linhas para cruzar de cabeça.

    Duas linhas tracejadas obrigam o leitor a intersectar dois sinais para saber
    onde um ponto caiu. Tingir a região dá a resposta antes da pergunta — e, de
    quebra, torna impossível esconder uma cor de ponto que discorde do lugar
    onde ele está.
    """
    return pd.DataFrame([
        {"x": 0.0, "x2": limite_x[1], "y": 0.0, "y2": limite_y[1],
         "quadrante": "Aquecimento"},
        {"x": 0.0, "x2": limite_x[1], "y": limite_y[0], "y2": 0.0,
         "quadrante": "Expansão"},
        {"x": limite_x[0], "x2": 0.0, "y": 0.0, "y2": limite_y[1],
         "quadrante": "Estagflação"},
        {"x": limite_x[0], "x2": 0.0, "y": limite_y[0], "y2": 0.0,
         "quadrante": "Desaceleração"},
    ]).assign(cor=lambda d: [PALETA[q] for q in d["quadrante"]])


def _recuado(limite: list[float], *, positivo: bool, recuo: float) -> float:
    """Um ponto dentro da metade pedida do eixo, recuado da borda externa.

    O recuo é fração do **próprio lado**, não do eixo inteiro. Essa distinção
    não é decorativa: o eixo de inflação passa a maior parte do tempo abaixo do
    corte, então a metade de cima é uma faixa fina, e recuar pela altura total
    empurrava "Aquecimento" para cinco pixels da linha do zero. O nome parava de
    identificar a região e passava a parecer a legenda da linha.
    """
    borda = limite[1] if positivo else limite[0]
    return borda - borda * recuo


def _cantos(limite_x: list[float], limite_y: list[float],
            *, recuo: float = 0.16) -> pd.DataFrame:
    """Os quatro nomes de quadrante, recuados para dentro do **seu** quadrante.

    Vega-Lite não aceita `align`/`baseline` como canal de codificação, então o
    recuo é feito na posição: cada nome entra um pouco no seu canto e a
    ancoragem padrão (centro) resolve o resto.
    """
    def ponto(nome: str, *, x: bool, y: bool) -> dict:
        return {
            "x": _recuado(limite_x, positivo=x, recuo=recuo),
            "y": _recuado(limite_y, positivo=y, recuo=recuo),
            "quadrante": nome,
            "cor": PALETA_FORTE[nome],
        }

    return pd.DataFrame([
        ponto("Aquecimento", x=True, y=True),
        ponto("Expansão", x=True, y=False),
        ponto("Estagflação", x=False, y=True),
        ponto("Desaceleração", x=False, y=False),
    ])


def mapa_de_quadrantes(reg: pd.DataFrame, *, meses: int = 24) -> alt.LayerChart:
    """Os últimos meses no plano crescimento × inflação, em distância ao corte.

    **A cor do ponto é a do quadrante onde ele está, e não a do regime vigente.**
    Os dois discordam enquanto a regra de persistência não confirma uma virada:
    o mês já cruzou a fronteira, mas o regime em vigor ainda é o anterior.
    Pintando pelo vigente, abril e maio de 2025 saíam verdes dentro da faixa
    amarela — a cor negando o eixo, que é o que o olho lê primeiro, e sem nada na
    tela dizendo por quê.

    O regime vigente voltou como **anel**, desenhado só nos meses em que os dois
    discordam. Assim a contradição deixa de ser ruído de leitura e vira a
    informação mais interessante do gráfico: o anel é o atraso da regra de
    persistência, visível no lugar onde ele acontece.

    O caminho importa mais que o ponto: dois meses no mesmo quadrante podem estar
    indo em direções opostas, e é a trajetória que mostra isso.
    """
    recorte = reg[reg["quadrante"].notna()].tail(meses).copy()
    recorte["rotulo"] = recorte["data"].dt.strftime("%m/%Y")
    recorte["situacao"] = [
        "confirmado" if not aguardando else
        f"{n} mês do novo sinal" if n == 1 else f"{n} meses do novo sinal"
        for aguardando, n in zip(
            recorte["pendente"].notna(),
            recorte["meses_pendente"].fillna(0).astype(int),
            strict=True,
        )
    ]
    aguardando = recorte[recorte["pendente"].notna()]
    ultimo = recorte.tail(1)

    # O domínio é forçado a conter o zero nos dois eixos. Sem isso, um período em
    # que a economia não cruza uma das fronteiras produziria um "mapa de
    # quadrantes" sem a fronteira à vista — e o leitor teria que acreditar na
    # legenda em vez de ver a posição.
    limite_x = _dominio(recorte["distancia_crescimento"])
    limite_y = _dominio(recorte["distancia_inflacao"])

    # As faixas vêm primeiro, e com a escala explícita: são a camada de base do
    # `layer`, e é delas que as outras herdam o domínio.
    faixas = alt.Chart(_regioes(limite_x, limite_y)).mark_rect(opacity=0.10).encode(
        x=alt.X("x:Q", scale=alt.Scale(domain=limite_x, nice=False), title=None),
        x2=alt.X2("x2:Q"),
        y=alt.Y("y:Q", scale=alt.Scale(domain=limite_y, nice=False), title=None),
        y2=alt.Y2("y2:Q"),
        # `scale=None` usa o hex da própria coluna. Sem escala não há domínio a
        # conciliar com as outras camadas de cor, que é onde o gráfico empilhado
        # deste painel já quebrou uma vez.
        color=alt.Color("cor:N", scale=None, legend=None),
        # Um tooltip explícito e útil. Sem ele, passar o mouse sobre a região
        # despeja os campos crus da tabela — `x2 0`, `cor #005a9d` — que é
        # vazamento de estrutura interna na cara do leitor.
        tooltip=[alt.Tooltip("quadrante:N", title="Quadrante")],
    )

    nomes = alt.Chart(_cantos(limite_x, limite_y)).mark_text(
        fontSize=12, fontWeight="bold", opacity=0.85,
    ).encode(
        x=alt.X("x:Q"), y=alt.Y("y:Q"),
        text=alt.Text("quadrante:N"),
        color=alt.Color("cor:N", scale=None, legend=None),
    )

    eixo_x = alt.Chart(pd.DataFrame({"v": [0.0]})).mark_rule(
        color=COR_CORTE, strokeDash=[4, 4]).encode(y=alt.Y("v:Q"))
    eixo_y = alt.Chart(pd.DataFrame({"v": [0.0]})).mark_rule(
        color=COR_CORTE, strokeDash=[4, 4]).encode(x=alt.X("v:Q"))

    caminho = alt.Chart(recorte).mark_line(
        color=TINTA, strokeWidth=1, opacity=0.45,
    ).encode(
        x=alt.X("distancia_crescimento:Q"),
        y=alt.Y("distancia_inflacao:Q"),
        order=alt.Order("data:T"),
    )

    dica = [
        alt.Tooltip("rotulo:N", title="Mês"),
        alt.Tooltip("quadrante_bruto:N", title="Quadrante do mês"),
        alt.Tooltip("quadrante:N", title="Regime vigente"),
        alt.Tooltip("situacao:N", title="Persistência"),
        alt.Tooltip("eixo_crescimento:Q", title="Crescimento", format=".2f"),
        alt.Tooltip("eixo_inflacao:Q", title="Inflação", format=".2f"),
        alt.Tooltip("corte_inflacao:Q", title="Corte de inflação", format=".2f"),
    ]

    pontos = alt.Chart(recorte).mark_circle(size=95).encode(
        x=alt.X("distancia_crescimento:Q",
                title="Crescimento − corte (p.p. anualizados)"),
        y=alt.Y("distancia_inflacao:Q",
                title="Inflação − corte (p.p. anualizados)"),
        # Pelo quadrante **do mês**, que é o que a posição já diz. A cor aqui é
        # redundante de propósito: redundância reforça, contradição confunde.
        color=alt.Color("quadrante_bruto:N", scale=_escala_quadrante(), legend=None),
        # A faixa de opacidade não desce abaixo de 0,45: sobre a região tingida,
        # um ponto a 0,3 perdia a cor e virava um borrão cinza.
        opacity=alt.Opacity("data:T", legend=None, scale=alt.Scale(range=[0.45, 1])),
        tooltip=dica,
    )

    # Só os meses em que o vigente discorda da posição. O anel leva a cor do
    # regime que ainda está em vigor: o ponto mudou de lado, o crachá não.
    anel = alt.Chart(aguardando).mark_point(
        size=250, filled=False, strokeWidth=2.5, opacity=0.95,
    ).encode(
        x=alt.X("distancia_crescimento:Q"),
        y=alt.Y("distancia_inflacao:Q"),
        color=alt.Color("quadrante:N", scale=_escala_quadrante(), legend=None),
        tooltip=dica,
    )

    destaque = alt.Chart(ultimo).mark_point(
        size=260, filled=False, strokeWidth=2, color=TINTA,
    ).encode(x=alt.X("distancia_crescimento:Q"), y=alt.Y("distancia_inflacao:Q"))

    etiqueta = alt.Chart(ultimo).mark_text(
        dx=12, dy=-12, fontSize=12, fontWeight="bold", color=TINTA, align="left",
    ).encode(
        x=alt.X("distancia_crescimento:Q"),
        y=alt.Y("distancia_inflacao:Q"),
        text=alt.Text("rotulo:N"),
    )

    return alt.layer(
        faixas, nomes, eixo_x, eixo_y, caminho, pontos, anel, destaque, etiqueta
    ).resolve_scale(color="independent").properties(height=420)


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
        color=TINTA, strokeWidth=1).encode(y=alt.Y("v:Q"))

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
                                range=[TINTA, PALETA["Aquecimento"]]),
                legend=alt.Legend(title=None, orient="bottom"),
            ),
            tooltip=[
                alt.Tooltip("data_referencia:T", title="Referência", format="%m/%Y"),
                alt.Tooltip("serie:N", title=None),
                alt.Tooltip("valor:Q", title="Valor", format=".2f"),
            ],
        )
    ).properties(height=240)


def series_comparadas(
    tabela: pd.DataFrame,
    *,
    titulo: str,
    recessoes: pd.DataFrame | None = None,
    cores: dict[str, str] | None = None,
    altura: int = 340,
) -> alt.LayerChart:
    """Duas ou mais séries de MESMA unidade no mesmo eixo, com as recessões ao fundo.

    Espera formato longo: `data_referencia`, `serie` (já com o rótulo de
    exibição, não o id) e `valor`.

    **Aqui o eixo é único, e isso é o oposto da escolha feita em
    `historia_do_regime`.** Lá os dois painéis são empilhados porque o momentum
    de crescimento foi de −38 a +40 e a inflação vive entre 0 e 13: num eixo só,
    a inflação vira uma linha reta. Aqui as séries são percentuais do mesmo
    denominador, medidas no mesmo trimestre, e ocupam a faixa de 14% a 21% — a
    comparação de nível entre elas é precisamente a informação que o gráfico
    existe para dar, e empilhar a destruiria. A regra não é "um eixo por série"
    nem "um eixo para todas": dividir eixo só é legítimo quando as séries são
    comensuráveis, e o custo de errar é simétrico nos dois sentidos.

    `zero=False` porque o zero fica catorze pontos abaixo do menor valor
    observado, e incluí-lo comprimiria trinta anos de variação numa faixa fina
    no alto do desenho.

    Genérica, e não `investimento_contra_governo`, porque o repositório já tem
    `realizado_contra_consenso` com os nomes cravados no corpo — que é
    exatamente a função que não deu para reaproveitar aqui.
    """
    cores = cores or {}
    # Ordem de aparição, e não alfabética: é ela que o Vega usa na legenda, e a
    # primeira série da tabela é a que o texto da página discute primeiro.
    ordem = list(dict.fromkeys(tabela["serie"]))
    linhas = alt.Chart(tabela).mark_line(strokeWidth=1.7).encode(
        x=alt.X("data_referencia:T", title=None),
        y=alt.Y("valor:Q", title=titulo, scale=alt.Scale(zero=False)),
        color=alt.Color(
            "serie:N",
            scale=alt.Scale(domain=ordem,
                            range=[cores.get(s, TINTA) for s in ordem]),
            legend=alt.Legend(title=None, orient="bottom"),
        ),
        tooltip=[
            alt.Tooltip("data_referencia:T", title="Trimestre", format="%m/%Y"),
            alt.Tooltip("serie:N", title=None),
            alt.Tooltip("valor:Q", title=titulo, format=".2f"),
        ],
    )
    if recessoes is None or tabela.empty:
        return alt.layer(linhas).properties(height=altura)

    janela = recortar(recessoes, tabela["data_referencia"].min(),
                      tabela["data_referencia"].max())
    return alt.layer(_sombra_recessao(janela), linhas).properties(height=altura)


def serie_simples(
    serie: pd.DataFrame, *, titulo: str, recessoes: pd.DataFrame | None = None
) -> alt.LayerChart:
    """Uma série qualquer no tempo, com as recessões oficiais ao fundo."""
    linha = alt.Chart(serie).mark_line(color=TINTA, strokeWidth=1.6).encode(
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
        size=420, filled=False, strokeWidth=2.5, color=TINTA,
    ).encode(x=alt.X("percentual_ligado:Q"), y=alt.Y("defasagem_pico_mediana:Q"))

    return alt.layer(pontos, escolhida).properties(height=380)
