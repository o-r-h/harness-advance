"""Configuración de la prueba asistida del proyecto: qué navegador y qué base usa el probador.

Vive en <proyecto>/.claude/prueba_asistida.json y la escribe `setup-prueba`. Ningún
perfil la trae: deploy.ps1 copia el perfil con -Force y la pisaría. Los nombres de
servidor y de herramienta son del proyecto; el harness genérico no conoce ninguno.
"""
from __future__ import annotations

from pathlib import Path

from . import contracts, harness

ARCHIVO = "prueba_asistida.json"
AGENTE = "probador.md"
MARCA = ("<!-- Generado por setup-prueba desde el probador genérico. No lo edites: "
         "se regenera. -->")


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


def prohibidas(config: dict | None) -> list[str]:
    base = (config or {}).get("base") or {}
    return list(base.get("prohibidas") or [])


def ruta_agente(raiz: Path) -> Path:
    """El probador del proyecto: Claude Code lo prefiere al global del mismo nombre."""
    return Path(raiz) / ".claude" / "agents" / AGENTE


def ruta_generico() -> Path:
    """El probador genérico, hermano de hooks/ tanto en el repo como en ~/.claude."""
    return Path(__file__).resolve().parents[2] / "agents" / AGENTE


def agente_con_prohibidas(generico: str, extra: list[str]) -> str:
    """El probador genérico con `extra` sumadas a disallowedTools y la marca de generado."""
    lineas = generico.splitlines()
    if not lineas or lineas[0].strip() != "---":
        raise ValueError("el probador genérico no empieza con frontmatter")
    try:
        cierre = lineas.index("---", 1)
    except ValueError:
        raise ValueError("el probador genérico no cierra su frontmatter") from None
    campo = next((i for i in range(1, cierre)
                  if lineas[i].startswith("disallowedTools:")), None)
    actuales = []
    if campo is not None:
        actuales = [h.strip() for h in lineas[campo].split(":", 1)[1].split(",") if h.strip()]
    todas = actuales + [h for h in dict.fromkeys(extra) if h not in actuales]
    linea = "disallowedTools: " + ", ".join(todas)
    if campo is None:
        lineas.insert(cierre, linea)
        cierre += 1
    else:
        lineas[campo] = linea
    lineas[cierre + 1:cierre + 1] = ["", MARCA]
    return "\n".join(lineas) + "\n"


def sincronizar_agente(raiz: Path, config: dict | None) -> str | None:
    """Deja el probador del proyecto de acuerdo con las prohibidas; dice qué hizo, o None.

    Las prohibidas del JSON son una instrucción; en disallowedTools son un bloqueo. El
    archivo vive en el proyecto porque el deploy pisa el probador global con -Force.
    Un probador del proyecto sin la marca es del humano: no se toca.
    """
    extra = prohibidas(config)
    archivo = ruta_agente(raiz)
    existente = archivo.read_text(encoding="utf-8") if archivo.is_file() else None
    if existente is not None and MARCA not in existente:
        if not extra:
            return None
        return (f"Aviso: {archivo} es un probador propio del proyecto y no se toca. "
                f"Agrega tú a su disallowedTools: {', '.join(extra)}")
    if not extra:
        if existente is None:
            return None
        archivo.unlink()
        return f"Sin prohibidas: se quitó {archivo} y vuelve a valer el probador global."
    try:
        esperado = agente_con_prohibidas(ruta_generico().read_text(encoding="utf-8"), extra)
    except (OSError, ValueError) as error:
        return (f"Aviso: no se pudo generar el probador del proyecto ({error}). Las "
                f"prohibidas quedan solo como instrucción, sin bloqueo técnico.")
    if existente == esperado:
        return None
    archivo.parent.mkdir(parents=True, exist_ok=True)
    archivo.write_text(esperado, encoding="utf-8")
    return (f"Bloqueo técnico: {archivo} le quita al probador {', '.join(extra)}. "
            f"Vale desde la próxima sesión de Claude Code.")


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
