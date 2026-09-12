"""Portões de qualidade de dado — o que faz o pipeline se recusar a publicar.

A CI não roda só lint e teste. Ela roda estas verificações contra os dados de
verdade, e **reprova o build** quando algo chega errado. A diferença prática:
um pipeline que quebra alto quando a fonte muda vale mais que um que segue
gravando lixo em silêncio, porque o segundo só é descoberto quando alguém olha
um gráfico estranho semanas depois.

Cada verificação devolve problemas em vez de levantar exceção, para que uma
execução reporte tudo o que está errado de uma vez, não o primeiro erro.
"""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass
from enum import StrEnum

import pandas as pd

from . import storage
from .config import Serie, catalogo

# Até quantos dias depois do fim do período a observação ainda pode não ter
# chegado. Derivado da defasagem real de publicação de cada tipo de série, com
# folga: o IBC-Br sai cerca de 45 dias depois do mês de referência.
FRESCOR_PADRAO = {"diaria": 10, "mensal": 100, "trimestral": 190}

# Um salto acima disto em desvios absolutos medianos é suspeito o bastante para
# reprovar. É proposital que seja alto: o portão existe para pegar mudança de
# unidade e lixo da fonte, não oscilação econômica forte.
LIMITE_SALTO_MAD = 15.0

# Quantos períodos contam como "recém-chegado" para efeito do alarme de salto.
PERIODOS_RECENTES = 12


class Gravidade(StrEnum):
    ERRO = "erro"       # reprova o build
    AVISO = "aviso"     # registra, não reprova


@dataclass(frozen=True)
class Problema:
    serie_id: str
    verificacao: str
    gravidade: Gravidade
    detalhe: str

    def __str__(self) -> str:
        marca = "ERRO " if self.gravidade is Gravidade.ERRO else "aviso"
        return f"[{marca}] {self.serie_id}: {self.verificacao} — {self.detalhe}"


def _passo_esperado(periodicidade: str) -> pd.DateOffset | None:
    if periodicidade == "mensal":
        return pd.DateOffset(months=1)
    if periodicidade == "trimestral":
        return pd.DateOffset(months=3)
    return None  # séries diárias têm feriado e fim de semana: buraco é normal


def verificar_serie(serie: Serie) -> list[Problema]:
    problemas: list[Problema] = []
    bruto = storage.ler_bruto(serie.id)

    if bruto.empty:
        return [Problema(serie.id, "existe", Gravidade.ERRO,
                         "nenhuma observação gravada")]

    # 1. Chave duplicada quebraria a noção de versão vigente.
    chave = ["data_referencia", "data_coleta"]
    duplicadas = int(bruto.duplicated(subset=chave).sum())
    if duplicadas:
        problemas.append(Problema(
            serie.id, "chave única", Gravidade.ERRO,
            f"{duplicadas} linha(s) com (data_referencia, data_coleta) repetida",
        ))

    # 2. Valores que não são número não podem ter entrado.
    nao_numericos = ~bruto["valor"].apply(pd.api.types.is_number)
    invalidos = int(bruto["valor"].isna().sum() + nao_numericos.sum())
    if invalidos:
        problemas.append(Problema(
            serie.id, "valores numéricos", Gravidade.ERRO,
            f"{invalidos} valor(es) nulo(s) ou não numérico(s)",
        ))

    vigente = storage.ler_vigente(serie.id).sort_values("data_referencia")

    # 3. Buraco na grade temporal indica coleta incompleta.
    passo = _passo_esperado(serie.periodicidade)
    if passo is not None and len(vigente) > 2:
        datas = pd.to_datetime(pd.Series(list(vigente["data_referencia"])))
        esperadas = pd.date_range(datas.iloc[0], datas.iloc[-1],
                                  freq="MS" if serie.periodicidade == "mensal" else "QS")
        faltando = sorted(set(esperadas.date) - set(vigente["data_referencia"]))
        if faltando:
            amostra = ", ".join(str(d) for d in faltando[:5])
            problemas.append(Problema(
                serie.id, "grade temporal", Gravidade.ERRO,
                f"{len(faltando)} período(s) ausente(s): {amostra}"
                + (" ..." if len(faltando) > 5 else ""),
            ))

    # 4. Frescor: a série parou de ser atualizada?
    # Série encerrada na fonte (caso da versão congelada dos núcleos) não envelhece:
    # ela está parada de propósito, e cobrar frescor dela seria alarme permanente.
    if not serie.extra.get("encerrada"):
        limite = serie.extra.get("frescor_max_dias") or FRESCOR_PADRAO.get(serie.periodicidade)
        if limite:
            ultima = max(vigente["data_referencia"])
            atraso = (dt.date.today() - ultima).days
            if atraso > limite:
                problemas.append(Problema(
                    serie.id, "frescor", Gravidade.ERRO,
                    f"última referência {ultima} está {atraso} dias atrás (limite {limite})",
                ))

    # 5. Salto absurdo no dado RECÉM-CHEGADO.
    # A referência é a história inteira, mas o alarme só dispara se o extremo está
    # na cauda recente. Sem esse recorte o portão passaria a vida denunciando a
    # hiperinflação de 1990 e a troca de moeda de 1993 — fatos verdadeiros que não
    # dizem nada sobre a coleta de hoje.
    if len(vigente) > 24:
        valores = pd.Series(list(vigente["valor"]), dtype="float64").reset_index(drop=True)
        diferencas = valores.diff().abs().dropna()
        mad = float((diferencas - diferencas.median()).abs().median())
        # Série muito regular tem MAD zero, e aí a escala vira a própria variação
        # típica. Sem esse cuidado a verificação se desligava exatamente no caso
        # em que um valor absurdo seria mais fácil de ver.
        escala = mad if mad > 0 else float(diferencas.median())
        if escala > 0:
            corte = LIMITE_SALTO_MAD * escala + float(diferencas.median())
            recentes = diferencas.tail(PERIODOS_RECENTES)
            if float(recentes.max()) > corte:
                posicao = int(recentes.idxmax())
                onde = list(vigente["data_referencia"])[posicao]
                problemas.append(Problema(
                    serie.id, "salto extremo", Gravidade.AVISO,
                    f"variação de {float(recentes.max()):.4g} em {onde}, "
                    f"acima do corte de {corte:.4g}",
                ))

    return problemas


def verificar_tudo() -> list[Problema]:
    problemas: list[Problema] = []
    for serie in catalogo().values():
        problemas.extend(verificar_serie(serie))
    return problemas


def main(argv: list[str] | None = None) -> int:
    import argparse
    import logging

    parser = argparse.ArgumentParser(description="Portões de qualidade dos dados")
    parser.add_argument("--serie", action="append", dest="series")
    parser.add_argument("--avisos-reprovam", action="store_true",
                        help="trata aviso como erro")
    args = parser.parse_args(argv)

    logging.basicConfig(level=logging.INFO, format="%(message)s")
    log = logging.getLogger("ciclo_br.qualidade")

    todas = catalogo()
    alvos = [todas[s] for s in args.series] if args.series else list(todas.values())

    problemas: list[Problema] = []
    for serie in alvos:
        problemas.extend(verificar_serie(serie))

    if not problemas:
        log.info("qualidade: %d série(s) verificada(s), nenhum problema", len(alvos))
        return 0

    for p in problemas:
        log.info("%s", p)

    erros = [p for p in problemas
             if p.gravidade is Gravidade.ERRO or args.avisos_reprovam]
    log.info("qualidade: %d problema(s), %d reprovando o build", len(problemas), len(erros))
    return 1 if erros else 0


if __name__ == "__main__":
    raise SystemExit(main())
