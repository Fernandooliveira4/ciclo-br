"""Classificador de regime: quadrantes de crescimento × inflação.

**Como o quadrante é definido.** Cada eixo é comparado a um corte, e o par de
sinais dá um dos quatro estados. Os dois cortes não são do mesmo tipo, e a
diferença é deliberada:

- **Crescimento: corte em zero.** Momentum negativo é atividade encolhendo. A
  pergunta é "está caindo?", que é a mesma pergunta que a datação oficial de
  recessões responde.
- **Inflação: mediana em janela expansiva.** Não existe um "zero" natural para
  inflação — todo número positivo é alguma inflação — então a referência é o
  próprio histórico brasileiro, com o corte de um mês sendo a mediana dos dados
  até aquele mês.

A janela expansiva não é detalhe de implementação. A mediana calculada sobre a
amostra inteira reintroduziria o viés de look-ahead que o ajuste sazonal
recursivo existe para eliminar — o corte de 2015 estaria usando dados de 2020.

**Por que o crescimento deixou de usar a mediana.** A primeira versão comparava
os dois eixos contra a mediana do próprio histórico. A validação contra o CODACE
mostrou o custo: entre maio de 2008 e junho de 2020, o momentum ficou abaixo da
sua mediana expansiva em **81% dos meses**. Nessa taxa base, "detectou todas as
recessões" quase não informa, e a aparente antecipação de doze meses era o sinal
ligando cedo e ficando ligado. Com corte em zero o sinal fica ligado em 36% dos
meses e passa a acompanhar as recessões com atraso de três a quatro meses — o
comportamento honesto de uma regra de momentum sobre dado publicado com 45 a 60
dias de defasagem. A medição está na seção 7 da metodologia.

**Por que uma regra e não um modelo estimado.** A janela de validação contra a
datação do CODACE contém três recessões. Com três eventos, qualquer modelo com
muitos parâmetros estaria sendo ajustado ao ruído. Uma regra de sinal é
auditável, explicável em uma frase, e honesta quanto ao tamanho da amostra.

**Persistência, e por que ela é por eixo.** Aplicada crua, a regra trocaria de
quadrante dezenas de vezes, com um terço dos episódios durando dois meses ou
menos — ruído apresentado como mudança de regime. Por isso uma virada só é
confirmada após `MESES_PERSISTENCIA` meses consecutivos do novo sinal.

A confirmação é feita **em cada eixo separadamente**, e não no rótulo de quatro
estados. A primeira versão desta camada contava meses do quadrante inteiro, e a
validação contra o CODACE mostrou que isso trava: com o crescimento firme acima
do corte, alternar entre "Expansão" e "Aquecimento" — que diferem só no eixo de
inflação — zerava o contador a cada mês, e o eixo de crescimento nunca
confirmava a virada. Um episódio de contração chegou a durar 116 meses por esse
motivo. O quadrante é a leitura conjunta de duas afirmações independentes; cada
uma precisa do seu próprio prazo de confirmação. Há teste nomeado para isso.

Enquanto não confirma, o estado anterior permanece vigente e a mudança fica
marcada como **pendente**, o que o painel mostra em vez de esconder.

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

# Cortes possíveis para o eixo de crescimento, e qual deles está em uso. O
# alternativo continua existindo para que a camada de validação meça os dois
# lado a lado — trocar de opinião aqui precisa custar uma medição, não um
# palpite.
CORTES_CRESCIMENTO = ("zero", "mediana")
CORTE_CRESCIMENTO = "zero"

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


def serie_de_corte(eixo: pd.Series, estrategia: str) -> pd.Series:
    """O corte do eixo de crescimento, conforme a estratégia escolhida.

    Calculado a partir do próprio eixo, e não lido de coluna gravada: assim a
    camada de validação reconstrói qualquer uma das duas versões a partir do
    mesmo arquivo, sem depender de qual delas estava ativa quando ele foi
    gerado.
    """
    if estrategia == "zero":
        return pd.Series(0.0, index=eixo.index)
    if estrategia == "mediana":
        return corte_expansivo(eixo)
    raise ValueError(f"corte desconhecido: {estrategia!r}")


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


def confirmar(sinal: pd.Series, *, meses: int = MESES_PERSISTENCIA) -> pd.DataFrame:
    """Confirma a virada de **um** sinal binário após `meses` meses seguidos.

    Devolve `vigente`, o sinal já confirmado, e `tentando`, há quantos meses o
    sinal cru discorda do vigente. Como o sinal é binário, não existe o problema
    de "candidato que muda": ou o mês concorda com o vigente e zera a contagem,
    ou discorda e soma mais um.
    """
    vigente: bool | None = None
    contador = 0
    vigentes: list[bool] = []
    tentativas: list[int] = []

    for valor in sinal:
        atual = bool(valor)
        if vigente is None or atual == vigente:
            vigente, contador = atual, 0
        else:
            contador += 1
            if contador >= meses:
                vigente, contador = atual, 0
        vigentes.append(vigente)
        tentativas.append(contador)

    return pd.DataFrame({"vigente": vigentes, "tentando": tentativas}, index=sinal.index)


def aplicar_persistencia(
    acima_crescimento: pd.Series,
    acima_inflacao: pd.Series,
    *,
    meses: int = MESES_PERSISTENCIA,
) -> pd.DataFrame:
    """Quadrante vigente a partir dos dois eixos confirmados separadamente.

    Devolve o quadrante vigente, o quadrante cru quando ele discorda do vigente
    (`pendente`) e há quantos meses alguma virada está esperando confirmação —
    a informação que o painel precisa para dizer "mudou, mas ainda não
    confirmou".
    """
    g = confirmar(acima_crescimento, meses=meses)
    i = confirmar(acima_inflacao, meses=meses)

    quadrante = [QUADRANTES[(a, b)] for a, b in zip(g["vigente"], i["vigente"], strict=True)]
    cru = [
        QUADRANTES[(bool(a), bool(b))]
        for a, b in zip(acima_crescimento, acima_inflacao, strict=True)
    ]
    espera = np.maximum(g["tentando"].to_numpy(), i["tentando"].to_numpy())
    pendente = [c if m > 0 else None for c, m in zip(cru, espera, strict=True)]

    return pd.DataFrame(
        {"quadrante": quadrante, "pendente": pendente, "meses_pendente": espera},
        index=acima_crescimento.index,
    )


def sinais(reg: pd.DataFrame, *, corte_crescimento: str = "mediana") -> tuple[pd.Series, pd.Series]:
    """Os dois sinais binários de um regime já calculado, indexados por mês.

    Só os meses em que os dois cortes existem. É o que a camada de validação
    consome para reaplicar a persistência com outros prazos.

    `corte_crescimento` escolhe contra o que o momentum é comparado:

    - ``"zero"``: momentum zero, isto é, nível de atividade caindo. Responde
      "está encolhendo?", que é a pergunta que o CODACE responde. **É o corte
      vigente**, definido em `CORTE_CRESCIMENTO`.
    - ``"mediana"``: a mediana expansiva do próprio eixo. Responde "cresce acima
      do padrão histórico brasileiro?". Foi o corte original, trocado depois da
      medição descrita na seção 7 da metodologia.

    Os dois continuam existindo para que a validação meça os dois com a mesma
    régua. O argumento contra a mediana está medido e versionado; refazer a
    escolha custa uma medição, não um palpite.
    """
    indice = pd.PeriodIndex(pd.to_datetime(reg["data_referencia"]), freq="M")
    eixo_g = pd.Series(reg["eixo_crescimento"].to_numpy(dtype="float64"), index=indice)
    limite = serie_de_corte(eixo_g, corte_crescimento)

    # A classificação só começa quando o corte de inflação existe, o que exige
    # 60 meses de história. O corte de crescimento em zero não exige nenhuma,
    # mas o quadrante precisa dos dois eixos, então quem manda é o mais lento.
    valido = (limite.notna().to_numpy() & reg["corte_inflacao"].notna().to_numpy())
    acima_g = pd.Series(eixo_g.to_numpy() > limite.to_numpy(), index=indice)
    acima_i = pd.Series(
        reg["eixo_inflacao"].to_numpy() > reg["corte_inflacao"].to_numpy(), index=indice
    )
    return acima_g[valido], acima_i[valido]


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

    corte_g = serie_de_corte(eixos["eixo_crescimento"], CORTE_CRESCIMENTO)
    corte_i = corte_expansivo(eixos["eixo_inflacao"])
    bruto = classificar_bruto(
        eixos["eixo_crescimento"], eixos["eixo_inflacao"], corte_g, corte_i
    )

    # A persistência só corre nos meses já classificáveis; antes disso não há
    # corte e portanto não há sinal para confirmar.
    valido = corte_g.notna() & corte_i.notna()
    persistente = aplicar_persistencia(
        (eixos["eixo_crescimento"] > corte_g)[valido],
        (eixos["eixo_inflacao"] > corte_i)[valido],
    ).reindex(eixos.index)
    persistente["meses_pendente"] = persistente["meses_pendente"].fillna(0)
    # `reindex` transforma os None de "nada pendente" em NaN, e NaN é verdadeiro
    # num `if`. Sem esta linha o painel anuncia "pendente: nan".
    for coluna in ("quadrante", "pendente"):
        persistente[coluna] = persistente[coluna].astype(object).where(
            persistente[coluna].notna(), None)

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
        "pendente": ultimo["pendente"] if pd.notna(ultimo["pendente"]) else None,
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
    log.info("regime: %d meses classificados%s", int(regime["quadrante"].notna().sum()),
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
