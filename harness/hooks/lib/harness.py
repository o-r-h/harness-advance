"""Resolución de rutas, perfil activo y estado del harness.

Este módulo no sabe nada de ningún stack concreto: solo de la estructura de
carpetas del harness. Todo conocimiento de un lenguaje o framework
pertenece a profiles/, nunca aquí.
"""
from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path

PROFILE_MARKER = "rules.json"


def find_project_root(start: str | Path) -> Path | None:
    """Primer ancestro (incluido `start`) que contenga .claude/rules.json."""
    inicio = Path(start).resolve()
    for candidato in [inicio, *inicio.parents]:
        if (candidato / ".claude" / PROFILE_MARKER).is_file():
            return candidato
    return None


def load_rules(project_root: Path) -> dict:
    return read_json(Path(project_root) / ".claude" / PROFILE_MARKER)


def list_agents(project_root: Path) -> set[str]:
    """Nombres de los subagentes del perfil: <proyecto>/.claude/agents/<nombre>.md."""
    carpeta = Path(project_root) / ".claude" / "agents"
    if not carpeta.is_dir():
        return set()
    return {ruta.stem for ruta in carpeta.glob("*.md") if ruta.is_file()}


def harness_dir(project_root: Path) -> Path:
    return Path(project_root) / ".harness"


def tickets_dir(project_root: Path) -> Path:
    return harness_dir(project_root) / "tickets"


def ticket_dir(project_root: Path, ticket_id: str) -> Path:
    return tickets_dir(project_root) / ticket_id


def fase_dir(project_root: Path, ticket_id: str, fase_id: str) -> Path:
    return ticket_dir(project_root, ticket_id) / fase_id


def intento_dir(project_root: Path, ticket_id: str, fase_id: str, intento: int) -> Path:
    return fase_dir(project_root, ticket_id, fase_id) / f"intento_{intento}"


def current_pointer_path(project_root: Path) -> Path:
    return harness_dir(project_root) / "current.json"


def read_current(project_root: Path) -> dict | None:
    ruta = current_pointer_path(project_root)
    return read_json(ruta) if ruta.is_file() else None


def write_current(project_root: Path, ticket_id: str, fase_id: str | None = None) -> None:
    write_json(current_pointer_path(project_root),
               {"ticket_id": ticket_id, "fase_id": fase_id})


def read_json(path: Path) -> dict:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def write_json(path: Path, data: dict) -> None:
    """Escritura atómica: nunca deja un JSON a medio escribir."""
    destino = Path(path)
    destino.parent.mkdir(parents=True, exist_ok=True)
    fd, temporal = tempfile.mkstemp(dir=str(destino.parent), suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            json.dump(data, fh, ensure_ascii=False, indent=2)
        os.replace(temporal, destino)
    except BaseException:
        Path(temporal).unlink(missing_ok=True)
        raise


def is_harness_source(project_root: Path) -> bool:
    """True si esta carpeta es el repo fuente del harness y no un proyecto.

    Evita que el harness se valide a sí mismo si alguien le pone un perfil.
    """
    raiz = Path(project_root)
    return (raiz / "harness" / "hooks").is_dir() and (raiz / "profiles").is_dir()
