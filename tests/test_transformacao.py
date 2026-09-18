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


def test_ruido_de_ponto_flutuante_nao_conta_como_alteracao():
    """O STL depende do BLAS, então Linux e Windows divergem nos últimos bits.

    Sem tolerância, a CI reprovaria a camada derivada só por ter sido calculada
    noutro sistema operacional — foi assim que este caso apareceu.
    """
    _gravar("ibcbr_sa", serie_sazonal(120, tendencia=0.1))
    derivado = transformacao.construir()

    outra_plataforma = derivado.copy()
    outra_plataforma["valor"] = outra_plataforma["valor"] + 1e-9

    assert transformacao.equivalente(derivado, outra_plataforma)


def test_diferenca_com_significado_conta_como_alteracao():
    _gravar("ibcbr_sa", serie_sazonal(120, tendencia=0.1))
    derivado = transformacao.construir()

    desatualizada = derivado.copy()
    desatualizada.loc[0, "valor"] = float(desatualizada.loc[0, "valor"]) + 0.01

    assert not transformacao.equivalente(derivado, desatualizada)


def test_tamanhos_diferentes_nao_sao_equivalentes():
    _gravar("ibcbr_sa", serie_sazonal(120, tendencia=0.1))
    derivado = transformacao.construir()
    assert not transformacao.equivalente(derivado, derivado.iloc[:-1])


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


# ------------------------------------------- variação interanual (PIB, S6)

def test_variacao_interanual_compara_periodos_homologos():
    """4% ao ano num índice trimestral tem de sair como 4%, não como 1%."""
    trimestres = pd.date_range("2020-01-01", periods=8, freq="QS")
    nivel = pd.Series([100.0] * 4 + [104.0] * 4, index=trimestres)
    yoy = transformacao.variacao_interanual(nivel, periodos_por_ano=4)
    assert yoy.iloc[:4].isna().all()
    assert yoy.iloc[4:].round(6).eq(4.0).all()


def test_variacao_interanual_ignora_sazonalidade():
    """É por isso que a ficha do PIB marca ajuste sazonal como não aplicável."""
    trimestres = pd.date_range("2020-01-01", periods=12, freq="QS")
    sazonal = [90.0, 100.0, 110.0, 120.0]
    nivel = pd.Series([v * (1.05**ano) for ano in range(3) for v in sazonal],
                      index=trimestres)
    yoy = transformacao.variacao_interanual(nivel, periodos_por_ano=4).dropna()
    assert yoy.round(6).eq(5.0).all()


def test_tolerancia_e_maior_que_a_granularidade_da_gravacao():
    """Regressão: comparar com tolerância igual ao arredondamento reprova na fronteira.

    Os valores são gravados com `CASAS_DECIMAIS` casas. Um recálculo que mexe meio
    dígito na última casa muda o arredondamento e produz diferença de exatamente
    10**-CASAS_DECIMAIS — que com tolerância igual cai fora por ruído de
    representação. A camada de regime amplificava isso pela mediana expansiva.
    """
    granularidade = 10 ** -transformacao.CASAS_DECIMAIS
    assert transformacao.TOLERANCIA >= 10 * granularidade


# ------------------------------------------------- razão de somas móveis

def serie_trimestral(n=40, inicio="2000-01-01", base=100.0, amplitude=10.0):
    idx = pd.date_range(inicio, periods=n, freq="QS")
    trimestre = np.arange(n) % 4
    return pd.Series(base + amplitude * np.sin(2 * np.pi * trimestre / 4), index=idx)


def test_razao_de_somas_moveis_nao_usa_o_futuro():
    """Espelha test_ajuste_recursivo_nao_usa_o_futuro, e pela mesma razão.

    O valor de um trimestre tem que ser idêntico quer a série termine ali, quer
    ela siga por mais dez anos. A janela móvel é retrospectiva por construção, e
    este teste é o que impede alguém de "melhorar" isso com um center=True.
    """
    num, den = serie_trimestral(40), serie_trimestral(40, base=500.0, amplitude=3.0)
    completa = transformacao.razao_de_somas_moveis(num, den)
    curta = transformacao.razao_de_somas_moveis(num.iloc[:30], den.iloc[:30])

    comum = curta.dropna().index
    pd.testing.assert_series_equal(completa.loc[comum], curta.loc[comum], check_names=False)


