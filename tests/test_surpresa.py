import datetime as dt

import pandas as pd
import pytest

from ciclo_br import storage, surpresa
from ciclo_br.ingestion import calendario


@pytest.fixture(autouse=True)
def dados_temporarios(tmp_path, monkeypatch):
    monkeypatch.setattr(storage, "DIR_BRUTO", tmp_path / "raw")
    monkeypatch.setattr(calendario, "CAMINHO", tmp_path / "calendario.parquet")
    monkeypatch.setattr(surpresa, "CAMINHO", tmp_path / "surpresa.csv")
    (tmp_path / "raw").mkdir(parents=True, exist_ok=True)
    return tmp_path


def gravar(serie_id, linhas, *, coletado_em=None):
    """linhas: [(data_referencia, valor)] ou [(ref, valor, coleta)]."""
    if linhas and len(linhas[0]) == 3:
        obs = pd.DataFrame({
            "data_referencia": [dt.date.fromisoformat(r) for r, _, _ in linhas],
            "valor": [v for _, v, _ in linhas],
            "data_coleta": [pd.Timestamp(c, tz="UTC") for _, _, c in linhas],
        })
        storage.anexar(serie_id, obs, execucao_id="teste")
        return
    obs = pd.DataFrame({
        "data_referencia": [dt.date.fromisoformat(r) for r, _ in linhas],
        "valor": [v for _, v in linhas],
    })
    storage.anexar(serie_id, obs, execucao_id="teste", coletado_em=coletado_em)


def agenda(eventos):
    """eventos: [(series_ids, data_referencia, data_divulgacao)]."""
    df = pd.DataFrame({
        "produto_id": [1] * len(eventos),
        "produto": ["teste"] * len(eventos),
        "series_ids": [s for s, _, _ in eventos],
        "titulo": ["teste"] * len(eventos),
        "data_divulgacao": [dt.date.fromisoformat(d) for _, _, d in eventos],
        "data_referencia": [dt.date.fromisoformat(r) for _, r, _ in eventos],
        "coletado_em": [dt.datetime.now(dt.UTC)] * len(eventos),
    })
    calendario.salvar(df)


PAR = {"teste": surpresa.Par(realizado="realizado", consenso="focus", unidade="p.p.")}


# ------------------------------------------------------ consenso da véspera

def _focus(linhas):
    return pd.DataFrame({
        "data_referencia": [pd.Timestamp(r) for r, _, _ in linhas],
        "valor": [v for _, v, _ in linhas],
        "data_coleta": [pd.Timestamp(c) for _, _, c in linhas],
    })


def test_consenso_e_a_ultima_apuracao_antes_da_divulgacao():
    focus = _focus([("2025-03-01", 0.40, "2025-03-20"),
                    ("2025-03-01", 0.55, "2025-04-05"),
                    ("2025-03-01", 0.60, "2025-04-20")])
    valor, data = surpresa.consenso_da_vespera(
        focus, pd.Timestamp("2025-03-01"), dt.date(2025, 4, 10))
    assert valor == 0.55
    assert data == dt.date(2025, 4, 5)


def test_apuracao_do_proprio_dia_da_divulgacao_nao_conta():
    """Quem operava antes do número sair não tinha essa apuração."""
    focus = _focus([("2025-03-01", 0.40, "2025-04-01"),
                    ("2025-03-01", 0.99, "2025-04-10")])
    valor, data = surpresa.consenso_da_vespera(
        focus, pd.Timestamp("2025-03-01"), dt.date(2025, 4, 10))
    assert valor == 0.40
    assert data == dt.date(2025, 4, 1)


def test_sem_apuracao_anterior_nao_ha_consenso():
    focus = _focus([("2025-03-01", 0.40, "2025-04-20")])
    assert surpresa.consenso_da_vespera(
        focus, pd.Timestamp("2025-03-01"), dt.date(2025, 4, 10)) is None


def test_consenso_nao_vaza_de_outra_referencia():
    focus = _focus([("2025-02-01", 9.99, "2025-04-01")])
    assert surpresa.consenso_da_vespera(
        focus, pd.Timestamp("2025-03-01"), dt.date(2025, 4, 10)) is None


# ---------------------------------------------------------------- construir

def test_surpresa_e_realizado_menos_consenso():
    gravar("realizado", [("2025-03-01", 0.71)])
    gravar("focus", [("2025-03-01", 0.55, "2025-04-05")])
    agenda([("realizado", "2025-03-01", "2025-04-10")])

    tabela = surpresa.construir(PAR)
    assert len(tabela) == 1
    linha = tabela.iloc[0]
    assert linha["realizado"] == 0.71
    assert linha["consenso"] == 0.55
    assert linha["surpresa"] == pytest.approx(0.16)
    assert linha["dias_sem_mudanca"] == 5


