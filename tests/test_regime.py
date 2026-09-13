import datetime as dt

import numpy as np
import pandas as pd
import pytest

from ciclo_br import regime, transformacao


@pytest.fixture(autouse=True)
def dados_temporarios(tmp_path, monkeypatch):
    monkeypatch.setattr(regime, "CAMINHO_REGIME", tmp_path / "regime.parquet")
    monkeypatch.setattr(transformacao, "CAMINHO_DERIVADO", tmp_path / "series.parquet")
    monkeypatch.setattr(transformacao, "DIR_DERIVADO", tmp_path)
    return tmp_path


def idx(n, inicio="2010-01-01"):
    return pd.date_range(inicio, periods=n, freq="MS")


# ------------------------------------------------------------------- cortes

def test_corte_expansivo_nao_usa_o_futuro():
    """Mesma disciplina do ajuste sazonal: o corte de um mês só conhece o passado.

    Sem isso, escolher a mediana como referência reintroduziria o look-ahead que
    a camada de transformação existe para eliminar.
    """
    completa = pd.Series(np.arange(120, dtype="float64"), index=idx(120))
    curta = completa.iloc[:80]

    corte_completo = regime.corte_expansivo(completa, minimo=60)
    corte_curto = regime.corte_expansivo(curta, minimo=60)

    comum = corte_curto.dropna().index
    pd.testing.assert_series_equal(
        corte_completo.loc[comum], corte_curto.loc[comum], check_names=False
    )


def test_corte_e_nan_enquanto_falta_historia():
    serie = pd.Series(np.arange(80, dtype="float64"), index=idx(80))
    corte = regime.corte_expansivo(serie, minimo=60)
    assert corte.iloc[:59].isna().all()
    assert corte.iloc[59:].notna().all()


# -------------------------------------------------------------- quadrantes

@pytest.mark.parametrize(
    ("g", "i", "esperado"),
    [
        (5.0, 9.0, "Aquecimento"),
        (5.0, 1.0, "Expansão"),
        (-1.0, 9.0, "Estagflação"),
        (-1.0, 1.0, "Desaceleração"),
    ],
)
def test_mapa_de_quadrantes(g, i, esperado):
    serie_g = pd.Series([g], index=idx(1))
    serie_i = pd.Series([i], index=idx(1))
    corte = pd.Series([2.0], index=idx(1))
    resultado = regime.classificar_bruto(serie_g, serie_i, corte, corte)
    assert resultado.iloc[0] == esperado


def test_sem_corte_nao_ha_classificacao():
    serie = pd.Series([5.0], index=idx(1))
    vazio = pd.Series([np.nan], index=idx(1))
    assert regime.classificar_bruto(serie, serie, vazio, vazio).iloc[0] is None


# ------------------------------------------------------------ persistência

def sinal(sequencia):
    return pd.Series(sequencia, index=idx(len(sequencia)))


def test_troca_so_confirma_apos_a_persistencia():
    g = sinal([True] * 4 + [False] * 4)
    i = sinal([False] * 8)
    resultado = regime.aplicar_persistencia(g, i, meses=3)

    # Os dois primeiros meses do novo sinal ainda não valem.
    assert list(resultado["quadrante"])[:6] == ["Expansão"] * 6
    assert list(resultado["quadrante"])[6:] == ["Desaceleração"] * 2


def test_oscilacao_curta_nao_troca_o_regime():
    """O caso que motivou a regra: um terço dos episódios durava 2 meses ou menos."""
    g = sinal([True] * 4 + [False] * 2 + [True] * 4)
    i = sinal([False] * 10)
    resultado = regime.aplicar_persistencia(g, i, meses=3)
    assert set(resultado["quadrante"]) == {"Expansão"}


def test_estado_pendente_fica_visivel():
    """O painel mostra 'mudou mas não confirmou' em vez de esconder."""
    g = sinal([True] * 3 + [False] * 2)
    i = sinal([False] * 5)
    resultado = regime.aplicar_persistencia(g, i, meses=3)
    assert list(resultado["pendente"])[-2:] == ["Desaceleração", "Desaceleração"]
    assert list(resultado["meses_pendente"])[-2:] == [1, 2]


