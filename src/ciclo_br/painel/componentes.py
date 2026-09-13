"""Peças de tela reaproveitadas pelas páginas.

O item menos decorativo daqui é `protegido`: quando um artefato falta, a página
mostra qual arquivo falta e qual comando o produz, em vez de um traceback. Um
painel que depende de arquivos versionados precisa saber dizer que um deles não
está lá — inclusive para quem acabou de clonar o repositório e ainda não rodou o
pipeline.
"""

from __future__ import annotations

import functools
from collections.abc import Callable

import streamlit as st

from .. import artefatos as dados
from .. import formato
from .graficos import PALETA


def protegido(pagina: Callable[[], None]) -> Callable[[], None]:
    """Transforma artefato ausente em instrução, não em erro."""

    @functools.wraps(pagina)
    def envolvida() -> None:
        try:
            pagina()
        except dados.ArtefatoAusente as ausente:
            artefato = ausente.artefato
            st.error(f"**{artefato.rotulo}** ainda não foi gerado.")
            st.markdown(
                f"O painel só lê arquivo, e este aqui não existe:\n\n"
                f"`{artefato.caminho}`\n\n"
                f"Ele guarda {artefato.descricao}. Para produzi-lo:"
            )
            st.code(artefato.comando, language="bash")

    return envolvida


def pilula(quadrante: str | None) -> str:
    """O nome do quadrante com a cor que ele tem nos gráficos."""
    if not quadrante:
        return "—"
    cor = PALETA.get(quadrante, "#6b7280")
    return (
        f'<span style="background:{cor};color:#fff;padding:2px 10px;'
        f'border-radius:999px;font-weight:600;white-space:nowrap">{quadrante}</span>'
    )


def titulo(texto: str, subtitulo: str | None = None) -> None:
    st.title(texto)
    if subtitulo:
        st.caption(subtitulo)


def barra_lateral() -> None:
    """Estado dos arquivos que o painel lê, sempre à vista.

    A pergunta "isso está atualizado?" é a primeira que alguém faz diante de um
    painel macro, e a resposta honesta não é a data de hoje: é quando o artefato
    foi gerado e até que mês ele vai.
    """
    with st.sidebar:
        st.markdown("### ciclo-br")
        try:
            info = dados.resumo_regime()
            st.markdown(
                f"Regime vigente: {pilula(info.get('quadrante'))}",
                unsafe_allow_html=True,
            )
            st.caption(
                f"Referência: {formato.mes_ano(info.get('referencia'))} · "
                f"desde {formato.mes_ano(info.get('desde'))}"
            )
        except dados.ArtefatoAusente:
            st.caption("Regime ainda não classificado.")

        st.divider()
        proc = dados.procedencia()
        faltando = proc[~proc["existe"]]
        if faltando.empty:
            gerado = proc["modificado_em"].dropna().max()
            st.caption(f"Artefatos: {len(proc)} arquivos, o mais recente "
                       f"{formato.idade(gerado)}.")
        else:
            st.warning(f"{len(faltando)} artefato(s) ausente(s).")

        st.caption(
            "Este painel **não** chama nenhuma API: tudo o que ele mostra vem de "
            "arquivo versionado no repositório. Há teste travando essa regra."
        )
