"""Carrega e valida as fichas de série de config/series.yaml.

A ficha é a fonte da verdade sobre cada série: código na fonte, unidade,
periodicidade, papel no projeto e transformação aplicada. Nenhuma série pode
ser ingerida sem ficha, e a validação abaixo é o que torna essa regra real em
vez de apenas uma boa intenção no README.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml

RAIZ = Path(__file__).resolve().parents[2]
CAMINHO_SERIES = RAIZ / "config" / "series.yaml"
DIR_DADOS = RAIZ / "data"

PAPEIS = {"eixo_crescimento", "eixo_inflacao", "contexto", "auditoria", "surpresa"}
AJUSTES = {"origem", "proprio", "nao_aplicavel"}
PERIODICIDADES = {"diaria", "mensal", "trimestral"}


class FichaInvalida(ValueError):
    """Uma ficha de série está incompleta ou inconsistente."""


@dataclass(frozen=True)
class Serie:
    id: str
    fonte: str
    nome: str
    bloco: str
    unidade: str
    periodicidade: str
    ajuste_sazonal: str
    papel: str
    codigo: int | None = None
    recurso: str | None = None
    indicador: str | None = None
    base_calculo: int | None = None
    inicio: str | None = None
    transformacao: str | None = None
    status: str | None = None
    notas: str | None = None
    extra: dict[str, Any] = field(default_factory=dict, repr=False)

    @property
    def implementada(self) -> bool:
        """Séries marcadas como planejadas ainda não têm cliente de ingestão."""
        return self.status not in {"planejado_s2"}


_CAMPOS = {f for f in Serie.__dataclass_fields__ if f != "extra"}


def _validar(bruto: dict[str, Any]) -> None:
    sid = bruto.get("id", "<sem id>")
    faltando = [c for c in ("id", "fonte", "nome", "bloco", "unidade",
                            "periodicidade", "ajuste_sazonal", "papel")
                if not bruto.get(c)]
    if faltando:
        raise FichaInvalida(f"série {sid}: campos obrigatórios ausentes: {faltando}")
    if bruto["papel"] not in PAPEIS:
        raise FichaInvalida(f"série {sid}: papel {bruto['papel']!r} fora de {sorted(PAPEIS)}")
    if bruto["ajuste_sazonal"] not in AJUSTES:
        raise FichaInvalida(
            f"série {sid}: ajuste_sazonal {bruto['ajuste_sazonal']!r} fora de {sorted(AJUSTES)}"
        )
    if bruto["periodicidade"] not in PERIODICIDADES:
        raise FichaInvalida(
            f"série {sid}: periodicidade {bruto['periodicidade']!r} "
            f"fora de {sorted(PERIODICIDADES)}"
        )
    if bruto["fonte"] == "sgs" and not bruto.get("codigo"):
        raise FichaInvalida(f"série {sid}: fonte sgs exige codigo")
    if bruto["fonte"] == "focus" and not (bruto.get("recurso") and bruto.get("indicador")):
        raise FichaInvalida(f"série {sid}: fonte focus exige recurso e indicador")


def carregar(caminho: Path | None = None) -> dict[str, Serie]:
    """Lê o catálogo e devolve {id: Serie}, validando cada ficha."""
    caminho = caminho or CAMINHO_SERIES
    dados = yaml.safe_load(caminho.read_text(encoding="utf-8"))

    catalogo: dict[str, Serie] = {}
    for bruto in dados.get("series", []):
        _validar(bruto)
        conhecidos = {k: v for k, v in bruto.items() if k in _CAMPOS}
        extra = {k: v for k, v in bruto.items() if k not in _CAMPOS}
        serie = Serie(**conhecidos, extra=extra)
        if serie.id in catalogo:
            raise FichaInvalida(f"série {serie.id}: id duplicado no catálogo")
        catalogo[serie.id] = serie

    if not catalogo:
        raise FichaInvalida(f"nenhuma série encontrada em {caminho}")
    return catalogo


@lru_cache(maxsize=1)
def catalogo() -> dict[str, Serie]:
    return carregar()


@lru_cache(maxsize=1)
def calendario_produtos(caminho: Path | None = None) -> dict[int, list[str]]:
    """Mapa produto_id do IBGE -> ids de série que aquele produto alimenta."""
    caminho = caminho or CAMINHO_SERIES
    dados = yaml.safe_load(caminho.read_text(encoding="utf-8"))
    produtos = (dados.get("calendario") or {}).get("produtos") or {}

    conhecidas = catalogo()
    for produto_id, ids in produtos.items():
        orfas = [i for i in ids if i not in conhecidas]
        if orfas:
            raise FichaInvalida(
                f"calendário: produto {produto_id} aponta para série sem ficha: {orfas}"
            )
    return {int(k): list(v) for k, v in produtos.items()}


def series_da_fonte(fonte: str, *, apenas_implementadas: bool = True) -> list[Serie]:
    return [
        s for s in catalogo().values()
        if s.fonte == fonte and (s.implementada or not apenas_implementadas)
    ]
