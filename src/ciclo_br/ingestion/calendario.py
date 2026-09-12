"""Calendário de divulgações do IBGE (API v3 de calendário).

Papel deliberadamente **auxiliar**. A fonte da verdade sobre "houve divulgação"
continua sendo o diff da própria série: o calendário não dispara nada, porque
depender dele criaria um ponto único de falha para o pipeline inteiro. Ele serve
para duas coisas:

  1. o painel "próximas divulgações" do dashboard;
  2. saber em que dias vale a pena consultar as APIs com mais frequência.

Se o calendário sumir, o pipeline continua funcionando e só perde a antecipação.

O calendário do Banco Central também existe, mas é endpoint interno do site, não
documentado e sem contrato público — fica de fora por isso.
"""

from __future__ import annotations

import datetime as dt
import logging

import pandas as pd
import requests
from tenacity import (
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

from ..config import DIR_DADOS

log = logging.getLogger(__name__)

BASE = "https://servicodados.ibge.gov.br/api/v3/calendario/"
TEMPO_LIMITE = 60
CAMINHO = DIR_DADOS / "calendario.parquet"


class ErroCalendario(RuntimeError):
    """Falha ao consultar o calendário do IBGE."""


@retry(
    retry=retry_if_exception_type((requests.RequestException, ErroCalendario)),
    stop=stop_after_attempt(4),
    wait=wait_exponential(multiplier=1, min=2, max=20),
    reraise=True,
)
def _buscar_produto(produto_id: int, de: dt.date, ate: dt.date, qtd: int = 100) -> list[dict]:
    resposta = requests.get(
        f"{BASE}{produto_id}",
        params={"de": de.isoformat(), "ate": ate.isoformat(), "qtd": str(qtd)},
        timeout=TEMPO_LIMITE,
        headers={"Accept": "application/json"},
    )
    if resposta.status_code >= 400:
        raise ErroCalendario(f"produto {produto_id}: HTTP {resposta.status_code}")
    try:
        return resposta.json().get("items", [])
    except ValueError as exc:
        raise ErroCalendario(f"produto {produto_id}: resposta não-JSON") from exc


def _data_divulgacao(bruto: str | None) -> dt.date | None:
    """Converte 'DD/MM/YYYY HH:MM:SS' na data."""
    if not bruto:
        return None
    try:
        return dt.datetime.strptime(bruto.split(" ")[0], "%d/%m/%Y").date()
    except ValueError:
        return None


def _data_referencia(item: dict) -> dt.date | None:
    ano, mes = item.get("ano_referencia_inicio"), item.get("mes_referencia_inicio")
    if not ano or not mes or not 1 <= int(mes) <= 12:
        return None
    return dt.date(int(ano), int(mes), 1)


def buscar(
    produtos: dict[int, list[str]],
    *,
    de: dt.date | None = None,
    ate: dt.date | None = None,
) -> pd.DataFrame:
    """Divulgações agendadas dos produtos pedidos.

    `produtos` mapeia produto_id do IBGE para os ids de série que aquele produto
    alimenta — é isso que permite ligar "sai o IPCA dia 9" à série `ipca`.
    """
    de = de or dt.date.today() - dt.timedelta(days=90)
    ate = ate or dt.date.today() + dt.timedelta(days=365)

    linhas = []
    for produto_id, series_ids in produtos.items():
        for item in _buscar_produto(produto_id, de, ate):
            divulgacao = _data_divulgacao(item.get("data_divulgacao"))
            if divulgacao is None:
                continue
            linhas.append({
                "produto_id": produto_id,
                "produto": item.get("nome_produto") or "",
                "series_ids": ",".join(series_ids),
                "titulo": item.get("titulo") or "",
                "data_divulgacao": divulgacao,
                "data_referencia": _data_referencia(item),
            })

    if not linhas:
        return pd.DataFrame(columns=["produto_id", "produto", "series_ids", "titulo",
                                     "data_divulgacao", "data_referencia", "coletado_em"])

    df = pd.DataFrame(linhas).sort_values("data_divulgacao", kind="stable")
    df["coletado_em"] = dt.datetime.now(dt.UTC)
    return df.reset_index(drop=True)


def salvar(df: pd.DataFrame) -> None:
    """Grava o instantâneo do calendário.

    Diferente das observações, o calendário é **substituído** a cada coleta: ele
    é metadado derivado e mutável (o IBGE remarca datas), não um fato datado que
    precise ser preservado. A regra de nunca sobrescrever vale para observação.
    """
    CAMINHO.parent.mkdir(parents=True, exist_ok=True)
    df.to_parquet(CAMINHO, index=False, compression="zstd")


def carregar() -> pd.DataFrame:
    if not CAMINHO.exists():
        return pd.DataFrame()
    return pd.read_parquet(CAMINHO)


def proximas(df: pd.DataFrame | None = None, *, limite: int = 5) -> pd.DataFrame:
    df = carregar() if df is None else df
    if df.empty:
        return df
    hoje = dt.date.today()
    futuras = df[df["data_divulgacao"] >= hoje]
    return futuras.sort_values("data_divulgacao").head(limite)


def main(argv: list[str] | None = None) -> int:
    import argparse

    from ..config import calendario_produtos

    parser = argparse.ArgumentParser(description="Coleta o calendário de divulgações do IBGE")
    parser.add_argument("--verboso", action="store_true")
    args = parser.parse_args(argv)

    logging.basicConfig(
        level=logging.DEBUG if args.verboso else logging.INFO,
        format="%(asctime)s %(levelname)-7s %(message)s", datefmt="%H:%M:%S",
    )

    produtos = calendario_produtos()
    try:
        df = buscar(produtos)
    except ErroCalendario as exc:
        # Falha aqui não pode derrubar o pipeline: o calendário é auxiliar.
        log.warning("calendário indisponível (%s) — seguindo sem ele", exc)
        return 0

    salvar(df)
    log.info("calendário: %d evento(s) de %d produto(s)", len(df), len(produtos))
    for _, linha in proximas(df, limite=5).iterrows():
        log.info("  %s  %s (ref %s)", linha["data_divulgacao"],
                 linha["produto"], linha["data_referencia"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
