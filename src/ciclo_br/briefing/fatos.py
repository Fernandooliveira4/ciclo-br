"""O JSON fechado de fatos: tudo o que o briefing pode afirmar, e nada além.

**Todo valor citável é string já formatada em português.** Não é preciosismo de
serialização: é o que torna a verificação possível. Se o JSON trouxesse `0.7182`
e o texto escrevesse "0,72", conferir viraria adivinhação sobre arredondamento.
Trazendo `"+0,7%"`, a conferência é comparação de string, e o modelo de
linguagem só precisa copiar.

**O gatilho é o diff dos próprios fatos**, não o log da ingestão. O que interessa
a quem lê não é o que o coletor fez, e sim o que mudou no que ele afirma: uma
divulgação nova, uma troca de quadrante, uma virada esperando confirmação. Se
nada mudou, não há briefing — um sistema que sabe não falar vale mais que um que
parafraseia estabilidade.
"""

from __future__ import annotations

import datetime as dt
import re

import pandas as pd

from .. import artefatos, formato
from .. import regime as regime_mod

VERSAO = 1

# Quantas divulgações recentes entram no JSON como contexto. Poucas de propósito:
# o briefing é sobre o que acabou de sair, e um histórico longo só daria ao
# modelo mais números para confundir.
DIVULGACOES_DE_CONTEXTO = 4
PROXIMAS_DIVULGACOES = 3

# No replay, quantos meses recuar o último mês de referência do regime. O IBC-Br
# sai com 45 a 60 dias de defasagem, então em 3 de março o mês de janeiro é o
# mais recente que existia. Isto é uma **regra**, não uma data observada: não há
# vintage da série, e o replay declara isso em `avisos` em vez de fingir que sabe.
MESES_DE_DEFASAGEM_NO_REPLAY = 2

# Tokens numéricos do texto: dígitos, com vírgula ou ponto entre eles.
NUMERO = re.compile(r"\d[\d.,]*")


def _desvios(surpresa: float, desvio_padrao: float) -> float:
    return abs(surpresa) / desvio_padrao if desvio_padrao else 0.0


def _divulgacao(linha: pd.Series, desvio_padrao: float) -> dict:
    return {
        "par": linha["par"],
        "referencia": formato.mes_ano(linha["data_referencia"]),
        "divulgado_em": formato.dia(linha["data_divulgacao"]),
        "realizado": formato.numero(linha["realizado"], 2),
        "consenso": formato.numero(linha["consenso"], 2),
        "surpresa": formato.numero(linha["surpresa"], 2, sinal=True,
                                   sufixo=f" {linha['unidade']}"),
        "desvios_padrao": formato.numero(
            _desvios(float(linha["surpresa"]), desvio_padrao), 1),
        "consenso_apurado_em": formato.dia(linha["data_consenso"]),
        "dias_sem_mudanca": int(linha["dias_sem_mudanca"]),
        "realizado_ja_revisado": not bool(linha["primeira_leitura"]),
    }


def _regime(reg: pd.DataFrame) -> dict:
    info = regime_mod.resumo(reg)
    if not info:
        return {}
    return {
        "quadrante": info["quadrante"],
        "desde": formato.mes_ano(info["desde"]),
        "meses_no_quadrante": info["meses_no_quadrante"],
        "referencia": formato.mes_ano(info["referencia"]),
        "crescimento": formato.numero(info["eixo_crescimento"], 1, sinal=True,
                                      sufixo="%"),
        "corte_de_crescimento": formato.numero(info["corte_crescimento"], 1),
        "inflacao": formato.numero(info["eixo_inflacao"], 1, sufixo="%"),
        "corte_de_inflacao": formato.numero(info["corte_inflacao"], 1),
        "virada_pendente": info["pendente"],
        "meses_esperando_confirmacao": info["meses_pendente"],
        "meses_para_confirmar": regime_mod.MESES_PERSISTENCIA,
    }


