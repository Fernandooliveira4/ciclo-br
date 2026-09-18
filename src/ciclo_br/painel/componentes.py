"""Peças de tela reaproveitadas pelas páginas.

O item menos decorativo daqui é `protegido`: quando um artefato falta, a página
mostra qual arquivo falta e qual comando o produz, em vez de um traceback. Um
painel que depende de arquivos versionados precisa saber dizer que um deles não
está lá — inclusive para quem acabou de clonar o repositório e ainda não rodou o
pipeline.

**Por que existem `numeros` e `figura` em vez de `st.metric` e `st.altair_chart`.**
A direção de desenho do painel é a de um documento de pesquisa, e as duas peças
padrão do Streamlit contradizem isso de formas específicas:

- `st.metric` embrulha cada número num cartão com bolinha de ajuda. A bolinha
  esconde a explicação atrás de um clique, e num relatório a nota de rodapé é
  visível — é ela que separa um número medido de um número afirmado. `numeros`
  põe a mesma informação na tela, separada por filete em vez de moldura.
- `st.altair_chart` desenha com o tema de fábrica do Streamlit. `figura` passa
  `theme=None` para que valha o tema do Altair definido em `tema.py`, e escreve
  a legenda numerada embaixo, de modo que o texto ao lado possa citar a figura
  pelo número em vez de dizer "o gráfico acima".

**O CSS daqui é o mínimo que a API de tema não alcança.** Quase toda a
aparência do painel entra por `.streamlit/config.toml`, que é contrato público
e sobrevive a atualização. O que sobrou aqui são três coisas que não têm chave
de tema: a medida do texto, os algarismos tabulares e o desenho da legenda de
figura. Os seletores usam `data-testid`, que o Streamlit mantém estável, e não
nome de classe gerado.
"""

from __future__ import annotations

import functools
import html
from collections.abc import Callable, Sequence

import streamlit as st

from .. import artefatos as dados
from .. import formato
from . import tema

_CHAVE_FIGURA = "_contador_de_figuras"

