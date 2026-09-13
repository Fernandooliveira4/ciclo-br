"""O texto escrito pelo Haiku 4.5 — e a verificação que pode recusá-lo.

Este é o único módulo do projeto que fala com um modelo de linguagem, e ele é
deliberadamente pequeno. O modelo recebe o JSON de fatos e mais nada: não tem
ferramenta, não tem busca, não tem histórico. O que ele faz é redação.

**A verificação não é opcional e não corrige.** Um texto reprovado é descartado
inteiro, e o gerador determinístico assume — porque "consertar" a saída de um
modelo exigiria decidir qual parte estava certa, e essa decisão não tem como ser
automática. O rodapé do briefing diz qual dos dois escreveu e, quando houve
recusa, o motivo. Um briefing que às vezes é escrito por template e avisa é mais
confiável que um que sempre parece ter sido escrito por IA.

**Sobre a lista de termos proibidos.** Ela é curta de propósito. Bloquear toda
palavra que cheire a futuro censuraria frase legítima: "o consenso previa 0,23"
descreve o passado e é exatamente o que o briefing deve dizer. O que está
bloqueado é o projeto falando em primeira pessoa sobre o que vem — previsão,
recomendação, aposta.
"""

from __future__ import annotations

import json
import logging
import os
import re
from dataclasses import dataclass

from . import fatos as fatos_mod

log = logging.getLogger(__name__)

MODELO = "claude-haiku-4-5-20251001"
VARIAVEL_DE_CHAVE = "ANTHROPIC_API_KEY"

MAX_TOKENS = 700
LIMITE_DE_CARACTERES = 1800

INSTRUCAO = """\
Você escreve o briefing diário de um projeto de macroeconomia brasileira.

Você recebe um JSON de fatos já apurados. Ele é a sua única fonte: você não tem
acesso a nenhum outro dado, e não deve recorrer ao que você sabe sobre a
economia brasileira.

Regras, todas obrigatórias:

1. Só escreva números que estejam na lista `numeros_permitidos`. Copie-os como
   estão, com vírgula decimal. Nunca calcule, arredonde ou converta um número.
2. Não faça previsão, não recomende posição, não diga o que deve acontecer.
   Descrever o que o consenso projetava antes de uma divulgação é permitido e
   desejável; dizer para onde algo vai, não.
3. Não atribua causa a nada. Os fatos não trazem causa, e inventar uma é o erro
   mais fácil de cometer aqui.
4. Mencione as ressalvas do campo `avisos` quando houver.
5. Português do Brasil, tom sóbrio, sem adjetivo de intensidade que os números
   não sustentem. De dois a quatro parágrafos curtos, no máximo 250 palavras.
6. Use negrito para a frase de abertura de cada parágrafo. Não use títulos com
   `#`, não use lista com marcadores, não escreva rodapé nem assinatura.

Escreva apenas o texto do briefing.\
"""

# Primeira pessoa sobre o futuro, e recomendação. Ver o docstring do módulo para
# o motivo de a lista ser curta.
TERMOS_PROIBIDOS = (
    re.compile(r"\brecomend\w*", re.IGNORECASE),
    re.compile(r"\bsugerimos\b|\bsugere-se\b", re.IGNORECASE),
    re.compile(r"\b(esperamos|prevemos|projetamos|apostamos|acreditamos)\b",
               re.IGNORECASE),
    re.compile(r"\b(deve|deverá|deverão|tende a|tendem a)\s+"
               r"(subir|cair|acelerar|desacelerar|avançar|recuar|melhorar|piorar)\b",
               re.IGNORECASE),
    re.compile(r"\b(noss[ao])\s+(previsão|projeção|expectativa|recomendação)\b",
               re.IGNORECASE),
)


@dataclass(frozen=True)
class Resultado:
    """O texto aceito, ou o motivo de não haver texto."""

    texto: str | None
    motivo: str | None
    modelo: str | None = None


def disponivel() -> bool:
    """Há SDK instalado e chave no ambiente?

    A ausência de qualquer um dos dois não é erro: é o caminho normal em quem
    clonou o repositório, e o gerador determinístico cobre.
    """
    if not os.environ.get(VARIAVEL_DE_CHAVE):
        return False
    try:
        import anthropic  # noqa: F401
    except ImportError:
        return False
    return True


def conferir(texto: str, fatos: dict) -> str | None:
    """Devolve o motivo da recusa, ou `None` se o texto passa.

    A ordem importa pouco, mas a primeira checagem é a que existe para valer:
    número fora dos fatos é a falha que este projeto não pode deixar passar.
    """
    if not texto or not texto.strip():
        return "o modelo devolveu texto vazio"

    inventados = fatos_mod.numeros_inventados(texto, fatos["numeros_permitidos"])
    if inventados:
        return f"números fora dos fatos: {', '.join(inventados)}"

    for padrao in TERMOS_PROIBIDOS:
        achado = padrao.search(texto)
        if achado:
            return f"termo de previsão ou recomendação: {achado.group(0)!r}"

    if len(texto) > LIMITE_DE_CARACTERES:
        return f"texto longo demais ({len(texto)} caracteres)"

    if re.search(r"^#{1,6}\s", texto, re.MULTILINE):
        return "o texto trouxe títulos, e a estrutura do documento é nossa"

    return None


def _mensagem(fatos: dict, mudancas: dict) -> str:
    return json.dumps(
        {"fatos": fatos, "o_que_mudou": mudancas}, ensure_ascii=False, indent=2)


def escrever(fatos: dict, mudancas: dict, *, cliente=None) -> Resultado:
    """Pede o texto ao modelo e devolve só o que passa na verificação."""
    if cliente is None:
        if not disponivel():
            return Resultado(None, "sem chave de API ou SDK da Anthropic", None)
        import anthropic

        cliente = anthropic.Anthropic()

    try:
        resposta = cliente.messages.create(
            model=MODELO,
            max_tokens=MAX_TOKENS,
            system=INSTRUCAO,
            messages=[{"role": "user", "content": _mensagem(fatos, mudancas)}],
        )
        texto = "".join(
            bloco.text for bloco in resposta.content
            if getattr(bloco, "type", None) == "text"
        ).strip()
    except Exception as erro:  # noqa: BLE001 - a falha não pode derrubar o pipeline
        log.warning("chamada ao modelo falhou: %s", erro)
        return Resultado(None, f"a chamada ao modelo falhou ({type(erro).__name__})",
                         MODELO)

    motivo = conferir(texto, fatos)
    if motivo:
        log.warning("texto do modelo recusado: %s", motivo)
        return Resultado(None, f"texto do modelo recusado — {motivo}", MODELO)
    return Resultado(texto, None, MODELO)
