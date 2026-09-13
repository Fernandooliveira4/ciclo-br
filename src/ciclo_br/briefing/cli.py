"""`ciclo-briefing`: publica o briefing — quando há o que dizer.

O comando é silencioso na maior parte dos dias, e isso é o comportamento
correto. Ele compara os fatos de hoje com os do último briefing publicado; se
nada mudou, não escreve. Um sistema que parafraseia estabilidade todo dia treina
o leitor a não ler.
"""

from __future__ import annotations

import argparse
import datetime as dt
import logging

from . import fatos as fatos_mod
from . import llm, modelo, publicacao

log = logging.getLogger(__name__)


def _gerar(fatos: dict, mudancas: dict, *, sem_llm: bool) -> dict:
    """Escolhe o gerador e devolve o registro pronto para publicar."""
    if sem_llm:
        return publicacao.montar(
            fatos, mudancas, modelo.escrever(fatos, mudancas),
            gerador="modelo", motivo="gerador determinístico pedido na linha de comando")

    resultado = llm.escrever(fatos, mudancas)
    if resultado.texto:
        return publicacao.montar(fatos, mudancas, resultado.texto,
                                 gerador="haiku", modelo=resultado.modelo)

    return publicacao.montar(
        fatos, mudancas, modelo.escrever(fatos, mudancas),
        gerador="modelo", modelo=resultado.modelo, motivo=resultado.motivo)


def _replay(data: dt.date, *, sem_llm: bool) -> int:
    """Reconstrói o briefing de uma data passada e imprime, sem publicar.

    Não grava de propósito: uma reconstrução no diretório dos briefings
    publicados viraria, no dia seguinte, um briefing que parece ter sido
    publicado naquela data.
    """
    fatos = fatos_mod.construir(ate=data)
    if not fatos["divulgacoes_do_dia"]:
        log.error("nenhuma divulgação medida até %s", data)
        return 1

    registro = _gerar(fatos, {"primeiro": True, "houve": True, "divulgacoes": []},
                      sem_llm=sem_llm)
    print(publicacao.renderizar(registro))
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Publica o briefing do dia, quando há dado novo")
    parser.add_argument("--sem-llm", action="store_true", dest="sem_llm",
                        help="usa só o gerador determinístico")
    parser.add_argument("--replay", metavar="AAAA-MM-DD",
                        help="reconstrói o briefing de uma data passada e imprime, "
                             "sem publicar")
    parser.add_argument("--auditar", action="store_true",
                        help="reconfere todos os briefings publicados; "
                             "código 1 se algum número não estiver nos fatos")
    parser.add_argument("--forcar", action="store_true",
                        help="publica mesmo sem novidade")
    parser.add_argument("--verboso", action="store_true")
    args = parser.parse_args(argv)

    logging.basicConfig(
        level=logging.DEBUG if args.verboso else logging.INFO,
        format="%(asctime)s %(levelname)-7s %(message)s", datefmt="%H:%M:%S",
    )

    if args.auditar:
        problemas = publicacao.auditar()
        for problema in problemas:
            log.error("%s", problema)
        if problemas:
            return 1
        log.info("briefings auditados: %d, nenhum número fora dos fatos",
                 len(publicacao.publicados()))
        return 0

    if args.replay:
        try:
            data = dt.date.fromisoformat(args.replay)
        except ValueError:
            parser.error("--replay espera uma data no formato AAAA-MM-DD")
        return _replay(data, sem_llm=args.sem_llm)

    fatos = fatos_mod.construir()
    anterior = publicacao.ultimo()
    mudancas = fatos_mod.mudancas(fatos, (anterior or {}).get("fatos"))

    if not mudancas["houve"] and not args.forcar:
        log.info("sem novidade desde o briefing de %s — nada a publicar",
                 (anterior or {}).get("data", "—"))
        return 0

    registro = _gerar(fatos, mudancas, sem_llm=args.sem_llm)
    mudou = publicacao.publicar(registro)

    log.info("briefing de %s %s (%s)", registro["data"],
             "publicado" if mudou else "sem alteração",
             publicacao.GERADORES.get(registro["gerador"], registro["gerador"]))
    if registro.get("motivo"):
        log.info("motivo: %s", registro["motivo"])
    for divulgacao in fatos["divulgacoes_do_dia"]:
        log.info("divulgação: %s ref %s, realizado %s, consenso %s, surpresa %s",
                 divulgacao["par"], divulgacao["referencia"],
                 divulgacao["realizado"], divulgacao["consenso"],
                 divulgacao["surpresa"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