# A medida do texto, e por que ela não mora no contêiner.
#
# A primeira versão travava o contêiner inteiro em 1120px para segurar a linha
# de texto. O efeito colateral apareceu na captura do README: a tabela de
# defasagens tem nove colunas, precisa de 1145px, recebia 960px e perdia a
# última — "Cobertura da recessão", justamente a coluna que a legenda ao lado
# manda ler. Era regressão de verdade, não da captura: acontecia em qualquer
# navegador.
#
# A trava certa é a de baixo: o contêiner fica largo o bastante para tabela e
# figura, e quem se limita é o **texto corrente**. É o arranjo de documento —
# a prosa numa coluna estreita, a figura ocupando a página.
_ESTILO = f"""
<style>
/* As três famílias, carregadas aqui e não pelo `theme.font` do config.toml.
   Aquela chave promete aceitar "Nome:url" e lista separada por vírgula, mas a
   implementação divide no primeiro dois-pontos e trata o resto como URL — uma
   lista de duas fontes vira URL inválida e nenhuma família carrega. O config
   agora só nomeia as famílias; quem as traz é este `@import`, que precisa ser
   a primeira regra da folha de estilo. */
@import url("{tema.URL_FONTES}");

[data-testid="stMainBlockContainer"] {{
  max-width: 1320px;
  padding-top: 3.2rem;
  padding-bottom: 5rem;
}}

/* Só o texto fica na medida. Tabela, gráfico e legenda de figura ficam de
   fora da trava — cada um tem a largura de que precisa. */
[data-testid="stMainBlockContainer"] [data-testid="stMarkdownContainer"] > p,
[data-testid="stMainBlockContainer"] [data-testid="stMarkdownContainer"] > ul,
[data-testid="stMainBlockContainer"] [data-testid="stMarkdownContainer"] > ol,
[data-testid="stMainBlockContainer"] [data-testid="stMarkdownContainer"] > blockquote {{
  max-width: 80ch;
}}

/* Algarismo tabular em tudo que é número alinhado: sem isto a coluna de
   valores dança conforme o dígito, e uma tabela de defasagens fica torta. */
.ciclo-num, [data-testid="stMetricValue"], [data-testid="stDataFrame"] {{
  font-variant-numeric: tabular-nums;
}}

/* A linha de números: filete entre as colunas, nenhuma moldura em volta. */
.ciclo-numeros {{
  display: flex; flex-wrap: wrap; gap: 0;
  border-top: 1px solid {tema.REGUA};
  border-bottom: 1px solid {tema.REGUA};
  margin: 0.2rem 0 0.9rem 0;
}}
.ciclo-numeros > div {{
  flex: 1 1 165px; padding: 0.85rem 1.1rem 0.9rem 0;
  border-right: 1px solid {tema.REGUA};
}}
.ciclo-numeros > div:last-child {{ border-right: 0; }}
.ciclo-rot {{
  font-family: "{tema.FAMILIA_DADOS}", sans-serif;
  font-size: 0.76rem; font-weight: 500; color: {tema.TINTA_3};
  line-height: 1.3;
}}
.ciclo-val {{
  font-family: "{tema.FAMILIA_DADOS}", sans-serif;
  font-variant-numeric: tabular-nums;
  font-size: 1.62rem; font-weight: 600; color: {tema.TINTA};
  line-height: 1.15; margin-top: 0.28rem; letter-spacing: -0.015em;
}}
.ciclo-nota {{
  font-family: "{tema.FAMILIA_DADOS}", sans-serif;
  font-size: 0.74rem; color: {tema.TINTA_3};
  line-height: 1.35; margin-top: 0.22rem;
}}

/* Legenda de figura: itálico, medida curta, o número em romano de dados. */
.ciclo-legenda {{
  font-size: 0.84rem; font-style: italic; color: {tema.TINTA_2};
  line-height: 1.55; max-width: 74ch; margin: 0.45rem 0 0.2rem 0;
}}
.ciclo-legenda b {{
  font-family: "{tema.FAMILIA_DADOS}", sans-serif;
  font-style: normal; font-weight: 600; font-size: 0.76rem;
  color: {tema.TINTA_3}; letter-spacing: 0.01em;
}}

/* O estado vigente: o nome do quadrante tipografado, não uma pílula gigante.
   A pílula funciona em tamanho pequeno — na barra lateral, no glossário — onde
   ela precisa se destacar de um texto em volta. Em corpo 40 ela vira um bloco
   de cor atravessando a página, que é justamente a estética de produto que
   esta direção evita. Aqui a cor vai para a letra, e o filete faz a separação. */
.ciclo-estado {{
  font-size: 2.6rem; font-weight: 600; line-height: 1.05;
  letter-spacing: -0.02em; margin: 0.1rem 0 0.1rem 0;
}}
.ciclo-estado-regua {{
  border: 0; border-top: 2px solid {tema.TINTA};
  margin: 0.55rem 0 0.9rem 0; max-width: 100%;
}}

/* Filete de seção: separa sem a régua cheia do `st.divider`. */
.ciclo-secao {{
  border: 0; border-top: 1px solid {tema.REGUA_FORTE};
  margin: 2.4rem 0 1.4rem 0;
}}
</style>
"""


