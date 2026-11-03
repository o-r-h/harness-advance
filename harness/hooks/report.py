#!/usr/bin/env python3
"""Reporte de solo lectura: agrega lecciones, hallazgos y fases del proyecto.

No escribe nada. Un archivo ilegible o mal formado no detiene el reporte: se
anota en `ilegibles` y se sigue con el resto.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from lib import biblioteca, contracts, harness  # noqa: E402

# Lo que puede salir al leer o interpretar un archivo a mano o de una versión vieja.
_ERRORES_DE_LECTURA = (OSError, ValueError, KeyError, TypeError, AttributeError)


def _rel(project_root: Path, ruta: Path) -> str:
    return Path(ruta).relative_to(project_root).as_posix()


def _subdirs(carpeta: Path) -> list[Path]:
    return sorted(p for p in carpeta.iterdir() if p.is_dir()) if carpeta.is_dir() else []


def _senal(item: dict) -> str:
    return item.get("senal") or item.get("leccion") or ""


def _fallas(entrada: dict, tipo: str) -> list[dict]:
    return [{"fecha": f["fecha"], "ref": f["ref"], "leccion": f["leccion"]}
            for f in entrada["fallas"] if f["tipo"] == tipo]


def _leer_lecciones(project_root: Path, ilegibles: list[str]) -> list[dict]:
    carpeta = biblioteca.biblioteca_dir(project_root) / "entradas"
    lecciones = []
    for archivo in sorted(carpeta.glob("*.md")) if carpeta.is_dir() else []:
        try:
            # La ref sale de la primera línea (`# <ref>`), no del nombre del archivo.
            primera = archivo.read_text(encoding="utf-8").split("\n", 1)[0]
            ref = primera[2:].strip() if primera.startswith("# ") else ""
            if not contracts.RE_REFERENCIA.fullmatch(ref):
                raise ValueError("primera línea sin referencia")
            entrada = biblioteca.leer_entrada(project_root, ref)
            if entrada is None:
                raise ValueError("entrada no encontrada por su referencia")
            lecciones.append(entrada)
        except _ERRORES_DE_LECTURA:
            ilegibles.append(_rel(project_root, archivo))
    return lecciones


def _clasificar_lecciones(lecciones: list[dict]) -> tuple[list, list, dict]:
    implementadas = [e for e in lecciones if e["implementada"]]
    fallaron = []
    for e in implementadas:
        fallas = _fallas(e, "implementada")
        if fallas:
            fallaron.append({"ref": e["ref"], "senal": _senal(e),
                             "componente": e["componente"], "fallas": fallas})
    deuda: dict[str, list[dict]] = {}
    for e in lecciones:
        if e["implementada"]:
            continue
        deuda.setdefault(e["componente"] or "sin pieza", []).append(
            {"ref": e["ref"], "senal": _senal(e), "fallas": _fallas(e, "sin pieza")})
    for grupo in deuda.values():
        grupo.sort(key=lambda d: (-len(d["fallas"]), d["ref"]))
    return implementadas, fallaron, {k: deuda[k] for k in sorted(deuda)}


def _leer_json(project_root: Path, ruta: Path, validar, ilegibles: list[str]):
    """El JSON del archivo, o None (y anotado en `ilegibles`) si no se pudo leer."""
    try:
        datos = harness.read_json(ruta)
        if validar(datos):
            raise ValueError("fuera de contrato")
        return datos
    except _ERRORES_DE_LECTURA:
        ilegibles.append(_rel(project_root, ruta))
        return None


def _validar_checks(datos) -> list[str]:
    ok = isinstance(datos, dict) and isinstance(datos.get("checks"), list)
    return [] if ok else ["checks: requerido, lista"]


def agregar(project_root: Path) -> dict:
    project_root = Path(project_root)
    ilegibles: list[str] = []

    lecciones = _leer_lecciones(project_root, ilegibles)
    implementadas, fallaron, deuda = _clasificar_lecciones(lecciones)

    tickets = _subdirs(harness.tickets_dir(project_root))
    n_fases = 0
    intentos_por_fase: dict[str, dict] = {}
    escaladas: list[str] = []
    origen_de_fallos: dict[str, int] = {}
    reglas: dict[str, int] = {}
    repetidos: list[dict] = []
    propuestos: list[dict] = []
    rechazados: list[dict] = []
    tal_cual = editados = reincidencias = del_humano = 0

    for ticket in tickets:
        for carpeta in _subdirs(ticket):
            if not contracts.RE_FASE_ID.match(carpeta.name):
                continue
            fase = f"{ticket.name}/{carpeta.name}"

            estado = carpeta / "fase_state.json"
            if estado.is_file():
                datos = _leer_json(project_root, estado, contracts.validate_fase_state,
                                   ilegibles)
                if datos is not None:
                    n_fases += 1
                    intentos_por_fase[fase] = {"intentos": datos["intento_actual"],
                                               "max": datos["max_reintentos"],
                                               "estado": datos["estado"]}
                    if datos["estado"] == "escalado":
                        escaladas.append(fase)
                    razones = []
                    for fallo in datos["historial_fallos"]:
                        origen = fallo["origen"]
                        origen_de_fallos[origen] = origen_de_fallos.get(origen, 0) + 1
                        if origen == "esceptico":
                            razones.append(fallo["razon"])
                    if len(razones) >= 2:
                        repetidos.append({"fase": fase, "veces": len(razones),
                                          "razones": razones})

            for archivo in sorted(carpeta.glob("intento_*/checks.json")):
                datos = _leer_json(project_root, archivo, _validar_checks, ilegibles)
                for check in (datos["checks"] if datos else []):
                    if isinstance(check, dict) and check.get("resultado") == "fallo":
                        clave = str(check.get("id", "?"))
                        reglas[clave] = reglas.get(clave, 0) + 1

            archivo = carpeta / "hallazgos.json"
            if archivo.is_file():
                datos = _leer_json(project_root, archivo, contracts.validate_hallazgos,
                                   ilegibles)
                for h in (datos["hallazgos"] if datos else []):
                    ref = f"{fase}/{h['id']}"
                    if h["origen"] == "humano":
                        del_humano += 1
                    elif h["estado"] == "propuesto":
                        propuestos.append({"ref": ref, "senal": _senal(h)})
                    elif h["estado"] == "rechazado":
                        rechazados.append({"ref": ref, "motivo": h["motivo"]})
                    elif h.get("reincide"):
                        reincidencias += 1
                    elif h.get("leccion_original"):
                        editados += 1
                    else:
                        tal_cual += 1

    return {
        "resumen": {
            "tickets": len(tickets),
            "fases": n_fases,
            "fases_escaladas": len(escaladas),
            "lecciones_aprobadas": len(lecciones),
            "implementadas": len(implementadas),
            "fallaron_implementadas": len(fallaron),
            "volvieron_sin_pieza": sum(1 for e in lecciones if _fallas(e, "sin pieza")),
        },
        "fallaron_implementadas": fallaron,
        "deuda": deuda,
        "hallazgos": {
            "propuestos": propuestos, "aprobados_tal_cual": tal_cual,
            "aprobados_editados": editados, "reincidencias": reincidencias,
            "del_humano": del_humano, "rechazados": rechazados,
        },
        "fases": {
            "intentos_por_fase": intentos_por_fase, "escaladas": escaladas,
            "origen_de_fallos": origen_de_fallos, "reglas_mas_violadas": reglas,
            "rechazos_repetidos_del_esceptico": repetidos,
        },
        "ilegibles": sorted(ilegibles),
    }
