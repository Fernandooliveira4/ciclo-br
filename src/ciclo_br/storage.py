"""Armazenamento append-only em Parquet, com DuckDB como motor de consulta.

Decisões que este módulo materializa:

1. O repositório É o banco de dados. Um arquivo Parquet por série, versionado no
   Git, de modo que o histórico de commits seja o histórico de coletas. Arquivo
   DuckDB binário foi descartado justamente por não versionar bem.

2. Nada é sobrescrito, nunca. A chave é (serie_id, data_referencia, data_coleta).
   Quando a fonte revisa um valor já publicado, gravamos uma LINHA NOVA em vez de
   corrigir a antiga. Duas consequências:
     - revisão retroativa vira um evento observável, não um dado que some;
     - a partir do dia 1 construímos nosso próprio banco de vintages, que é a
       coisa que não existe publicamente para séries brasileiras.

3. DuckDB lê Parquet direto. Não há importação, não há cópia, não há estado.
"""

from __future__ import annotations

import datetime as dt
import uuid
from dataclasses import dataclass
from pathlib import Path

import duckdb
import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq

from .config import DIR_DADOS

DIR_BRUTO = DIR_DADOS / "raw"
CAMINHO_EXECUCOES = DIR_DADOS / "_execucoes.parquet"

# Diferença mínima para considerar que a fonte revisou um valor. Existe para não
# transformar ruído de ponto flutuante em "revisão detectada".
TOLERANCIA = 1e-9

ESQUEMA = pa.schema([
    ("serie_id", pa.string()),
    ("data_referencia", pa.date32()),
    ("valor", pa.float64()),
    ("data_coleta", pa.timestamp("us", tz="UTC")),
    ("execucao_id", pa.string()),
])

ESQUEMA_EXECUCOES = pa.schema([
    ("execucao_id", pa.string()),
    ("iniciada_em", pa.timestamp("us", tz="UTC")),
    ("serie_id", pa.string()),
    ("novas", pa.int64()),
    ("revisoes", pa.int64()),
    ("inalteradas", pa.int64()),
    ("erro", pa.string()),
])


@dataclass(frozen=True)
class ResultadoAnexo:
    """Quantas observações eram inéditas, revisadas e já conhecidas."""

    serie_id: str
    novas: int
    revisoes: int
    inalteradas: int

    @property
    def gravadas(self) -> int:
        return self.novas + self.revisoes

    def __str__(self) -> str:
        return (f"{self.serie_id}: {self.novas} novas, {self.revisoes} revisões, "
                f"{self.inalteradas} inalteradas")


def novo_execucao_id() -> str:
    """Id de execução legível: carimbo de tempo + sufixo curto."""
    agora = dt.datetime.now(dt.UTC)
    return f"{agora:%Y%m%dT%H%M%SZ}-{uuid.uuid4().hex[:6]}"


def caminho_serie(serie_id: str) -> Path:
    return DIR_BRUTO / f"{serie_id}.parquet"


def ler_bruto(serie_id: str) -> pd.DataFrame:
    """Todas as linhas já gravadas da série, inclusive versões superadas."""
    caminho = caminho_serie(serie_id)
    if not caminho.exists():
        return pd.DataFrame(columns=[c for c in ESQUEMA.names])
    return pq.read_table(caminho).to_pandas()


def ler_vigente(serie_id: str) -> pd.DataFrame:
    """A versão mais recente de cada data de referência."""
    bruto = ler_bruto(serie_id)
    if bruto.empty:
        return bruto
    # Ordenação estável: quando duas coletas caem no mesmo tique do relógio, o
    # desempate é a ordem de gravação no arquivo, que é a ordem cronológica real.
    bruto = bruto.sort_values(["data_referencia", "data_coleta"], kind="stable")
    vigente = bruto.drop_duplicates("data_referencia", keep="last")
    return vigente.reset_index(drop=True)


