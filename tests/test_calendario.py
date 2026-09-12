import datetime as dt

import pytest

from ciclo_br.config import calendario_produtos, catalogo
from ciclo_br.ingestion import calendario


def test_produtos_do_calendario_apontam_para_series_com_ficha():
    produtos = calendario_produtos()
    conhecidas = catalogo()
    assert produtos
    for ids in produtos.values():
        for serie_id in ids:
            assert serie_id in conhecidas


@pytest.mark.parametrize(
    ("bruto", "esperado"),
    [
        ("09/10/2026 12:00:00", dt.date(2026, 10, 9)),
        ("12/01/2027 12:00:00", dt.date(2027, 1, 12)),
        ("", None),
        (None, None),
        ("data ruim", None),
    ],
)
def test_conversao_da_data_de_divulgacao(bruto, esperado):
    assert calendario._data_divulgacao(bruto) == esperado


def test_data_de_referencia_vem_de_ano_e_mes():
    assert calendario._data_referencia(
        {"ano_referencia_inicio": 2026, "mes_referencia_inicio": 9}
    ) == dt.date(2026, 9, 1)
    assert calendario._data_referencia({"ano_referencia_inicio": 2026}) is None
    assert calendario._data_referencia(
        {"ano_referencia_inicio": 2026, "mes_referencia_inicio": 13}
    ) is None


def test_buscar_liga_produto_a_series(monkeypatch):
    monkeypatch.setattr(calendario, "_buscar_produto", lambda *a, **k: [{
        "titulo": "IPCA", "nome_produto": "IPCA",
        "data_divulgacao": "09/10/2026 12:00:00",
        "ano_referencia_inicio": 2026, "mes_referencia_inicio": 9,
    }])

    df = calendario.buscar({9256: ["ipca", "ipca_12m"]})

    assert len(df) == 1
    assert df.loc[0, "series_ids"] == "ipca,ipca_12m"
    assert df.loc[0, "data_divulgacao"] == dt.date(2026, 10, 9)
    assert df.loc[0, "data_referencia"] == dt.date(2026, 9, 1)


def test_evento_sem_data_e_descartado(monkeypatch):
    monkeypatch.setattr(calendario, "_buscar_produto", lambda *a, **k: [
        {"data_divulgacao": None, "nome_produto": "X"},
    ])
    assert calendario.buscar({9256: ["ipca"]}).empty


def test_falha_do_calendario_nao_derruba_o_pipeline(monkeypatch):
    """Papel auxiliar: se o calendário cair, a ingestão continua."""
    def explode(*a, **k):
        raise calendario.ErroCalendario("fora do ar")

    monkeypatch.setattr(calendario, "_buscar_produto", explode)
    monkeypatch.setattr(calendario, "salvar", lambda df: None)
    assert calendario.main([]) == 0
