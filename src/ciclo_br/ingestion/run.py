"""Orquestra a ingestão das séries do SGS.

Dois modos:

  backfill     baixa desde o início declarado na ficha. Roda uma vez.
  incremental  rebaixa uma janela recente. É o modo do agendamento diário.

O incremental reconsulta os últimos meses de propósito, mesmo já tendo o dado:
é assim que revisões retroativas são detectadas. Como o armazenamento só grava
o que mudou, reconsultar não custa espaço.
"""

from __future__ import annotations

import argparse
import datetime as dt
import logging
import sys

from .. import storage
from ..config import Serie, catalogo, series_da_fonte
from . import sgs

log = logging.getLogger("ciclo_br.ingest")

# Quantos meses o modo incremental reconsulta para trás, à caça de revisões.
MESES_RETROATIVOS = 24
INICIO_PADRAO = dt.date(1994, 7, 1)  # Plano Real: antes disso nada aqui faz sentido


def _inicio_da_ficha(serie: Serie) -> dt.date:
    if not serie.inicio:
        return INICIO_PADRAO
    ano, mes = str(serie.inicio).split("-")[:2]
    return dt.date(int(ano), int(mes), 1)


def _inicio_incremental(serie: Serie) -> dt.date:
    vigente = storage.ler_vigente(serie.id)
    if vigente.empty:
        return _inicio_da_ficha(serie)
    ultima = max(vigente["data_referencia"])
    mes = ultima.month - MESES_RETROATIVOS
    ano = ultima.year + (mes - 1) // 12
    mes = (mes - 1) % 12 + 1
    return max(dt.date(ano, mes, 1), _inicio_da_ficha(serie))


def ingerir(serie: Serie, *, execucao_id: str, backfill: bool) -> storage.ResultadoAnexo:
    inicio = _inicio_da_ficha(serie) if backfill else _inicio_incremental(serie)
    iniciada_em = dt.datetime.now(dt.UTC)
    log.info("%s (SGS %s) desde %s", serie.id, serie.codigo, inicio)

    try:
        observacoes = sgs.buscar(serie.codigo, inicio)
    except Exception as exc:  # noqa: BLE001 - queremos registrar e seguir
        log.error("%s: falhou (%s)", serie.id, exc)
        vazio = storage.ResultadoAnexo(serie.id, 0, 0, 0)
        storage.registrar_execucao(
            execucao_id, vazio, iniciada_em=iniciada_em, erro=str(exc)
        )
        raise

    resultado = storage.anexar(serie.id, observacoes, execucao_id=execucao_id)
    storage.registrar_execucao(execucao_id, resultado, iniciada_em=iniciada_em)
    log.info("%s", resultado)
    return resultado


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Ingestão de séries do SGS/BCB")
    parser.add_argument("--serie", action="append", dest="series",
                        help="id da série (repetível). Padrão: todas do SGS.")
    parser.add_argument("--backfill", action="store_true",
                        help="baixa desde o início declarado na ficha")
    parser.add_argument("--verboso", action="store_true")
    args = parser.parse_args(argv)

    logging.basicConfig(
        level=logging.DEBUG if args.verboso else logging.INFO,
        format="%(asctime)s %(levelname)-7s %(message)s",
        datefmt="%H:%M:%S",
    )

    todas = catalogo()
    if args.series:
        desconhecidas = [s for s in args.series if s not in todas]
        if desconhecidas:
            parser.error(f"série(s) sem ficha em config/series.yaml: {desconhecidas}")
        alvos = [todas[s] for s in args.series]
    else:
        alvos = series_da_fonte("sgs")

    execucao_id = storage.novo_execucao_id()
    log.info("execução %s | %d série(s) | modo %s",
             execucao_id, len(alvos), "backfill" if args.backfill else "incremental")

    falhas, total = [], storage.ResultadoAnexo("total", 0, 0, 0)
    for serie in alvos:
        try:
            r = ingerir(serie, execucao_id=execucao_id, backfill=args.backfill)
        except Exception:  # noqa: BLE001 - uma série ruim não derruba as outras
            falhas.append(serie.id)
            continue
        total = storage.ResultadoAnexo(
            "total", total.novas + r.novas, total.revisoes + r.revisoes,
            total.inalteradas + r.inalteradas,
        )

    log.info("%s", total)
    if falhas:
        log.error("séries com falha: %s", falhas)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