def test_ruido_no_outro_eixo_nao_trava_a_virada():
    """Regressão da versão que contava meses do quadrante inteiro.

    O crescimento vira e fica firme, mas a inflação oscila todo mês. Com a
    contagem sobre o rótulo de quatro estados, o candidato mudava de nome a cada
    mês ("Expansão", "Aquecimento", "Expansão"...), o contador zerava e a virada
    do crescimento nunca confirmava — na série real isso produziu um episódio de
    contração de 116 meses. Com a contagem por eixo, o crescimento confirma no
    terceiro mês, independentemente do que a inflação faça.
    """
    g = sinal([False] * 3 + [True] * 6)
    i = sinal([True, False] * 4 + [True])
    resultado = regime.aplicar_persistencia(g, i, meses=3)

    vigentes = list(resultado["quadrante"])
    assert all(q in ("Desaceleração", "Estagflação") for q in vigentes[:5])
    assert all(q in ("Expansão", "Aquecimento") for q in vigentes[5:])


def test_primeiro_quadrante_vale_de_imediato():
    resultado = regime.aplicar_persistencia(sinal([True]), sinal([False]), meses=3)
    assert resultado["quadrante"].iloc[0] == "Expansão"


def test_persistencia_reduz_o_numero_de_trocas():
    g = sinal([True, False] * 20)
    i = sinal([False] * 40)
    com = regime.aplicar_persistencia(g, i, meses=3)["quadrante"]
    trocas_com = int((com != com.shift()).sum() - 1)
    assert trocas_com == 0


def test_sinais_leem_o_corte_escolhido():
    """O corte alternativo existe para a validação medir, e precisa ser de fato outro."""
    reg = pd.DataFrame({
        "data_referencia": [d.date() for d in idx(3)],
        "eixo_crescimento": [1.0, 1.0, 1.0],
        "eixo_inflacao": [0.0, 0.0, 0.0],
        "corte_crescimento": [2.0, 2.0, 2.0],
        "corte_inflacao": [1.0, 1.0, 1.0],
    })
    assert not regime.sinais(reg, corte_crescimento="mediana")[0].any()
    assert regime.sinais(reg, corte_crescimento="zero")[0].all()
    with pytest.raises(ValueError):
        regime.sinais(reg, corte_crescimento="meta")


# ------------------------------------------------------------- camada toda

def _derivado(n=140):
    datas = idx(n)
    rng = np.random.default_rng(42)
    crescimento = pd.Series(np.linspace(-5, 8, n) + rng.normal(0, 0.3, n), index=datas)
    inflacao = pd.Series(np.linspace(8, 3, n) + rng.normal(0, 0.3, n), index=datas)
    partes = [
        pd.DataFrame({"serie_id": "eixo_crescimento",
                      "data_referencia": [d.date() for d in datas],
                      "valor": crescimento.to_numpy()}),
        pd.DataFrame({"serie_id": "eixo_inflacao",
                      "data_referencia": [d.date() for d in datas],
                      "valor": inflacao.to_numpy()}),
    ]
    d = pd.concat(partes, ignore_index=True)
    d["calculado_em"] = dt.datetime.now(dt.UTC)
    transformacao.salvar(d)


def test_construir_produz_as_colunas_que_o_painel_consome():
    _derivado()
    r = regime.construir()
    for coluna in ("data_referencia", "eixo_crescimento", "corte_crescimento",
                   "quadrante_bruto", "quadrante", "pendente", "meses_pendente"):
        assert coluna in r.columns


def test_construir_sem_camada_derivada_devolve_vazio():
    assert regime.construir().empty


def test_resumo_traz_o_vigente_e_a_contagem_de_trocas():
    _derivado()
    info = regime.resumo(regime.construir())
    assert info["quadrante"] in regime.QUADRANTES.values()
    assert info["trocas_com_persistencia"] <= info["trocas_sem_persistencia"]
    assert info["meses_no_quadrante"] >= 1


def test_salvar_e_idempotente():
    _derivado()
    r = regime.construir()
    assert regime.salvar(r) is True
    assert regime.salvar(regime.construir()) is False


def test_equivalente_tolera_ruido_mas_nao_mudanca_de_rotulo():
    _derivado()
    r = regime.construir()

    ruido = r.copy()
    ruido["eixo_crescimento"] = ruido["eixo_crescimento"] + 1e-9
    assert regime.equivalente(r, ruido)

    rotulo = r.copy()
    rotulo.loc[rotulo.index[-1], "quadrante"] = "Aquecimento" \
        if rotulo["quadrante"].iloc[-1] != "Aquecimento" else "Expansão"
    assert not regime.equivalente(r, rotulo)


def test_main_reprova_quando_o_arquivo_esta_desatualizado():
    _derivado()
    regime.salvar(regime.construir())
    assert regime.main(["--verificar"]) == 0

    desatualizado = regime.carregar()
    desatualizado.loc[desatualizado.index[-1], "quadrante"] = "Aquecimento"
    desatualizado.to_parquet(regime.CAMINHO_REGIME, index=False)
    assert regime.main(["--verificar"]) == 1
