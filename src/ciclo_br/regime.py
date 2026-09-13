"""Classificador de regime: quadrantes de crescimento × inflação.

**Como o quadrante é definido.** Cada eixo é comparado a um corte, e o par de
sinais dá um dos quatro estados. Os cortes são a **mediana em janela expansiva**
de cada eixo: o corte de um mês é a mediana dos dados até aquele mês.

Essa escolha de janela não é detalhe de implementação. A mediana calculada sobre
a amostra inteira reintroduziria o viés de look-ahead que o ajuste sazonal
recursivo existe para eliminar — o corte de 2015 estaria usando dados de 2020.
Em janela expansiva o corte só conhece o passado, como o resto da cadeia.

**Por que uma regra e não um modelo estimado.** A janela de validação contra a
datação do CODACE contém três recessões. Com três eventos, qualquer modelo com
muitos parâmetros estaria sendo ajustado ao ruído. Uma regra de sinal é
auditável, explicável em uma frase, e honesta quanto ao tamanho da amostra.

**Persistência.** Aplicada crua, a regra trocaria de quadrante 44 vezes em 277
meses, com um terço dos episódios durando dois meses ou menos — ruído
apresentado como mudança de regime. Por isso uma troca só é confirmada após
`MESES_PERSISTENCIA` meses consecutivos do novo sinal. Enquanto não confirma, o
estado anterior permanece vigente e a mudança fica marcada como **pendente**, o
que o painel mostra em vez de esconder.

O custo dessa regra é atraso, e atraso é exatamente o que a validação mede. Por
isso a camada expõe também o quadrante **sem** persistência: a comparação com a
cronologia oficial é feita nas duas versões, e o parâmetro deixa de ser escolhido
no olho para ser escolhido contra evidência.
"""

from __future__ import annotations

import datetime as dt
import logging

import numpy as np
import pandas as pd

from . import transformacao
from .config import DIR_DADOS

log = logging.getLogger(__name__)

CAMINHO_REGIME = DIR_DADOS / "derivado" / "regime.parquet"

# Quantos meses o novo sinal precisa persistir para a troca ser confirmada.
MESES_PERSISTENCIA = 3

# Mínimo de história antes de o corte expansivo significar alguma coisa.
MINIMO_PARA_CORTE = 60

QUADRANTES = {
    (True, True): "Aquecimento",      # cresce e pressiona preços
    (True, False): "Expansão",        # cresce sem pressionar
    (False, True): "Estagflação",     # não cresce e pressiona
    (False, False): "Desaceleração",  # não cresce e não pressiona
}


def corte_expansivo(serie: pd.Series, *, minimo: int = MINIMO_PARA_CORTE) -> pd.Series:
    """Mediana usando apenas os dados até cada ponto.

    NaN enquanto não há história suficiente — sem isso o corte dos primeiros anos
    seria a mediana de meia dúzia de observações.
    """
    corte = serie.expanding(min_periods=minimo).median()
    return corte


def classificar_bruto(
    crescimento: pd.Series,
    inflacao: pd.Series,
    corte_crescimento: pd.Series,
    corte_inflacao: pd.Series,
) -> pd.Series:
    """Quadrante mês a mês, sem regra de persistência."""
    acima_g = crescimento > corte_crescimento
    acima_i = inflacao > corte_inflacao
    valido = (
        crescimento.notna() & inflacao.notna()
        & corte_crescimento.notna() & corte_inflacao.notna()
    )
    rotulos = [
        QUADRANTES[(bool(g), bool(i))] if bool(v) else None
        for g, i, v in zip(acima_g, acima_i, valido, strict=True)
    ]
    return pd.Series(rotulos, index=crescimento.index, dtype="object")


def aplicar_persistencia(
    bruto: pd.Series, *, meses: int = MESES_PERSISTENCIA
) -> pd.DataFrame:
    """Confirma a troca só depois de `meses` consecutivos do novo sinal.

    Devolve o quadrante vigente, o candidato ainda não confirmado (se houver) e
    há quantos meses ele está pendente — a informação que o painel precisa para
    dizer "mudou, mas ainda não confirmou".
    """
    vigente: str | None = None
    candidato: str | None = None
    contador = 0

    linhas = []
    for data, atual in bruto.items():
        if atual is None:
            linhas.append((data, None, None, 0))
            continue

        if vigente is None:
            vigente, candidato, contador = atual, None, 0
        elif atual == vigente:
            candidato, contador = None, 0
        else:
            if atual == candidato:
                contador += 1
            else:
                candidato, contador = atual, 1
            if contador >= meses:
                vigente, candidato, contador = atual, None, 0

        linhas.append((data, vigente, candidato, contador))

    return pd.DataFrame(
        linhas, columns=["data_referencia", "quadrante", "pendente", "meses_pendente"]
    ).set_index("data_referencia")