def test_razao_de_somas_moveis_espera_quatro_trimestres_antes_do_primeiro_valor():
    idx = pd.date_range("2020-01-01", periods=5, freq="QS")
    num = pd.Series([1.0, 2.0, 3.0, 4.0, 5.0], index=idx)
    den = pd.Series([10.0] * 5, index=idx)

    razao = transformacao.razao_de_somas_moveis(num, den)

    assert razao.iloc[:3].isna().all()
    assert razao.iloc[3] == pytest.approx((1 + 2 + 3 + 4) / 40 * 100)
    assert razao.iloc[4] == pytest.approx((2 + 3 + 4 + 5) / 40 * 100)


def test_razao_de_somas_moveis_e_a_razao_das_somas_e_nao_a_media_das_razoes():
    """As duas contas divergem quando numerador e denominador têm sazonalidades
    diferentes, e só uma delas é a taxa de investimento do IBGE."""
    idx = pd.date_range("2020-01-01", periods=4, freq="QS")
    num = pd.Series([1.0, 1.0, 1.0, 10.0], index=idx)
    den = pd.Series([10.0, 10.0, 10.0, 1.0], index=idx)

    razao = transformacao.razao_de_somas_moveis(num, den)

    assert razao.iloc[3] == pytest.approx(13 / 31 * 100)
    media_das_razoes = (num / den * 100).mean()
    assert razao.iloc[3] != pytest.approx(media_das_razoes)


def test_razao_de_somas_moveis_alinha_pelo_trimestre_e_nao_pela_posicao():
    """Trimestre presente em só uma das séries vira NaN, e não razão calculada
    contra o vizinho errado — que passaria despercebida por ser plausível."""
    num = pd.Series([1.0] * 8, index=pd.date_range("2020-01-01", periods=8, freq="QS"))
    den = pd.Series([10.0] * 8, index=pd.date_range("2020-04-01", periods=8, freq="QS"))

    razao = transformacao.razao_de_somas_moveis(num, den)

    # numerador já tem janela cheia, denominador ainda não
    assert pd.isna(razao.loc["2020-10-01"])
    # trimestre que só o denominador cobre
    assert pd.isna(razao.loc["2022-01-01"])
    # onde as duas janelas se sobrepõem, a razão sai
    assert razao.loc["2021-01-01"] == pytest.approx(10.0)


def test_as_razoes_do_pib_ficam_na_faixa_plausivel():
    """Sobre o artefato versionado, e não sobre uma fixture.

    Lê o caminho real de propósito: a fixture autouse deste módulo isola o
    armazenamento, e o que interessa aqui é o número que o repositório publica.
    A faixa é larga porque a série é revisada — cravar decimal viraria
    manutenção a cada divulgação, e a conferência exata mora no campo
    `verificacao` da ficha. O que esta faixa pega é o que importa: categoria
    trocada, unidade trocada, ou numerador dividido pelo denominador errado.
    """
    from ciclo_br.config import DIR_DERIVADO

    derivado = pd.read_parquet(DIR_DERIVADO / "series.parquet")
    recentes = derivado[derivado["data_referencia"] >= dt.date(2024, 1, 1)]

    investimento = recentes[recentes["serie_id"] == "taxa_investimento"]["valor"]
    governo = recentes[recentes["serie_id"] == "consumo_governo_pib"]["valor"]

    assert not investimento.empty and not governo.empty
    assert investimento.between(12, 24).all(), "taxa de investimento fora da faixa"
    assert governo.between(15, 25).all(), "consumo do governo fora da faixa"
