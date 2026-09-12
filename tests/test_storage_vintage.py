"""Comportamento do armazenamento quando a data de coleta vem por linha (Focus)."""

import datetime as dt

import pandas as pd
import pytest

from ciclo_br import storage


@pytest.fixture(autouse=True)
def dados_temporarios(tmp_path, monkeypatch):
    monkeypatch.setattr(storage, "DIR_BRUTO", tmp_path / "raw")
    monkeypatch.setattr(storage, "CAMINHO_EXECUCOES", tmp_path / "_execucoes.parquet")
    return tmp_path


def obs(linhas):
    return pd.DataFrame(
        [{"data_referencia": dt.date(*r), "valor": v,
          "data_coleta": dt.datetime(*c, tzinfo=dt.UTC)}
         for r, v, c in linhas]
    )


def test_cada_coleta_com_valor_novo_vira_uma_linha():
    r = storage.anexar("focus_ipca_mensal", obs([
        ((2026, 8, 1), 0.25, (2026, 9, 1)),
        ((2026, 8, 1), 0.26, (2026, 9, 2)),
        ((2026, 8, 1), 0.28, (2026, 9, 3)),
    ]), execucao_id="e1")

    assert (r.novas, r.revisoes) == (1, 2)
    assert len(storage.ler_bruto("focus_ipca_mensal")) == 3


def test_consenso_repetido_nao_gera_linha():
    """Se a mediana não mudou, não houve notícia — e o arquivo não cresce."""
    r = storage.anexar("focus_ipca_mensal", obs([
        ((2026, 8, 1), 0.26, (2026, 9, 1)),
        ((2026, 8, 1), 0.26, (2026, 9, 2)),
        ((2026, 8, 1), 0.26, (2026, 9, 3)),
    ]), execucao_id="e1")

    assert (r.novas, r.revisoes, r.inalteradas) == (1, 0, 2)
    assert len(storage.ler_bruto("focus_ipca_mensal")) == 1


def test_coleta_anterior_a_ultima_gravada_e_ignorada():
    """O passado do Focus é imutável: reescrevê-lo destruiria o vintage."""
    storage.anexar("focus_ipca_mensal", obs([
        ((2026, 8, 1), 0.26, (2026, 9, 5)),
    ]), execucao_id="e1")

    r = storage.anexar("focus_ipca_mensal", obs([
        ((2026, 8, 1), 0.10, (2026, 9, 1)),   # coleta antiga: ignorar
        ((2026, 8, 1), 0.30, (2026, 9, 6)),   # coleta nova: gravar
    ]), execucao_id="e2")

    assert (r.ignoradas, r.revisoes) == (1, 1)
    bruto = storage.ler_bruto("focus_ipca_mensal")
    assert sorted(bruto["valor"]) == [0.26, 0.30]


def test_consenso_vigente_na_vespera_e_reconstruivel():
    """O caso de uso que justifica o desenho inteiro: qual era o consenso em X?"""
    storage.anexar("focus_ipca_mensal", obs([
        ((2026, 8, 1), 0.20, (2026, 8, 20)),
        ((2026, 8, 1), 0.26, (2026, 9, 2)),
        ((2026, 8, 1), 0.31, (2026, 9, 12)),   # depois da divulgação: não vale
    ]), execucao_id="e1")

    con = storage.conectar()
    consenso = con.execute("""
        SELECT valor FROM obs_bruto
        WHERE serie_id = 'focus_ipca_mensal'
          AND data_referencia = DATE '2026-08-01'
          AND data_coleta < TIMESTAMPTZ '2026-09-09 00:00:00+00'
        ORDER BY data_coleta DESC LIMIT 1
    """).fetchone()[0]

    assert consenso == 0.26


def test_referencias_diferentes_nao_se_misturam():
    r = storage.anexar("focus_ipca_mensal", obs([
        ((2026, 8, 1), 0.26, (2026, 9, 2)),
        ((2026, 9, 1), 0.31, (2026, 9, 2)),
    ]), execucao_id="e1")
    assert r.novas == 2


def test_serie_do_sgs_continua_sem_data_coleta_por_linha():
    """A generalização não pode mudar o comportamento da fonte antiga."""
    r = storage.anexar("ipca", pd.DataFrame([
        {"data_referencia": dt.date(2026, 8, 1), "valor": -0.32},
    ]), execucao_id="e1")
    assert (r.novas, r.ignoradas) == (1, 0)
