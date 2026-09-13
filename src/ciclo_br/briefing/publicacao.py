"""Gravação dos briefings: o par `.md` + `.json`, o índice e a auditoria.

Cada briefing é gravado duas vezes, e não por descuido. O `.md` é o que se lê; o
`.json` é **o que o texto viu** — os fatos fechados, quem escreveu, e o motivo de
uma eventual recusa. Sem o segundo arquivo, "o modelo não pode inventar número"
seria uma afirmação sobre o passado que ninguém consegue conferir.

A auditoria (`auditar`) refaz a conferência sobre tudo que já foi publicado: todo
número do texto tem que estar nos fatos daquele mesmo briefing, e o `.md` tem que
conter o texto do `.json` palavra por palavra. A segunda checagem pega a edição
manual — um briefing corrigido à mão depois de publicado deixaria de ser o que a
verificação aprovou.
"""

from __future__ import annotations

import datetime as dt
import hashlib
import json
import logging

import pandas as pd

from .. import formato
from ..config import CAMINHO_INDICE_BRIEFINGS
from ..config import DIR_BRIEFINGS as _DIR
from . import fatos as fatos_mod

log = logging.getLogger(__name__)

DIR_BRIEFINGS = _DIR
CAMINHO_INDICE = CAMINHO_INDICE_BRIEFINGS

VERSAO = 1

GERADORES = {
    "haiku": "Haiku 4.5",
    "modelo": "gerador determinístico do projeto",
}


def caminho_md(data: str):
    return DIR_BRIEFINGS / f"{data}.md"


def caminho_json(data: str):
    return DIR_BRIEFINGS / f"{data}.json"


def _serializar(registro: dict) -> str:
    return json.dumps(registro, ensure_ascii=False, indent=2, sort_keys=True) + "\n"


def impressao_digital(fatos: dict) -> str:
    """sha256 dos fatos, para o rodapé poder apontar para algo verificável."""
    canonico = json.dumps(fatos, ensure_ascii=False, sort_keys=True,
                          separators=(",", ":"))
    return hashlib.sha256(canonico.encode("utf-8")).hexdigest()


def montar(fatos: dict, mudancas: dict, texto: str, *, gerador: str,
           modelo: str | None = None, motivo: str | None = None) -> dict:
    return {
        "versao": VERSAO,
        "data": fatos["data"],
        "replay": bool(fatos.get("replay")),
        "gerado_em": dt.datetime.now(dt.UTC).replace(microsecond=0).isoformat(),
        "gerador": gerador,
        "modelo": modelo,
        "motivo": motivo,
        "texto": texto,
        "mudancas": mudancas,
        "fatos": fatos,
    }


def rodape(registro: dict) -> str:
    """Quem escreveu, sobre o que, e como conferir.

    O rodapé é sempre nosso, nunca do modelo — inclusive quando o modelo escreveu
    o texto. Deixar a assinatura a cargo de quem está sendo auditado seria um
    desenho estranho.
    """
    quem = GERADORES.get(registro["gerador"], registro["gerador"])
    linhas = [f"Escrito pelo **{quem}**."]
    if registro.get("modelo") and registro["gerador"] == "haiku":
        linhas.append(f"Modelo: `{registro['modelo']}`.")
    if registro.get("motivo"):
        linhas.append(f"Por quê: {registro['motivo']}.")

    digital = impressao_digital(registro["fatos"])
    if registro.get("replay"):
        # Replay não é publicado, então não há arquivo para apontar. Citar um
        # caminho inexistente seria pior que não citar nenhum.
        linhas.append(f"Fatos reconstruídos, não publicados (sha256 `{digital[:12]}`).")
    else:
        linhas.append(
            f"Os fatos que originaram este texto estão em "
            f"`data/briefings/{registro['data']}.json` (sha256 `{digital[:12]}`)."
        )
    linhas.append(
        "A estatística decide; o texto apenas descreve. Nenhum número deste "
        "briefing veio de fora do arquivo de fatos, e a CI reconfere isso a cada "
        "build."
    )
    if registro.get("replay"):
        linhas.insert(0, "**Reconstrução para demonstração — não foi publicado "
                         "nesta data.**")
    return "---\n\n" + "\n".join(f"*{linha}*  " for linha in linhas)