def _defasagem() -> dict:
    config = artefatos.configuracao_vigente()
    if not config:
        return {}
    return {
        "corte_de_crescimento": config["corte_crescimento"],
        "persistencia_em_meses": int(config["persistencia"]),
        "recessoes_detectadas": int(config["recessoes_detectadas"]),
        "recessoes_avaliadas": int(config["recessoes_avaliadas"]),
        "defasagem_no_pico": formato.numero(config["defasagem_pico_mediana"], 0,
                                            sinal=True),
        "defasagem_no_vale": formato.numero(config["defasagem_vale_mediana"], 0,
                                            sinal=True),
        "fracao_da_janela_com_sinal": formato.numero(
            config["fracao_da_janela_com_sinal"] * 100, 0, sufixo="%"),
    }


def construir(*, ate: dt.date | None = None) -> dict:
    """Os fatos de hoje, ou os de uma data passada (replay).

    Com `ate`, o corte é feito na **data de divulgação**: só entram números que
    já tinham ido ao ar naquele dia. Isso é honesto do lado do consenso, que é
    point-in-time por construção, e **não** é do lado do regime, calculado com a
    série como ela está hoje. A diferença fica declarada no próprio JSON, em
    `avisos`, para que ela chegue ao texto em vez de ficar no código.
    """
    hoje = dt.date.today()
    data = ate or hoje

    reg = artefatos.regime_mensal()
    limite_do_regime = (
        pd.Timestamp(data) - pd.DateOffset(months=MESES_DE_DEFASAGEM_NO_REPLAY)
        if ate else pd.Timestamp(data)
    )
    reg = reg[reg["data"] <= limite_do_regime]

    surpresas = artefatos.surpresas()
    surpresas = surpresas[surpresas["data_divulgacao"].dt.date <= data]
    desvios = {
        linha["par"]: float(linha["desvio_padrao"])
        for _, linha in artefatos.surpresas_por_par(surpresas).iterrows()
    } if not surpresas.empty else {}

    if surpresas.empty:
        do_dia, contexto = [], []
    else:
        ultima = surpresas["data_divulgacao"].max()
        recorte = surpresas.sort_values("data_divulgacao", kind="stable")
        do_dia = [
            _divulgacao(linha, desvios.get(linha["par"], 0.0))
            for _, linha in recorte[recorte["data_divulgacao"] == ultima].iterrows()
        ]
        anteriores = recorte[recorte["data_divulgacao"] < ultima]
        contexto = [
            _divulgacao(linha, desvios.get(linha["par"], 0.0))
            for _, linha in anteriores.tail(DIVULGACOES_DE_CONTEXTO).iterrows()
        ]

    proximas = [
        {
            "divulgacao": formato.dia(linha["data_divulgacao"]),
            "pesquisa": linha["titulo"],
            "referencia": formato.mes_ano(linha["data_referencia"]),
        }
        for _, linha in artefatos.proximas_divulgacoes(
            limite=PROXIMAS_DIVULGACOES, hoje=data).iterrows()
    ]

    fatos = {
        "versao": VERSAO,
        "data": data.isoformat(),
        "replay": ate is not None,
        "regime": _regime(reg),
        "validacao": _defasagem(),
        "divulgacoes_do_dia": do_dia,
        "divulgacoes_anteriores": contexto,
        "proximas_divulgacoes": proximas,
        "avisos": _avisos(reg, do_dia, replay=ate is not None),
    }
    fatos["numeros_permitidos"] = numeros_permitidos(fatos)
    return fatos


