"""Testes do painel.

Dois deles não são sobre aparência e sim sobre a promessa da camada:

- `test_o_painel_nao_alcanca_a_rede` trava, por leitura do código-fonte, que
  nenhum módulo do painel importe a ingestão ou um cliente HTTP. A regra "o app
  só lê arquivo" é o que permite o modo replay e o que garante que a tela nunca
  discorde do pipeline; sem teste, ela duraria até o primeiro atalho.
- `test_pagina_sem_artefato_ensina_o_comando` garante que a ausência de um
  arquivo vire instrução, e não traceback.

O resto renderiza cada página de verdade, com os dados versionados do
repositório, e reprova se alguma levantar exceção.
"""

from __future__ import annotations

import ast
import datetime as dt
from pathlib import Path

import pandas as pd
import pytest
from streamlit.testing.v1 import AppTest

from ciclo_br import artefatos as dados
from ciclo_br import formato
from ciclo_br.painel import graficos

PAGINAS = ("regime", "briefing", "series", "surpresas", "validacao",
           "metodologia")

DIR_PAINEL = Path(graficos.__file__).parent

# Portas para o mundo externo. `requests` é o cliente HTTP do projeto;
# `ciclo_br.ingestion` é o pacote que fala com o BCB e com o IBGE.
PROIBIDOS = ("requests", "urllib", "http", "socket")
PROIBIDO_INTERNO = "ingestion"


def _modulos_do_painel() -> list[Path]:
    """Os módulos do painel **e** a camada de leitura que ele consome.

    `artefatos.py` entra na varredura porque é por onde um import de rede
    chegaria sem passar pelo pacote do painel.
    """
    return sorted(DIR_PAINEL.rglob("*.py")) + [Path(dados.__file__)]


def test_o_painel_nao_carrega_o_cliente_do_modelo_de_linguagem():
    """A página de Briefing usa o gerador determinístico, e só ele.

    `ciclo_br.briefing.llm` é o único módulo do projeto que fala com um modelo; o
    painel monta a reconstrução sem ele, e é isso que mantém a promessa de que a
    tela sai de arquivo.
    """
    import sys

    for modulo in ("ciclo_br.briefing.llm", "anthropic"):
        sys.modules.pop(modulo, None)

    import ciclo_br.painel.app  # noqa: F401

    assert "ciclo_br.briefing.llm" not in sys.modules
    assert "anthropic" not in sys.modules


# ------------------------------------------------------- a promessa da camada

def test_o_painel_nao_alcanca_a_rede():
    """Nenhum módulo do painel importa cliente HTTP nem a camada de ingestão."""
    assert _modulos_do_painel(), "não achei os módulos do painel"

    for caminho in _modulos_do_painel():
        arvore = ast.parse(caminho.read_text(encoding="utf-8"))
        for no in ast.walk(arvore):
            if isinstance(no, ast.Import):
                nomes = [alias.name for alias in no.names]
            elif isinstance(no, ast.ImportFrom):
                nomes = [no.module or ""]
            else:
                continue
            for nome in nomes:
                raiz = nome.split(".")[0]
                assert raiz not in PROIBIDOS, f"{caminho.name} importa {nome}"
                assert PROIBIDO_INTERNO not in nome, f"{caminho.name} importa {nome}"


def test_importar_o_painel_nao_carrega_a_ingestao():
    """A garantia em tempo de execução, complementar à leitura do código.

    A leitura do código pega o import direto; esta pega o indireto — um módulo do
    painel que importasse `ciclo_br.surpresa`, por exemplo, arrastaria a ingestão
    junto sem nunca escrever a palavra.
    """
    import sys

    guardados = {m: sys.modules[m] for m in list(sys.modules)
                 if m.startswith("ciclo_br.ingestion")}
    for modulo in guardados:
        del sys.modules[modulo]
    try:
        import ciclo_br.painel.app  # noqa: F401

        assert not any(m.startswith("ciclo_br.ingestion") for m in sys.modules)
    finally:
        # Os módulos de ingestão voltam como os mesmos objetos: outros testes já
        # guardaram referência a eles, e reimportar criaria um segundo módulo com
        # estado próprio.
        sys.modules.update(guardados)


# --------------------------------------------------------------- renderização

