"""Surpresa de cada divulgação: realizado menos o consenso do Focus da véspera.

**Por que surpresa e não outlier.** Um detector de outlier responde "esse número
é raro" — e o IPCA de janeiro é sempre alto, então ele gritaria todo janeiro. A
pergunta que uma mesa faz é outra: o número veio diferente do que o mercado
esperava? Só a segunda tem conteúdo econômico, e ela exige saber o que o mercado
esperava **antes** de o número sair.

**O que torna isso possível.** Três peças que já existiam separadas:

1. A API de Expectativas do BCB é point-in-time por construção: cada linha traz a
   data da apuração e o período projetado. O armazenamento append-only guarda a
   trajetória inteira do consenso sem sobrescrever nada.
2. O calendário do IBGE devolve, para cada divulgação, o período de referência do
   dado divulgado. É daí que sai a data em que cada número foi ao ar.
3. O realizado está gravado com a data em que foi coletado, o que permite
   distinguir primeira leitura de valor já revisado.

**A janela é 2017 em diante, e o motivo é o calendário.** A API de calendário do
IBGE não devolve nada antes de 2017 — verificado produto a produto. Sem data de
divulgação não há véspera, e sem véspera não há surpresa. Estimar a data de
divulgação a partir do mês de referência seria possível e seria errado: o ganho
de cobertura viria de um número inventado.

**O consenso usado** é a última apuração do Focus **estritamente anterior** à
data de divulgação. Estrito porque uma apuração feita no próprio dia não estava
disponível para quem operava antes do número sair.

A coluna `dias_sem_mudanca` mede quantos dias fazia que o consenso não se movia
quando o número saiu — e não há quantos dias ele estava desatualizado. A ingestão
não grava mediana repetida (se o consenso não mudou, não houve notícia), então
uma distância grande significa consenso parado, não consenso velho. Para o IPCA a
média é de 6 dias; para a desocupação, 15, porque é série que o mercado revisita
pouco.

**Revisão contamina a surpresa histórica, e dá para ver.** O realizado gravado
para 2017-2026 é o valor *vigente hoje*, não o primeiro print — o backfill trouxe
a série já revisada. A média das surpresas mostra o efeito com clareza:

- IPCA: média **+0,01 p.p.** em 117 divulgações. Praticamente não há revisão, e o
  consenso aparece como o que deveria ser — não enviesado.
- PIB: média **+0,41 p.p.** em 39 trimestres. Revisão para cima do PIB explica
  isso melhor que pessimismo sistemático do mercado.
- Desocupação: média **−0,17 p.p.** em 60 divulgações. Aqui as duas explicações
  competem, e os dados não decidem entre elas: a janela (fim de 2021 em diante) é
  quase toda de desemprego em queda, e projetar uma tendência longa sempre fica
  para trás dela.

A coluna `primeira_leitura` marca quais linhas foram observadas ao vivo pelo
pipeline; ela vira verdadeira sozinha conforme o projeto roda, e é o que vai
permitir, daqui a alguns anos, medir a surpresa sem esse viés.
"""

from __future__ import annotations

import datetime as dt
import logging
from dataclasses import dataclass

import pandas as pd

from . import storage, transformacao
from .config import DIR_DADOS, catalogo
from .ingestion import calendario

log = logging.getLogger(__name__)

CAMINHO = DIR_DADOS / "derivado" / "surpresa.csv"

# Quantos dias depois da divulgação a coleta ainda conta como "observada ao
# vivo". A ingestão roda duas vezes por dia útil, então uma divulgação de sexta
# aparece no máximo na segunda.
DIAS_PARA_PRIMEIRA_LEITURA = 4

CASAS = 4


@dataclass(frozen=True)
class Par:
    """Um realizado e o consenso que o projetava, na mesma unidade."""

    realizado: str
    consenso: str
    unidade: str
    derivado: bool = False
    bruto_de_origem: str | None = None

    @property
    def serie_de_coleta(self) -> str:
        """De qual série bruta vem a data de coleta que marca a primeira leitura."""
        return self.bruto_de_origem or self.realizado


# Só entram pares em que as duas pontas medem a mesma coisa na mesma unidade.
# O câmbio ficou de fora de propósito: a PTAX é preço de mercado contínuo, não
# tem data de divulgação, e "surpresa" ali não seria surpresa de divulgação.
PARES: dict[str, Par] = {
    "ipca": Par(realizado="ipca", consenso="focus_ipca_mensal", unidade="p.p."),
    "desocupacao": Par(
        realizado="desocupacao", consenso="focus_desocupacao_mensal", unidade="p.p."
    ),
    "pib": Par(
        realizado="pib_yoy", consenso="focus_pib_trimestral", unidade="p.p.",
        derivado=True, bruto_de_origem="pib",
    ),
}


