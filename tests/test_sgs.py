import datetime as dt

import pandas as pd
import pytest

from ciclo_br.ingestion import sgs


def test_janelas_respeitam_o_limite_de_dez_anos():
    janelas = sgs._janelas(dt.date(2003, 1, 1), dt.date(2026, 9, 12))
    assert janelas[0][0] == dt.date(2003, 1, 1)
    assert janelas[-1][1] == dt.date(2026, 9, 12)
    for inicio, fim in janelas:
        assert (fim - inicio).days < 3653, "janela acima do limite de 10 anos da API"


def test_janelas_sao_contiguas_e_sem_sobreposicao():
    janelas = sgs._janelas(dt.date(2003, 1, 1), dt.date(2026, 9, 12))
    for anterior, seguinte in zip(janelas, janelas[1:], strict=False):
        assert seguinte[0] == anterior[1] + dt.timedelta(days=1)


def test_janelas_vazias_quando_intervalo_invertido():
    assert sgs._janelas(dt.date(2026, 1, 1), dt.date(2025, 1, 1)) == []


@pytest.mark.parametrize(
    ("bruto", "esperado"),
    [("0.24", 0.24), ("-0.32", -0.32), ("1.234,56", 1234.56), (5, 5.0), ("", None), (None, None)],
)
def test_conversao_de_valor(bruto, esperado):
    assert sgs._converter_valor(bruto) == esperado


def test_buscar_concatena_janelas_e_ordena(monkeypatch):
    lotes = {
        dt.date(2003, 1, 1): [{"data": "01/02/2003", "valor": "2.0"},
                              {"data": "01/01/2003", "valor": "1.0"}],
        dt.date(2012, 1, 1): [{"data": "01/03/2012", "valor": "3.0"}],
    }
    monkeypatch.setattr(sgs, "PAUSA_ENTRE_JANELAS", 0)
    monkeypatch.setattr(sgs, "_buscar_janela",
                        lambda codigo, inicio, fim: lotes.get(inicio, []))

    df = sgs.buscar(24364, dt.date(2003, 1, 1), dt.date(2020, 1, 1))

    assert list(df["data_referencia"]) == [dt.date(2003, 1, 1), dt.date(2003, 2, 1),
                                           dt.date(2012, 3, 1)]
    assert list(df["valor"]) == [1.0, 2.0, 3.0]


def test_buscar_sem_dados_devolve_dataframe_vazio_com_colunas(monkeypatch):
    monkeypatch.setattr(sgs, "PAUSA_ENTRE_JANELAS", 0)
    monkeypatch.setattr(sgs, "_buscar_janela", lambda *a, **k: [])
    df = sgs.buscar(1, dt.date(2020, 1, 1), dt.date(2021, 1, 1))
    assert df.empty
    assert list(df.columns) == ["data_referencia", "valor"]


def test_janela_404_e_ausencia_de_dado_nao_falha(monkeypatch):
    """404 no SGS significa 'não há dado no intervalo', não erro de rede."""
    class RespostaFalsa:
        status_code = 404

        def json(self):  # pragma: no cover - não deve ser chamado
            raise AssertionError("não deveria tentar decodificar um 404")

    monkeypatch.setattr(sgs.requests, "get", lambda *a, **k: RespostaFalsa())
    assert sgs._buscar_janela(1, dt.date(1990, 1, 1), dt.date(1991, 1, 1)) == []


def test_resposta_html_vira_erro_explicito(monkeypatch):
    class RespostaFalsa:
        status_code = 200

        def json(self):
            raise ValueError("not json")

    monkeypatch.setattr(sgs.requests, "get", lambda *a, **k: RespostaFalsa())
    with pytest.raises(sgs.ErroSGS):
        sgs._buscar_janela.retry_with(stop=lambda *_: True)(
            1, dt.date(2020, 1, 1), dt.date(2021, 1, 1)
        )


def test_buscar_remove_duplicatas_de_data(monkeypatch):
    monkeypatch.setattr(sgs, "PAUSA_ENTRE_JANELAS", 0)
    monkeypatch.setattr(sgs, "_buscar_janela", lambda *a, **k: [
        {"data": "01/01/2020", "valor": "1.0"},
        {"data": "01/01/2020", "valor": "9.9"},
    ])
    df = sgs.buscar(1, dt.date(2020, 1, 1), dt.date(2020, 12, 31))
    assert len(df) == 1
    assert df.loc[0, "valor"] == 9.9


def test_valores_nulos_sao_descartados(monkeypatch):
    monkeypatch.setattr(sgs, "PAUSA_ENTRE_JANELAS", 0)
    monkeypatch.setattr(sgs, "_buscar_janela", lambda *a, **k: [
        {"data": "01/01/2020", "valor": ""},
        {"data": "01/02/2020", "valor": "1.5"},
    ])
    df = sgs.buscar(1, dt.date(2020, 1, 1), dt.date(2020, 12, 31))
    assert list(df["data_referencia"]) == [dt.date(2020, 2, 1)]


def test_dataframe_de_saida_tem_tipos_esperados(monkeypatch):
    monkeypatch.setattr(sgs, "PAUSA_ENTRE_JANELAS", 0)
    monkeypatch.setattr(sgs, "_buscar_janela", lambda *a, **k: [
        {"data": "01/01/2020", "valor": "1.5"},
    ])
    df = sgs.buscar(1, dt.date(2020, 1, 1), dt.date(2020, 12, 31))
    assert isinstance(df.loc[0, "data_referencia"], dt.date)
    assert pd.api.types.is_float_dtype(df["valor"])
