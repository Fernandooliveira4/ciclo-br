"""Leitura dos artefatos versionados. Nada aqui calcula regime nem busca dado.

Cada artefato é declarado junto com o comando que o produz. Quando um arquivo
falta, o painel não quebra com um traceback: ele diz qual arquivo falta e qual
comando o gera. Num projeto cujo argumento é "o repositório é o banco de dados",
não saber responder de onde veio um número seria a falha mais cara possível.

**Não há cache.** As tabelas têm centenas de linhas, a leitura custa
milissegundos, e a alternativa traria a classe de bug mais irritante de um painel
de dados: a tela continuar mostrando o número velho depois de o pipeline rodar.
"""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass
from pathlib import Path

import pandas as pd

from .. import regime as regime_mod
from .. import storage, transformacao, validacao
from ..config import (
    CAMINHO_CALENDARIO,
    CAMINHO_METODOLOGIA,
    CAMINHO_SURPRESA,
    RAIZ,
    catalogo,
)


@dataclass(frozen=True)
class Artefato:
    rotulo: str
    caminho: Path
    comando: str
    descricao: str


ARTEFATOS: dict[str, Artefato] = {
    "regime": Artefato(
        "Regime", regime_mod.CAMINHO_REGIME, "ciclo-regime",
        "quadrante mês a mês, com e sem a regra de persistência"),
    "derivado": Artefato(
        "Camada derivada", transformacao.CAMINHO_DERIVADO, "ciclo-transformar",
        "eixos dessazonalizados em janela expansiva e momentum"),
    "defasagens": Artefato(
        "Defasagens", validacao.CAMINHO_DEFASAGENS, "ciclo-validar",
        "uma linha por recessão datada, para cada configuração varrida"),
    "validacao": Artefato(
        "Resumo da validação", validacao.CAMINHO_RESUMO, "ciclo-validar",
        "o que cada corte e prazo de persistência custa em atraso"),
    "surpresa": Artefato(
        "Surpresas", CAMINHO_SURPRESA, "ciclo-surpresa",
        "realizado menos o consenso do Focus da véspera, por divulgação"),
    "calendario": Artefato(
        "Calendário", CAMINHO_CALENDARIO, "ciclo-calendario --backfill",
        "datas de divulgação do IBGE, com o período de referência de cada uma"),
    "cronologia": Artefato(
        "Cronologia do CODACE", validacao.CAMINHO_CRONOLOGIA, "transcrição manual",
        "datação oficial de recessões, transcrita da fonte e versionada"),
    "metodologia": Artefato(
        "Metodologia", CAMINHO_METODOLOGIA, "escrita à mão",
        "o documento que o painel não pode contradizer"),
}


class ArtefatoAusente(FileNotFoundError):
    """Falta um arquivo que o painel só lê — e o erro carrega o comando que o gera."""

    def __init__(self, chave: str):
        self.chave = chave
        self.artefato = ARTEFATOS[chave]
        super().__init__(
            f"{self.artefato.caminho} não existe — rode `{self.artefato.comando}`")


def _caminho(chave: str) -> Path:
    artefato = ARTEFATOS[chave]
    if not artefato.caminho.exists():
        raise ArtefatoAusente(chave)
    return artefato.caminho


# -------------------------------------------------------------------- regime

def regime() -> pd.DataFrame:
    """A série de quadrantes como o classificador gravou, sem conversão."""
    return pd.read_parquet(_caminho("regime"))


def regime_mensal() -> pd.DataFrame:
    """A mesma série pronta para gráfico: data em datetime e distância ao corte.

    A distância ao corte existe porque o corte de inflação **se move** — é a
    mediana expansiva do próprio histórico. Num gráfico de quadrantes com eixos
    crus, a fronteira seria uma linha que anda, e o leitor teria que adivinhar
    onde ela estava em cada mês. Plotando a distância, a fronteira é o zero em
    todos os meses, e o quadrante que se vê é exatamente o que o classificador
    diz.
    """
    reg = regime()
    return reg.assign(
        data=pd.to_datetime(reg["data_referencia"]),
        distancia_crescimento=reg["eixo_crescimento"] - reg["corte_crescimento"],
        distancia_inflacao=reg["eixo_inflacao"] - reg["corte_inflacao"],
    )


def resumo_regime() -> dict:
    """O mesmo resumo que `ciclo-regime` imprime — não uma segunda versão dele."""
    return regime_mod.resumo(regime())


