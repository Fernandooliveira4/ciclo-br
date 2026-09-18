"""Cliente da API de agregados do IBGE (tabelas do SIDRA).

**Por que existe uma segunda fonte, e por que ela é o IBGE.** A taxa de
investimento é uma razão a preços correntes — formação bruta de capital fixo
sobre PIB — e o SGS não tem mais o numerador nem o denominador nessa forma: a
família 22xxx das Contas Nacionais só publica índice de volume, e as séries a
preços correntes foram descontinuadas em 2022 (sondadas: devolvem dois
trimestres de 2022 e param). Sem preços correntes não existe "% do PIB". A
alternativa foi testada e descartada, não ignorada.

**Este módulo não é o `calendario.py`.** Os dois falam com o IBGE, no mesmo host,
e é só isso que têm em comum: aquele consome a API de calendário, que devolve
datas de divulgação; este consome a de agregados, que devolve séries. Contratos
diferentes, erros diferentes, e por isso módulos diferentes.

**Três diferenças em relação ao SGS que o código precisa marcar**, porque quem
copiar de `sgs.py` por hábito vai trazer o comportamento errado:

1. **404 aqui não é ausência de dado.** No SGS é — ausência num intervalo volta
   como 404, e por isso lá ele devolve lista vazia. Aqui 404 significa tabela ou
   variável que não existe, ou seja, ficha errada. Traduzir isso para "série
   vazia" faria o portão de qualidade reclamar de falta de dado quando o defeito
   está na configuração.

2. **A resposta repete a categoria pedida, e nós conferimos.** Esta é a
   verificação mais importante do módulo. Gravar consumo do governo dentro de
   `fbcf_corrente.parquet` por causa de um parâmetro trocado passaria nos oito
   portões sem tropeçar em nada: mesma unidade, mesma ordem de grandeza, mesma
   sazonalidade, mesma grade trimestral. Não há camada a jusante capaz de pegar
   esse erro, então ele tem que morrer aqui.

3. **O IBGE marca ausência com reticências, traço e X**, não com `null`. Sem o
   conjunto `AUSENTES`, um `float("-")` derruba a coleta inteira por um ponto.

Uma pegadinha de depuração: a API devolve corpo comprimido mesmo quando ninguém
pede `Accept-Encoding`. O `requests` descomprime sozinho e o cliente não sente,
mas quem for investigar com `urllib` ou `curl` cru recebe bytes binários e perde
meia hora achando que é problema de encoding.
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

log = logging.getLogger(__name__)

BASE = "https://servicodados.ibge.gov.br/api/v3/agregados"
TEMPO_LIMITE = 60
CABECALHOS = {
    "Accept": "application/json",
    "User-Agent": "ciclo-br (+https://github.com/Fernandooliveira4/ciclo-br)",
}

# Como o IBGE escreve "não há valor". Nenhum deles sobrevive a um float().
AUSENTES = frozenset({"...", "..", ".", "-", "X", ""})


class ErroIBGE(RuntimeError):
    """Falha ao consultar a API de agregados do IBGE."""


def _data_do_periodo(bruto: str | None, periodicidade: str) -> dt.date | None:
    """Converte o período 'AAAATT' para o primeiro dia do trimestre.

    Recebe a periodicidade em vez de deduzi-la porque o mesmo literal de seis
    dígitos significa coisas diferentes em tabelas diferentes: numa tabela
    mensal '202601' é janeiro, e aqui é o primeiro trimestre. Os dois caem na
    mesma faixa de dois dígitos, então não há como distinguir pelo valor —
    adivinhar seria errar em silêncio num ano inteiro de datas.

    Período malformado devolve None, e não exceção, de propósito: o ponto vira
    buraco na grade, que o portão de qualidade acusa com a data exata. Uma
    exceção aqui derrubaria a série inteira por causa de um registro.
    """
    if periodicidade != "trimestral":
        raise ErroIBGE(f"periodicidade {periodicidade!r} sem conversor de período")
    texto = (bruto or "").strip()
    if len(texto) != 6 or not texto.isdigit():
        return None
    ano, trimestre = int(texto[:4]), int(texto[4:])
    if not 1 <= trimestre <= 4:
        return None
    return dt.date(ano, (trimestre - 1) * 3 + 1, 1)


def _converter_valor(bruto: str | float | None) -> float | None:
    if bruto is None:
        return None
    if isinstance(bruto, (int, float)):
        return float(bruto)
    texto = str(bruto).strip()
    if texto in AUSENTES:
        return None
    return float(texto.replace(",", "."))


@retry(
    retry=retry_if_exception_type((requests.RequestException, ErroIBGE)),
    stop=stop_after_attempt(4),
    wait=wait_exponential(multiplier=1, min=2, max=20),
    reraise=True,
)
def _consultar(tabela: int, variavel: int, categoria: int, *, classificacao: int) -> list:
    """Uma requisição à API, com a série inteira ('periodos/all').

    Pedir tudo sempre, em vez de traduzir uma data de início para o vocabulário
    'AAAATT' da API, mantém a conversão de período num lugar só. Com os dois
    lados convertendo, os dois poderiam discordar sobre onde começa um
    trimestre, e o sintoma apareceria como buraco na grade — longe da causa.
    """
    url = f"{BASE}/{tabela}/periodos/all/variaveis/{variavel}"
    alvo = f"{tabela}/{variavel}/{classificacao}[{categoria}]"
    resposta = requests.get(
        url,
        params={
            "localidades": "N1[all]",
            "classificacao": f"{classificacao}[{categoria}]",
        },
        timeout=TEMPO_LIMITE,
        headers=CABECALHOS,
    )

    # Ao contrário do SGS, 404 aqui não é ausência de dado: é tabela ou variável
    # inexistente. Devolver lista vazia transformaria ficha errada em série vazia.
    if resposta.status_code >= 400:
        raise ErroIBGE(f"{alvo}: HTTP {resposta.status_code}")

    try:
        dados = resposta.json()
    except ValueError as exc:
        raise ErroIBGE(f"{alvo}: resposta não-JSON") from exc

    if not isinstance(dados, list) or not dados:
        raise ErroIBGE(f"{alvo}: resposta vazia ou em formato inesperado")
    return dados


def _extrair(dados: list, categoria: int, *, classificacao: int) -> dict[str, str]:
    """A série do Brasil (N1) para a categoria pedida, conferindo que é ela mesma.

    As duas conferências — categoria devolvida e localidade — existem pelo mesmo
    motivo: um parâmetro trocado aqui produz um arquivo plausível, com a unidade
    certa e a grandeza certa, que nenhum portão a jusante tem como recusar.
    """
    alvo = f"{classificacao}[{categoria}]"
    for resultado in dados[0].get("resultados", []):
        classes = {
            str(c.get("id")): (c.get("categoria") or {})
            for c in resultado.get("classificacoes", [])
        }
        devolvida = classes.get(str(classificacao))
        if devolvida is None or str(categoria) not in devolvida:
            continue
        for serie in resultado.get("series", []):
            if str((serie.get("localidade") or {}).get("id")) == "1":
                return serie.get("serie") or {}
        raise ErroIBGE(f"{alvo}: resposta sem a localidade Brasil (N1)")

    vistas = sorted({
        chave
        for resultado in dados[0].get("resultados", [])
        for c in resultado.get("classificacoes", [])
        if str(c.get("id")) == str(classificacao)
        for chave in (c.get("categoria") or {})
    })
    raise ErroIBGE(f"{alvo}: a resposta não traz a categoria pedida (veio {vistas})")


def buscar(
    tabela: int,
    variavel: int,
    categoria: int,
    *,
    classificacao: int,
    periodicidade: str = "trimestral",
    desde: dt.date | None = None,
) -> pd.DataFrame:
    """Uma categoria de uma tabela de agregados, para o Brasil.

    Devolve data_referencia (date) e valor (float), ordenado e sem duplicata de
    data — o mesmo contrato de `sgs.buscar`, para que `storage.anexar` não
    precise saber de que fonte veio a linha.
    """
    dados = _consultar(tabela, variavel, categoria, classificacao=classificacao)
    serie = _extrair(dados, categoria, classificacao=classificacao)

    registros: list[tuple[dt.date, float]] = []
    for periodo in sorted(serie):
        data = _data_do_periodo(periodo, periodicidade)
        if data is None:
            log.warning("tabela %s categoria %s: período ilegível %r",
                        tabela, categoria, periodo)
            continue
        if desde and data < desde:
            continue
        valor = _converter_valor(serie[periodo])
        if valor is None:
            continue
        registros.append((data, valor))

    if not registros:
        return pd.DataFrame(columns=["data_referencia", "valor"])

    df = pd.DataFrame(registros, columns=["data_referencia", "valor"])
    df["valor"] = df["valor"].astype("float64")
    df = df.sort_values("data_referencia").drop_duplicates("data_referencia", keep="last")
    return df.reset_index(drop=True)