def anexar(
    serie_id: str,
    observacoes: pd.DataFrame,
    *,
    execucao_id: str,
    coletado_em: dt.datetime | None = None,
) -> ResultadoAnexo:
    """Grava apenas o que é inédito ou foi revisado.

    `observacoes` precisa ter as colunas data_referencia (date) e valor (float).
    Observação já conhecida com o mesmo valor não gera linha: sem isso o arquivo
    cresceria a cada execução diária sem informação nova.
    """
    if observacoes.empty:
        return ResultadoAnexo(serie_id, 0, 0, 0)

    coletado_em = coletado_em or dt.datetime.now(dt.UTC)
    entrada = observacoes[["data_referencia", "valor"]].copy()
    entrada["data_referencia"] = pd.to_datetime(entrada["data_referencia"]).dt.date
    entrada["valor"] = entrada["valor"].astype("float64")
    entrada = entrada.dropna(subset=["valor"]).drop_duplicates(
        "data_referencia", keep="last"
    )

    vigente = ler_vigente(serie_id)
    conhecidos: dict[dt.date, float] = (
        {} if vigente.empty
        else dict(zip(vigente["data_referencia"], vigente["valor"], strict=True))
    )

    novas, revisoes, inalteradas = [], [], 0
    for data_ref, valor in zip(entrada["data_referencia"], entrada["valor"], strict=True):
        anterior = conhecidos.get(data_ref)
        if anterior is None:
            novas.append((data_ref, valor))
        elif abs(anterior - valor) > TOLERANCIA:
            revisoes.append((data_ref, valor))
        else:
            inalteradas += 1

    a_gravar = novas + revisoes
    if a_gravar:
        linhas = pd.DataFrame(a_gravar, columns=["data_referencia", "valor"])
        linhas.insert(0, "serie_id", serie_id)
        linhas["data_coleta"] = coletado_em
        linhas["execucao_id"] = execucao_id
        _acrescentar_parquet(caminho_serie(serie_id), linhas, ESQUEMA)

    return ResultadoAnexo(serie_id, len(novas), len(revisoes), inalteradas)


def registrar_execucao(
    execucao_id: str,
    resultado: ResultadoAnexo,
    *,
    iniciada_em: dt.datetime,
    erro: str | None = None,
) -> None:
    """Trilha de auditoria: o que cada execução fez com cada série."""
    linha = pd.DataFrame([{
        "execucao_id": execucao_id,
        "iniciada_em": iniciada_em,
        "serie_id": resultado.serie_id,
        "novas": resultado.novas,
        "revisoes": resultado.revisoes,
        "inalteradas": resultado.inalteradas,
        "erro": erro,
    }])
    _acrescentar_parquet(CAMINHO_EXECUCOES, linha, ESQUEMA_EXECUCOES)


def _acrescentar_parquet(caminho: Path, linhas: pd.DataFrame, esquema: pa.Schema) -> None:
    caminho.parent.mkdir(parents=True, exist_ok=True)
    nova = pa.Table.from_pandas(linhas, schema=esquema, preserve_index=False)
    tabela = pa.concat_tables([pq.read_table(caminho), nova]) if caminho.exists() else nova
    pq.write_table(tabela, caminho, compression="zstd")


def conectar() -> duckdb.DuckDBPyConnection:
    """Conexão em memória com as visões do projeto sobre os Parquet.

    obs_bruto -> tudo, inclusive versões superadas (é o banco de vintages)
    obs       -> versão vigente de cada observação (é o que a análise consome)
    revisoes  -> apenas observações que a fonte alterou depois de publicar
    """
    con = duckdb.connect(":memory:")
    padrao = (DIR_BRUTO / "*.parquet").as_posix()
    if not any(DIR_BRUTO.glob("*.parquet")):
        con.execute(
            "CREATE VIEW obs_bruto AS SELECT NULL::VARCHAR AS serie_id, "
            "NULL::DATE AS data_referencia, NULL::DOUBLE AS valor, "
            "NULL::TIMESTAMPTZ AS data_coleta, NULL::VARCHAR AS execucao_id, "
            "NULL::BIGINT AS linha WHERE FALSE"
        )
    else:
        # file_row_number preserva a ordem de gravação, que é o desempate quando
        # duas coletas caem no mesmo tique do relógio. Cada série é um arquivo,
        # então a numeração nunca atravessa partições.
        con.execute(f"""
            CREATE VIEW obs_bruto AS
            SELECT serie_id, data_referencia, valor, data_coleta, execucao_id,
                   file_row_number AS linha
            FROM read_parquet('{padrao}', file_row_number = true)
        """)

    con.execute("""
        CREATE VIEW obs AS
        SELECT serie_id, data_referencia, valor, data_coleta
        FROM (
            SELECT *, row_number() OVER (
                PARTITION BY serie_id, data_referencia
                ORDER BY data_coleta DESC, linha DESC
            ) AS rn
            FROM obs_bruto
        )
        WHERE rn = 1
    """)
    con.execute("""
        CREATE VIEW revisoes AS
        SELECT serie_id, data_referencia, count(*) AS versoes,
               min(valor) AS menor, max(valor) AS maior,
               max(data_coleta) AS revisado_em
        FROM obs_bruto
        GROUP BY serie_id, data_referencia
        HAVING count(*) > 1
    """)
    return con
