"""Formatação em português para a tela e para o texto do briefing.

Mora fora do painel porque os dois consumidores precisam escrever os números do
mesmo jeito: o briefing cita "+0,7%" e a tela mostra "+0,7%", e a verificação de
números do briefing compara strings. Duas implementações de "formate isto em
português" quebrariam essa comparação no primeiro arredondamento divergente.

`locale` não é usado de propósito: o nome do locale muda entre Windows, o runner
do GitHub Actions e o contêiner do Streamlit Cloud, e um painel que mostra
"December 2025" em um deles não serve. Uma tabela de doze nomes resolve e não
depende do sistema.
"""

from __future__ import annotations

import datetime as dt
import math

MESES = ("janeiro", "fevereiro", "março", "abril", "maio", "junho", "julho",
         "agosto", "setembro", "outubro", "novembro", "dezembro")

MESES_CURTOS = ("jan", "fev", "mar", "abr", "mai", "jun",
                "jul", "ago", "set", "out", "nov", "dez")


def mes_ano(data) -> str:
    """dezembro de 2025."""
    if data is None:
        return "—"
    return f"{MESES[data.month - 1]} de {data.year}"


def mes_curto(data) -> str:
    """dez/2025."""
    if data is None:
        return "—"
    return f"{MESES_CURTOS[data.month - 1]}/{data.year}"


def dia(data) -> str:
    """12/09/2026."""
    if data is None:
        return "—"
    return f"{data.day:02d}/{data.month:02d}/{data.year}"


def numero(valor, casas: int = 1, *, sinal: bool = False, sufixo: str = "") -> str:
    """Número com vírgula decimal. `None`/NaN viram travessão, nunca 'nan'."""
    if valor is None:
        return "—"
    try:
        valor = float(valor)
    except (TypeError, ValueError):
        return "—"
    if math.isnan(valor):
        return "—"
    texto = f"{valor:{'+' if sinal else ''}.{casas}f}".replace(".", ",")
    return texto + sufixo


def dias(quantidade) -> str:
    """1 dia, 2 dias."""
    if quantidade is None:
        return "—"
    quantidade = int(quantidade)
    return f"{quantidade} dia" if abs(quantidade) == 1 else f"{quantidade} dias"


def meses(quantidade) -> str:
    """1 mês, 2 meses — a concordância que um painel em português precisa ter."""
    if quantidade is None:
        return "—"
    quantidade = int(quantidade)
    return f"{quantidade} mês" if abs(quantidade) == 1 else f"{quantidade} meses"


def defasagem(valor) -> str:
    """+4 meses de atraso / −2 meses de antecipação / no mês.

    Escrito por extenso porque o sinal sozinho é ambíguo na tela: em uma tabela
    de defasagem, "+4" só significa atraso para quem já leu a metodologia.
    """
    if valor is None or (isinstance(valor, float) and math.isnan(valor)):
        return "—"
    valor = int(round(float(valor)))
    if valor == 0:
        return "no mês"
    palavra = "atraso" if valor > 0 else "antecipação"
    return f"{numero(valor, 0, sinal=True)} — {meses(abs(valor))} de {palavra}"


def idade(momento: dt.datetime | None, *, agora: dt.datetime | None = None) -> str:
    """Há quanto tempo um arquivo foi gerado, em linguagem de painel."""
    if momento is None:
        return "—"
    agora = agora or dt.datetime.now(dt.UTC)
    if momento.tzinfo is None:
        momento = momento.replace(tzinfo=dt.UTC)
    horas = (agora - momento).total_seconds() / 3600
    if horas < 1:
        return "há menos de uma hora"
    if horas < 24:
        return f"há {int(horas)} h"
    dias = int(horas // 24)
    return "ontem" if dias == 1 else f"há {dias} dias"