def construir() -> pd.DataFrame:
    """Série histórica de regime, com e sem persistência, e os cortes usados."""
    derivado = transformacao.carregar()
    if derivado.empty:
        log.warning("camada derivada vazia — rode `ciclo-transformar` antes")
        return pd.DataFrame()

    piv = derivado.pivot(index="data_referencia", columns="serie_id", values="valor")
    piv.index = pd.to_datetime(piv.index)
    eixos = piv[["eixo_crescimento", "eixo_inflacao"]].dropna().sort_index()
    if eixos.empty:
        log.warning("eixos indisponíveis na camada derivada")
        return pd.DataFrame()

    corte_g = corte_expansivo(eixos["eixo_crescimento"])
    corte_i = corte_expansivo(eixos["eixo_inflacao"])
    bruto = classificar_bruto(
        eixos["eixo_crescimento"], eixos["eixo_inflacao"], corte_g, corte_i
    )
    persistente = aplicar_persistencia(bruto)

    regime = pd.DataFrame({
        "data_referencia": [d.date() for d in eixos.index],
        "eixo_crescimento": eixos["eixo_crescimento"].to_numpy(dtype="float64"),
        "eixo_inflacao": eixos["eixo_inflacao"].to_numpy(dtype="float64"),
        "corte_crescimento": corte_g.to_numpy(dtype="float64"),
        "corte_inflacao": corte_i.to_numpy(dtype="float64"),
        "quadrante_bruto": bruto.to_numpy(dtype=object),
        "quadrante": persistente["quadrante"].to_numpy(dtype=object),
        "pendente": persistente["pendente"].to_numpy(dtype=object),
        "meses_pendente": persistente["meses_pendente"].to_numpy(dtype="int64"),
    })
    for coluna in ("corte_crescimento", "corte_inflacao"):
        regime[coluna] = regime[coluna].round(transformacao.CASAS_DECIMAIS)
    regime["calculado_em"] = dt.datetime.now(dt.UTC)
    return regime


def resumo(regime: pd.DataFrame) -> dict:
    """Números que o briefing e o dashboard consomem."""
    classificados = regime[regime["quadrante"].notna()]
    if classificados.empty:
        return {}

    ultimo = classificados.iloc[-1]
    vigente = ultimo["quadrante"]
    desde = classificados[classificados["quadrante"] == vigente]
    inicio = desde["data_referencia"].iloc[-1]
    for data, q in zip(reversed(list(classificados["data_referencia"])),
                       reversed(list(classificados["quadrante"])), strict=True):
        if q != vigente:
            break
        inicio = data

    trocas = int((classificados["quadrante"] != classificados["quadrante"].shift()).sum() - 1)
    trocas_brutas = int(
        (classificados["quadrante_bruto"] != classificados["quadrante_bruto"].shift()).sum() - 1
    )

    return {
        "referencia": ultimo["data_referencia"],
        "quadrante": vigente,
        "desde": inicio,
        "meses_no_quadrante": int(
            (ultimo["data_referencia"].year - inicio.year) * 12
            + ultimo["data_referencia"].month - inicio.month + 1
        ),
        "pendente": ultimo["pendente"],
        "meses_pendente": int(ultimo["meses_pendente"]),
        "eixo_crescimento": float(ultimo["eixo_crescimento"]),
        "eixo_inflacao": float(ultimo["eixo_inflacao"]),
        "corte_crescimento": float(ultimo["corte_crescimento"]),
        "corte_inflacao": float(ultimo["corte_inflacao"]),
        "trocas_com_persistencia": trocas,
        "trocas_sem_persistencia": trocas_brutas,
    }


def equivalente(a: pd.DataFrame, b: pd.DataFrame) -> bool:
    if a.empty or b.empty or len(a) != len(b):
        return False
    categoricas = ["data_referencia", "quadrante_bruto", "quadrante"]
    if not a[categoricas].reset_index(drop=True).equals(b[categoricas].reset_index(drop=True)):
        return False
    numericas = ["eixo_crescimento", "eixo_inflacao", "corte_crescimento", "corte_inflacao"]
    return bool(np.allclose(
        a[numericas].to_numpy(dtype="float64"),
        b[numericas].to_numpy(dtype="float64"),
        atol=transformacao.TOLERANCIA, rtol=0, equal_nan=True,
    ))


def salvar(regime: pd.DataFrame) -> bool:
    CAMINHO_REGIME.parent.mkdir(parents=True, exist_ok=True)
    if CAMINHO_REGIME.exists() and equivalente(pd.read_parquet(CAMINHO_REGIME), regime):
        log.info("regime sem alteração — arquivo mantido")
        return False
    regime.to_parquet(CAMINHO_REGIME, index=False, compression="zstd")
    return True


def carregar() -> pd.DataFrame:
    if not CAMINHO_REGIME.exists():
        return pd.DataFrame()
    return pd.read_parquet(CAMINHO_REGIME)


def main(argv: list[str] | None = None) -> int:
    import argparse

    parser = argparse.ArgumentParser(description="Classifica o regime macroeconômico")
    parser.add_argument("--verificar", action="store_true",
                        help="não grava; reprova se o arquivo versionado estiver "
                             "desatualizado")
    parser.add_argument("--verboso", action="store_true")
    args = parser.parse_args(argv)

    logging.basicConfig(
        level=logging.DEBUG if args.verboso else logging.INFO,
        format="%(asctime)s %(levelname)-7s %(message)s", datefmt="%H:%M:%S",
    )

    regime = construir()
    if regime.empty:
        log.error("não foi possível classificar: camada derivada indisponível")
        return 1

    if args.verificar:
        if not equivalente(carregar(), regime):
            log.error("regime desatualizado: rode `ciclo-regime` e versione "
                      "data/derivado/regime.parquet")
            return 1
        log.info("regime em dia com a camada derivada (%d meses)", len(regime))
        return 0

    mudou = salvar(regime)
    info = resumo(regime)
    log.info("regime: %d meses classificados%s", len(regime),
             "" if mudou else " (sem alteração)")
    if info:
        log.info("vigente: %s desde %s (%d meses)",
                 info["quadrante"], info["desde"], info["meses_no_quadrante"])
        if info["pendente"]:
            log.info("pendente: %s há %d mês(es), aguardando %d",
                     info["pendente"], info["meses_pendente"], MESES_PERSISTENCIA)
        log.info("trocas: %d com persistência, %d sem",
                 info["trocas_com_persistencia"], info["trocas_sem_persistencia"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