def episodios(reg: pd.DataFrame, coluna: str = "quadrante") -> pd.DataFrame:
    """Blocos contíguos do mesmo quadrante, como (início, fim, duração).

    O gráfico de faixas precisa de um retângulo por episódio; desenhar um por mês
    produziria centenas de marcas com borda visível entre meses iguais.
    """
    vazio = pd.DataFrame(columns=["quadrante", "inicio", "ultimo", "fim", "meses"])
    classificado = reg[reg[coluna].notna()].sort_values("data")
    if classificado.empty:
        return vazio

    grupo = (classificado[coluna] != classificado[coluna].shift()).cumsum()
    blocos = []
    for _, parte in classificado.groupby(grupo, sort=True):
        blocos.append({
            "quadrante": parte[coluna].iloc[0],
            "inicio": parte["data"].iloc[0],
            "ultimo": parte["data"].iloc[-1],
            # `fim` é o começo do mês seguinte, e existe separado de `ultimo`
            # porque o gráfico precisa que o retângulo cubra o último mês
            # inteiro, enquanto a tabela precisa do nome desse mês.
            "fim": parte["data"].iloc[-1] + pd.offsets.MonthBegin(1),
            "meses": len(parte),
        })
    return pd.DataFrame(blocos)


# ----------------------------------------------------------------- validação

def cronologia() -> pd.DataFrame:
    """A datação do CODACE, revalidada na leitura.

    `carregar_cronologia` recusa pico depois do vale, recessões sobrepostas e
    fora de ordem. O painel passa pela mesma porta que a CI: se a transcrição for
    corrompida, a tela reclama em vez de desenhar uma faixa errada.
    """
    return validacao.carregar_cronologia(_caminho("cronologia"))


def recessoes() -> pd.DataFrame:
    """Janelas de recessão em datetime, para sombrear os gráficos."""
    crono = cronologia()
    return pd.DataFrame({
        "recessao_id": crono["recessao_id"],
        "granularidade": crono["granularidade"],
        "inicio": crono["inicio"].dt.to_timestamp(),
        "fim": (crono["fim"] + 1).dt.to_timestamp(),
        "duracao": crono["duracao"],
    })


def validacao_resumo() -> pd.DataFrame:
    return pd.read_csv(_caminho("validacao"))


def validacao_defasagens() -> pd.DataFrame:
    return pd.read_csv(_caminho("defasagens"))


def configuracao_vigente() -> dict:
    """A linha da varredura que corresponde ao classificador em uso.

    Sem isso o painel poderia exibir a defasagem de uma configuração que não é a
    que gerou os quadrantes mostrados ao lado.
    """
    resumo = validacao_resumo()
    linha = resumo[
        (resumo["corte_crescimento"] == regime_mod.CORTE_CRESCIMENTO)
        & (resumo["persistencia"] == regime_mod.MESES_PERSISTENCIA)
    ]
    return {} if linha.empty else linha.iloc[0].to_dict()


def defasagens_vigentes() -> pd.DataFrame:
    """Uma linha por recessão datada, na configuração que o projeto usa."""
    tabela = validacao_defasagens()
    return tabela[
        (tabela["corte_crescimento"] == regime_mod.CORTE_CRESCIMENTO)
        & (tabela["persistencia"] == regime_mod.MESES_PERSISTENCIA)
    ].reset_index(drop=True)


# ----------------------------------------------------------------- surpresas

def surpresas() -> pd.DataFrame:
    tabela = pd.read_csv(_caminho("surpresa"))
    for coluna in ("data_referencia", "data_divulgacao", "data_consenso"):
        tabela[coluna] = pd.to_datetime(tabela[coluna])
    return tabela


def surpresas_por_par(tabela: pd.DataFrame | None = None) -> pd.DataFrame:
    """Estatística de cada par, com a última divulgação medida.

    O desvio padrão histórico não é enfeite: sem escala não dá para dizer se uma
    surpresa de 0,15 p.p. é notícia ou rotina.
    """
    tabela = surpresas() if tabela is None else tabela
    linhas = []
    for nome, grupo in tabela.groupby("par"):
        grupo = grupo.sort_values("data_divulgacao", kind="stable")
        ultima = grupo.iloc[-1]
        linhas.append({
            "par": nome,
            "observacoes": len(grupo),
            "media": float(grupo["surpresa"].mean()),
            "desvio_padrao": float(grupo["surpresa"].std()),
            "primeiras_leituras": int(grupo["primeira_leitura"].sum()),
            "dias_sem_mudanca_medio": float(grupo["dias_sem_mudanca"].mean()),
            "desde": grupo["data_divulgacao"].iloc[0],
            "ultima_referencia": ultima["data_referencia"],
            "ultima_divulgacao": ultima["data_divulgacao"],
            "realizado": float(ultima["realizado"]),
            "consenso": float(ultima["consenso"]),
            "surpresa": float(ultima["surpresa"]),
            "unidade": ultima["unidade"],
            "primeira_leitura": bool(ultima["primeira_leitura"]),
        })
    return pd.DataFrame(linhas).sort_values("par").reset_index(drop=True)


# ---------------------------------------------------------------- calendário

def calendario() -> pd.DataFrame:
    agenda = pd.read_parquet(_caminho("calendario"))
    for coluna in ("data_divulgacao", "data_referencia"):
        agenda[coluna] = pd.to_datetime(agenda[coluna])
    return agenda.sort_values("data_divulgacao").reset_index(drop=True)


