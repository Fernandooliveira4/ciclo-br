"""Cliente do SGS (Sistema Gerenciador de Séries Temporais do Banco Central).

Duas particularidades da API que ditam o desenho deste módulo:

1. Desde 26/03/2025 cada consulta cobre no máximo 10 anos. Um backfill de 2003
   até hoje precisa ser fatiado, e é por isso que existe `_janelas`. Usamos 9
   anos de folga para não depender de como o servidor conta a borda.

2. Quando não há dado no intervalo pedido, o servidor responde 404 com uma
   página HTML em vez de uma lista vazia. Isso é ausência de dado, não falha, e
   precisa ser distinguido de um erro de verdade — senão o backfill quebra ao
   varrer anos anteriores ao início da série.
"""

from __future__ import annotations

import datetime as dt
import logging
import time

import pandas as pd
import requests
from tenacity import (
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

log = logging.getLogger(__name__)

URL = "https://api.bcb.gov.br/dados/serie/bcdata.sgs.{codigo}/dados"
ANOS_POR_JANELA = 9
TEMPO_LIMITE = 30
PAUSA_ENTRE_JANELAS = 0.5


class ErroSGS(RuntimeError):
    """Falha ao consultar o SGS que não é simples ausência de dados."""


def _janelas(inicio: dt.date, fim: dt.date) -> list[tuple[dt.date, dt.date]]:
    """Fatia o intervalo em pedaços que cabem no limite da API."""
    if inicio > fim:
        return []
    janelas = []
    corrente = inicio
    while corrente <= fim:
        try:
            proximo = corrente.replace(year=corrente.year + ANOS_POR_JANELA)
        except ValueError:  # 29 de fevereiro
            proximo = corrente.replace(year=corrente.year + ANOS_POR_JANELA, day=28)
        termino = min(proximo - dt.timedelta(days=1), fim)
        janelas.append((corrente, termino))
        corrente = termino + dt.timedelta(days=1)
    return janelas


def _converter_valor(bruto: str | float | None) -> float | None:
    if bruto is None or bruto == "":
        return None
    if isinstance(bruto, (int, float)):
        return float(bruto)
    texto = str(bruto).strip()
    if not texto:
        return None
    # O SGS entrega ponto decimal, mas alguns pontos de acesso usam formato pt-BR.
    if "," in texto:
        texto = texto.replace(".", "").replace(",", ".")
    return float(texto)


@retry(
    retry=retry_if_exception_type((requests.RequestException, ErroSGS)),
    stop=stop_after_attempt(5),
    wait=wait_exponential(multiplier=1, min=2, max=30),
    reraise=True,
)
def _buscar_janela(codigo: int, inicio: dt.date, fim: dt.date) -> list[dict]:
    resposta = requests.get(
        URL.format(codigo=codigo),
        params={
            "formato": "json",
            "dataInicial": inicio.strftime("%d/%m/%Y"),
            "dataFinal": fim.strftime("%d/%m/%Y"),
        },
        timeout=TEMPO_LIMITE,
        headers={"Accept": "application/json"},
    )

    # 404 aqui quase sempre significa "não há dado nesta janela", não erro.
    if resposta.status_code == 404:
        return []
    if resposta.status_code >= 400:
        raise ErroSGS(f"série {codigo}: HTTP {resposta.status_code} em {inicio}..{fim}")

    try:
        dados = resposta.json()
    except ValueError as exc:
        # O SGS devolve HTML quando está instável; tratamos como falha transitória.
        raise ErroSGS(f"série {codigo}: resposta não-JSON em {inicio}..{fim}") from exc

    if not isinstance(dados, list):
        raise ErroSGS(f"série {codigo}: formato inesperado em {inicio}..{fim}")
    return dados


def buscar(codigo: int, inicio: dt.date, fim: dt.date | None = None) -> pd.DataFrame:
    """Baixa a série inteira no intervalo, fatiando conforme o limite da API.

    Devolve um DataFrame com data_referencia (date) e valor (float), ordenado e
    sem duplicatas de data.
    """
    fim = fim or dt.date.today()
    registros: list[dict] = []
    for i, (ini, term) in enumerate(_janelas(inicio, fim)):
        if i:
            time.sleep(PAUSA_ENTRE_JANELAS)
        lote = _buscar_janela(codigo, ini, term)
        log.debug("série %s janela %s..%s: %d registros", codigo, ini, term, len(lote))
        registros.extend(lote)

    if not registros:
        return pd.DataFrame(columns=["data_referencia", "valor"])

    df = pd.DataFrame(registros)
    df["data_referencia"] = pd.to_datetime(df["data"], format="%d/%m/%Y").dt.date
    df["valor"] = df["valor"].map(_converter_valor)
    df = df[["data_referencia", "valor"]].dropna(subset=["valor"])
    df = df.sort_values("data_referencia").drop_duplicates("data_referencia", keep="last")
    return df.reset_index(drop=True)
