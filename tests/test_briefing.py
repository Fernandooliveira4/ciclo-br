"""Testes do briefing.

O teste que justifica o pacote inteiro é `test_conferir_recusa_numero_que_nao_esta_nos_fatos`:
é ele que transforma "o modelo não pode inventar um dado" de promessa de README
em comportamento verificado. Os demais cuidam de que a recusa realmente leve ao
gerador determinístico, de que o determinístico também obedeça à mesma régua, e
de que a auditoria pegue um briefing editado à mão depois de publicado.
"""

from __future__ import annotations

import datetime as dt
import json
from dataclasses import dataclass

import pytest

from ciclo_br.briefing import cli, llm, modelo, publicacao
from ciclo_br.briefing import fatos as fatos_mod


@pytest.fixture
def diretorio(tmp_path, monkeypatch):
    monkeypatch.setattr(publicacao, "DIR_BRIEFINGS", tmp_path / "briefings")
    monkeypatch.setattr(publicacao, "CAMINHO_INDICE",
                        tmp_path / "briefings" / "indice.csv")
    return tmp_path


FATOS = {
    "versao": 1,
    "data": "2026-09-13",
    "replay": False,
    "regime": {"quadrante": "Expansão", "desde": "dezembro de 2025",
               "meses_no_quadrante": 7, "referencia": "junho de 2026",
               "crescimento": "+0,7%", "corte_de_crescimento": "0,0",
               "inflacao": "4,2%", "corte_de_inflacao": "5,3",
               "virada_pendente": None, "meses_esperando_confirmacao": 0,
               "meses_para_confirmar": 3},
    "validacao": {},
    "divulgacoes_do_dia": [{
        "par": "ipca", "referencia": "agosto de 2026", "divulgado_em": "11/09/2026",
        "realizado": "-0,32", "consenso": "-0,23", "surpresa": "-0,09 p.p.",
        "desvios_padrao": "0,9", "consenso_apurado_em": "04/09/2026",
        "dias_sem_mudanca": 7, "realizado_ja_revisado": False,
    }],
    "divulgacoes_anteriores": [],
    "proximas_divulgacoes": [],
    "avisos": [],
}
FATOS["numeros_permitidos"] = fatos_mod.numeros_permitidos(FATOS)

MUDANCAS = {"primeiro": True, "houve": True, "divulgacoes": ["ipca agosto de 2026"]}


# ------------------------------------------------------- a régua dos números

def test_numeros_permitidos_sai_dos_proprios_fatos():
    permitidos = set(FATOS["numeros_permitidos"])
    assert {"0,32", "0,23", "0,09", "0,7", "4,2", "2026", "7"} <= permitidos


def test_numeros_inventados_ignora_pontuacao_final():
    """'em 2026.' traz o token '2026.' e o ponto é do português, não do número."""
    assert fatos_mod.numeros_inventados("saiu em 2026.", ["2026"]) == []


def test_numeros_inventados_encontra_o_que_nao_esta_nos_fatos():
    assert fatos_mod.numeros_inventados(
        "o consenso era 0,99", FATOS["numeros_permitidos"]) == ["0,99"]


# ----------------------------------------------------------- a verificação

def test_conferir_recusa_numero_que_nao_esta_nos_fatos():
    """O teste que sustenta a afirmação central do projeto sobre o LLM."""
    motivo = llm.conferir("O IPCA veio a -0,32, contra 0,99 esperado.", FATOS)
    assert motivo and "0,99" in motivo


def test_conferir_aceita_texto_que_so_copia_os_fatos():
    texto = ("**IPCA de agosto de 2026 em -0,32.** O consenso da véspera era "
             "-0,23, então a surpresa foi de -0,09 p.p.")
    assert llm.conferir(texto, FATOS) is None


def test_conferir_recusa_previsao_e_recomendacao():
    for texto in ("Recomendamos cautela.", "Esperamos алgo diferente.",
                  "A inflação deve subir."):
        assert llm.conferir(texto, FATOS) is not None


def test_conferir_permite_descrever_o_que_o_consenso_projetava():
    """Bloquear toda palavra de futuro censuraria a frase mais útil do briefing."""
    assert llm.conferir("O consenso previa -0,23 e o número veio a -0,32.",
                        FATOS) is None


def test_conferir_recusa_titulos_e_texto_vazio():
    assert llm.conferir("# Briefing\n\ntexto", FATOS) is not None
    assert llm.conferir("   ", FATOS) is not None