def _realizado(par: Par) -> pd.DataFrame:
    """Valor vigente por data de referência, com a data da primeira coleta."""
    if par.derivado:
        derivado = transformacao.carregar()
        alvo = derivado[derivado["serie_id"] == par.realizado]
        valores = pd.DataFrame({
            "data_referencia": pd.to_datetime(alvo["data_referencia"]),
            "realizado": alvo["valor"].to_numpy(dtype="float64"),
        })
    else:
        vigente = storage.ler_vigente(par.realizado)
        if vigente.empty:
            return pd.DataFrame()
        valores = pd.DataFrame({
            "data_referencia": pd.to_datetime(pd.Series(list(vigente["data_referencia"]))),
            "realizado": pd.Series(list(vigente["valor"]), dtype="float64"),
        })

    bruto = storage.ler_bruto(par.serie_de_coleta)
    if bruto.empty:
        return pd.DataFrame()
    primeira = (bruto.assign(data_referencia=pd.to_datetime(bruto["data_referencia"]),
                             data_coleta=pd.to_datetime(bruto["data_coleta"]))
                     .groupby("data_referencia")["data_coleta"].min())
    valores["coletado_em"] = valores["data_referencia"].map(primeira)
    return valores.dropna(subset=["realizado"]).sort_values("data_referencia")


def consenso_da_vespera(
    focus: pd.DataFrame, referencia: pd.Timestamp, divulgacao: dt.date
) -> tuple[float, dt.date] | None:
    """Última mediana do Focus para `referencia` apurada antes de `divulgacao`.

    "Antes" é estrito: uma apuração feita no próprio dia da divulgação não estava
    disponível para quem operava antes dela.
    """
    candidatas = focus[
        (focus["data_referencia"] == referencia)
        & (focus["data_coleta"].dt.date < divulgacao)
    ]
    if candidatas.empty:
        return None
    ultima = candidatas.sort_values("data_coleta", kind="stable").iloc[-1]
    return float(ultima["valor"]), ultima["data_coleta"].date()


def _focus(serie_id: str) -> pd.DataFrame:
    bruto = storage.ler_bruto(serie_id)
    if bruto.empty:
        return pd.DataFrame(columns=["data_referencia", "valor", "data_coleta"])
    return pd.DataFrame({
        "data_referencia": pd.to_datetime(pd.Series(list(bruto["data_referencia"]))),
        "valor": pd.Series(list(bruto["valor"]), dtype="float64"),
        "data_coleta": pd.to_datetime(pd.Series(list(bruto["data_coleta"]))).dt.tz_localize(None),
    })


def construir(pares: dict[str, Par] | None = None) -> pd.DataFrame:
    """Uma linha por divulgação com realizado, consenso e surpresa."""
    pares = PARES if pares is None else pares
    agenda = calendario.carregar()
    if agenda.empty:
        log.warning("calendário vazio — rode `ciclo-calendario --backfill` antes")
        return pd.DataFrame()

    linhas = []
    for nome, par in pares.items():
        realizado = _realizado(par)
        focus = _focus(par.consenso)
        datas = calendario.divulgacoes(_produto_da_serie(par), agenda)
        if realizado.empty or focus.empty or datas.empty:
            log.warning("%s: faltam dados de um dos lados — par ignorado", nome)
            continue

        for _, linha in realizado.iterrows():
            referencia = linha["data_referencia"]
            divulgacao = datas.get(referencia.date())
            if divulgacao is None:
                continue
            achado = consenso_da_vespera(focus, referencia, divulgacao)
            if achado is None:
                continue
            consenso, data_consenso = achado

            coletado = linha.get("coletado_em")
            ao_vivo = bool(
                pd.notna(coletado)
                and 0 <= (coletado.date() - divulgacao).days <= DIAS_PARA_PRIMEIRA_LEITURA
            )
            linhas.append({
                "par": nome,
                "serie_realizado": par.realizado,
                "data_referencia": referencia.date().isoformat(),
                "data_divulgacao": divulgacao.isoformat(),
                "realizado": round(float(linha["realizado"]), CASAS),
                "consenso": round(consenso, CASAS),
                "surpresa": round(float(linha["realizado"]) - consenso, CASAS),
                "unidade": par.unidade,
                "data_consenso": data_consenso.isoformat(),
                "dias_sem_mudanca": (divulgacao - data_consenso).days,
                "primeira_leitura": ao_vivo,
            })

    if not linhas:
        return pd.DataFrame()
    return (pd.DataFrame(linhas)
              .sort_values(["par", "data_referencia"], kind="stable")
              .reset_index(drop=True))


