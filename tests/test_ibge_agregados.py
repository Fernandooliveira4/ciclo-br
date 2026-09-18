import datetime as dt

import pandas as pd
import pytest

from ciclo_br.ingestion import ibge_agregados as ibge


def carga(serie, *, categoria=93406, classificacao=11255, localidade="1"):
    """Uma resposta da API de agregados, no formato que o IBGE devolve."""
    return [{
        "id": "585",
        "variavel": "Valores a precos correntes",
        "unidade": "Milhoes de Reais",
        "resultados": [{
            "classificacoes": [{
                "id": str(classificacao),
                "nome": "Setores e subsetores",
                "categoria": {str(categoria): "Formacao bruta de capital fixo"},
            }],
            "series": [{
                "localidade": {"id": localidade, "nivel": {"id": "N1"}, "nome": "Brasil"},
                "serie": serie,
            }],
        }],
    }]


@pytest.mark.parametrize(
    ("periodo", "esperado"),
    [
        ("199601", dt.date(1996, 1, 1)),
        ("199602", dt.date(1996, 4, 1)),
        ("199603", dt.date(1996, 7, 1)),
        ("199604", dt.date(1996, 10, 1)),
        ("202602", dt.date(2026, 4, 1)),
    ],
)
def test_periodo_trimestral_vira_o_primeiro_dia_do_trimestre(periodo, esperado):
    assert ibge._data_do_periodo(periodo, "trimestral") == esperado


@pytest.mark.parametrize("periodo", ["2026", "", None, "202605", "202600", "20260a", "1996013"])
def test_periodo_fora_do_formato_vira_buraco_em_vez_de_excecao(periodo):
    """O buraco é pego pelo portão de grade, com a data exata em volta dele.

    Levantar aqui derrubaria a série inteira por causa de um registro, que é o
    oposto do que se quer: um ponto estranho tem que ficar visível, não fatal.
    """
    assert ibge._data_do_periodo(periodo, "trimestral") is None


def test_periodo_mensal_e_recusado_em_vez_de_adivinhado():
    """'202601' é janeiro numa tabela mensal e 1º trimestre nesta.

    Os dois caem na mesma faixa de dois dígitos, então não há como distinguir
    pelo valor. Adivinhar erraria um ano inteiro de datas em silêncio.
    """
    with pytest.raises(ibge.ErroIBGE):
        ibge._data_do_periodo("202601", "mensal")


@pytest.mark.parametrize(
    ("bruto", "esperado"),
    [("...", None), ("..", None), ("-", None), ("X", None), ("", None), (None, None),
     ("552092", 552092.0), ("16,1", 16.1), ("16.1", 16.1), (3425728, 3425728.0)],
)
def test_marcadores_de_ausencia_do_ibge_nao_viram_numero(bruto, esperado):
    """O IBGE marca ausência com reticências, traço e X, não com null."""
    assert ibge._converter_valor(bruto) == esperado


def test_a_serie_extraida_e_a_da_localidade_brasil():
    dados = carga({"202601": "1"})
    dados[0]["resultados"][0]["series"].insert(0, {
        "localidade": {"id": "2", "nome": "Nordeste"},
        "serie": {"202601": "999"},
    })
    assert ibge._extrair(dados, 93406, classificacao=11255) == {"202601": "1"}


def test_categoria_diferente_da_pedida_vira_erro():
    """Gravar consumo do governo dentro de fbcf_corrente.parquet passaria nos
    oito portões: mesma unidade, mesma ordem de grandeza, mesma sazonalidade e
    mesma grade trimestral. Não há camada a jusante capaz de pegar isso."""
    dados = carga({"202601": "1"}, categoria=93405)
    with pytest.raises(ibge.ErroIBGE, match="categoria pedida"):
        ibge._extrair(dados, 93406, classificacao=11255)


def test_resposta_sem_a_localidade_brasil_vira_erro():
    dados = carga({"202601": "1"}, localidade="2")
    with pytest.raises(ibge.ErroIBGE, match="Brasil"):
        ibge._extrair(dados, 93406, classificacao=11255)


