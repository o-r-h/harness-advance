#!/usr/bin/env python3
"""Hook Stop: impide cerrar el turno con el ciclo de fase a mitad de vuelo.

Solo bloquea los estados en que el ciclo está corriendo. 'esperando_humano' y
'escalado' NO bloquean: en ambos el objetivo es precisamente devolverle el
turno al humano, y bloquear ahí produciría un bucle.

Antes de modificar este archivo, revisar docs/hook-payloads.md.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from lib import harness, state  # noqa: E402

BLOQUEANTES = frozenset({"en_ejecucion", "en_verificacion", "en_correccion"})

SIGUIENTE_PASO = {
    "en_ejecucion": "termina el trabajo de la fase y corre 'cli.py run-checks'",
    "en_verificacion": "invoca al escéptico y registra su veredicto con "
                       "'cli.py record-veredicto'",
    "en_correccion": "aplica la corrección leyendo el historial_fallos completo, "
                     "y vuelve a correr 'cli.py run-checks'",
}


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
    if not isinstance(payload, dict) or payload.get("stop_hook_active"):
        return 0

    # El payload de Stop no trae ninguna ruta de archivo: cwd es la única vía
    # para ubicar el proyecto (desvío 2 de docs/hook-payloads.md).
    raiz = harness.find_project_root(payload.get("cwd") or Path.cwd())
    if raiz is None or harness.is_harness_source(raiz):
        return 0

    actual = harness.read_current(raiz)
    if not actual or not actual.get("ticket_id") or not actual.get("fase_id"):
        return 0

    try:
        estado = state.leer_fase(raiz, actual["ticket_id"], actual["fase_id"])
    except (OSError, json.JSONDecodeError):
        return 0
    if estado is None or estado["estado"] not in BLOQUEANTES:
        return 0

    sys.stderr.write(
        f"HARNESS · la fase {estado['fase_id']} está en estado '{estado['estado']}' "
        f"(intento {estado['intento_actual']}/{estado['max_reintentos']}): el ciclo "
        f"no terminó.\nSiguiente paso: {SIGUIENTE_PASO[estado['estado']]}.\n"
        f"Si de verdad hay que detenerse aquí, escala explícitamente al humano "
        f"explicando por qué.\n")
    return 2


if __name__ == "__main__":
    sys.exit(main())
