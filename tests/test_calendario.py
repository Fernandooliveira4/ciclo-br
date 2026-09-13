import datetime as dt

import pandas as pd
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


def test_nao_reescreve_quando_so_o_carimbo_de_tempo_muda(tmp_path, monkeypatch):
    """Senão o Git encheria de commits diários que não dizem nada."""
    monkeypatch.setattr(calendario, "CAMINHO", tmp_path / "calendario.parquet")
    monkeypatch.setattr(calendario, "_buscar_produto", lambda *a, **k: [{
        "titulo": "IPCA", "nome_produto": "IPCA",
        "data_divulgacao": "09/10/2026 12:00:00",
        "ano_referencia_inicio": 2026, "mes_referencia_inicio": 9,
    }])

    assert calendario.salvar(calendario.buscar({9256: ["ipca"]})) is True
    assert calendario.salvar(calendario.buscar({9256: ["ipca"]})) is False


def test_reescreve_quando_o_ibge_remarca_uma_data(tmp_path, monkeypatch):
    monkeypatch.setattr(calendario, "CAMINHO", tmp_path / "calendario.parquet")
    evento = {"titulo": "IPCA", "nome_produto": "IPCA",
              "data_divulgacao": "09/10/2026 12:00:00",
              "ano_referencia_inicio": 2026, "mes_referencia_inicio": 9}

    monkeypatch.setattr(calendario, "_buscar_produto", lambda *a, **k: [evento])
    calendario.salvar(calendario.buscar({9256: ["ipca"]}))

    remarcado = dict(evento, data_divulgacao="13/10/2026 12:00:00")
    monkeypatch.setattr(calendario, "_buscar_produto", lambda *a, **k: [remarcado])
    assert calendario.salvar(calendario.buscar({9256: ["ipca"]})) is True


def test_falha_do_calendario_nao_derruba_o_pipeline(monkeypatch):
    """Papel auxiliar: se o calendário cair, a ingestão continua."""
    def explode(*a, **k):
        raise calendario.ErroCalendario("fora do ar")

    monkeypatch.setattr(calendario, "_buscar_produto", explode)
    monkeypatch.setattr(calendario, "salvar", lambda df: None)
    assert calendario.main([]) == 0


# ------------------------------------------------- histórico e mescla (S6)

def _evento(produto_id, series_ids, referencia, divulgacao):
    return {
        "produto_id": produto_id, "produto": "teste", "series_ids": series_ids,
        "titulo": "teste",
        "data_divulgacao": dt.date.fromisoformat(divulgacao),
        "data_referencia": dt.date.fromisoformat(referencia),
        "coletado_em": dt.datetime.now(dt.UTC),
    }


def test_mesclar_preserva_o_historico_fora_da_janela_coletada():
    """A rodada diária consulta uma janela curta; o arquivo guarda tudo.

    Sem mesclar, cada execução apagaria as datas de divulgação de 2017 em diante
    — que são exatamente o que a camada de surpresa consome.
    """
    antigo = pd.DataFrame([_evento(1, "ipca", "2017-01-01", "2017-02-08")])
    novo = pd.DataFrame([_evento(1, "ipca", "2026-08-01", "2026-09-11")])

    junto = calendario.mesclar(antigo, novo)
    assert len(junto) == 2
    assert dt.date(2017, 2, 8) in list(junto["data_divulgacao"])


def test_mesclar_deixa_a_coleta_nova_vencer_na_mesma_referencia():
    """O IBGE remarca datas; a informação mais recente é a correta."""
    antigo = pd.DataFrame([_evento(1, "ipca", "2026-08-01", "2026-09-10")])
    novo = pd.DataFrame([_evento(1, "ipca", "2026-08-01", "2026-09-11")])

    junto = calendario.mesclar(antigo, novo)
    assert len(junto) == 1
    assert junto["data_divulgacao"].iloc[0] == dt.date(2026, 9, 11)


def test_divulgacoes_mapeia_referencia_para_data_por_serie():
    agenda = pd.DataFrame([
        _evento(1, "ipca,ipca_12m", "2026-07-01", "2026-08-11"),
        _evento(2, "desocupacao", "2026-07-01", "2026-08-27"),
    ])
    datas = calendario.divulgacoes("ipca", agenda)
    assert datas[dt.date(2026, 7, 1)] == dt.date(2026, 8, 11)
    assert calendario.divulgacoes("desocupacao", agenda)[dt.date(2026, 7, 1)] \
        == dt.date(2026, 8, 27)


def test_divulgacoes_nao_confunde_serie_com_prefixo():
    """`ipca` não pode casar com a linha de `ipca_12m` por acaso."""
    agenda = pd.DataFrame([_evento(1, "ipca_12m", "2026-07-01", "2026-08-11")])
    assert calendario.divulgacoes("ipca", agenda).empty