def _rodar_pagina(nome: str, timeout: int = 90) -> AppTest:
    """Roda a página como script, que é como o Streamlit a executa de verdade."""
    roteiro = "\n".join([
        f"from ciclo_br.painel.paginas import {nome}",
        f"{nome}.renderizar()",
    ])
    return AppTest.from_string(roteiro).run(timeout=timeout)


@pytest.mark.parametrize("nome", PAGINAS)
def test_cada_pagina_renderiza(nome):
    app = _rodar_pagina(nome)
    assert not app.exception, f"{nome}: {[e.message for e in app.exception]}"


def test_o_app_inteiro_sobe():
    app = AppTest.from_file(str(Path(dados.__file__).parents[2] / "app.py"))
    app.run(timeout=90)
    assert not app.exception, [e.message for e in app.exception]


def test_pagina_sem_artefato_ensina_o_comando(monkeypatch, tmp_path):
    """Falta de arquivo vira instrução, não traceback."""
    ausente = dados.Artefato(
        "Regime", tmp_path / "nao_existe.parquet", "ciclo-regime", "o quadrante")
    monkeypatch.setitem(dados.ARTEFATOS, "regime", ausente)

    app = _rodar_pagina("regime")
    assert not app.exception
    assert any("ciclo-regime" in bloco.value for bloco in app.code)


# ---------------------------------------------------------------------- dados

def test_artefato_ausente_carrega_o_comando_que_o_gera(monkeypatch, tmp_path):
    monkeypatch.setitem(
        dados.ARTEFATOS, "surpresa",
        dados.Artefato("Surpresas", tmp_path / "x.csv", "ciclo-surpresa", "…"))
    with pytest.raises(dados.ArtefatoAusente) as erro:
        dados.surpresas()
    assert "ciclo-surpresa" in str(erro.value)


def test_episodios_agrupam_meses_iguais():
    reg = pd.DataFrame({
        "data": pd.to_datetime(["2020-01-01", "2020-02-01", "2020-03-01",
                                "2020-04-01"]),
        "quadrante": ["Expansão", "Expansão", "Estagflação", "Estagflação"],
    })
    blocos = dados.episodios(reg)
    assert list(blocos["quadrante"]) == ["Expansão", "Estagflação"]
    assert list(blocos["meses"]) == [2, 2]
    # O retângulo do gráfico cobre o último mês inteiro; a tabela mostra o nome
    # desse mês.
    assert blocos["ultimo"].iloc[0] == pd.Timestamp("2020-02-01")
    assert blocos["fim"].iloc[0] == pd.Timestamp("2020-03-01")


def test_episodios_ignoram_meses_sem_classificacao():
    reg = pd.DataFrame({
        "data": pd.to_datetime(["2020-01-01", "2020-02-01"]),
        "quadrante": [None, "Expansão"],
    })
    assert list(dados.episodios(reg)["quadrante"]) == ["Expansão"]


def test_regime_mensal_mede_distancia_ate_o_corte():
    """É o que torna a fronteira do quadrante o zero em todos os meses."""
    reg = dados.regime_mensal()
    linha = reg[reg["quadrante"].notna()].iloc[-1]
    assert linha["distancia_crescimento"] == pytest.approx(
        linha["eixo_crescimento"] - linha["corte_crescimento"])
    assert linha["distancia_inflacao"] == pytest.approx(
        linha["eixo_inflacao"] - linha["corte_inflacao"])


def test_configuracao_vigente_e_a_do_classificador():
    """O painel não pode mostrar a defasagem de uma configuração que não usa."""
    from ciclo_br import regime as regime_mod

    config = dados.configuracao_vigente()
    assert config["corte_crescimento"] == regime_mod.CORTE_CRESCIMENTO
    assert config["persistencia"] == regime_mod.MESES_PERSISTENCIA


def test_resumo_do_painel_e_o_mesmo_do_comando():
    from ciclo_br import regime as regime_mod

    assert dados.resumo_regime() == regime_mod.resumo(regime_mod.carregar())


