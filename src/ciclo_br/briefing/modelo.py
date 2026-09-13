"""Gerador determinístico: o briefing escrito sem modelo de linguagem.

Ele não é um plano B envergonhado. É o gerador padrão quando não há chave de
API, é o que assume quando o texto do modelo é recusado pela verificação, e é o
que o painel usa no modo de demonstração — porque o painel não fala com a rede.
Na ordem de sacrifício do projeto, o LLM é a primeira coisa a cair justamente
porque isto aqui cobre.

O texto é montado a partir do mesmo JSON de fatos que o modelo receberia, então
ele passa pela mesma auditoria de números. Se um dia esta função escrever um
valor que não está nos fatos, a CI reprova — e está certo que reprove.
"""

from __future__ import annotations

from .. import formato

NOMES = {
    "ipca": "IPCA",
    "desocupacao": "Taxa de desocupação",
    "pib": "PIB",
}

# Acima disso a divulgação é tratada como notícia, e não como rotina. Um desvio
# padrão é a régua mais simples que existe e a única que os dados sustentam com
# 117 observações no par mais longo.
DESVIOS_PARA_DESTAQUE = 1.0


def _nome(par: str) -> str:
    return NOMES.get(par, par)


def _divulgacao(item: dict) -> str:
    try:
        desvios = float(item["desvios_padrao"].replace(",", "."))
    except (ValueError, AttributeError):
        desvios = 0.0

    veredito = (
        "acima do que o consenso projetava"
        if item["surpresa"].startswith("+")
        else "abaixo do que o consenso projetava"
    )
    escala = (
        f"Surpresa de {item['surpresa']}, {item['desvios_padrao']}× o desvio "
        f"padrão histórico do par — "
        + ("fora da faixa de rotina." if desvios >= DESVIOS_PARA_DESTAQUE
           else "dentro da faixa de rotina.")
    )
    return (
        f"**{_nome(item['par'])}, referência {item['referencia']}: "
        f"{item['realizado']} contra consenso de {item['consenso']}.** "
        f"O número saiu {veredito}. {escala} "
        f"O consenso usado é a apuração do Focus de {item['consenso_apurado_em']}, "
        f"a última antes da divulgação de {item['divulgado_em']}; ele estava "
        f"parado havia {formato.dias(item['dias_sem_mudanca'])}."
    )


def _regime(regime: dict) -> str:
    if not regime:
        return "**Regime:** ainda não há mês classificado."

    frase = (
        f"**Regime: {regime['quadrante']} desde {regime['desde']} "
        f"({formato.meses(regime['meses_no_quadrante'])}).** Na referência de "
        f"{regime['referencia']}, o eixo de crescimento está em "
        f"{regime['crescimento']} contra corte em "
        f"{regime['corte_de_crescimento']}, e o de inflação em "
        f"{regime['inflacao']} contra corte em {regime['corte_de_inflacao']}."
    )
    if regime.get("virada_pendente"):
        frase += (
            f" O sinal cru já aponta {regime['virada_pendente']} há "
            f"{formato.meses(regime['meses_esperando_confirmacao'])}; a regra exige "
            f"{regime['meses_para_confirmar']} meses seguidos para confirmar a "
            f"virada, então o quadrante vigente continua sendo o acima."
        )
    else:
        frase += " Nenhuma virada esperando confirmação."
    return frase


def _validacao(validacao: dict) -> str:
    if not validacao:
        return ""
    return (
        f"**O sinal acompanha, não antecipa.** Contra a datação do CODACE, esta "
        f"configuração — corte em {validacao['corte_de_crescimento']}, "
        f"persistência de {validacao['persistencia_em_meses']} meses — entra em "
        f"contração com defasagem mediana de {validacao['defasagem_no_pico']} "
        f"meses e sai com {validacao['defasagem_no_vale']}, e fica ligada em "
        f"{validacao['fracao_da_janela_com_sinal']} dos meses da janela avaliada."
    )


def _proximas(proximas: list[dict]) -> str:
    if not proximas:
        return ""
    itens = "; ".join(
        f"{p['pesquisa']} em {p['divulgacao']} (referência {p['referencia']})"
        for p in proximas
    )
    return f"**No calendário:** {itens}."


def escrever(fatos: dict, mudancas: dict | None = None) -> str:
    """O corpo do briefing. O rodapé é acrescentado na publicação."""
    partes: list[str] = []

    do_dia = fatos.get("divulgacoes_do_dia") or []
    if do_dia:
        partes.extend(_divulgacao(item) for item in do_dia)
    elif (mudancas or {}).get("referencia_avancou"):
        partes.append(
            "**Sem divulgação nova nesta rodada.** O que mudou foi a camada "
            "derivada, recalculada sobre o dado mais recente."
        )
    else:
        partes.append("**Sem divulgação nova nesta rodada.**")

    partes.append(_regime(fatos.get("regime") or {}))

    if (mudancas or {}).get("quadrante_mudou"):
        partes.append(
            f"**Houve troca de quadrante** em relação ao briefing anterior, que "
            f"registrava {mudancas['quadrante_anterior']}."
        )

    validacao = _validacao(fatos.get("validacao") or {})
    if validacao:
        partes.append(validacao)

    proximas = _proximas(fatos.get("proximas_divulgacoes") or [])
    if proximas:
        partes.append(proximas)

    avisos = fatos.get("avisos") or []
    if avisos:
        partes.append("**Ressalvas.** " + " ".join(avisos))

    return "\n\n".join(partes)
