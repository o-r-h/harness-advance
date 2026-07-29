"""Máquina de estados de fase: transiciones, contador y memoria de fallos.

Decisión D5 del spec: los contadores son aritmética, no juicio. Este módulo
es el único lugar del harness que escribe intento_actual.
"""
from __future__ import annotations

from pathlib import Path

from . import contracts, harness


class TransicionInvalida(Exception):
    """Se intentó una transición que el contrato no permite."""


TERMINALES = frozenset({"aprobada", "escalado"})


def _ruta_estado(project_root: Path, ticket_id: str, fase_id: str) -> Path:
    return harness.fase_dir(project_root, ticket_id, fase_id) / "fase_state.json"


def leer_fase(project_root: Path, ticket_id: str, fase_id: str) -> dict | None:
    ruta = _ruta_estado(project_root, ticket_id, fase_id)
    return harness.read_json(ruta) if ruta.is_file() else None


def _guardar(project_root: Path, ticket_id: str, estado: dict) -> dict:
    errores = contracts.validate_fase_state(estado)
    if errores:
        raise TransicionInvalida("estado de fase inválido: " + "; ".join(errores))
    harness.write_json(_ruta_estado(project_root, ticket_id, estado["fase_id"]), estado)
    return estado


def abrir_fase(project_root: Path, ticket_id: str, fase: dict) -> dict:
    """Crea el estado inicial de la fase. Idempotente."""
    existente = leer_fase(project_root, ticket_id, fase["id"])
    if existente is not None:
        return existente
    estado = {
        "fase_id": fase["id"],
        "estado": "en_ejecucion",
        "intento_actual": 1,
        "max_reintentos": int(fase.get("max_reintentos", 3)),
        "historial_fallos": [],
    }
    return _guardar(project_root, ticket_id, estado)


def set_estado(project_root: Path, ticket_id: str, fase_id: str, nuevo: str) -> dict:
    estado = leer_fase(project_root, ticket_id, fase_id)
    if estado is None:
        raise TransicionInvalida(f"la fase {fase_id} no está abierta")
    if nuevo not in contracts.ESTADOS_FASE:
        raise TransicionInvalida(f"estado desconocido: {nuevo}")
    estado["estado"] = nuevo
    return _guardar(project_root, ticket_id, estado)


def registrar_fallo(project_root: Path, ticket_id: str, fase_id: str, origen: str,
                    razon: str, correccion: str = "") -> dict:
    """Suma el fallo al historial, incrementa el intento y escala si se agotó."""
    if origen not in contracts.ORIGENES:
        raise TransicionInvalida(f"origen de fallo desconocido: {origen}")
    estado = leer_fase(project_root, ticket_id, fase_id)
    if estado is None:
        raise TransicionInvalida(f"la fase {fase_id} no está abierta")
    if estado["estado"] in TERMINALES:
        raise TransicionInvalida(
            f"la fase {fase_id} ya está en estado terminal '{estado['estado']}'")

    estado["historial_fallos"].append({
        "intento": estado["intento_actual"],
        "origen": origen,
        "razon": razon,
        "correccion_aplicada": correccion,
    })
    if estado["intento_actual"] >= estado["max_reintentos"]:
        estado["estado"] = "escalado"
    else:
        estado["intento_actual"] += 1
        estado["estado"] = "en_correccion"
    return _guardar(project_root, ticket_id, estado)


def aprobar_fase(project_root: Path, ticket_id: str, fase_id: str) -> dict:
    estado = leer_fase(project_root, ticket_id, fase_id)
    if estado is None:
        raise TransicionInvalida(f"la fase {fase_id} no está abierta")
    if estado["estado"] == "escalado":
        raise TransicionInvalida(
            f"la fase {fase_id} está escalada: requiere intervención humana explícita")
    estado["estado"] = "aprobada"
    return _guardar(project_root, ticket_id, estado)
