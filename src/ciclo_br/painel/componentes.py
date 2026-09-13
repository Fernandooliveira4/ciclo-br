"""Peças de tela reaproveitadas pelas páginas.

O item menos decorativo daqui é `protegido`: quando um artefato falta, a página
mostra qual arquivo falta e qual comando o produz, em vez de um traceback. Um
painel que depende de arquivos versionados precisa saber dizer que um deles não
está lá — inclusive para quem acabou de clonar o repositório e ainda não rodou o
pipeline.
"""

from __future__ import annotations

import functools
import html
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
    """O nome do quadrante com a cor que ele tem nos gráficos.

    O nome é escapado antes de virar HTML. Hoje ele só pode ser um dos quatro
    literais de `regime.QUADRANTES`, então não há nada a explorar — mas essa
    garantia mora no classificador, e quem escreve HTML aqui não tem como
    verificá-la. "O dado por acaso é restrito" não é uma defesa; é uma
    coincidência que dura até alguém passar outra coisa para esta função.

    A cor vem de `PALETA.get`, que devolve um literal nosso ou o padrão: ela
    nunca carrega texto de fora, e por isso não precisa do mesmo cuidado.
    """
    if not quadrante:
        return "—"
    cor = PALETA.get(quadrante, "#6b7280")
    return (
        f'<span style="background:{cor};color:#fff;padding:2px 10px;'
        f'border-radius:999px;font-weight:600;white-space:nowrap">'
        f'{html.escape(quadrante)}</span>'
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
            # A data vem de dentro do arquivo, não do sistema de arquivos.
            # Num servidor, a data do arquivo é a hora em que o repositório foi
            # clonado — dizer "atualizado há uma hora" com base nela seria
            # anunciar frescor de dado quando o que é fresco é a implantação.
            calculo = dados.gerado_em("derivado")
            if calculo:
                st.caption(
                    f"Camada derivada calculada em {formato.dia(calculo)}. "
                    f"{len(proc)} artefatos versionados."
                )
            else:
                st.caption(f"{len(proc)} artefatos versionados.")
        else:
            st.warning(f"{len(faltando)} artefato(s) ausente(s).")

        st.caption(
            "Este painel **não** chama nenhuma API: tudo o que ele mostra vem de "
            "arquivo versionado no repositório. Há teste travando essa regra."
        )
