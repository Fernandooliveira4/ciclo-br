import datetime as dt

import pytest

from ciclo_br.ingestion import focus


def test_url_usa_percent20_e_nao_mais():
    """A API do BCB recusa '+' como espaço — este teste trava essa regressão."""
    url = focus._url("ExpectativaMercadoMensais", **{"$filter": "Indicador eq 'IPCA'"})
    assert "%20" in url
    assert "+" not in url


@pytest.mark.parametrize(
    ("bruto", "periodicidade", "esperado"),
    [
        ("08/2026", "mensal", dt.date(2026, 8, 1)),
        ("12/1999", "mensal", dt.date(1999, 12, 1)),
        ("1/2026", "trimestral", dt.date(2026, 1, 1)),
        ("3/2026", "trimestral", dt.date(2026, 7, 1)),
        ("4/2026", "trimestral", dt.date(2026, 10, 1)),
        ("13/2026", "mensal", None),
        ("5/2026", "trimestral", None),
        ("lixo", "mensal", None),
    ],
)
def test_conversao_de_data_referencia(bruto, periodicidade, esperado):
    assert focus._referencia_para_data(bruto, periodicidade) == esperado


def test_defasagem_em_meses():
    assert focus._defasagem_em_meses(dt.date(2026, 9, 4), dt.date(2026, 8, 1)) == 1
    assert focus._defasagem_em_meses(dt.date(2026, 9, 4), dt.date(2026, 9, 1)) == 0
    assert focus._defasagem_em_meses(dt.date(2026, 9, 4), dt.date(2028, 8, 1)) == -23


def _lote(coleta, referencias):
    return [{"Data": coleta, "DataReferencia": r, "Mediana": v, "numeroRespondentes": 50}
            for r, v in referencias]


def test_descarta_projecao_de_longo_prazo(monkeypatch):
    """Só interessa o período prestes a ser divulgado, não a projeção de 2028."""
    monkeypatch.setattr(focus, "_pagina", lambda *a, **k: _lote(
        "2026-09-04", [("08/2026", 0.26), ("09/2026", 0.31), ("08/2028", 0.15)]
    ) if a[2] == 0 else [])

    df = focus.buscar("ExpectativaMercadoMensais", "IPCA",
                      periodicidade="mensal", desde=dt.date(2026, 1, 1))

    assert list(df["data_referencia"]) == [dt.date(2026, 8, 1), dt.date(2026, 9, 1)]
    assert list(df["valor"]) == [0.26, 0.31]


def test_janela_trimestral_e_mais_larga(monkeypatch):
    """O PIB do 2º tri sai em setembro: cinco meses de defasagem ainda contam."""
    monkeypatch.setattr(focus, "_pagina", lambda *a, **k: _lote(
        "2026-09-04", [("2/2026", 1.9), ("3/2026", 2.0), ("1/2025", 0.5)]
    ) if a[2] == 0 else [])

    df = focus.buscar("ExpectativasMercadoTrimestrais", "PIB Total",
                      periodicidade="trimestral", desde=dt.date(2026, 1, 1))

    assert list(df["data_referencia"]) == [dt.date(2026, 4, 1), dt.date(2026, 7, 1)]


def test_saida_tem_data_coleta_por_linha(monkeypatch):
    """É isso que faz o armazenamento tratar cada coleta como fato próprio."""
    monkeypatch.setattr(focus, "_pagina", lambda *a, **k: (
        _lote("2026-09-03", [("08/2026", 0.25)]) + _lote("2026-09-04", [("08/2026", 0.26)])
    ) if a[2] == 0 else [])

    df = focus.buscar("ExpectativaMercadoMensais", "IPCA",
                      periodicidade="mensal", desde=dt.date(2026, 1, 1))

    assert list(df.columns) == ["data_referencia", "valor", "data_coleta"]
    assert len(df) == 2
    assert [d.strftime("%Y-%m-%d") for d in df["data_coleta"]] == ["2026-09-03", "2026-09-04"]


def test_pagina_ate_esgotar(monkeypatch):
    chamadas = []

    def falsa(recurso, filtro, skip):
        chamadas.append(skip)
        if skip == 0:
            return _lote("2026-09-04", [("08/2026", 0.26)]) * focus.TAMANHO_PAGINA
        return _lote("2026-09-05", [("08/2026", 0.27)])

    monkeypatch.setattr(focus, "_pagina", falsa)
    monkeypatch.setattr(focus, "PAUSA_ENTRE_PAGINAS", 0)
    focus.buscar("ExpectativaMercadoMensais", "IPCA",
                 periodicidade="mensal", desde=dt.date(2026, 1, 1))

    assert chamadas == [0, focus.TAMANHO_PAGINA]


def test_resposta_vazia_devolve_colunas_esperadas(monkeypatch):
    monkeypatch.setattr(focus, "_pagina", lambda *a, **k: [])
    df = focus.buscar("ExpectativaMercadoMensais", "IPCA",
                      periodicidade="mensal", desde=dt.date(2026, 1, 1))
    assert df.empty
    assert list(df.columns) == ["data_referencia", "valor", "data_coleta"]


def test_erro_http_e_explicito(monkeypatch):
    class RespostaFalsa:
        status_code = 500
        text = "erro interno"

    monkeypatch.setattr(focus.requests, "get", lambda *a, **k: RespostaFalsa())
    with pytest.raises(focus.ErroFocus):
        focus._pagina.retry_with(stop=lambda *_: True)(
            "ExpectativaMercadoMensais", "Indicador eq 'IPCA'", 0
        )