def test_referencia_sem_data_de_divulgacao_e_ignorada():
    """Sem data de divulgação não há véspera, e nada é inventado."""
    gravar("realizado", [("2025-03-01", 0.71), ("2025-04-01", 0.50)])
    gravar("focus", [("2025-03-01", 0.55, "2025-04-05"),
                     ("2025-04-01", 0.45, "2025-05-05")])
    agenda([("realizado", "2025-03-01", "2025-04-10")])

    tabela = surpresa.construir(PAR)
    assert list(tabela["data_referencia"]) == ["2025-03-01"]


def test_calendario_vazio_devolve_vazio():
    gravar("realizado", [("2025-03-01", 0.71)])
    gravar("focus", [("2025-03-01", 0.55, "2025-04-05")])
    assert surpresa.construir(PAR).empty


def test_primeira_leitura_so_quando_a_coleta_acompanhou_a_divulgacao():
    """A marca separa surpresa contra primeiro print de surpresa contra revisado."""
    gravar("realizado", [("2025-03-01", 0.71)],
           coletado_em=dt.datetime(2025, 4, 11, tzinfo=dt.UTC))
    gravar("focus", [("2025-03-01", 0.55, "2025-04-05")])
    agenda([("realizado", "2025-03-01", "2025-04-10")])
    assert bool(surpresa.construir(PAR)["primeira_leitura"].iloc[0]) is True


def test_backfill_tardio_nao_passa_por_primeira_leitura():
    gravar("realizado", [("2025-03-01", 0.71)],
           coletado_em=dt.datetime(2026, 1, 1, tzinfo=dt.UTC))
    gravar("focus", [("2025-03-01", 0.55, "2025-04-05")])
    agenda([("realizado", "2025-03-01", "2025-04-10")])
    assert bool(surpresa.construir(PAR)["primeira_leitura"].iloc[0]) is False


def test_realizado_usado_e_a_versao_vigente():
    """Revisão do realizado muda a surpresa; é o comportamento declarado."""
    gravar("realizado", [("2025-03-01", 0.71, "2025-04-11")])
    gravar("focus", [("2025-03-01", 0.55, "2025-04-05")])
    agenda([("realizado", "2025-03-01", "2025-04-10")])
    assert surpresa.construir(PAR)["surpresa"].iloc[0] == pytest.approx(0.16)

    gravar("realizado", [("2025-03-01", 0.81, "2025-06-11")])
    assert surpresa.construir(PAR)["surpresa"].iloc[0] == pytest.approx(0.26)


# ------------------------------------------------------------------ resumo

def test_resumo_traz_a_ultima_de_cada_par_com_escala():
    gravar("realizado", [("2025-03-01", 0.71), ("2025-04-01", 0.30)])
    gravar("focus", [("2025-03-01", 0.55, "2025-04-05"),
                     ("2025-04-01", 0.45, "2025-05-05")])
    agenda([("realizado", "2025-03-01", "2025-04-10"),
            ("realizado", "2025-04-01", "2025-05-09")])

    info = surpresa.resumo(surpresa.construir(PAR))["teste"]
    assert info["data_referencia"] == "2025-04-01"
    assert info["surpresa"] == pytest.approx(-0.15)
    assert info["observacoes"] == 2
    # Sem escala, não dá para dizer se 0,15 p.p. é muito.
    assert info["desvio_padrao_historico"] > 0


# ---------------------------------------------------------------- gravação

def test_main_reprova_quando_o_versionado_esta_desatualizado(monkeypatch):
    gravar("realizado", [("2025-03-01", 0.71)])
    gravar("focus", [("2025-03-01", 0.55, "2025-04-05")])
    agenda([("realizado", "2025-03-01", "2025-04-10")])
    monkeypatch.setattr(surpresa, "PARES", PAR)

    assert surpresa.main([]) == 0
    assert surpresa.main(["--verificar"]) == 0

    surpresa.CAMINHO.write_text(
        surpresa.CAMINHO.read_text(encoding="utf-8").replace("0.71", "9.99"),
        encoding="utf-8")
    assert surpresa.main(["--verificar"]) == 1


def test_salvar_e_idempotente():
    gravar("realizado", [("2025-03-01", 0.71)])
    gravar("focus", [("2025-03-01", 0.55, "2025-04-05")])
    agenda([("realizado", "2025-03-01", "2025-04-10")])
    tabela = surpresa.construir(PAR)
    assert surpresa.salvar(tabela) is True
    assert surpresa.salvar(tabela) is False
