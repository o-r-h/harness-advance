#!/usr/bin/env python3
"""Hook PostToolUse: valida el archivo recién tocado contra rules.json.

Contrato de salida de Claude Code: exit 2 devuelve el stderr al modelo. En
cualquier otro caso salimos con 0 y en silencio — los warning se reportan
en checks.json, porque un aviso que el modelo no ve no sirve de nada.

Antes de modificar este archivo, revisar docs/hook-payloads.md: los nombres
de campo del payload están documentados a partir de una captura real.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from lib import checks, harness  # noqa: E402


def _contexto_activo(raiz: Path) -> dict | None:
    actual = harness.read_current(raiz)
    if not actual or not actual.get("ticket_id"):
        return None
    ruta = harness.ticket_dir(raiz, actual["ticket_id"]) / "ticket_context.json"
    return harness.read_json(ruta) if ruta.is_file() else None


def _resolver_raiz(payload: dict, ruta_archivo: str) -> Path | None:
    """Perfil que gobierna el archivo tocado, no el de la sesión.

    Desvío 1 de docs/hook-payloads.md: `cwd` es el directorio de la sesión y no
    el del archivo editado, así que resolver por `cwd` primero juzgaría un
    archivo de otro proyecto con las reglas del proyecto donde arrancó la
    sesión. El archivo manda; `cwd` es solo el respaldo.
    """
    raiz = harness.find_project_root(Path(ruta_archivo).parent)
    if raiz is None and payload.get("cwd"):
        raiz = harness.find_project_root(payload["cwd"])
    return raiz


def main() -> int:
    for flujo in (sys.stdout, sys.stderr):
        try:
            flujo.reconfigure(encoding="utf-8")
        except (AttributeError, ValueError):
            pass

    try:
        payload = json.load(sys.stdin)
    except (json.JSONDecodeError, UnicodeDecodeError):
        return 0
    if not isinstance(payload, dict):
        return 0

    entrada = payload.get("tool_input") or {}
    ruta_archivo = entrada.get("file_path")
    if not ruta_archivo:
        return 0

    raiz = _resolver_raiz(payload, ruta_archivo)
    if raiz is None or harness.is_harness_source(raiz):
        return 0

    try:
        reglas = harness.load_rules(raiz)
    except (OSError, json.JSONDecodeError) as error:
        sys.stderr.write(f"HARNESS · rules.json ilegible: {error}\n")
        return 2

    hallazgos = checks.run_file_checks(raiz, Path(ruta_archivo), reglas,
                                       _contexto_activo(raiz))
    errores = [h for h in hallazgos
               if h["severidad"] == "error" and h["resultado"] == "fallo"]
    if not errores:
        return 0

    lineas = ["HARNESS · reglas del proyecto violadas en el archivo que acabas de escribir:"]
    for hallazgo in errores:
        lineas.append(f"  - [{hallazgo['id']}] {hallazgo['detalle']}")
    lineas.append("Corrige esto ahora, antes de continuar. No cuenta como reintento "
                  "de la fase: es autocorrección.")
    sys.stderr.write("\n".join(lineas) + "\n")
    return 2


if __name__ == "__main__":
    sys.exit(main())