def test_http_404_e_ficha_errada_e_nao_ausencia_de_dado(monkeypatch):
    """Ao contrário do SGS, 404 aqui é tabela ou variável inexistente.

    Devolver lista vazia transformaria erro de ficha em série vazia, e o portão
    de qualidade reclamaria da coisa errada.
    """
    class RespostaFalsa:
        status_code = 404

        def json(self):  # pragma: no cover - não deve ser chamado
            raise AssertionError("não deveria decodificar um 404")

    monkeypatch.setattr(ibge.requests, "get", lambda *a, **k: RespostaFalsa())
    with pytest.raises(ibge.ErroIBGE, match="HTTP 404"):
        ibge._consultar.retry_with(stop=lambda *_: True)(
            1846, 585, 93406, classificacao=11255
        )


def test_resposta_nao_json_vira_erro_explicito(monkeypatch):
    class RespostaFalsa:
        status_code = 200

        def json(self):
            raise ValueError("not json")

    monkeypatch.setattr(ibge.requests, "get", lambda *a, **k: RespostaFalsa())
    with pytest.raises(ibge.ErroIBGE, match="não-JSON"):
        ibge._consultar.retry_with(stop=lambda *_: True)(
            1846, 585, 93406, classificacao=11255
        )


def test_a_consulta_pede_o_brasil_e_se_identifica(monkeypatch):
    capturado = {}

    class RespostaFalsa:
        status_code = 200

        def json(self):
            return carga({"202601": "1"})

    def falsa_get(url, **kwargs):
        capturado["url"] = url
        capturado.update(kwargs)
        return RespostaFalsa()

    monkeypatch.setattr(ibge.requests, "get", falsa_get)
    ibge._consultar(1846, 585, 93406, classificacao=11255)

    assert capturado["params"]["localidades"] == "N1[all]"
    assert capturado["params"]["classificacao"] == "11255[93406]"
    assert "User-Agent" in capturado["headers"]
    assert "1846/periodos/all/variaveis/585" in capturado["url"]


def test_buscar_ordena_e_descarta_periodos_anteriores_ao_pedido(monkeypatch):
    monkeypatch.setattr(
        ibge, "_consultar",
        lambda *a, **k: carga({"202602": "3", "199601": "1", "202601": "2"}),
    )
    df = ibge.buscar(1846, 585, 93406, classificacao=11255, desde=dt.date(2026, 1, 1))
    assert list(df["data_referencia"]) == [dt.date(2026, 1, 1), dt.date(2026, 4, 1)]
    assert list(df["valor"]) == [2.0, 3.0]


def test_buscar_descarta_periodo_ilegivel_e_valor_ausente(monkeypatch):
    monkeypatch.setattr(
        ibge, "_consultar",
        lambda *a, **k: carga({"202601": "...", "202602": "5", "2026": "9"}),
    )
    df = ibge.buscar(1846, 585, 93406, classificacao=11255)
    assert list(df["data_referencia"]) == [dt.date(2026, 4, 1)]


def test_buscar_sem_dados_devolve_dataframe_vazio_com_colunas(monkeypatch):
    monkeypatch.setattr(ibge, "_consultar", lambda *a, **k: carga({}))
    df = ibge.buscar(1846, 585, 93406, classificacao=11255)
    assert df.empty
    assert list(df.columns) == ["data_referencia", "valor"]


def test_dataframe_de_saida_tem_os_mesmos_tipos_que_o_do_sgs(monkeypatch):
    """É o que permite `storage.anexar` não saber de que fonte veio a linha."""
    monkeypatch.setattr(ibge, "_consultar", lambda *a, **k: carga({"202601": "1.5"}))
    df = ibge.buscar(1846, 585, 93406, classificacao=11255)
    assert isinstance(df.loc[0, "data_referencia"], dt.date)
    assert pd.api.types.is_float_dtype(df["valor"])
