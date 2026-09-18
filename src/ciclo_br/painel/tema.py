"""Tokens de desenho do painel: cor, tipografia e o tema do Altair.

**Por que existe um módulo só para isto.** As mesmas quatro cores aparecem na
pílula de regime, na tarja de episódios, nas regiões do mapa de quadrantes e na
paleta categórica que o Streamlit entrega ao Vega. Enquanto cada uma dessas
peças carregava o próprio hexadecimal, mudar a paleta era uma caçada — e a
caçada esquecia um lugar. Aqui a cor é declarada uma vez e todo o resto importa.

**Por que duas tintas por quadrante, e não uma.** Cor de área e cor de letra não
podem ser o mesmo valor: é aritmética de contraste, não gosto. O tom de
preenchimento é escolhido para a região tingida do mapa, onde ele precisa de
3:1 contra o papel; o tom forte é o mesmo matiz escurecido até servir **ao mesmo
tempo** como letra sobre o papel e como fundo de pílula sob letra branca —
escurecer melhora as duas coisas, então um valor resolve os dois papéis. No azul
e no vermelho os dois tons coincidem, porque eles já nascem escuros o bastante.

A versão anterior desta paleta tinha uma `PALETA_TEXTO` escolhida no olho, e o
motivo dela existir era um defeito: o âmbar `#e9c46a` tinha 1,63:1 contra o
fundo e sumia como letra. A paleta atual foi buscada por otimização sob os
portões de paleta categórica (faixa de luminosidade, piso de croma, separação
sob daltonismo em **todos** os pares, contraste contra o fundo) com os matizes
presos à semântica de cada quadrante. Há teste conferindo os contrastes; mudar
um hexadecimal aqui sem refazer a conta reprova.

**Por que o verde e o vermelho estão em luminosidades diferentes.** São os dois
estados mais opostos do classificador e o par mais difícil sob deuteranopia — a
confusão clássica entre vermelho e verde. O que os separa não é o matiz, é a
folga de luminosidade: âmbar claro contra vermelho fechado. Por isso o vermelho
daqui é mais escuro do que um vermelho de alerta seria.
"""

from __future__ import annotations

import altair as alt

# ---------------------------------------------------------------- neutros
# Papel e tinta de documento, não branco e preto de tela. A tinta puxa para o
# azul-ardósia porque preto puro sobre papel claro vibra; o papel tem um traço
# mínimo de calor, longe do bege que a tela lê como "tema sépia".
PAPEL = "#fbfaf8"
PAPEL_2 = "#f2f1ec"      # fundo secundário: barra lateral, cabeçalho de tabela
TINTA = "#1b2a33"        # 14,1:1 — texto corrente e títulos
TINTA_2 = "#49585f"      # 7,1:1  — texto de apoio, rótulos de eixo
TINTA_3 = "#64727a"      # 4,8:1  — legendas de figura; o piso de texto pequeno
REGUA = "#e2ddd2"        # filete: separa sem desenhar caixa
REGUA_FORTE = "#c9c2b2"  # filete de seção

# Cinza das faixas de recessão e das linhas de corte. Não é cor de dado: é
# anotação, e por isso fica fora da paleta dos quadrantes.
COR_RECESSAO = "#6b7a82"
COR_CORTE = "#9aa3a8"

# ------------------------------------------------------------- quadrantes
# Tom de preenchimento: regiões do mapa, segmentos da tarja, marcas de gráfico.
PALETA = {
    "Expansão": "#20a08b",
    "Aquecimento": "#c17a00",
    "Desaceleração": "#005a9d",
    "Estagflação": "#873745",
}

# Tom forte: letra sobre o papel e fundo de pílula sob letra branca.
PALETA_FORTE = {
    "Expansão": "#0c8270",
    "Aquecimento": "#a36600",
    "Desaceleração": "#005a9d",
    "Estagflação": "#873745",
}

# A ordem de leitura dos quatro, e não a ordem alfabética: os dois estados de
# crescimento primeiro, os dois de contração depois.
ORDEM = ("Expansão", "Aquecimento", "Desaceleração", "Estagflação")

# ------------------------------------------------------------- tipografia
# Spectral para o texto: serifa desenhada para tela, com itálico de verdade —
# e este projeto italiciza muito. IBM Plex Sans para todo número e rótulo de
# eixo, porque algarismo em serifa numa tabela densa cansa e desalinha.
FAMILIA_TEXTO = "Spectral"
FAMILIA_DADOS = "IBM Plex Sans"
FAMILIA_CODIGO = "IBM Plex Mono"

# As três famílias numa requisição só, carregada por `componentes.estilo()`.
# Não vai no `theme.font` do config.toml: aquela chave divide a string no
# primeiro dois-pontos e trata todo o resto como URL, sem nunca separar a lista
# de fallback por vírgula — então uma URL com duas famílias é rejeitada e uma
# com sufixo `, serif` sai corrompida. O config nomeia; aqui carrega.
URL_FONTES = (
    "https://fonts.googleapis.com/css2"
    "?family=IBM+Plex+Mono:wght@400;500"
    "&family=IBM+Plex+Sans:wght@400;500;600"
    "&family=Spectral:ital,wght@0,300;0,400;0,500;0,600;1,400"
    "&display=swap"
)


def escala_quadrante() -> alt.Scale:
    """A escala de cor dos quadrantes, na ordem de leitura."""
    return alt.Scale(domain=list(ORDEM), range=[PALETA[q] for q in ORDEM])


# ------------------------------------------------------------ tema Altair
# Registrado no import e consumido por `componentes.figura`, que desenha com
# `theme=None` para que este tema valha em vez do tema padrão do Streamlit.
# Sem isso o gráfico volta à tipografia e à grade de fábrica, e a figura deixa
# de pertencer ao documento em que está.
@alt.theme.register("ciclo_br", enable=True)
def _tema_ciclo_br() -> alt.theme.ThemeConfig:
    eixo = {
        "labelFont": FAMILIA_DADOS,
        "labelFontSize": 11,
        "labelColor": TINTA_2,
        "titleFont": FAMILIA_DADOS,
        "titleFontSize": 11,
        "titleFontWeight": 500,
        "titleColor": TINTA_2,
        "titlePadding": 10,
        # Grade quase invisível e sem linha de eixo: numa figura de relatório a
        # moldura compete com o dado, e o dado é o que se veio ler.
        "gridColor": REGUA,
        "gridWidth": 1,
        "domain": False,
        "tickColor": REGUA,
        "tickSize": 4,
    }
    return {
        "config": {
            "background": "transparent",
            "font": FAMILIA_DADOS,
            "axis": eixo,
            "axisX": {**eixo, "grid": False},
            "view": {"stroke": None, "continuousWidth": 600, "continuousHeight": 300},
            "legend": {
                "labelFont": FAMILIA_DADOS,
                "labelFontSize": 11,
                "labelColor": TINTA_2,
                "titleFont": FAMILIA_DADOS,
                "titleFontSize": 11,
                "titleColor": TINTA_2,
                "symbolType": "square",
                "symbolSize": 90,
                "padding": 0,
            },
            "title": {
                "font": FAMILIA_DADOS,
                "fontSize": 12,
                "fontWeight": 600,
                "color": TINTA,
                "anchor": "start",
                "offset": 12,
            },
            "range": {"category": [PALETA[q] for q in ORDEM]},
            "line": {"color": TINTA, "strokeWidth": 1.5},
            "point": {"color": TINTA},
            "rule": {"color": COR_CORTE},
            "text": {"font": FAMILIA_DADOS, "color": TINTA},
        }
    }