def _produto_da_serie(par: Par) -> str:
    """A série bruta que o calendário conhece.

    O calendário mapeia produto do IBGE para ids de série bruta; uma série
    derivada como `pib_yoy` não aparece lá, então a consulta usa a bruta de
    origem.
    """
    return par.serie_de_coleta


def resumo(surpresas: pd.DataFrame) -> dict:
    """O que o briefing e o painel consomem: a última surpresa de cada par."""
    if surpresas.empty:
        return {}
    ultimas = {}
    for nome, grupo in surpresas.groupby("par"):
        linha = grupo.sort_values("data_divulgacao", kind="stable").iloc[-1]
        historico = grupo["surpresa"].astype(float)
        ultimas[nome] = {
            "data_referencia": linha["data_referencia"],
            "data_divulgacao": linha["data_divulgacao"],
            "realizado": float(linha["realizado"]),
            "consenso": float(linha["consenso"]),
            "surpresa": float(linha["surpresa"]),
            "unidade": linha["unidade"],
            "primeira_leitura": bool(linha["primeira_leitura"]),
            # Sem escala, uma surpresa de 0,1 p.p. não diz se é muito ou pouco.
            "desvio_padrao_historico": round(float(historico.std()), CASAS),
            "observacoes": int(len(grupo)),
        }
    return ultimas


def texto(tabela: pd.DataFrame) -> str:
    return tabela.to_csv(index=False, lineterminator="\n")


def salvar(surpresas: pd.DataFrame) -> bool:
    CAMINHO.parent.mkdir(parents=True, exist_ok=True)
    novo = texto(surpresas)
    if CAMINHO.exists() and CAMINHO.read_text(encoding="utf-8") == novo:
        log.info("surpresas sem alteração — arquivo mantido")
        return False
    CAMINHO.write_text(novo, encoding="utf-8")
    return True


def carregar() -> pd.DataFrame:
    if not CAMINHO.exists():
        return pd.DataFrame()
    return pd.read_csv(CAMINHO)


def em_dia(surpresas: pd.DataFrame) -> bool:
    return CAMINHO.exists() and CAMINHO.read_text(encoding="utf-8") == texto(surpresas)


def main(argv: list[str] | None = None) -> int:
    import argparse

    parser = argparse.ArgumentParser(
        description="Mede a surpresa de cada divulgação contra o consenso do Focus")
    parser.add_argument("--verificar", action="store_true",
                        help="não grava; reprova se o versionado estiver desatualizado")
    parser.add_argument("--verboso", action="store_true")
    args = parser.parse_args(argv)

    logging.basicConfig(
        level=logging.DEBUG if args.verboso else logging.INFO,
        format="%(asctime)s %(levelname)-7s %(message)s", datefmt="%H:%M:%S",
    )

    surpresas = construir()
    if surpresas.empty:
        log.error("não foi possível medir surpresa: falta calendário ou expectativa")
        return 1

    if args.verificar:
        if not em_dia(surpresas):
            log.error("surpresas desatualizadas: rode `ciclo-surpresa` e versione "
                      "data/derivado/surpresa.csv")
            return 1
        log.info("surpresas em dia (%d divulgações)", len(surpresas))
        return 0

    mudou = salvar(surpresas)
    log.info("surpresas: %d divulgação(ões)%s", len(surpresas),
             "" if mudou else " (sem alteração)")
    for nome, info in resumo(surpresas).items():
        # O rótulo vem da série bruta: uma derivada como `pib_yoy` não tem ficha.
        # Log não derruba comando: sem ficha, o próprio nome do par serve.
        ficha = catalogo().get(PARES[nome].serie_de_coleta) if nome in PARES else None
        rotulo = ficha.nome if ficha else nome
        log.info("%s (%s, ref %s): realizado %.2f, consenso %.2f, surpresa %+.2f %s "
                 "(dp histórico %.2f, n=%d)%s",
                 nome, rotulo, info["data_referencia"], info["realizado"],
                 info["consenso"], info["surpresa"], info["unidade"],
                 info["desvio_padrao_historico"], info["observacoes"],
                 "" if info["primeira_leitura"] else " [realizado já revisado]")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