def estilo() -> None:
    """Injeta o pouco de CSS que a API de tema não cobre. Chamado uma vez."""
    st.markdown(_ESTILO, unsafe_allow_html=True)


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

    Usa o **tom forte** do quadrante, não o de preenchimento: aqui a cor vira
    fundo de texto branco, e o tom de preenchimento do verde e do âmbar dá
    3,2:1 contra o branco — abaixo do mínimo para texto pequeno. O tom forte é
    o mesmo matiz escurecido até passar; ver a derivação em `tema.py`.

    O nome é escapado antes de virar HTML. Hoje ele só pode ser um dos quatro
    literais de `regime.QUADRANTES`, então não há nada a explorar — mas essa
    garantia mora no classificador, e quem escreve HTML aqui não tem como
    verificá-la. "O dado por acaso é restrito" não é uma defesa; é uma
    coincidência que dura até alguém passar outra coisa para esta função.

    A cor vem de `get`, que devolve um literal nosso ou o padrão: ela nunca
    carrega texto de fora, e por isso não precisa do mesmo cuidado.
    """
    if not quadrante:
        return "—"
    cor = tema.PALETA_FORTE.get(quadrante, tema.TINTA_2)
    return (
        f'<span style="background:{cor};color:#fff;padding:2px 11px 3px;'
        f'font-weight:600;white-space:nowrap;letter-spacing:.01em">'
        f'{html.escape(quadrante)}</span>'
    )


def estado(quadrante: str | None) -> None:
    """O quadrante vigente, tipografado grande, na cor forte do próprio estado.

    Não é a `pilula`: em corpo 40 o fundo colorido vira um bloco atravessando a
    página, que é a estética de produto que esta direção evita. A cor vai para
    a letra — o tom forte passa em 4,5:1 contra o papel, e é para isso que ele
    existe — e a separação fica por conta do filete.
    """
    nome = quadrante or "—"
    cor = tema.PALETA_FORTE.get(nome, tema.TINTA)
    st.markdown(
        f'<div class="ciclo-estado" style="color:{cor}">{html.escape(nome)}</div>'
        f'<hr class="ciclo-estado-regua">',
        unsafe_allow_html=True,
    )


def titulo(texto: str, subtitulo: str | None = None) -> None:
    """O título da página, e o reinício da contagem de figuras.

    A contagem vive aqui porque toda página começa por este componente: é o
    único ponto do painel por onde todas passam, e uma contagem que não zera
    faz a segunda visita à mesma página abrir na Figura 7.
    """
    st.session_state[_CHAVE_FIGURA] = 0
    st.title(texto)
    if subtitulo:
        st.caption(subtitulo)


def secao(texto: str | None = None) -> None:
    """Um filete e, opcionalmente, um subtítulo — a divisão do documento.

    Sem texto quando a seção seguinte traz os próprios títulos, como a
    metodologia renderizada: um subtítulo nosso ali competiria com os dela.
    """
    st.markdown('<hr class="ciclo-secao">', unsafe_allow_html=True)
    if texto:
        st.subheader(texto)


def numeros(itens: Sequence[tuple[str, str, str | None]]) -> None:
    """Uma linha de números tipografados, separados por filete.

    Cada item é `(rótulo, valor, nota)`. A nota é a linha pequena embaixo — o
    corte, a comparação, a base de cálculo — e é o que `st.metric` esconderia
    atrás de uma bolinha de ajuda.
    """
    celulas = "".join(
        f'<div><div class="ciclo-rot">{html.escape(rotulo)}</div>'
        f'<div class="ciclo-val">{html.escape(valor)}</div>'
        + (f'<div class="ciclo-nota">{html.escape(nota)}</div>' if nota else "")
        + "</div>"
        for rotulo, valor, nota in itens
    )
    st.markdown(f'<div class="ciclo-numeros">{celulas}</div>', unsafe_allow_html=True)


def figura(grafico, legenda: str, *, numerar: bool = True) -> None:
    """Desenha um gráfico como figura de relatório, com legenda numerada embaixo.

    `theme=None` é o ponto: sem ele o Streamlit aplica o tema de fábrica do
    Vega e a figura sai com outra tipografia e outra grade que o resto da
    página — deixando de pertencer ao documento em que está.

    `numerar=False` para o gráfico que nenhum texto cita. Número de figura é um
    sistema de referência, não enfeite: numerar o que ninguém aponta só produz
    uma etiqueta a mais para o leitor ignorar.
    """
    st.altair_chart(grafico, width="stretch", theme=None)

    if numerar:
        n = st.session_state.get(_CHAVE_FIGURA, 0) + 1
        st.session_state[_CHAVE_FIGURA] = n
        marca = f"<b>Figura {n}</b> — "
    else:
        marca = ""
    st.markdown(
        f'<p class="ciclo-legenda">{marca}{legenda}</p>', unsafe_allow_html=True
    )


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