def test_surpresas_por_par_traz_a_ultima_divulgacao():
    tabela = pd.DataFrame({
        "par": ["ipca", "ipca"],
        "data_referencia": pd.to_datetime(["2025-01-01", "2025-02-01"]),
        "data_divulgacao": pd.to_datetime(["2025-02-11", "2025-03-12"]),
        "realizado": [0.5, 0.8],
        "consenso": [0.4, 0.6],
        "surpresa": [0.1, 0.2],
        "unidade": ["p.p.", "p.p."],
        "dias_sem_mudanca": [3, 5],
        "primeira_leitura": [False, True],
    })
    info = dados.surpresas_por_par(tabela).iloc[0]
    assert info["observacoes"] == 2
    assert info["surpresa"] == pytest.approx(0.2)
    assert info["primeiras_leituras"] == 1
    assert info["media"] == pytest.approx(0.15)


def test_a_data_de_geracao_vem_de_dentro_do_arquivo():
    """Num servidor, a data do arquivo é a hora do clone, não a do cálculo.

    Mostrar a data do sistema de arquivos como "atualizado há uma hora" faria o
    painel anunciar dado fresco quando o que é fresco é a implantação. Os
    artefatos que carregam a própria data de geração são lidos por dentro.
    """
    import pandas as pd_

    calculo = dados.gerado_em("regime")
    gravado = pd_.Timestamp(dados.regime()["calculado_em"].max()).to_pydatetime()
    assert calculo == gravado

    # Quem não carrega carimbo devolve None, e o painel mostra travessão.
    assert dados.gerado_em("cronologia") is None


def test_procedencia_separa_calculo_de_gravacao():
    proc = dados.procedencia()
    assert {"gerado_em", "modificado_em"} <= set(proc.columns)
    com_carimbo = proc[proc["gerado_em"].notna()]
    assert set(com_carimbo["chave"]) >= {"regime", "derivado"}


def test_procedencia_lista_todo_artefato_que_o_painel_le():
    proc = dados.procedencia()
    assert set(proc["chave"]) == set(dados.ARTEFATOS)
    assert proc["existe"].all(), "artefato versionado faltando no repositório"


# -------------------------------------------------------------------- formato

def test_formato_nunca_escreve_nan_na_tela():
    """NaN é verdadeiro num `if`, e já apareceu como 'pendente: nan' no log."""
    assert formato.numero(float("nan")) == "—"
    assert formato.numero(None) == "—"
    assert formato.mes_ano(None) == "—"
    assert formato.defasagem(float("nan")) == "—"


@pytest.mark.parametrize("vazio", [None, pd.NaT, float("nan")])
def test_formato_aguenta_as_tres_formas_de_data_ausente(vazio):
    """`NaT` tem `.day` e `.month`, e eles devolvem `nan`.

    Sem o tratamento, `f"{data.day:02d}"` estoura com "Unknown format code 'd'
    for object of type 'float'" em vez de cair no ramo de valor ausente — foi
    exatamente assim que a página de Metodologia quebrou ao ganhar uma coluna
    com artefatos sem carimbo de geração.
    """
    assert formato.dia(vazio) == "—"
    assert formato.mes_ano(vazio) == "—"
    assert formato.mes_curto(vazio) == "—"
    assert formato.idade(vazio) == "—"
    assert formato.meses(vazio) == "—"


def test_defasagem_diz_atraso_ou_antecipacao():
    """O sinal sozinho é ambíguo na tela para quem não leu a metodologia."""
    assert "atraso" in formato.defasagem(4)
    assert "antecipação" in formato.defasagem(-2)
    assert formato.defasagem(0) == "no mês"


def test_numero_usa_virgula_decimal():
    assert formato.numero(0.0083, 2, sinal=True) == "+0,01"


def test_meses_concorda_no_singular():
    assert formato.meses(1) == "1 mês"
    assert formato.meses(3) == "3 meses"


def test_idade_em_linguagem_de_painel():
    agora = dt.datetime(2026, 9, 12, 12, 0, tzinfo=dt.UTC)
    assert formato.idade(agora - dt.timedelta(minutes=10), agora=agora) == (
        "há menos de uma hora")
    assert formato.idade(agora - dt.timedelta(days=1), agora=agora) == "ontem"
    assert formato.idade(None) == "—"


# ------------------------------------------------------------------- gráficos

