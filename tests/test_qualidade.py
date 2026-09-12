"""O portão de qualidade precisa reprovar o que deve e passar o que é normal.

Cada teste injeta um defeito conhecido e confere que ele é pego — e, tão
importante quanto, que dado saudável não dispara alarme.
"""

import datetime as dt

import pandas as pd
import pytest

from ciclo_br import qualidade, storage
from ciclo_br.config import Serie


@pytest.fixture(autouse=True)
def dados_temporarios(tmp_path, monkeypatch):
    monkeypatch.setattr(storage, "DIR_BRUTO", tmp_path / "raw")
    monkeypatch.setattr(storage, "CAMINHO_EXECUCOES", tmp_path / "_execucoes.parquet")
    return tmp_path


def ficha(**kwargs) -> Serie:
    base = dict(
        id="teste", fonte="sgs", nome="Série de teste", bloco="atividade",
        unidade="índice", periodicidade="mensal", ajuste_sazonal="nao_aplicavel",
        papel="contexto", codigo=1,
    )
    extra = kwargs.pop("extra", {})
    base.update(kwargs)
    return Serie(**base, extra=extra)


def gravar(serie_id, meses, valores=None, fim=None):
    """Grava `meses` observações mensais terminando em `fim` (padrão: mês passado)."""
    fim = fim or dt.date.today().replace(day=1) - dt.timedelta(days=1)
    fim = fim.replace(day=1)
    datas = list(pd.date_range(end=pd.Timestamp(fim), periods=meses, freq="MS").date)
    valores = valores or [100.0 + i * 0.1 for i in range(meses)]
    storage.anexar(
        serie_id,
        pd.DataFrame({"data_referencia": datas, "valor": valores}),
        execucao_id="e1",
    )
    return datas


def erros(problemas):
    return [p for p in problemas if p.gravidade is qualidade.Gravidade.ERRO]


def test_serie_saudavel_nao_gera_problema():
    gravar("teste", 60)
    assert qualidade.verificar_serie(ficha()) == []


def test_serie_vazia_reprova():
    problemas = qualidade.verificar_serie(ficha())
    assert erros(problemas)
    assert "nenhuma observação" in problemas[0].detalhe


def test_buraco_na_grade_reprova():
    datas = list(pd.date_range("2020-01-01", periods=40, freq="MS").date)
    del datas[20]
    storage.anexar("teste", pd.DataFrame({
        "data_referencia": datas, "valor": [100.0] * len(datas),
    }), execucao_id="e1")

    problemas = qualidade.verificar_serie(ficha(extra={"frescor_max_dias": 100_000}))
    grade = [p for p in problemas if p.verificacao == "grade temporal"]
    assert grade and grade[0].gravidade is qualidade.Gravidade.ERRO


def test_serie_parada_reprova_por_frescor():
    gravar("teste", 30, fim=dt.date(2024, 1, 1))
    problemas = qualidade.verificar_serie(ficha())
    frescor = [p for p in problemas if p.verificacao == "frescor"]
    assert frescor and frescor[0].gravidade is qualidade.Gravidade.ERRO


def test_serie_encerrada_nao_reprova_por_frescor():
    """A versão congelada dos núcleos está parada de propósito."""
    gravar("teste", 30, fim=dt.date(2024, 1, 1))
    problemas = qualidade.verificar_serie(ficha(extra={"encerrada": True}))
    assert not [p for p in problemas if p.verificacao == "frescor"]


def test_limite_de_frescor_da_ficha_tem_precedencia():
    gravar("teste", 30, fim=dt.date.today().replace(day=1) - dt.timedelta(days=120))
    assert [p for p in qualidade.verificar_serie(ficha()) if p.verificacao == "frescor"]
    folgado = ficha(extra={"frescor_max_dias": 400})
    assert not [p for p in qualidade.verificar_serie(folgado) if p.verificacao == "frescor"]


def test_salto_recente_vira_aviso():
    valores = [100.0 + i * 0.1 for i in range(59)] + [9_999.0]
    gravar("teste", 60, valores)
    avisos = [p for p in qualidade.verificar_serie(ficha())
              if p.verificacao == "salto extremo"]
    assert avisos and avisos[0].gravidade is qualidade.Gravidade.AVISO


def test_salto_antigo_nao_dispara_alarme():
    """Hiperinflação de 1990 é fato verdadeiro, não defeito da coleta de hoje."""
    valores = [100.0] * 5 + [9_999.0] + [100.0 + i * 0.1 for i in range(54)]
    gravar("teste", 60, valores)
    assert not [p for p in qualidade.verificar_serie(ficha())
                if p.verificacao == "salto extremo"]


def test_serie_diaria_nao_cobra_grade_continua():
    """Fim de semana e feriado são buraco normal em série diária."""
    datas = list(pd.bdate_range(end=pd.Timestamp(dt.date.today()), periods=300).date)
    storage.anexar("teste", pd.DataFrame({
        "data_referencia": datas, "valor": [5.0] * len(datas),
    }), execucao_id="e1")
    problemas = qualidade.verificar_serie(ficha(periodicidade="diaria"))
    assert not [p for p in problemas if p.verificacao == "grade temporal"]


def test_main_devolve_codigo_de_falha_quando_ha_erro(monkeypatch):
    monkeypatch.setattr(qualidade, "catalogo", lambda: {"teste": ficha()})
    assert qualidade.main([]) == 1


def test_main_devolve_zero_quando_tudo_certo(monkeypatch):
    gravar("teste", 60)
    monkeypatch.setattr(qualidade, "catalogo", lambda: {"teste": ficha()})
    assert qualidade.main([]) == 0
