"""Configuración de la prueba asistida del proyecto: qué navegador y qué base usa el probador.

Vive en <proyecto>/.claude/prueba_asistida.json y la escribe `setup-prueba`. Ningún
perfil la trae: deploy.ps1 copia el perfil con -Force y la pisaría. Los nombres de
servidor y de herramienta son del proyecto; el harness genérico no conoce ninguno.
"""
from __future__ import annotations

from pathlib import Path

from . import contracts, harness

ARCHIVO = "prueba_asistida.json"


def ruta(raiz: Path) -> Path:
    return Path(raiz) / ".claude" / ARCHIVO


def leer(raiz: Path) -> dict | None:
    """La configuración guardada, o None si el setup nunca se hizo."""
    archivo = ruta(raiz)
    return harness.read_json(archivo) if archivo.is_file() else None


def estado(raiz: Path) -> tuple[dict | None, list[str]]:
    """(configuración válida o None, errores). Un JSON roto cuenta como inválido."""
    try:
        config = leer(raiz)
    except ValueError as error:
        return None, [f"{ARCHIVO} no es JSON válido: {error}"]
    if config is None:
        return None, []
    errores = contracts.validate_prueba_asistida(config)
    return (None, errores) if errores else (config, [])


def resumen(config: dict) -> str:
    base = config.get("base")
    if config.get("navegador"):
        navegador = config["navegador"]
    elif base is None:
        navegador = "sin navegador ni base: todos los pasos son del humano"
    else:
        navegador = ("sin navegador: el probador corre solo los pasos de consulta o de "
                     "API; los de pantalla son del humano")
    if base is None:
        texto_base = "sin base: la columna SQL del probador queda pendiente"
    else:
        texto_base = base["servidor"]
        if base.get("ambiente"):
            texto_base += f" (ambiente {base['ambiente']}, solo lectura)"
        else:
            texto_base += " (solo lectura, el ambiente que ya esté activo)"
        if base.get("prohibidas"):
            texto_base += "; prohibidas: " + ", ".join(base["prohibidas"])
    return f"Navegador: {navegador}\nBase: {texto_base}"