def proximas_divulgacoes(limite: int = 6, *, hoje: dt.date | None = None) -> pd.DataFrame:
    hoje = hoje or dt.date.today()
    agenda = calendario()
    futuras = agenda[agenda["data_divulgacao"].dt.date >= hoje]
    return futuras.head(limite).reset_index(drop=True)


# ------------------------------------------------------------------- séries

def derivado() -> pd.DataFrame:
    tabela = pd.read_parquet(_caminho("derivado"))
    tabela["data_referencia"] = pd.to_datetime(tabela["data_referencia"])
    return tabela


def receitas() -> pd.DataFrame:
    """De onde vem cada série derivada, declarado no próprio módulo que a produz."""
    return pd.DataFrame([
        {"serie_id": sid, **receita} for sid, receita in transformacao.RECEITAS.items()
    ])


def fichas() -> pd.DataFrame:
    """O catálogo de séries como tabela — a ficha obrigatória de cada uma."""
    return pd.DataFrame([
        {
            "id": serie.id,
            "nome": serie.nome,
            "bloco": serie.bloco,
            "papel": serie.papel,
            "fonte": serie.fonte,
            "codigo": str(serie.codigo or serie.indicador or ""),
            "unidade": serie.unidade,
            "periodicidade": serie.periodicidade,
            "ajuste_sazonal": serie.ajuste_sazonal,
            "transformacao": serie.transformacao or "",
            "notas": " ".join((serie.notas or "").split()),
        }
        for serie in catalogo().values()
    ])


def serie_bruta(serie_id: str) -> pd.DataFrame:
    """Versão vigente de cada observação, com a data em que foi coletada."""
    vigente = storage.ler_vigente(serie_id)
    colunas = ["data_referencia", "valor", "data_coleta"]
    if vigente.empty:
        return pd.DataFrame(columns=colunas)
    return pd.DataFrame({
        "data_referencia": pd.to_datetime(pd.Series(list(vigente["data_referencia"]))),
        "valor": pd.Series(list(vigente["valor"]), dtype="float64"),
        "data_coleta": pd.to_datetime(pd.Series(list(vigente["data_coleta"]))),
    })


def revisoes(serie_id: str) -> pd.DataFrame:
    """Observações que a fonte alterou depois de publicar.

    Esta tabela só existe porque nada é sobrescrito. Em quase todo painel macro
    ela seria impossível de montar: o valor antigo teria sumido no lugar do novo.
    """
    colunas = ["data_referencia", "valor_anterior", "valor", "diferenca", "revisado_em"]
    bruto = storage.ler_bruto(serie_id)
    if bruto.empty:
        return pd.DataFrame(columns=colunas)

    bruto = bruto.sort_values(["data_referencia", "data_coleta"], kind="stable")
    repetidas = bruto.groupby("data_referencia")["valor"].transform("size") > 1
    revistas = bruto[repetidas].copy()
    if revistas.empty:
        return pd.DataFrame(columns=colunas)

    revistas["valor_anterior"] = revistas.groupby("data_referencia")["valor"].shift()
    revistas = revistas.dropna(subset=["valor_anterior"])
    if revistas.empty:
        return pd.DataFrame(columns=colunas)

    return pd.DataFrame({
        "data_referencia": pd.to_datetime(pd.Series(list(revistas["data_referencia"]))),
        "valor_anterior": revistas["valor_anterior"].to_numpy(dtype="float64"),
        "valor": revistas["valor"].to_numpy(dtype="float64"),
        "diferenca": (revistas["valor"] - revistas["valor_anterior"]).to_numpy(
            dtype="float64"),
        "revisado_em": pd.to_datetime(pd.Series(list(revistas["data_coleta"]))),
    }).sort_values("revisado_em", ascending=False).reset_index(drop=True)


# -------------------------------------------------------------- procedência

def metodologia() -> str:
    return _caminho("metodologia").read_text(encoding="utf-8")


def procedencia() -> pd.DataFrame:
    """Todo arquivo que o painel lê, com estado e data de geração.

    É a resposta literal a "de onde vem o que está na tela", e o lugar onde a
    ausência de um artefato vira informação em vez de exceção.
    """
    linhas = []
    for chave, artefato in ARTEFATOS.items():
        existe = artefato.caminho.exists()
        estatistica = artefato.caminho.stat() if existe else None
        linhas.append({
            "chave": chave,
            "artefato": artefato.rotulo,
            "arquivo": artefato.caminho.relative_to(RAIZ).as_posix(),
            "existe": existe,
            "gerado_por": artefato.comando,
            "descricao": artefato.descricao,
            "modificado_em": (
                dt.datetime.fromtimestamp(estatistica.st_mtime, dt.UTC)
                if estatistica else None
            ),
            "kb": round(estatistica.st_size / 1024, 1) if estatistica else 0.0,
        })
    return pd.DataFrame(linhas)