def renderizar(registro: dict) -> str:
    data = dt.date.fromisoformat(registro["data"])
    titulo = f"# Briefing — {formato.dia(data)}"
    return f"{titulo}\n\n{registro['texto'].strip()}\n\n{rodape(registro)}\n"


def publicar(registro: dict) -> bool:
    """Grava o par de arquivos e atualiza o índice. Devolve se algo mudou."""
    DIR_BRIEFINGS.mkdir(parents=True, exist_ok=True)
    md, js = caminho_md(registro["data"]), caminho_json(registro["data"])

    texto_md = renderizar(registro)
    texto_js = _serializar(registro)
    mudou = False
    for caminho, conteudo in ((md, texto_md), (js, texto_js)):
        atual = caminho.read_text(encoding="utf-8") if caminho.exists() else None
        if atual != conteudo:
            caminho.write_text(conteudo, encoding="utf-8")
            mudou = True

    escrever_indice()
    return mudou


def carregar(data: str) -> dict | None:
    caminho = caminho_json(data)
    if not caminho.exists():
        return None
    return json.loads(caminho.read_text(encoding="utf-8"))


def publicados() -> list[dict]:
    """Todos os briefings já gravados, do mais recente para o mais antigo."""
    if not DIR_BRIEFINGS.exists():
        return []
    registros = []
    for caminho in sorted(DIR_BRIEFINGS.glob("*.json")):
        try:
            registros.append(json.loads(caminho.read_text(encoding="utf-8")))
        except json.JSONDecodeError:
            log.warning("briefing ilegível: %s", caminho.name)
    return sorted(registros, key=lambda r: r.get("data", ""), reverse=True)


def ultimo() -> dict | None:
    registros = [r for r in publicados() if not r.get("replay")]
    return registros[0] if registros else None


def escrever_indice() -> bool:
    """Uma linha por briefing. CSV porque é o que produz diff legível no GitHub."""
    registros = publicados()
    if not registros:
        return False

    tabela = pd.DataFrame([
        {
            "data": r["data"],
            "gerador": r["gerador"],
            "modelo": r.get("modelo") or "",
            "quadrante": (r.get("fatos", {}).get("regime", {}) or {}).get(
                "quadrante", ""),
            "divulgacoes": " ".join(
                d["par"] for d in r.get("fatos", {}).get("divulgacoes_do_dia", [])),
            "motivo": r.get("motivo") or "",
        }
        for r in sorted(registros, key=lambda r: r.get("data", ""))
    ])
    novo = tabela.to_csv(index=False, lineterminator="\n")
    atual = (CAMINHO_INDICE.read_text(encoding="utf-8")
             if CAMINHO_INDICE.exists() else None)
    if novo == atual:
        return False
    CAMINHO_INDICE.write_text(novo, encoding="utf-8")
    return True


def auditar() -> list[str]:
    """Refaz a verificação sobre tudo que já foi publicado.

    É o portão de CI do briefing. O texto não é reprodutível — o modelo escreve
    diferente a cada vez — mas a promessa sobre ele é, e é ela que se confere.
    """
    problemas: list[str] = []
    for registro in publicados():
        data = registro.get("data", "?")
        fatos = registro.get("fatos") or {}
        texto = registro.get("texto") or ""

        permitidos = fatos.get("numeros_permitidos")
        if permitidos is None:
            problemas.append(f"{data}: fatos sem lista de números permitidos")
            continue

        inventados = fatos_mod.numeros_inventados(texto, permitidos)
        if inventados:
            problemas.append(
                f"{data}: número no texto que não está nos fatos: "
                f"{', '.join(inventados)}")

        md = caminho_md(data)
        if not md.exists():
            problemas.append(f"{data}: falta o arquivo .md")
        elif texto.strip() not in md.read_text(encoding="utf-8"):
            problemas.append(
                f"{data}: o .md não contém o texto aprovado — foi editado à mão?")
    return problemas
