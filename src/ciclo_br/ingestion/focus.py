"""Cliente da API de Expectativas de Mercado do BCB (Olinda/OData) — o Focus.

Três particularidades da API ditam este módulo:

1. **Espaço precisa virar `%20`, não `+`.** O servidor rejeita com HTTP 400 e uma
   mensagem enganosa ("The types 'Edm.Boolean' and 'Edm.String' are not
   compatible") qualquer filtro OData com espaço codificado à maneira de
   formulário. Como `requests` usa `+` por padrão, a query é montada à mão.

2. **Não há `$count` nem `nextLink`.** A paginação é manual, por `$skip`.

3. **Cada coleta traz 25 meses de referência** (o corrente e 24 à frente).
   O projeto só usa o consenso do período prestes a ser divulgado, então o resto
   é descartado na ingestão: guardar tudo seriam ~160 mil linhas por indicador
   desde 2000, das quais mais de 90% são projeções de longo prazo que nenhuma
   parte do projeto consulta.

O que sai daqui tem `data_coleta` por linha, e não por execução: no Focus a data
da coleta é parte da identidade da observação — o consenso de terça e o de quarta
são fatos distintos, não um corrigindo o outro.
"""

from __future__ import annotations

import datetime as dt
import logging
import time
from urllib.parse import quote, urlencode

import pandas as pd
import requests
from tenacity import (
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

log = logging.getLogger(__name__)

BASE = "https://olinda.bcb.gov.br/olinda/servico/Expectativas/versao/v1/odata/"
TAMANHO_PAGINA = 10_000
TEMPO_LIMITE = 90
PAUSA_ENTRE_PAGINAS = 0.3

# Quantos meses de defasagem entre a coleta e o período projetado ainda
# interessam. Mensal: o mês corrente e o anterior bastam, porque o IPCA de
# agosto é divulgado no início de setembro. Trimestral: o PIB do 2º trimestre
# sai em setembro, cinco meses depois do início do trimestre.
JANELA_MESES = {"mensal": 1, "trimestral": 6}


class ErroFocus(RuntimeError):
    """Falha ao consultar a API de Expectativas."""


def _url(recurso: str, **params: str) -> str:
    params.setdefault("$format", "json")
    # quote_via=quote é o ponto inteiro: sem isso os espaços viram '+' e a API recusa.
    return f"{BASE}{recurso}?{urlencode(params, quote_via=quote)}"


@retry(
    retry=retry_if_exception_type((requests.RequestException, ErroFocus)),
    stop=stop_after_attempt(5),
    wait=wait_exponential(multiplier=1, min=2, max=30),
    reraise=True,
)
def _pagina(recurso: str, filtro: str, skip: int) -> list[dict]:
    url = _url(
        recurso,
        **{
            "$filter": filtro,
            "$select": "Data,DataReferencia,Mediana,numeroRespondentes",
            "$orderby": "Data asc",
            "$top": str(TAMANHO_PAGINA),
            "$skip": str(skip),
        },
    )
    resposta = requests.get(url, timeout=TEMPO_LIMITE, headers={"Accept": "application/json"})
    if resposta.status_code >= 400:
        raise ErroFocus(f"{recurso}: HTTP {resposta.status_code} — {resposta.text[:200]}")
    try:
        return resposta.json().get("value", [])
    except ValueError as exc:
        raise ErroFocus(f"{recurso}: resposta não-JSON") from exc


def _referencia_para_data(bruto: str, periodicidade: str) -> dt.date | None:
    """Converte '08/2026' (mensal) ou '3/2026' (trimestral) no 1º dia do período."""
    try:
        parte, ano = bruto.split("/")
        ano, parte = int(ano), int(parte)
    except (ValueError, AttributeError):
        return None
    if periodicidade == "trimestral":
        if not 1 <= parte <= 4:
            return None
        return dt.date(ano, 3 * parte - 2, 1)
    if not 1 <= parte <= 12:
        return None
    return dt.date(ano, parte, 1)


def _defasagem_em_meses(coleta: dt.date, referencia: dt.date) -> int:
    return (coleta.year - referencia.year) * 12 + (coleta.month - referencia.month)


def buscar(
    recurso: str,
    indicador: str,
    *,
    periodicidade: str,
    base_calculo: int = 0,
    desde: dt.date,
    ate: dt.date | None = None,
) -> pd.DataFrame:
    """Baixa o consenso (mediana) do indicador, já recortado à janela útil.

    Devolve data_referencia (período projetado), valor (mediana) e data_coleta
    (data da apuração do Focus) — o formato que o armazenamento append-only
    espera quando a data da coleta faz parte da observação.
    """
    ate = ate or dt.date.today()
    janela = JANELA_MESES[periodicidade]
    filtro = (
        f"Indicador eq '{indicador}' and baseCalculo eq {base_calculo} "
        f"and Data ge '{desde:%Y-%m-%d}' and Data le '{ate:%Y-%m-%d}'"
    )

    registros: list[dict] = []
    skip = 0
    while True:
        lote = _pagina(recurso, filtro, skip)
        registros.extend(lote)
        log.debug("%s/%s: página skip=%d trouxe %d", recurso, indicador, skip, len(lote))
        if len(lote) < TAMANHO_PAGINA:
            break
        skip += TAMANHO_PAGINA
        time.sleep(PAUSA_ENTRE_PAGINAS)

    if not registros:
        return pd.DataFrame(columns=["data_referencia", "valor", "data_coleta"])

    df = pd.DataFrame(registros)
    df["data_coleta"] = pd.to_datetime(df["Data"], format="%Y-%m-%d", utc=True)
    df["data_referencia"] = df["DataReferencia"].map(
        lambda x: _referencia_para_data(x, periodicidade)
    )
    df["valor"] = pd.to_numeric(df["Mediana"], errors="coerce")
    df = df.dropna(subset=["data_referencia", "valor"])

    # Recorte da janela útil: descarta projeção de longo prazo, que o projeto não usa.
    defasagem = [
        _defasagem_em_meses(c.date(), r)
        for c, r in zip(df["data_coleta"], df["data_referencia"], strict=True)
    ]
    df = df[[0 <= d <= janela for d in defasagem]]

    df = df[["data_referencia", "valor", "data_coleta"]]
    df = df.sort_values(["data_referencia", "data_coleta"], kind="stable")
    return df.reset_index(drop=True)
