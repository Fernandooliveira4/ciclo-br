import pandas as pd
import pytest

from ciclo_br import regime, validacao

CABECALHO = "recessao_id,pico,vale,granularidade,fonte,observacao\n"


def escrever(tmp_path, linhas, cabecalho=CABECALHO):
    caminho = tmp_path / "crono.csv"
    caminho.write_text("# comentário que deve ser ignorado\n" + cabecalho + linhas,
                       encoding="utf-8")
    return caminho


def meses(inicio, n):
    return pd.period_range(inicio, periods=n, freq="M")


# ------------------------------------------------------- cronologia oficial

def test_cronologia_versionada_carrega_e_bate_com_a_datacao_trimestral():
    """A transcrição do CODACE precisa fechar com a fonte independente.

    A datação mensal e a trimestral são publicadas em documentos diferentes.
    Para 2014-2016 elas têm de dar o mesmo número de meses: 11 trimestres. Se a
    transcrição escorregar um mês, este teste cai.
    """
    crono = validacao.carregar_cronologia()
    assert len(crono) >= 10
    assert crono["pico"].is_monotonic_increasing

    recessao = crono.set_index("recessao_id").loc["2014-2016"]
    assert recessao["duracao"] == 33
    assert str(recessao["inicio"]) == "2014-04"
    assert str(recessao["fim"]) == "2016-12"


def test_covid_esta_marcada_como_datacao_trimestral():
    """O CODACE nunca datou a recessão da covid em meses. Isso não pode sumir."""
    crono = validacao.carregar_cronologia().set_index("recessao_id")
    assert crono.loc["2019-2020", "granularidade"] == "trimestral"
    assert (crono.drop(index="2019-2020")["granularidade"] == "mensal").all()


def test_cronologia_recusa_vale_antes_do_pico(tmp_path):
    caminho = escrever(tmp_path, "x,2015-06,2015-01,mensal,teste,\n")
    with pytest.raises(validacao.CronologiaInvalida, match="pico não antecede"):
        validacao.carregar_cronologia(caminho)


def test_cronologia_recusa_recessoes_sobrepostas(tmp_path):
    caminho = escrever(tmp_path, "a,2010-01,2011-01,mensal,teste,\n"
                                 "b,2010-06,2012-01,mensal,teste,\n")
    with pytest.raises(validacao.CronologiaInvalida, match="sobrepostas"):
        validacao.carregar_cronologia(caminho)


def test_cronologia_recusa_granularidade_inventada(tmp_path):
    caminho = escrever(tmp_path, "a,2010-01,2011-01,semanal,teste,\n")
    with pytest.raises(validacao.CronologiaInvalida, match="granularidade"):
        validacao.carregar_cronologia(caminho)


# ------------------------------------------------------------------ episódios

def test_episodios_encontra_blocos_contiguos():
    s = pd.Series([False, True, True, False, True], index=meses("2020-01", 5))
    assert validacao.episodios(s) == [
        (pd.Period("2020-02", "M"), pd.Period("2020-03", "M")),
        (pd.Period("2020-05", "M"), pd.Period("2020-05", "M")),
    ]


def test_episodio_aberto_no_fim_da_serie_ainda_conta():
    s = pd.Series([False, True, True], index=meses("2020-01", 3))
    assert validacao.episodios(s) == [(pd.Period("2020-02", "M"), pd.Period("2020-03", "M"))]


# ------------------------------------------------------------------ defasagem

def _crono(tmp_path):
    return validacao.carregar_cronologia(
        escrever(tmp_path, "teste,2020-03,2020-08,mensal,teste,\n"))


def _sinal(ligados, inicio="2018-01", n=84):
    indice = meses(inicio, n)
    return pd.Series([m in ligados for m in indice.astype(str)], index=indice)


def test_defasagem_zero_quando_o_sinal_acerta_as_duas_pontas(tmp_path):
    crono = _crono(tmp_path)
    # Recessão: abril a agosto de 2020. Sinal ligado exatamente nesses meses.
    ligados = [str(m) for m in meses("2020-04", 5)]
    tabela = validacao.defasagens(_sinal(ligados), crono)
    assert tabela["defasagem_pico"].iloc[0] == 0
    assert tabela["defasagem_vale"].iloc[0] == 0
    assert tabela["cobertura_da_recessao"].iloc[0] == 1.0


def test_sinal_antecipado_tem_defasagem_negativa(tmp_path):
    crono = _crono(tmp_path)
    ligados = [str(m) for m in meses("2020-01", 8)]
    tabela = validacao.defasagens(_sinal(ligados), crono)
    assert tabela["defasagem_pico"].iloc[0] == -3
    assert tabela["defasagem_vale"].iloc[0] == 0


def test_sinal_atrasado_tem_defasagem_positiva(tmp_path):
    crono = _crono(tmp_path)
    ligados = [str(m) for m in meses("2020-06", 6)]
    tabela = validacao.defasagens(_sinal(ligados), crono)
    assert tabela["defasagem_pico"].iloc[0] == 2
    assert tabela["defasagem_vale"].iloc[0] == 3


def test_recessao_sem_sobreposicao_conta_como_nao_detectada(tmp_path):
    crono = _crono(tmp_path)
    tabela = validacao.defasagens(_sinal([str(m) for m in meses("2021-01", 4)]), crono)
    assert not bool(tabela["detectada"].iloc[0])
    assert pd.isna(tabela["defasagem_pico"].iloc[0])