def test_conferir_recusa_texto_longo_demais():
    assert llm.conferir("palavra " * 400, FATOS) is not None


# ------------------------------------------------------------ o cliente falso

@dataclass
class _Bloco:
    text: str
    type: str = "text"


@dataclass
class _Resposta:
    content: list


class ClienteFalso:
    def __init__(self, texto: str | None = None, erro: Exception | None = None):
        self.texto, self.erro = texto, erro
        self.messages = self

    def create(self, **kwargs):
        self.recebido = kwargs
        if self.erro:
            raise self.erro
        return _Resposta([_Bloco(self.texto)])


def test_texto_aprovado_do_modelo_e_usado():
    cliente = ClienteFalso("**IPCA de agosto de 2026 em -0,32**, contra -0,23.")
    resultado = llm.escrever(FATOS, MUDANCAS, cliente=cliente)
    assert resultado.texto and resultado.motivo is None
    assert resultado.modelo == llm.MODELO


def test_texto_reprovado_e_descartado_inteiro():
    """Recusa não corrige: não há como decidir automaticamente o que estava certo."""
    cliente = ClienteFalso("O IPCA veio a 9,99.")
    resultado = llm.escrever(FATOS, MUDANCAS, cliente=cliente)
    assert resultado.texto is None
    assert "9,99" in resultado.motivo


def test_falha_de_rede_nao_derruba_o_briefing():
    resultado = llm.escrever(FATOS, MUDANCAS,
                             cliente=ClienteFalso(erro=TimeoutError("estourou")))
    assert resultado.texto is None
    assert "TimeoutError" in resultado.motivo


def test_o_modelo_recebe_os_fatos_e_mais_nada():
    cliente = ClienteFalso("-0,32 e -0,23.")
    llm.escrever(FATOS, MUDANCAS, cliente=cliente)
    enviado = cliente.recebido["messages"][0]["content"]
    assert "numeros_permitidos" in enviado
    assert cliente.recebido["model"] == llm.MODELO
    assert "não deve recorrer" in cliente.recebido["system"]


# -------------------------------------------------- o gerador determinístico

def test_o_gerador_deterministico_nao_inventa_numero():
    """Se um dia o template escrever um valor fora dos fatos, isto reprova."""
    texto = modelo.escrever(FATOS, MUDANCAS)
    assert fatos_mod.numeros_inventados(texto, FATOS["numeros_permitidos"]) == []


def test_o_gerador_deterministico_anuncia_virada_pendente():
    fatos = json.loads(json.dumps(FATOS))
    fatos["regime"]["virada_pendente"] = "Desaceleração"
    fatos["regime"]["meses_esperando_confirmacao"] = 2
    fatos["numeros_permitidos"] = fatos_mod.numeros_permitidos(fatos)
    texto = modelo.escrever(fatos, MUDANCAS)
    assert "Desaceleração" in texto and "confirmar" in texto
    assert fatos_mod.numeros_inventados(texto, fatos["numeros_permitidos"]) == []


def test_sem_divulgacao_o_texto_diz_que_nao_houve():
    fatos = json.loads(json.dumps(FATOS))
    fatos["divulgacoes_do_dia"] = []
    assert "Sem divulgação nova" in modelo.escrever(fatos, MUDANCAS)


# --------------------------------------------------------------- o gatilho

def test_sem_fatos_anteriores_tudo_e_novidade():
    assert fatos_mod.mudancas(FATOS, None)["houve"] is True


def test_fatos_iguais_nao_geram_briefing():
    assert fatos_mod.mudancas(FATOS, FATOS)["houve"] is False


def test_divulgacao_nova_gera_briefing():
    anteriores = json.loads(json.dumps(FATOS))
    anteriores["divulgacoes_do_dia"] = []
    diff = fatos_mod.mudancas(FATOS, anteriores)
    assert diff["houve"] is True
    assert diff["divulgacoes"] == ["ipca agosto de 2026"]


def test_troca_de_quadrante_gera_briefing():
    anteriores = json.loads(json.dumps(FATOS))
    anteriores["regime"]["quadrante"] = "Aquecimento"
    diff = fatos_mod.mudancas(FATOS, anteriores)
    assert diff["quadrante_mudou"] is True
    assert diff["quadrante_anterior"] == "Aquecimento"


# -------------------------------------------------------------- publicação

def _registro(texto="**IPCA em -0,32**, contra -0,23."):
    return publicacao.montar(FATOS, MUDANCAS, texto, gerador="modelo")


