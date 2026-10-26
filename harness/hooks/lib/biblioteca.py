"""Biblioteca de lecciones del proyecto: entradas aprobadas/rechazadas e INDEX.md derivado.

Vive en <proyecto>/.claude/biblioteca/ y se versiona con el proyecto (DA6).
"""
from __future__ import annotations

import re
from pathlib import Path

# (campo en el JSON, etiqueta en la entrada), en el orden de la entrada.
_CAMPOS = (("senal", "señal"), ("leccion", "lección"), ("evidencia", "evidencia"),
           ("confianza", "confianza"), ("dimension", "dimension"),
           ("componente", "componente"), ("origen", "origen"),
           ("leccion_original", "lección original"), ("motivo", "motivo"))

_INTRO = ("Índice derivado: se reconstruye desde las entradas en disco. **Toda lección es "
          "hipótesis hasta re-verificarla en el código (DA8).**")


def biblioteca_dir(project_root: Path) -> Path:
    return Path(project_root) / ".claude" / "biblioteca"


def escribir_entrada(project_root: Path, ticket_id: str, fase_id: str, hallazgo: dict) -> Path:
    estado = hallazgo.get("estado")
    if estado == "aprobado":
        subdir = "entradas"
    elif estado == "rechazado":
        subdir = "rechazados"
    else:
        raise ValueError(f"solo se guardan hallazgos aprobados o rechazados, no '{estado}'")
    destino = biblioteca_dir(project_root) / subdir / f"{ticket_id}-{fase_id}-{hallazgo['id']}.md"
    destino.parent.mkdir(parents=True, exist_ok=True)
    lineas = [f"# {ticket_id}/{fase_id}/{hallazgo['id']}", ""]
    for clave, etiqueta in _CAMPOS:
        valor = hallazgo.get(clave)
        if valor:
            lineas.append(f"- **{etiqueta}**: {' '.join(str(valor).split())}")
    destino.write_text("\n".join(lineas) + "\n", encoding="utf-8")
    reconstruir_indice(project_root)
    return destino


def _campo(texto: str, etiqueta: str) -> str:
    m = re.search(rf"^- \*\*{re.escape(etiqueta)}\*\*: (.*)$", texto, re.MULTILINE)
    return m.group(1).strip() if m else ""


def _archivos(carpeta: Path) -> list[Path]:
    return sorted(carpeta.glob("*.md"), key=lambda p: p.name) if carpeta.is_dir() else []


def reconstruir_indice(project_root: Path) -> Path:
    base = biblioteca_dir(project_root)
    aprobadas = []
    for f in _archivos(base / "entradas"):
        t = f.read_text(encoding="utf-8")
        aprobadas.append(f"- [{_campo(t, 'dimension')} · {_campo(t, 'componente')}] "
                         f"{_campo(t, 'señal')} — entradas/{f.name}")
    rechazadas = []
    for f in _archivos(base / "rechazados"):
        t = f.read_text(encoding="utf-8")
        rechazadas.append(f"- {_campo(t, 'señal')} — motivo: {_campo(t, 'motivo')}")
    lineas = ["# Biblioteca de lecciones", "", _INTRO, "", "## Aprobadas", "",
              *(aprobadas or ["_(vacía)_"]), "",
              "## Rechazadas — no volver a proponer", "",
              *(rechazadas or ["_(vacía)_"])]
    destino = base / "INDEX.md"
    destino.parent.mkdir(parents=True, exist_ok=True)
    destino.write_text("\n".join(lineas) + "\n", encoding="utf-8")
    return destino
