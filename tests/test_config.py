"""Estes testes existem para tornar executável a regra 'nenhuma série sem ficha'."""

import pytest
import yaml

from ciclo_br import config


def test_catalogo_real_carrega_e_valida():
    catalogo = config.carregar()
    assert len(catalogo) >= 12
    assert "ibcbr_sa" in catalogo
    assert "ipca_nucleo_ma_suav" in catalogo


def test_existe_exatamente_um_eixo_de_cada():
    catalogo = config.carregar()
    papeis = [s.papel for s in catalogo.values()]
    assert papeis.count("eixo_crescimento") == 1
    assert papeis.count("eixo_inflacao") == 1


def test_toda_serie_sgs_tem_codigo_e_toda_focus_tem_indicador():
    for serie in config.carregar().values():
        if serie.fonte == "sgs":
            assert isinstance(serie.codigo, int)
        if serie.fonte == "focus":
            assert serie.recurso and serie.indicador


def test_focus_usa_uma_unica_base_de_calculo():
    """Misturar baseCalculo 0 e 1 compara amostras diferentes de respondentes."""
    bases = {s.base_calculo for s in config.series_da_fonte("focus")}
    assert bases == {0}


def test_focus_tem_periodicidade_com_janela_definida():
    from ciclo_br.ingestion.focus import JANELA_MESES
    for serie in config.series_da_fonte("focus"):
        assert serie.periodicidade in JANELA_MESES


def test_ficha_sem_unidade_e_rejeitada(tmp_path):
    caminho = tmp_path / "series.yaml"
    caminho.write_text(yaml.safe_dump({"series": [{
        "id": "x", "fonte": "sgs", "codigo": 1, "nome": "X", "bloco": "b",
        "periodicidade": "mensal", "ajuste_sazonal": "origem", "papel": "contexto",
    }]}), encoding="utf-8")
    with pytest.raises(config.FichaInvalida, match="unidade"):
        config.carregar(caminho)


def test_papel_desconhecido_e_rejeitado(tmp_path):
    caminho = tmp_path / "series.yaml"
    caminho.write_text(yaml.safe_dump({"series": [{
        "id": "x", "fonte": "sgs", "codigo": 1, "nome": "X", "bloco": "b",
        "unidade": "u", "periodicidade": "mensal", "ajuste_sazonal": "origem",
        "papel": "chute",
    }]}), encoding="utf-8")
    with pytest.raises(config.FichaInvalida, match="papel"):
        config.carregar(caminho)


def test_serie_sgs_sem_codigo_e_rejeitada(tmp_path):
    caminho = tmp_path / "series.yaml"
    caminho.write_text(yaml.safe_dump({"series": [{
        "id": "x", "fonte": "sgs", "nome": "X", "bloco": "b", "unidade": "u",
        "periodicidade": "mensal", "ajuste_sazonal": "origem", "papel": "contexto",
    }]}), encoding="utf-8")
    with pytest.raises(config.FichaInvalida, match="codigo"):
        config.carregar(caminho)


def test_id_duplicado_e_rejeitado(tmp_path):
    ficha = {
        "id": "x", "fonte": "sgs", "codigo": 1, "nome": "X", "bloco": "b",
        "unidade": "u", "periodicidade": "mensal", "ajuste_sazonal": "origem",
        "papel": "contexto",
    }
    caminho = tmp_path / "series.yaml"
    caminho.write_text(yaml.safe_dump({"series": [ficha, dict(ficha)]}), encoding="utf-8")
    with pytest.raises(config.FichaInvalida, match="duplicado"):
        config.carregar(caminho)