def test_episodio_aberto_no_fim_deixa_a_defasagem_do_vale_indefinida(tmp_path):
    """Sinal que ainda não desligou não tem data de saída — e não pode inventar uma."""
    crono = _crono(tmp_path)
    indice = meses("2020-01", 6)
    sinal = pd.Series([m >= pd.Period("2020-04", "M") for m in indice], index=indice)
    tabela = validacao.defasagens(sinal, crono)
    assert tabela["defasagem_pico"].iloc[0] == 0
    assert pd.isna(tabela["defasagem_vale"].iloc[0])


def test_runway_curto_e_marcado_como_cobertura_parcial(tmp_path):
    """Se a série começa logo antes do pico, a antecipação medida está truncada."""
    crono = _crono(tmp_path)
    indice = meses("2020-01", 12)
    sinal = pd.Series([pd.Period("2020-04", "M") <= m <= pd.Period("2020-08", "M")
                       for m in indice], index=indice)
    assert validacao.defasagens(sinal, crono)["cobertura"].iloc[0] == "parcial"


# ------------------------------------------------------------- características

def test_episodio_apos_o_ultimo_vale_nao_conta_como_falso_alarme(tmp_path):
    """O CODACE anuncia com anos de atraso: depois do último vale nada é avaliável."""
    crono = _crono(tmp_path)
    ligados = [str(m) for m in meses("2020-04", 5)] + [str(m) for m in meses("2023-01", 4)]
    info = validacao.caracteristicas(_sinal(ligados), crono)
    assert info["episodios_fora_de_recessao"] == 0
    assert info["episodios_apos_ultimo_vale"] == 1


def test_sinal_sempre_ligado_aparece_como_degenerado(tmp_path):
    """Um sinal que nunca desliga não tem falso alarme — e é inútil.

    Sem `maior_episodio_meses` e `fracao_da_janela_com_sinal`, a degeneração
    apareceria na tabela de evidência como o melhor resultado possível.
    """
    crono = _crono(tmp_path)
    indice = meses("2018-01", 60)
    info = validacao.caracteristicas(pd.Series(True, index=indice), crono)
    assert info["episodios_fora_de_recessao"] == 0
    assert info["fracao_da_janela_com_sinal"] == 1.0
    assert info["maior_episodio_meses"] == 60


# ------------------------------------------------------------------ varredura

def _regime_sintetico(n=120):
    indice = pd.period_range("2015-01", periods=n, freq="M")
    crescimento = [(-2.0 if 63 <= k < 80 else 4.0) for k in range(n)]
    return pd.DataFrame({
        "data_referencia": [p.to_timestamp().date() for p in indice],
        "eixo_crescimento": crescimento,
        "eixo_inflacao": [3.0] * n,
        "corte_crescimento": [1.0] * n,
        "corte_inflacao": [2.0] * n,
        "quadrante_bruto": [None] * n,
    })


def test_varredura_cobre_a_grade_inteira(tmp_path):
    crono = _crono(tmp_path)
    defas, resumo = validacao.varrer(_regime_sintetico(), crono)
    esperado = len(regime.CORTES_CRESCIMENTO) * len(validacao.PERSISTENCIAS)
    assert len(resumo) == esperado
    assert set(resumo["corte_crescimento"]) == set(regime.CORTES_CRESCIMENTO)
    assert set(defas["persistencia"]) <= set(validacao.PERSISTENCIAS)


def test_persistencia_maior_atrasa_a_entrada(tmp_path):
    """A troca em evidência: o prazo de confirmação compra sossego e custa atraso."""
    crono = _crono(tmp_path)
    defas, _ = validacao.varrer(_regime_sintetico(), crono)
    detectadas = defas[defas["detectada"]]
    if detectadas.empty:
        pytest.skip("cenário sintético não sobrepôs a recessão de teste")
    por_prazo = detectadas.groupby("persistencia")["defasagem_pico"].min()
    assert por_prazo.is_monotonic_increasing


# ------------------------------------------------------------------- gravação

def test_main_reprova_quando_o_versionado_esta_desatualizado(tmp_path, monkeypatch):
    monkeypatch.setattr(validacao, "CAMINHO_DEFASAGENS", tmp_path / "d.csv")
    monkeypatch.setattr(validacao, "CAMINHO_RESUMO", tmp_path / "r.csv")

    assert validacao.main([]) == 0
    assert validacao.main(["--verificar"]) == 0

    resumo = (tmp_path / "r.csv").read_text(encoding="utf-8")
    (tmp_path / "r.csv").write_text(resumo.replace("mediana,1,", "mediana,9,", 1),
                                    encoding="utf-8")
    assert validacao.main(["--verificar"]) == 1


def test_salvar_e_idempotente(tmp_path, monkeypatch):
    monkeypatch.setattr(validacao, "CAMINHO_DEFASAGENS", tmp_path / "d.csv")
    monkeypatch.setattr(validacao, "CAMINHO_RESUMO", tmp_path / "r.csv")
    defas, resumo = validacao.construir()
    assert validacao.salvar(defas, resumo) is True
    assert validacao.salvar(defas, resumo) is False