def test_publicar_grava_o_par_de_arquivos(diretorio):
    registro = _registro()
    assert publicacao.publicar(registro) is True
    assert publicacao.caminho_md("2026-09-13").exists()
    assert publicacao.caminho_json("2026-09-13").exists()
    assert publicacao.CAMINHO_INDICE.exists()


def test_publicar_e_idempotente(diretorio):
    registro = _registro()
    publicacao.publicar(registro)
    assert publicacao.publicar(registro) is False


def test_o_rodape_diz_quem_escreveu_e_por_que(diretorio):
    registro = publicacao.montar(FATOS, MUDANCAS, "texto", gerador="modelo",
                                 modelo=llm.MODELO,
                                 motivo="texto do modelo recusado — números fora")
    rodape = publicacao.rodape(registro)
    assert "gerador determinístico" in rodape
    assert "números fora" in rodape


def test_replay_nao_aponta_para_arquivo_que_nao_existe():
    fatos = json.loads(json.dumps(FATOS))
    fatos["replay"] = True
    registro = publicacao.montar(fatos, MUDANCAS, "texto", gerador="modelo")
    rodape = publicacao.rodape(registro)
    assert "não publicados" in rodape
    assert "data/briefings/" not in rodape


def test_auditoria_pega_briefing_editado_a_mao(diretorio):
    publicacao.publicar(_registro())
    md = publicacao.caminho_md("2026-09-13")
    md.write_text(md.read_text(encoding="utf-8").replace("-0,32", "-9,99"),
                  encoding="utf-8")
    problemas = publicacao.auditar()
    assert any("editado à mão" in p for p in problemas)


def test_auditoria_pega_numero_fora_dos_fatos(diretorio):
    publicacao.publicar(_registro(texto="O IPCA veio a 9,99."))
    assert any("9,99" in p for p in publicacao.auditar())


def test_auditoria_aprova_briefing_integro(diretorio):
    publicacao.publicar(_registro())
    assert publicacao.auditar() == []


# --------------------------------------------------------------------- CLI

def test_o_comando_publica_e_depois_fica_calado(diretorio, monkeypatch):
    """Na maior parte dos dias não há o que dizer, e o comando não diz."""
    monkeypatch.setattr(llm, "disponivel", lambda: False)
    assert cli.main([]) == 0
    publicados = publicacao.publicados()
    assert len(publicados) == 1

    assert cli.main([]) == 0
    assert len(publicacao.publicados()) == 1


def test_sem_llm_usa_o_gerador_deterministico(diretorio):
    assert cli.main(["--sem-llm"]) == 0
    registro = publicacao.publicados()[0]
    assert registro["gerador"] == "modelo"
    assert "linha de comando" in registro["motivo"]


def test_auditar_pela_linha_de_comando(diretorio):
    cli.main(["--sem-llm"])
    assert cli.main(["--auditar"]) == 0


def test_replay_nao_grava_nada(diretorio, capsys):
    data = _primeira_divulgacao()
    assert cli.main(["--replay", data.isoformat(), "--sem-llm"]) == 0
    assert capsys.readouterr().out.strip()
    assert publicacao.publicados() == []


def test_replay_recua_o_regime_pela_defasagem_de_publicacao():
    """Em 3 de março, o IBC-Br de março ainda não existia."""
    data = dt.date(2026, 3, 3)
    reconstruido = fatos_mod.construir(ate=data)
    assert reconstruido["replay"] is True
    assert "janeiro de 2026" == reconstruido["regime"]["referencia"]
    assert any("reconstrução" in a.lower() for a in reconstruido["avisos"])


def test_replay_recusa_data_sem_divulgacao(diretorio):
    assert cli.main(["--replay", "1999-01-01", "--sem-llm"]) == 1


def _primeira_divulgacao() -> dt.date:
    from ciclo_br import artefatos

    return artefatos.surpresas()["data_divulgacao"].min().date()


# ------------------------------------------- os fatos sobre o dado de verdade

def test_os_fatos_do_repositorio_sustentam_o_texto():
    """O gerador determinístico rodando sobre os artefatos versionados."""
    fatos = fatos_mod.construir()
    texto = modelo.escrever(fatos, fatos_mod.mudancas(fatos, None))
    assert fatos_mod.numeros_inventados(texto, fatos["numeros_permitidos"]) == []
    assert fatos["regime"]["quadrante"]
