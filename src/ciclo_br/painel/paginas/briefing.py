"""Página do briefing: o texto publicado, e a reconstrução para demonstração.

Duas abas, e a diferença entre elas é a coisa mais importante desta página.

**Publicados** são os briefings que existiram: gravados pelo pipeline na data em
que os fatos mudaram, versionados com o JSON que os originou, e conferidos pela
CI. **Reconstrução** é um texto montado agora sobre uma data passada — útil para
demonstrar o sistema sem esperar uma divulgação, e rotulado como tal em toda
parte, porque um briefing reconstruído que se pareça com um publicado seria a
pior coisa que este projeto poderia colocar na tela.

A reconstrução usa **só o gerador determinístico**. Não é limitação contornável:
o painel não fala com a rede, e é essa regra que garante que o que está aqui saiu
de arquivo.
"""

from __future__ import annotations

import datetime as dt

import pandas as pd
import streamlit as st

from ... import artefatos as dados
from ... import formato
from ...briefing import fatos as fatos_mod
from ...briefing import modelo, publicacao
from .. import componentes


@componentes.protegido
def renderizar() -> None:
    componentes.titulo(
        "Briefing",
        "Escrito por divulgação, não por dia — e só quando os fatos mudam.",
    )

    publicados, reconstrucao = st.tabs(["Publicados", "Reconstrução"])
    with publicados:
        _publicados()
    with reconstrucao:
        _reconstrucao()


def _publicados() -> None:
    registros = [r for r in publicacao.publicados() if not r.get("replay")]
    if not registros:
        st.info(
            "Nenhum briefing publicado ainda. O comando `ciclo-briefing` grava um "
            "quando os fatos mudam — e fica calado quando não mudam.",
            icon="📭",
        )
        return

    rotulos = {
        f"{formato.dia(dt.date.fromisoformat(r['data']))}"
        f"{'  ·  ' + _resumo_divulgacoes(r) if _resumo_divulgacoes(r) else ''}": r
        for r in registros
    }
    escolha = st.selectbox("Briefing", list(rotulos))
    registro = rotulos[escolha]

    st.markdown(publicacao.renderizar(registro))

    st.divider()
    _quem_escreveu(registros)


def _resumo_divulgacoes(registro: dict) -> str:
    pares = [d["par"] for d in registro.get("fatos", {}).get("divulgacoes_do_dia", [])]
    return ", ".join(pares)


def _quem_escreveu(registros: list[dict]) -> None:
    st.subheader("Quem escreveu cada briefing")
    st.dataframe(
        pd.DataFrame([
            {
                "Data": formato.dia(dt.date.fromisoformat(r["data"])),
                "Gerador": publicacao.GERADORES.get(r["gerador"], r["gerador"]),
                "Modelo": r.get("modelo") or "—",
                "Motivo": r.get("motivo") or "—",
                "Divulgações": _resumo_divulgacoes(r) or "—",
            }
            for r in registros
        ]),
        hide_index=True, width="stretch",
        column_config={"Motivo": st.column_config.TextColumn(width="large")},
    )
    st.caption(
        "O rodapé de cada briefing diz quem o escreveu, e esta tabela junta a "
        "série inteira. Quando o texto do modelo de linguagem é recusado pela "
        "verificação, o motivo da recusa fica registrado aqui — um briefing "
        "escrito por template com o motivo à vista é mais confiável que um que "
        "sempre parece ter saído de uma IA."
    )


def _reconstrucao() -> None:
    st.warning(
        "**Isto não é um briefing publicado.** É um texto montado agora sobre uma "
        "data passada, para demonstrar o sistema sem esperar uma divulgação. As "
        "surpresas são genuinamente point-in-time — o consenso é o que o Focus "
        "apurava na véspera, e a data de divulgação veio do calendário do IBGE. O "
        "estado de regime **não** é: foi calculado com a série como ela está hoje.",
        icon="🎬",
    )

    datas = _datas_com_divulgacao()
    if not datas:
        st.info("Nenhuma divulgação medida ainda.")
        return

    escolha = st.selectbox(
        "Data da divulgação", datas, index=len(datas) - 1,
        format_func=lambda d: formato.dia(d),
    )

    fatos = fatos_mod.construir(ate=escolha)
    texto = modelo.escrever(fatos, {"primeiro": True, "houve": True,
                                    "divulgacoes": []})
    registro = publicacao.montar(
        fatos, {"primeiro": True, "houve": True, "divulgacoes": []}, texto,
        gerador="modelo",
        motivo="reconstrução no painel, que não chama modelo de linguagem")

    st.markdown(publicacao.renderizar(registro))

    with st.expander("Os fatos que geraram este texto"):
        st.caption(
            "É exatamente este JSON que o modelo de linguagem receberia, e nada "
            "além dele. A lista `numeros_permitidos` é a régua: todo número do "
            "texto precisa estar nela, e um texto que escreva outro é descartado "
            "inteiro."
        )
        st.json(fatos, expanded=False)


def _datas_com_divulgacao() -> list[dt.date]:
    """As datas em que algo foi medido — as únicas que fazem sentido reconstruir."""
    surpresas = dados.surpresas()
    if surpresas.empty:
        return []
    return sorted({d.date() for d in surpresas["data_divulgacao"]})
