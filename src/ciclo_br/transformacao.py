"""Camada derivada: ajuste sazonal recursivo e momentum.

Aqui mora a promessa metodológica central do projeto.

**Por que o ajuste sazonal é recursivo.** Rodar um dessazonalizador sobre a série
inteira e depois classificar o passado é trapaça: o fator sazonal estimado para
março de 2015 teria usado dados de 2016 a 2026, informação que ninguém possuía em
2015. O backtest fica bonito por construção. Aqui, para obter o valor
dessazonalizado de um mês, o STL é reestimado usando **apenas os dados até aquele
mês** — janela expansiva. O resultado é mais feio e é esse o ponto.

Isso elimina a parte do viés de look-ahead que está sob nosso controle. A parte
que não está — a revisão do dado bruto, e o ajuste que a própria fonte aplica com
amostra completa no IBC-Br e na produção industrial — permanece, e está declarada
em docs/metodologia.md.

**Por que STL e não X-13ARIMA-SEATS.** O X-13 é o padrão de órgão estatístico,
mas depende de um binário do Census Bureau, que não existe no runner do GitHub
Actions nem no Streamlit Cloud. O STL é Python puro e roda em qualquer lugar. A
troca é consciente e o custo é conhecido: o STL não trata efeito de calendário
nem dias úteis, o que importa pouco aqui porque as duas séries que dessazonalizamos
(desocupação e núcleo do IPCA) não sofrem efeito de dias úteis como a produção
industrial sofreria.

**Por que momentum e não nível.** "Crescimento alto" e "crescimento acelerando"
produzem classificações diferentes e às vezes opostas: em 2021 o nível estava
altíssimo por efeito-base de 2020 e o momentum já caía. Momentum reage cedo e não
fica refém da base de comparação.
"""

from __future__ import annotations

import datetime as dt
import logging

import numpy as np
import pandas as pd
from statsmodels.tsa.seasonal import STL

from . import storage
from .config import DIR_DADOS

log = logging.getLogger(__name__)

DIR_DERIVADO = DIR_DADOS / "derivado"
CAMINHO_DERIVADO = DIR_DERIVADO / "series.parquet"

PERIODO_SAZONAL = 12
# Três ciclos sazonais completos: abaixo disso o STL estima fator sazonal em cima
# de ruído, e o valor dessazonalizado diz mais sobre o estimador que sobre a economia.
MINIMO_OBSERVACOES = 36

# O STL usa LOESS, que passa por BLAS/LAPACK, e o backend numérico difere entre
# plataformas: a mesma entrada produz valores que divergem nos últimos bits no
# Linux e no Windows. Portanto a camada derivada é reprodutível a menos de ruído
# de ponto flutuante, não bit a bit. Comparações usam esta tolerância — muito
# abaixo de qualquer diferença com significado econômico, já que os valores são
# percentuais. Sem isso a CI reprovaria só por ter rodado noutro sistema.
TOLERANCIA = 1e-6
CASAS_DECIMAIS = 6


def dessazonalizar_recursivo(
    serie: pd.Series,
    *,
    periodo: int = PERIODO_SAZONAL,
    minimo: int = MINIMO_OBSERVACOES,
) -> pd.Series:
    """Dessazonaliza cada ponto usando somente a informação disponível até ele.

    Devolve uma série do mesmo tamanho, com NaN nos primeiros pontos em que ainda
    não há história suficiente para estimar sazonalidade.
    """
    valores = np.full(len(serie), np.nan)
    bruto = serie.to_numpy(dtype="float64")

    for i in range(minimo - 1, len(serie)):
        janela = bruto[: i + 1]
        ajuste = STL(janela, period=periodo, robust=True).fit()
        valores[i] = janela[-1] - ajuste.seasonal[-1]

    return pd.Series(valores, index=serie.index)


def momentum_3m3m(nivel: pd.Series) -> pd.Series:
    """Variação da média dos últimos 3 meses sobre os 3 anteriores, anualizada (%).

    Aplica-se a série em NÍVEL (índice), como o IBC-Br. A média de 3 meses suaviza
    o ruído mensal sem introduzir a lentidão do acumulado em 12 meses.
    """
    media3 = nivel.rolling(3).mean()
    return ((media3 / media3.shift(3)) ** 4 - 1) * 100


def taxa_mm3m_anualizada(taxa_mensal: pd.Series) -> pd.Series:
    """Compõe 3 meses de uma taxa mensal (%) e anualiza.

    Aplica-se a série que já é TAXA, como o núcleo do IPCA. A composição é
    multiplicativa, não média aritmética: 1% ao mês por três meses não é 3% ao
    trimestre, e para inflação essa diferença não é detalhe.
    """
    fator = 1 + taxa_mensal / 100
    composto = fator.rolling(3).apply(np.prod, raw=True)
    return (composto**4 - 1) * 100


def _serie_mensal(serie_id: str) -> pd.Series:
    """Série vigente, indexada por data de referência, sem buraco na grade."""
    vigente = storage.ler_vigente(serie_id)
    if vigente.empty:
        return pd.Series(dtype="float64")
    serie = pd.Series(
        list(vigente["valor"]),
        index=pd.to_datetime(pd.Series(list(vigente["data_referencia"]))),
        dtype="float64",
    ).sort_index()
    return serie.asfreq("MS")