def _avisos(reg: pd.DataFrame, do_dia: list[dict], *, replay: bool) -> list[str]:
    """As ressalvas que valem para este briefing específico.

    Ficam nos fatos, e não no código do gerador, porque o modelo de linguagem
    precisa poder mencioná-las — e porque uma ressalva que só existe no rodapé
    tende a ser lida como formalidade.
    """
    avisos = []
    if replay:
        avisos.append(
            "Este briefing é uma reconstrução para demonstração. As surpresas são "
            "point-in-time: o consenso é o que o Focus apurava na véspera, e a data "
            "de divulgação veio do calendário do IBGE. O estado de regime não é: "
            "foi calculado com a série como ela está hoje, inclusive revisões "
            "posteriores, e o último mês de referência foi recuado pela defasagem "
            "típica de publicação — uma regra, não uma data observada."
        )
    if any(d["realizado_ja_revisado"] for d in do_dia):
        avisos.append(
            "O valor realizado desta divulgação foi lido do histórico já revisado, "
            "não do primeiro print."
        )
    if not reg.empty and reg["quadrante"].notna().any():
        avisos.append(
            "O eixo de crescimento vem do IBC-Br, publicado com 45 a 60 dias de "
            "defasagem: o mês de referência do regime é sempre anterior ao mês "
            "corrente."
        )
    return avisos


# ------------------------------------------------------- o que mudou desde o último

def mudancas(novos: dict, anteriores: dict | None) -> dict:
    """O diff entre dois conjuntos de fatos — o gatilho do briefing.

    Sem fatos anteriores, tudo é novidade: é o primeiro briefing do projeto.
    """
    if not anteriores:
        return {"primeiro": True, "divulgacoes": _chaves(novos), "houve": True}

    novas = [c for c in _chaves(novos) if c not in _chaves(anteriores)]
    antes, agora = anteriores.get("regime", {}), novos.get("regime", {})

    diff = {
        "primeiro": False,
        "divulgacoes": novas,
        "quadrante_mudou": bool(
            antes.get("quadrante") and agora.get("quadrante")
            and antes["quadrante"] != agora["quadrante"]),
        "quadrante_anterior": antes.get("quadrante"),
        "referencia_avancou": bool(
            antes.get("referencia") != agora.get("referencia")),
        "pendencia_mudou": bool(
            antes.get("virada_pendente") != agora.get("virada_pendente")),
    }
    diff["houve"] = bool(
        novas or diff["quadrante_mudou"] or diff["referencia_avancou"]
        or diff["pendencia_mudou"])
    return diff


def _chaves(fatos: dict) -> list[str]:
    """Identidade de cada divulgação, para o diff não depender da ordem."""
    return [f"{d['par']} {d['referencia']}"
            for d in fatos.get("divulgacoes_do_dia", [])]


# -------------------------------------------------------- números permitidos

def numeros_permitidos(fatos: dict) -> list[str]:
    """Todo token numérico que aparece nos fatos — e, portanto, no texto.

    É a lista que o modelo recebe e a régua contra a qual o texto é conferido.
    Os dois saem da mesma função de propósito: uma régua diferente da instrução
    reprovaria texto obediente.
    """
    encontrados: set[str] = set()
    _coletar(fatos, encontrados)
    return sorted(encontrados, key=lambda s: (len(s), s))


def _coletar(no, destino: set[str]) -> None:
    if isinstance(no, dict):
        for chave, valor in no.items():
            if chave != "numeros_permitidos":
                _coletar(valor, destino)
    elif isinstance(no, list):
        for item in no:
            _coletar(item, destino)
    elif isinstance(no, bool):
        return
    elif isinstance(no, int | float):
        destino.add(str(no))
    elif isinstance(no, str):
        destino.update(NUMERO.findall(no))


def numeros_do_texto(texto: str) -> list[str]:
    """Os tokens numéricos escritos no texto, na ordem em que aparecem."""
    return NUMERO.findall(texto)


def numeros_inventados(texto: str, permitidos: list[str]) -> list[str]:
    """Números presentes no texto e ausentes dos fatos.

    Pontuação final é aparada: "em 2026." traz o token "2026." e o ponto é do
    português, não do número.
    """
    permitido = set(permitidos)
    fora = []
    for token in numeros_do_texto(texto):
        limpo = token.rstrip(".,")
        if limpo and limpo not in permitido and token not in permitido:
            fora.append(limpo)
    return sorted(set(fora))
