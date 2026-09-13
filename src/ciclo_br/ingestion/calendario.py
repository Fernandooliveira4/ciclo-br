"""Calendário de divulgações do IBGE (API v3 de calendário).

**Não dispara nada.** A fonte da verdade sobre "houve divulgação" continua sendo
o diff da própria série: depender do calendário criaria um ponto único de falha
para o pipeline inteiro. Se o calendário sumir, a ingestão continua funcionando.

Mas ele deixou de ser só enfeite de painel. A API devolve, para cada divulgação,
o **período de referência** do dado divulgado — e isso é o que torna a camada de
surpresa possível: sem a data em que o número saiu, não há como saber qual era o
consenso do Focus na véspera. A cobertura histórica começa em **2017**; antes
disso a API devolve vazio, e é esse o motivo de a série de surpresa começar lá.

Três usos, então:

  1. a data de divulgação de cada referência, que a camada de surpresa consome;
  2. o painel "próximas divulgações" do dashboard;
  3. saber em que dias vale a pena consultar as APIs com mais frequência.

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

# Antes de 2017 a API responde com lista vazia para todos os produtos usados
# aqui. Verificado produto a produto em 12/09/2026; é o limite da fonte, não uma
# escolha nossa.
INICIO_COBERTURA = dt.date(2017, 1, 1)


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


def _chave(linha) -> tuple:
    """Uma divulgação por produto e período de referência.

    Quando o item vem sem referência (acontece em alguns avisos), a própria data
    de divulgação faz o papel de chave, para não colapsar eventos distintos.
    """
    referencia = linha["data_referencia"]
    if pd.isna(referencia) or referencia is None:
        return (linha["produto_id"], None, linha["data_divulgacao"])
    return (linha["produto_id"], referencia, None)


def mesclar(anterior: pd.DataFrame, novo: pd.DataFrame) -> pd.DataFrame:
    """Junta o que já estava gravado com a coleta atual, a coleta atual vencendo.

    A rodada diária consulta uma janela curta, mas o arquivo precisa guardar todo
    o histórico de datas de divulgação — é dele que a camada de surpresa tira a
    véspera de cada release. Sem mesclar, cada execução apagaria 2017-2025.

    Onde as duas versões falam do mesmo par (produto, referência), vale a nova: o
    IBGE remarca datas, e a informação mais recente é a correta. Isso é diferente
    da regra das observações, que nunca sobrescreve — o calendário é metadado
    mutável, não fato datado.
    """
    if anterior.empty:
        return novo
    if novo.empty:
        return anterior

    juntos = pd.concat([anterior, novo], ignore_index=True)
    juntos["_chave"] = [_chave(linha) for _, linha in juntos.iterrows()]
    # `keep="last"` com o novo no fim: a coleta atual vence.
    juntos = juntos.drop_duplicates(subset="_chave", keep="last").drop(columns="_chave")
    return (juntos.sort_values(["data_divulgacao", "produto_id"], kind="stable")
                  .reset_index(drop=True))


def salvar(df: pd.DataFrame) -> bool:
    """Mescla com o gravado e regrava só se o conteúdo mudou.

    A comparação ignora `coletado_em`. Sem esse cuidado o arquivo seria reescrito
    todo dia só porque o carimbo de tempo é novo, e o histórico do Git encheria de
    commits que não dizem nada.
    """
    CAMINHO.parent.mkdir(parents=True, exist_ok=True)

    anterior = carregar()
    completo = mesclar(anterior, df)
    colunas = [c for c in completo.columns if c != "coletado_em"]
    if not anterior.empty and anterior[colunas].reset_index(drop=True).equals(
            completo[colunas].reset_index(drop=True)):
        log.info("calendário sem alteração — arquivo mantido")
        return False

    completo.to_parquet(CAMINHO, index=False, compression="zstd")
    return True


def divulgacoes(series_id: str, df: pd.DataFrame | None = None) -> pd.Series:
    """Data de divulgação por período de referência, para uma série.

    Chave do dicionário é `data_referencia`; valor é a data em que aquele número
    foi ao ar. É o que a camada de surpresa precisa para achar o consenso da
    véspera.
    """
    df = carregar() if df is None else df
    if df.empty:
        return pd.Series(dtype="object")
    alvo = df[df["series_ids"].str.split(",").apply(lambda ids: series_id in ids)]
    alvo = alvo[alvo["data_referencia"].notna()]
    if alvo.empty:
        return pd.Series(dtype="object")
    alvo = alvo.sort_values("data_divulgacao", kind="stable")
    return alvo.set_index("data_referencia")["data_divulgacao"]


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
    parser.add_argument("--backfill", action="store_true",
                        help=f"varre desde {INICIO_COBERTURA:%Y}, ano a ano, em vez da "
                             "janela curta da rodada diária")
    parser.add_argument("--verboso", action="store_true")
    args = parser.parse_args(argv)

    logging.basicConfig(
        level=logging.DEBUG if args.verboso else logging.INFO,
        format="%(asctime)s %(levelname)-7s %(message)s", datefmt="%H:%M:%S",
    )

    produtos = calendario_produtos()
    try:
        if args.backfill:
            partes = []
            for ano in range(INICIO_COBERTURA.year, dt.date.today().year + 2):
                parte = buscar(produtos, de=dt.date(ano, 1, 1), ate=dt.date(ano, 12, 31))
                log.info("  %d: %d evento(s)", ano, len(parte))
                partes.append(parte)
            df = pd.concat([p for p in partes if not p.empty], ignore_index=True)
        else:
            df = buscar(produtos)
    except ErroCalendario as exc:
        # Falha aqui não pode derrubar o pipeline: o calendário não dispara nada.
        log.warning("calendário indisponível (%s) — seguindo sem ele", exc)
        return 0

    salvar(df)
    log.info("calendário: %d evento(s) coletado(s) de %d produto(s); %d no arquivo",
             len(df), len(produtos), len(carregar()))
    for _, linha in proximas(df, limite=5).iterrows():
        log.info("  %s  %s (ref %s)", linha["data_divulgacao"],
                 linha["produto"], linha["data_referencia"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
