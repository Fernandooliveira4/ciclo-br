"""Página de metodologia: o documento inteiro, e de onde veio cada arquivo.

Esta página **renderiza `docs/metodologia.md`**, não uma versão resumida dele.
Duas versões do mesmo argumento divergiriam na primeira mudança, e a que ficaria
desatualizada seria justamente a que o leitor vê. O documento é a fonte; o painel
é o leitor.

A tabela de procedência está aqui pelo mesmo motivo. Um projeto que afirma "o
repositório é o banco de dados" precisa mostrar, na tela, quais arquivos ele
abriu para desenhar o que está desenhado.
"""

from __future__ import annotations

import pandas as pd
import streamlit as st

from ... import artefatos as dados
from ... import formato
from .. import componentes


@componentes.protegido
def renderizar() -> None:
    componentes.titulo(
        "Metodologia",
        "O documento versionado em `docs/metodologia.md`, renderizado tal como "
        "está — inclusive as limitações.",
    )

    _procedencia()
    st.divider()
    _documento()


def _procedencia() -> None:
    st.subheader("De onde vem o que está na tela")
    proc = dados.procedencia()

    st.dataframe(
        pd.DataFrame({
            "Artefato": proc["artefato"],
            "Arquivo": proc["arquivo"],
            "O que guarda": proc["descricao"],
            "Gerado por": proc["gerado_por"],
            "Estado": ["versionado" if e else "ausente" for e in proc["existe"]],
            "Atualizado": [formato.idade(m) for m in proc["modificado_em"]],
            "KB": proc["kb"],
        }),
        hide_index=True, width="stretch",
        column_config={"O que guarda": st.column_config.TextColumn(width="large")},
    )

    st.info(
        "**O painel só lê arquivo.** Nenhuma página aqui importa a camada de "
        "ingestão nem chama API: tudo o que aparece na tela saiu de um dos "
        "arquivos acima, versionados no repositório. Há teste travando a regra de "
        "importação, e sete portões de CI conferindo que esses arquivos estão em "
        "dia com o dado bruto.",
        icon="📄",
    )

    st.caption(
        "Consequência disso, e é de propósito: voltar o repositório a um commit "
        "anterior faz o painel mostrar exatamente o que ele mostrava naquele dia, "
        "sem nenhum modo especial. O que o painel **não** tem é um seletor de "
        "\"como estava em março de 2015\" — reconstruir aquela tela com o dado "
        "revisado de hoje seria o mesmo viés de look-ahead que a camada derivada "
        "existe para evitar, e sairia mais bonito do que a verdade permite."
    )


def _documento() -> None:
    texto = dados.metodologia()
    # A primeira linha é o título H1 do documento, que repetiria o título da
    # página logo acima.
    corpo = texto.split("\n", 1)[1] if texto.startswith("# ") else texto
    st.markdown(corpo)
    st.caption(
        "Os links relativos acima apontam para arquivos do repositório e "
        "funcionam no GitHub, não aqui dentro."
    )
