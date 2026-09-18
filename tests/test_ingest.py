"""Testes do orquestrador de ingestão — o que a execução padrão alcança.

O foco aqui não é o que cada cliente baixa (isso é de test_sgs, test_focus e
test_ibge_agregados), e sim que nenhuma série do catálogo fique órfã do
agendamento diário.
"""

import datetime as dt

import pandas as pd
import pytest

from ciclo_br import storage
from ciclo_br.config import Serie, catalogo
from ciclo_br.ingestion import run


@pytest.fixture
def ingestao_falsa(monkeypatch):
    """Registra quais séries a execução tocaria, sem tocar em rede nem disco."""
    tocadas: list[str] = []

    def falsa(serie, *, execucao_id, backfill):
        tocadas.append(serie.id)
        return storage.ResultadoAnexo(serie.id, 0, 0, 0)

    monkeypatch.setattr(run, "ingerir", falsa)
    return tocadas


def test_toda_fonte_do_catalogo_entra_na_execucao_padrao(ingestao_falsa):
    """`ciclo-ingest` sem argumento é exatamente como o agendamento diário chama.

    Enquanto as fontes eram escritas à mão aqui, uma fonte nova coletava no
    backfill manual, passava nos oito portões e sumia do agendamento. O sintoma
    aparecia meses depois, como portão de frescor vermelho sem causa aparente —
    longe demais da causa para alguém ligar as duas coisas.
    """
    assert run.main([]) == 0

    esperado = {s.id for s in catalogo().values() if s.implementada}
    assert set(ingestao_falsa) == esperado


def test_a_execucao_padrao_alcanca_as_contas_nacionais(ingestao_falsa):
    run.main([])
    assert {"pib_corrente", "fbcf_corrente", "consumo_governo_corrente"} <= set(ingestao_falsa)


def test_restringir_a_uma_fonte_so_pega_aquela_fonte(ingestao_falsa):
    run.main(["--fonte", "ibge"])
    assert set(ingestao_falsa) == {
        s.id for s in catalogo().values() if s.fonte == "ibge"
    }


def test_toda_fonte_do_catalogo_tem_ramo_em_baixar(monkeypatch):
    """Sem ramo em `_baixar`, a série levanta ValueError dentro do try/except
    que registra e segue: o pipeline continua verde e a série nunca coleta."""
    vazio = pd.DataFrame(columns=["data_referencia", "valor"])
    monkeypatch.setattr(run.sgs, "buscar", lambda *a, **k: vazio)
    monkeypatch.setattr(run.focus, "buscar", lambda *a, **k: vazio)
    monkeypatch.setattr(run.ibge_agregados, "buscar", lambda *a, **k: vazio)

    for fonte in {s.fonte for s in catalogo().values()}:
        serie = next(s for s in catalogo().values() if s.fonte == fonte)
        run._baixar(serie, dt.date(2020, 1, 1))  # não pode levantar


def test_fonte_sem_cliente_e_recusada_em_vez_de_ignorada():
    orfa = Serie(
        id="orfa", fonte="inventada", nome="x", bloco="y", unidade="z",
        periodicidade="mensal", ajuste_sazonal="nao_aplicavel", papel="contexto",
    )
    with pytest.raises(ValueError, match="fonte desconhecida"):
        run._baixar(orfa, dt.date(2020, 1, 1))


def test_contas_nacionais_reconsultam_a_serie_inteira(monkeypatch):
    """O IBGE revisa o histórico inteiro a cada divulgação, e a série cabe numa
    requisição só. Uma janela de 24 meses descartaria de graça as revisões
    antigas, que são justamente as que ninguém mais registra."""
    monkeypatch.setattr(storage, "ler_vigente", lambda _: pd.DataFrame(
        {"data_referencia": [dt.date(2026, 4, 1)],
         "valor": [1.0],
         "data_coleta": [pd.Timestamp("2026-09-01", tz="UTC")]}
    ))
    serie = catalogo()["fbcf_corrente"]
    assert run._inicio_incremental(serie) == dt.date(1996, 1, 1)


def test_sgs_recua_a_janela_retroativa_sobre_a_referencia(monkeypatch):
    monkeypatch.setattr(storage, "ler_vigente", lambda _: pd.DataFrame(
        {"data_referencia": [dt.date(2026, 7, 1)],
         "valor": [1.0],
         "data_coleta": [pd.Timestamp("2026-09-01", tz="UTC")]}
    ))
    serie = catalogo()["ibcbr_sa"]
    assert run._inicio_incremental(serie) == dt.date(2024, 7, 1)
