"""Orquestra a ingestão de todas as fontes.

Dois modos:

  backfill     baixa desde o início declarado na ficha. Roda uma vez.
  incremental  rebaixa uma janela recente. É o modo do agendamento diário.

O incremental reconsulta o passado recente de propósito, mesmo já tendo o dado:
é assim que revisões retroativas são detectadas. Como o armazenamento só grava
o que mudou, reconsultar não custa espaço.

A janela retroativa difere por fonte. No SGS ela é contada sobre a data de
referência, porque o que se procura é o Banco Central ter mexido num mês antigo.
No Focus ela é contada sobre a data de coleta, porque o passado do Focus é
imutável — cada coleta é um fato datado, e só interessa o que veio depois da
última que já temos. No IBGE não há janela: as Contas Nacionais revisam o
histórico inteiro a cada divulgação, e a série cabe numa requisição só, então
recortar os últimos meses descartaria de graça justamente as revisões antigas,
que são as que ninguém mais registra.
"""

from __future__ import annotations

import argparse
import datetime as dt
import logging
import sys

from .. import storage
from ..config import FONTES, Serie, catalogo, series_da_fonte
from . import focus, ibge_agregados, sgs

log = logging.getLogger("ciclo_br.ingest")

MESES_RETROATIVOS = 24   # SGS: quanto do passado reconsultar à caça de revisões
DIAS_RETROATIVOS = 30    # Focus: sobreposição de segurança sobre a última coleta
INICIO_PADRAO = dt.date(1994, 7, 1)  # Plano Real: antes disso nada aqui faz sentido


def _inicio_da_ficha(serie: Serie) -> dt.date:
    if not serie.inicio:
        return INICIO_PADRAO
    ano, mes = str(serie.inicio).split("-")[:2]
    return dt.date(int(ano), int(mes), 1)


def _recuar_meses(data: dt.date, meses: int) -> dt.date:
    mes = data.month - meses
    ano = data.year + (mes - 1) // 12
    return dt.date(ano, (mes - 1) % 12 + 1, 1)


def _inicio_incremental(serie: Serie) -> dt.date:
    vigente = storage.ler_vigente(serie.id)
    if vigente.empty:
        return _inicio_da_ficha(serie)

    if serie.fonte == "ibge":
        # Sem janela: ver a docstring do módulo. A revisão das Contas Nacionais
        # reescreve anos, não meses, e é ela que dá conteúdo à aba de Revisões.
        return _inicio_da_ficha(serie)

    if serie.fonte == "focus":
        ultima_coleta = max(vigente["data_coleta"]).date()
        candidato = ultima_coleta - dt.timedelta(days=DIAS_RETROATIVOS)
    else:
        candidato = _recuar_meses(max(vigente["data_referencia"]), MESES_RETROATIVOS)

    return max(candidato, _inicio_da_ficha(serie))


def _baixar(serie: Serie, inicio: dt.date):
    if serie.fonte == "sgs":
        return sgs.buscar(serie.codigo, inicio)
    if serie.fonte == "focus":
        return focus.buscar(
            serie.recurso,
            serie.indicador,
            periodicidade=serie.periodicidade,
            base_calculo=serie.base_calculo if serie.base_calculo is not None else 0,
            desde=inicio,
        )
    if serie.fonte == "ibge":
        return ibge_agregados.buscar(
            serie.tabela,
            serie.variavel,
            serie.categoria,
            classificacao=serie.classificacao,
            periodicidade=serie.periodicidade,
            desde=inicio,
        )
    raise ValueError(f"série {serie.id}: fonte desconhecida {serie.fonte!r}")


def ingerir(serie: Serie, *, execucao_id: str, backfill: bool) -> storage.ResultadoAnexo:
    inicio = _inicio_da_ficha(serie) if backfill else _inicio_incremental(serie)
    iniciada_em = dt.datetime.now(dt.UTC)
    log.info("%s (%s %s) desde %s", serie.id, serie.fonte.upper(),
             serie.referencia_na_fonte, inicio)

    try:
        observacoes = _baixar(serie, inicio)
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
    parser = argparse.ArgumentParser(description="Ingestão de séries do BCB (SGS e Focus)")
    parser.add_argument("--serie", action="append", dest="series",
                        help="id da série (repetível). Padrão: todas.")
    parser.add_argument("--fonte", choices=sorted(FONTES),
                        help="restringe a uma fonte")
    parser.add_argument("--backfill", action="store_true",
                        help="baixa desde o início declarado na ficha")
    parser.add_argument("--resumo-arquivo", dest="resumo_arquivo",
                        help="grava uma linha com o que a execução achou "
                             "(usada como mensagem de commit no agendamento)")
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
    elif args.fonte:
        alvos = series_da_fonte(args.fonte)
    else:
        # Derivado do catálogo, e não escrito à mão, porque é assim que o
        # agendamento diário chama. Com a lista fixa, uma fonte nova coletava no
        # backfill manual, passava nos oito portões e sumia do agendamento — e o
        # sintoma só aparecia meses depois, como portão de frescor vermelho sem
        # causa aparente. Há teste travando a equivalência com o catálogo.
        alvos = [s for s in todas.values() if s.implementada]

    execucao_id = storage.novo_execucao_id()
    log.info("execução %s | %d série(s) | modo %s",
             execucao_id, len(alvos), "backfill" if args.backfill else "incremental")

    falhas, total = [], storage.ResultadoAnexo("total", 0, 0, 0)
    com_novidade: list[str] = []
    for serie in alvos:
        try:
            r = ingerir(serie, execucao_id=execucao_id, backfill=args.backfill)
        except Exception:  # noqa: BLE001 - uma série ruim não derruba as outras
            falhas.append(serie.id)
            continue
        if r.gravadas:
            com_novidade.append(serie.id)
        total = storage.ResultadoAnexo(
            "total", total.novas + r.novas, total.revisoes + r.revisoes,
            total.inalteradas + r.inalteradas, total.ignoradas + r.ignoradas,
        )

    log.info("%s", total)
    if args.resumo_arquivo:
        _gravar_resumo(args.resumo_arquivo, total, com_novidade, falhas)
    if falhas:
        log.error("séries com falha: %s", falhas)
        return 1
    return 0


def _gravar_resumo(
    caminho: str,
    total: storage.ResultadoAnexo,
    com_novidade: list[str],
    falhas: list[str],
) -> None:
    """Uma linha descrevendo a execução, para virar mensagem de commit.

    O objetivo é que o histórico do Git seja legível: 'sem dado novo' na maioria
    dos dias e, quando houver, exatamente o que chegou e em qual série.
    """
    if falhas:
        texto = f"ingest: falha em {', '.join(falhas)}"
    elif not total.gravadas:
        texto = "ingest: sem dado novo"
    else:
        partes = []
        if total.novas:
            partes.append(f"{total.novas} nova(s)")
        if total.revisoes:
            partes.append(f"{total.revisoes} revisão(ões)")
        texto = f"ingest: {' e '.join(partes)} em {', '.join(com_novidade)}"

    from pathlib import Path
    Path(caminho).write_text(texto[:200] + "\n", encoding="utf-8")


if __name__ == "__main__":
    sys.exit(main())