def test_o_empilhamento_nunca_remove_o_eixo_de_um_painel():
    """`axis=None` num `vconcat` de escala compartilhada quebra o Vega no navegador.

    Regressão observada de verdade: ao esconder as réguas de ano repetidas, os
    dois painéis de cima ficaram com `axis=None`, o Vega-Lite não resolveu a
    escala compartilhada e o gráfico inteiro sumiu — com erro só no console do
    JavaScript. Nenhum teste de Python pegava, porque do lado de cá a
    especificação era gerada sem exceção. O jeito certo é esconder rótulos e
    marcas, mantendo o objeto de eixo.
    """
    reg = dados.regime_mensal()
    especificacao = graficos.historia_do_regime(
        reg, dados.episodios(reg), dados.recessoes()).to_dict()

    paineis = especificacao["vconcat"]
    assert len(paineis) == 3
    for painel in paineis:
        camadas = painel.get("layer", [painel])
        for camada in camadas:
            x = camada.get("encoding", {}).get("x")
            if x is None:
                continue
            assert "axis" not in x or isinstance(x["axis"], dict), (
                "eixo removido em vez de escondido — o gráfico some no navegador")


def test_todo_quadrante_tem_cor():
    from ciclo_br.regime import QUADRANTES

    assert set(QUADRANTES.values()) == set(graficos.PALETA)
    assert set(graficos.ORDEM) == set(graficos.PALETA)
    assert set(graficos.PALETA_TEXTO) == set(graficos.PALETA)


def test_todo_quadrante_tem_explicacao_em_portugues_claro():
    """O nome sozinho não explica nada a quem não é da área.

    O título da página é uma dessas quatro palavras, então o leitor encontra o
    termo antes de ter chance de procurar o que ele significa. Um quadrante novo
    sem frase passaria despercebido até alguém de fora abrir o painel.
    """
    from ciclo_br.painel.paginas.regime import SENTIDO

    assert set(SENTIDO) == set(graficos.PALETA)
    for nome, frase in SENTIDO.items():
        assert len(frase.split()) >= 15, f"{nome}: frase curta demais para explicar"


def _quadrante_da_posicao(x: float, y: float) -> str:
    """O quadrante que a posição no plano implica, sem consultar o classificador."""
    if y > 0:
        return "Aquecimento" if x > 0 else "Estagflação"
    return "Expansão" if x > 0 else "Desaceleração"


def test_a_cor_do_ponto_nunca_contradiz_o_lado_da_fronteira():
    """O ponto é pintado pelo quadrante do mês, não pelo regime vigente.

    Os dois discordam enquanto a persistência não confirma uma virada, e pintar
    pelo vigente produzia ponto verde dentro da faixa amarela: a cor negando o
    eixo. O olho lê posição antes de cor, então quem cede é a cor.
    """
    reg = dados.regime_mensal()
    grafico = graficos.mapa_de_quadrantes(reg, meses=24)
    especificacao = grafico.to_dict()

    pintados = [
        camada for camada in especificacao["layer"]
        if camada.get("mark", {}).get("type") == "circle"
    ]
    assert len(pintados) == 1, "o mapa deveria ter uma única camada de pontos"
    assert pintados[0]["encoding"]["color"]["field"] == "quadrante_bruto"

    recorte = reg[reg["quadrante"].notna()].tail(24)
    for _, mes in recorte.iterrows():
        assert mes["quadrante_bruto"] == _quadrante_da_posicao(
            mes["distancia_crescimento"], mes["distancia_inflacao"]
        ), f"{mes['data_referencia']}: a cor cairia fora da faixa onde o ponto está"


def test_o_nome_do_quadrante_fica_dentro_do_proprio_quadrante():
    """O recuo é fração do lado, não do eixo inteiro.

    Com o recuo medido no eixo inteiro, "Aquecimento" ia parar a cinco pixels da
    linha do zero — nomeando a linha, não a região — porque a metade de cima do
    eixo de inflação é uma faixa fina. O caso extremo abaixo é justamente esse.
    """
    for limite_y in ([-12.0, 0.4], [-0.4, 12.0], [-5.0, 5.0]):
        cantos = graficos._cantos([-8.0, 3.0], limite_y)
        for _, nome in cantos.iterrows():
            assert _quadrante_da_posicao(nome["x"], nome["y"]) == nome["quadrante"], (
                f"{nome['quadrante']} desenhado fora do seu quadrante "
                f"com o eixo em {limite_y}"
            )
