"""Montagem do painel: sete páginas, nenhuma delas opcional.

A página de **Metodologia** é a razão de o resto existir. Um painel macro que
mostra um classificador sem mostrar contra o que ele foi validado, com que atraso
ele responde e o que ele não consegue afirmar está vendendo confiança que não
construiu.
"""

from __future__ import annotations

import streamlit as st

from . import componentes
from .paginas import (
    briefing,
    investimento,
    metodologia,
    regime,
    series,
    surpresas,
    validacao,
)

PAGINAS = (
    (regime.renderizar, "Regime", "🧭", "regime"),
    (briefing.renderizar, "Briefing", "📝", "briefing"),
    (series.renderizar, "Séries", "📈", "series"),
    (investimento.renderizar, "Investimento", "🏗️", "investimento"),
    (surpresas.renderizar, "Surpresas", "⚡", "surpresas"),
    (validacao.renderizar, "Validação", "🎯", "validacao"),
    (metodologia.renderizar, "Metodologia", "📐", "metodologia"),
)


def main() -> None:
    st.set_page_config(
        page_title="ciclo-br",
        page_icon="🧭",
        layout="wide",
        initial_sidebar_state="expanded",
    )

    navegacao = st.navigation([
        st.Page(funcao, title=titulo, icon=icone, url_path=caminho,
                default=indice == 0)
        for indice, (funcao, titulo, icone, caminho) in enumerate(PAGINAS)
    ])
    # Antes da barra lateral e da página: as duas desenham com estas regras.
    componentes.estilo()
    componentes.marca()
    componentes.barra_lateral()
    navegacao.run()


if __name__ == "__main__":
    main()
