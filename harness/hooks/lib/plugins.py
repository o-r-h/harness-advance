"""Carga de los checks estructurales del perfil.

Los checks que necesitan entender un stack (Web Forms, SPs) viven en
<proyecto>/.claude/checks/*.py y se cargan dinámicamente. Cada módulo debe
exponer:  run(project_root, archivos_modificados, ctx) -> list[Finding]
"""
from __future__ import annotations

import importlib.util
import traceback
from pathlib import Path


def _cargar_modulo(ruta: Path):
    especificacion = importlib.util.spec_from_file_location(f"harness_check_{ruta.stem}", ruta)
    if especificacion is None or especificacion.loader is None:
        raise ImportError(f"no se pudo preparar el módulo {ruta}")
    modulo = importlib.util.module_from_spec(especificacion)
    especificacion.loader.exec_module(modulo)
    return modulo


def cargar_checks_estructurales(project_root: Path) -> dict[str, object]:
    """{id: callable run}. Los ids que fallen al cargar quedan como excepción."""
    carpeta = Path(project_root) / ".claude" / "checks"
    cargados: dict[str, object] = {}
    if not carpeta.is_dir():
        return cargados
    for ruta in sorted(carpeta.glob("*.py")):
        if ruta.name.startswith("_"):
            continue
        try:
            modulo = _cargar_modulo(ruta)
            funcion = getattr(modulo, "run", None)
            if not callable(funcion):
                raise AttributeError(f"{ruta.name} no expone una función run()")
            cargados[ruta.stem] = funcion
        except Exception:
            cargados[ruta.stem] = ImportError(traceback.format_exc())
    return cargados


def ejecutar(check_id: str, funcion, project_root: Path, archivos: list[Path],
             ctx: dict | None) -> list[dict]:
    """Corre un check estructural aislando sus fallos como error_check."""
    if isinstance(funcion, BaseException):
        return [{"id": check_id, "resultado": "error_check", "severidad": "error",
                 "detalle": f"no se pudo cargar el check: {funcion}"}]
    try:
        resultado = funcion(project_root, archivos, ctx)
        return list(resultado or [])
    except Exception:
        return [{"id": check_id, "resultado": "error_check", "severidad": "error",
                 "detalle": traceback.format_exc()}]
