import datetime as dt

import numpy as np
import pandas as pd
import pytest

from ciclo_br import storage, transformacao


@pytest.fixture(autouse=True)
def dados_temporarios(tmp_path, monkeypatch):
    monkeypatch.setattr(storage, "DIR_BRUTO", tmp_path / "raw")
    monkeypatch.setattr(storage, "CAMINHO_EXECUCOES", tmp_path / "_execucoes.parquet")
    monkeypatch.setattr(transformacao, "DIR_DERIVADO", tmp_path / "derivado")
    monkeypatch.setattr(transformacao, "CAMINHO_DERIVADO",
                        tmp_path / "derivado" / "series.parquet")
    return tmp_path


def serie_sazonal(n=120, inicio="2010-01-01", amplitude=1.0, tendencia=0.0):
    idx = pd.date_range(inicio, periods=n, freq="MS")
    mes = np.arange(n) % 12
    return pd.Series(
        10 + tendencia * np.arange(n) + amplitude * np.sin(2 * np.pi * mes / 12),
        index=idx,
    )


# --------------------------------------------------------------- look-ahead

def test_ajuste_recursivo_nao_usa_o_futuro():
    """O teste que sustenta a promessa metodológica do projeto.

    O valor dessazonalizado de um mês tem que ser idêntico quer a série termine
    ali, quer ela continue por mais dois anos. Se mudar, o passado está sendo
    reescrito com informação que não existia — e o backtest vira ficção.
    """
    completa = serie_sazonal(120)
    curta = completa.iloc[:96]

    sa_completa = transformacao.dessazonalizar_recursivo(completa)
    sa_curta = transformacao.dessazonalizar_recursivo(curta)

    comum = sa_curta.dropna().index
    pd.testing.assert_series_equal(
        sa_completa.loc[comum], sa_curta.loc[comum], check_names=False
    )


def test_ajuste_recursivo_deixa_nan_enquanto_falta_historia():
    serie = serie_sazonal(60)
    sa = transformacao.dessazonalizar_recursivo(serie)
    assert sa.iloc[: transformacao.MINIMO_OBSERVACOES - 1].isna().all()
    assert sa.iloc[transformacao.MINIMO_OBSERVACOES - 1 :].notna().all()


def test_ajuste_remove_a_sazonalidade():
    """Série puramente sazonal em torno de um nível fixo deve ficar plana."""
    serie = serie_sazonal(120, amplitude=3.0)
    sa = transformacao.dessazonalizar_recursivo(serie).dropna()
    assert sa.std() < serie.std() / 3


def test_serie_curta_demais_devolve_tudo_nan():
    sa = transformacao.dessazonalizar_recursivo(serie_sazonal(12))
    assert sa.isna().all()


# ----------------------------------------------------------------- momentum

def test_momentum_de_nivel_crescendo_1_por_cento_ao_mes():
    """1% ao mês composto por 12 meses = 12,68% ao ano."""
    idx = pd.date_range("2020-01-01", periods=24, freq="MS")
    nivel = pd.Series(100 * 1.01 ** np.arange(24), index=idx)
    resultado = transformacao.momentum_3m3m(nivel).dropna()
    assert resultado.round(2).eq(12.68).all()


def test_momentum_de_nivel_constante_e_zero():
    idx = pd.date_range("2020-01-01", periods=24, freq="MS")
    resultado = transformacao.momentum_3m3m(pd.Series(100.0, index=idx)).dropna()
    assert np.allclose(resultado, 0.0)


def test_momentum_precisa_de_seis_meses():
    idx = pd.date_range("2020-01-01", periods=8, freq="MS")
    resultado = transformacao.momentum_3m3m(pd.Series(100.0, index=idx))
    assert resultado.iloc[:5].isna().all()
    assert resultado.iloc[5:].notna().all()


# --------------------------------------------------------- taxa anualizada

def test_taxa_mensal_de_1_por_cento_anualiza_para_12_68():
    idx = pd.date_range("2020-01-01", periods=12, freq="MS")
    taxa = pd.Series(1.0, index=idx)
    resultado = transformacao.taxa_mm3m_anualizada(taxa).dropna()
    assert resultado.round(2).eq(12.68).all()


def test_composicao_nao_e_media_aritmetica():
    """1% ao mês por 3 meses não é 3% no trimestre — para inflação isso importa."""
    idx = pd.date_range("2020-01-01", periods=6, freq="MS")
    resultado = transformacao.taxa_mm3m_anualizada(pd.Series(1.0, index=idx)).dropna()
    assert float(resultado.iloc[0]) > 12.0  # 12% seria a aproximação linear


def test_taxa_zero_anualiza_para_zero():
    idx = pd.date_range("2020-01-01", periods=6, freq="MS")
    resultado = transformacao.taxa_mm3m_anualizada(pd.Series(0.0, index=idx)).dropna()
    assert np.allclose(resultado, 0.0)


# ------------------------------------------------------------- camada toda

def _gravar(serie_id, serie):
    storage.anexar(serie_id, pd.DataFrame({
        "data_referencia": [d.date() for d in serie.index],
        "valor": serie.to_numpy(dtype="float64"),
    }), execucao_id="e1")


def test_construir_produz_as_receitas_declaradas():
    _gravar("ibcbr_sa", serie_sazonal(120, tendencia=0.1))
    _gravar("ipca_nucleo_ma_suav", serie_sazonal(120, amplitude=0.2) / 20)
    _gravar("desocupacao", serie_sazonal(120, amplitude=0.5))
    _gravar("pim_sa", serie_sazonal(120, tendencia=0.1))

    derivado = transformacao.construir()
    produzidas = set(derivado["serie_id"])

    assert "eixo_crescimento" in produzidas
    assert "eixo_inflacao" in produzidas
    assert produzidas <= set(transformacao.RECEITAS)


def test_serie_ausente_nao_derruba_a_camada(caplog):
    """Falta de uma série de contexto não pode impedir o cálculo dos eixos."""
    _gravar("ibcbr_sa", serie_sazonal(120, tendencia=0.1))
    _gravar("ipca_nucleo_ma_suav", serie_sazonal(120, amplitude=0.2) / 20)

    derivado = transformacao.construir()
    assert "eixo_crescimento" in set(derivado["serie_id"])
    assert "desocupacao_sa" not in set(derivado["serie_id"])


def test_salvar_e_idempotente():
    _gravar("ibcbr_sa", serie_sazonal(120, tendencia=0.1))
    derivado = transformacao.construir()
    assert transformacao.salvar(derivado) is True
    assert transformacao.salvar(transformacao.construir()) is False


def test_carregar_sem_arquivo_devolve_colunas_esperadas():
    vazio = transformacao.carregar()
    assert vazio.empty
    assert list(vazio.columns) == ["serie_id", "data_referencia", "valor", "calculado_em"]


def test_toda_receita_declara_origem_e_unidade():
    for nome, receita in transformacao.RECEITAS.items():
        assert receita["origem"], nome
        assert receita["unidade"], nome
        assert receita["descricao"], nome


def test_data_referencia_e_date_e_nao_timestamp():
    _gravar("ibcbr_sa", serie_sazonal(120, tendencia=0.1))
    derivado = transformacao.construir()
    assert isinstance(derivado.loc[0, "data_referencia"], dt.date)
