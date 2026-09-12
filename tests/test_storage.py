import datetime as dt

import pandas as pd
import pytest

from ciclo_br import storage


@pytest.fixture(autouse=True)
def dados_temporarios(tmp_path, monkeypatch):
    """Isola cada teste num diretório de dados próprio."""
    monkeypatch.setattr(storage, "DIR_BRUTO", tmp_path / "raw")
    monkeypatch.setattr(storage, "CAMINHO_EXECUCOES", tmp_path / "_execucoes.parquet")
    return tmp_path


def obs(pares):
    return pd.DataFrame(
        [{"data_referencia": dt.date(*d), "valor": v} for d, v in pares]
    )


def test_primeira_carga_grava_tudo_como_novo():
    r = storage.anexar("ibcbr_sa", obs([((2020, 1, 1), 100.0), ((2020, 2, 1), 101.0)]),
                       execucao_id="e1")
    assert (r.novas, r.revisoes, r.inalteradas) == (2, 0, 0)


def test_reingestao_identica_nao_grava_nada():
    dados = obs([((2020, 1, 1), 100.0)])
    storage.anexar("ibcbr_sa", dados, execucao_id="e1")
    r = storage.anexar("ibcbr_sa", dados, execucao_id="e2")

    assert (r.novas, r.revisoes, r.inalteradas) == (0, 0, 1)
    assert len(storage.ler_bruto("ibcbr_sa")) == 1, "arquivo cresceu sem informação nova"


def test_revisao_gera_linha_nova_e_preserva_a_anterior():
    storage.anexar("ibcbr_sa", obs([((2020, 1, 1), 100.0)]), execucao_id="e1")
    r = storage.anexar("ibcbr_sa", obs([((2020, 1, 1), 100.7)]), execucao_id="e2")

    assert (r.novas, r.revisoes, r.inalteradas) == (0, 1, 0)

    bruto = storage.ler_bruto("ibcbr_sa")
    assert len(bruto) == 2, "a versão anterior tem que continuar existindo"
    assert sorted(bruto["valor"]) == [100.0, 100.7]

    vigente = storage.ler_vigente("ibcbr_sa")
    assert len(vigente) == 1
    assert vigente.loc[0, "valor"] == 100.7


def test_ruido_de_ponto_flutuante_nao_conta_como_revisao():
    storage.anexar("ibcbr_sa", obs([((2020, 1, 1), 100.0)]), execucao_id="e1")
    r = storage.anexar("ibcbr_sa", obs([((2020, 1, 1), 100.0 + 1e-12)]), execucao_id="e2")
    assert r.revisoes == 0
    assert r.inalteradas == 1


def test_carga_incremental_mistura_novo_revisado_e_inalterado():
    storage.anexar("ipca", obs([((2020, 1, 1), 0.21), ((2020, 2, 1), 0.25)]),
                   execucao_id="e1")
    r = storage.anexar(
        "ipca",
        obs([((2020, 1, 1), 0.21), ((2020, 2, 1), 0.26), ((2020, 3, 1), 0.07)]),
        execucao_id="e2",
    )
    assert (r.novas, r.revisoes, r.inalteradas) == (1, 1, 1)


def test_entrada_vazia_e_no_op():
    r = storage.anexar("ipca", pd.DataFrame(columns=["data_referencia", "valor"]),
                       execucao_id="e1")
    assert r.gravadas == 0
    assert not storage.caminho_serie("ipca").exists()


def test_visao_obs_devolve_apenas_a_versao_vigente():
    storage.anexar("ibcbr_sa", obs([((2020, 1, 1), 100.0)]), execucao_id="e1")
    storage.anexar("ibcbr_sa", obs([((2020, 1, 1), 100.7)]), execucao_id="e2")
    storage.anexar("ipca", obs([((2020, 1, 1), 0.21)]), execucao_id="e2")

    con = storage.conectar()
    assert con.execute("SELECT count(*) FROM obs_bruto").fetchone()[0] == 3
    assert con.execute("SELECT count(*) FROM obs").fetchone()[0] == 2
    valor = con.execute(
        "SELECT valor FROM obs WHERE serie_id = 'ibcbr_sa'"
    ).fetchone()[0]
    assert valor == 100.7


def test_visao_revisoes_lista_so_o_que_a_fonte_alterou():
    storage.anexar("ibcbr_sa", obs([((2020, 1, 1), 100.0), ((2020, 2, 1), 101.0)]),
                   execucao_id="e1")
    storage.anexar("ibcbr_sa", obs([((2020, 1, 1), 100.7)]), execucao_id="e2")

    con = storage.conectar()
    linhas = con.execute("SELECT serie_id, data_referencia, versoes FROM revisoes").fetchall()
    assert linhas == [("ibcbr_sa", dt.date(2020, 1, 1), 2)]


def test_coletas_no_mesmo_tique_do_relogio_resolvem_pela_ordem_de_gravacao():
    """No Windows o relógio é grosseiro: duas coletas podem ter o mesmo carimbo.

    O desempate tem que ser a ordem de gravação, senão 'versão vigente' fica
    indefinido — foi assim que este bug apareceu.
    """
    instante = dt.datetime(2026, 9, 12, 12, 0, 0, tzinfo=dt.UTC)
    storage.anexar("ibcbr_sa", obs([((2020, 1, 1), 100.0)]),
                   execucao_id="e1", coletado_em=instante)
    storage.anexar("ibcbr_sa", obs([((2020, 1, 1), 100.7)]),
                   execucao_id="e2", coletado_em=instante)

    assert storage.ler_vigente("ibcbr_sa").loc[0, "valor"] == 100.7

    con = storage.conectar()
    assert con.execute(
        "SELECT valor FROM obs WHERE serie_id = 'ibcbr_sa'"
    ).fetchone()[0] == 100.7


def test_conexao_funciona_com_banco_vazio():
    con = storage.conectar()
    assert con.execute("SELECT count(*) FROM obs").fetchone()[0] == 0


def test_execucoes_sao_registradas():
    r = storage.anexar("ipca", obs([((2020, 1, 1), 0.21)]), execucao_id="e1")
    storage.registrar_execucao("e1", r, iniciada_em=dt.datetime.now(dt.UTC))
    registro = pd.read_parquet(storage.CAMINHO_EXECUCOES)
    assert registro.loc[0, "serie_id"] == "ipca"
    assert registro.loc[0, "novas"] == 1


def test_id_de_execucao_e_unico_e_ordenavel():
    a, b = storage.novo_execucao_id(), storage.novo_execucao_id()
    assert a != b
    assert a[:4].isdigit()