# O que a camada derivada produz, e de onde vem. Declarado em um lugar só para
# que a origem de cada número exibido no dashboard seja rastreável.
RECEITAS: dict[str, dict] = {
    "eixo_crescimento": {
        "origem": "ibcbr_sa",
        "papel": "eixo_crescimento",
        "descricao": "IBC-Br dessazonalizado na fonte, momentum 3m/3m anualizado",
        "unidade": "% anualizado",
    },
    "eixo_inflacao": {
        "origem": "ipca_nucleo_ma_suav",
        "papel": "eixo_inflacao",
        "descricao": "Núcleo do IPCA dessazonalizado por nós (janela expansiva), "
                     "média móvel de 3 meses composta e anualizada",
        "unidade": "% anualizado",
    },
    "nucleo_sa": {
        "origem": "ipca_nucleo_ma_suav",
        "papel": "intermediario",
        "descricao": "Núcleo do IPCA dessazonalizado em janela expansiva",
        "unidade": "% ao mês",
    },
    "desocupacao_sa": {
        "origem": "desocupacao",
        "papel": "contexto",
        "descricao": "Taxa de desocupação dessazonalizada em janela expansiva",
        "unidade": "% da força de trabalho",
    },
    "pim_momentum": {
        "origem": "pim_sa",
        "papel": "contexto",
        "descricao": "Produção industrial dessazonalizada na fonte, momentum 3m/3m "
                     "anualizado — checagem independente do eixo de crescimento",
        "unidade": "% anualizado",
    },
}


def construir() -> pd.DataFrame:
    """Recalcula toda a camada derivada a partir das séries brutas vigentes."""
    nucleo = _serie_mensal("ipca_nucleo_ma_suav")
    nucleo_sa = dessazonalizar_recursivo(nucleo)
    desocupacao_sa = dessazonalizar_recursivo(_serie_mensal("desocupacao"))

    resultados = {
        "eixo_crescimento": momentum_3m3m(_serie_mensal("ibcbr_sa")),
        "nucleo_sa": nucleo_sa,
        "eixo_inflacao": taxa_mm3m_anualizada(nucleo_sa),
        "desocupacao_sa": desocupacao_sa,
        "pim_momentum": momentum_3m3m(_serie_mensal("pim_sa")),
    }

    partes = []
    for serie_id, valores in resultados.items():
        limpo = valores.dropna()
        if limpo.empty:
            log.warning("%s: nenhuma observação derivada", serie_id)
            continue
        partes.append(pd.DataFrame({
            "serie_id": serie_id,
            "data_referencia": [d.date() for d in limpo.index],
            "valor": limpo.to_numpy(dtype="float64"),
        }))
        log.info("%s: %d observações (%s a %s)", serie_id, len(limpo),
                 limpo.index[0].date(), limpo.index[-1].date())

    if not partes:
        return pd.DataFrame(columns=["serie_id", "data_referencia", "valor", "calculado_em"])

    derivado = pd.concat(partes, ignore_index=True)
    derivado["valor"] = derivado["valor"].round(CASAS_DECIMAIS)
    derivado["calculado_em"] = dt.datetime.now(dt.UTC)
    return derivado


def equivalente(a: pd.DataFrame, b: pd.DataFrame) -> bool:
    """Compara duas versões da camada derivada a menos de ruído numérico.

    Chaves têm que bater exatamente; valores, dentro da tolerância. É isso que
    permite a mesma camada ser considerada íntegra tendo sido calculada em
    sistemas operacionais diferentes.
    """
    if a.empty or b.empty or len(a) != len(b):
        return False
    chaves = ["serie_id", "data_referencia"]
    if not a[chaves].reset_index(drop=True).equals(b[chaves].reset_index(drop=True)):
        return False
    return bool(np.allclose(
        a["valor"].to_numpy(dtype="float64"),
        b["valor"].to_numpy(dtype="float64"),
        atol=TOLERANCIA, rtol=0, equal_nan=True,
    ))


def salvar(derivado: pd.DataFrame) -> bool:
    """Grava a camada derivada; devolve se os valores mudaram de fato.

    Como o cálculo é determinístico, o arquivo só muda quando o dado bruto mudou.
    Ignorar `calculado_em` e o ruído de ponto flutuante evita commit diário sem
    informação — inclusive quando a execução anterior rodou noutra plataforma.
    """
    DIR_DERIVADO.mkdir(parents=True, exist_ok=True)

    if CAMINHO_DERIVADO.exists() and equivalente(pd.read_parquet(CAMINHO_DERIVADO), derivado):
        log.info("camada derivada sem alteração — arquivo mantido")
        return False

    derivado.to_parquet(CAMINHO_DERIVADO, index=False, compression="zstd")
    return True


def carregar() -> pd.DataFrame:
    if not CAMINHO_DERIVADO.exists():
        return pd.DataFrame(columns=["serie_id", "data_referencia", "valor", "calculado_em"])
    return pd.read_parquet(CAMINHO_DERIVADO)


def main(argv: list[str] | None = None) -> int:
    import argparse

    parser = argparse.ArgumentParser(description="Recalcula a camada derivada")
    parser.add_argument("--verificar", action="store_true",
                        help="não grava; reprova se o arquivo versionado estiver "
                             "desatualizado em relação ao dado bruto")
    parser.add_argument("--verboso", action="store_true")
    args = parser.parse_args(argv)

    logging.basicConfig(
        level=logging.DEBUG if args.verboso else logging.INFO,
        format="%(asctime)s %(levelname)-7s %(message)s", datefmt="%H:%M:%S",
    )

    derivado = construir()

    if args.verificar:
        if not equivalente(carregar(), derivado):
            log.error("camada derivada desatualizada: rode `ciclo-transformar` "
                      "e versione data/derivado/series.parquet")
            return 1
        log.info("camada derivada em dia com o dado bruto (%d linhas)", len(derivado))
        return 0

    mudou = salvar(derivado)
    log.info("camada derivada: %d linha(s)%s", len(derivado),
             "" if mudou else " (sem alteração)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
