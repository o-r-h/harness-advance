#!/usr/bin/env python3
"""Reporte de solo lectura: agrega lecciones, hallazgos y fases del proyecto.

No escribe nada. Un archivo ilegible o mal formado no detiene el reporte: se
anota en `ilegibles` y se sigue con el resto.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from lib import biblioteca, contracts, curacion, harness, senales  # noqa: E402

# Lo que puede salir al leer o interpretar un archivo a mano o de una versión vieja.
_ERRORES_DE_LECTURA = (OSError, ValueError, KeyError, TypeError, AttributeError)


def _rel(project_root: Path, ruta: Path) -> str:
    return Path(ruta).relative_to(project_root).as_posix()


def _listar(project_root: Path, carpeta: Path, ilegibles: list[str], patron: str = "*",
            solo_dirs: bool = False) -> list[Path]:
    """Contenido ordenado de la carpeta; si no se puede recorrer, la carpeta va a `ilegibles`."""
    try:
        if not carpeta.is_dir():
            return []
        hallados = carpeta.glob(patron)
        return sorted(p for p in hallados if p.is_dir() or not solo_dirs)
    except OSError:
        ilegibles.append(_rel(project_root, carpeta))
        return []


def _senal(item: dict) -> str:
    return item.get("senal") or item.get("leccion") or ""


def _fallas(entrada: dict, tipo: str) -> list[dict]:
    return [{"fecha": f["fecha"], "ref": f["ref"], "leccion": f["leccion"]}
            for f in entrada["fallas"] if f["tipo"] == tipo]


def _leer_lecciones(project_root: Path, ilegibles: list[str]) -> list[dict]:
    carpeta = biblioteca.biblioteca_dir(project_root) / "entradas"
    lecciones = []
    for archivo in _listar(project_root, carpeta, ilegibles, "*.md"):
        try:
            # La ref sale de la primera línea (`# <ref>`), no del nombre del archivo.
            primera = archivo.read_text(encoding="utf-8").split("\n", 1)[0]
            ref = primera[2:].strip() if primera.startswith("# ") else ""
            if not contracts.RE_REFERENCIA.fullmatch(ref):
                raise ValueError("primera línea sin referencia")
            if biblioteca.entrada_path(project_root, ref) != archivo:
                # Una copia o un archivo renombrado contaría la lección dos veces.
                raise ValueError("el nombre del archivo no corresponde a su referencia")
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
                             "componente": e["componente"],
                             "implementada": e["implementada"], "fallas": fallas})
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


def _curacion(project_root: Path, ilegibles: list[str]) -> dict:
    datos = senales.senales(project_root)
    try:
        estado = curacion.leer(project_root) or {"acciones": []}
    except _ERRORES_DE_LECTURA:
        ilegibles.append(_rel(project_root, curacion.ruta(project_root)))
        estado = {"acciones": []}
    retiradas = biblioteca.biblioteca_dir(project_root) / "retiradas"
    return {
        "sin_uso": [{"ref": l["ref"], "senal": l["senal"]}
                    for l in datos["lecciones"] if l["usos"] == 0],
        "rutas_ausentes": [{"ref": l["ref"], "rutas": l["rutas_ausentes"]}
                           for l in datos["lecciones"] if l["rutas_ausentes"]],
        "pendientes": sum(1 for a in estado["acciones"] if a["estado"] == "propuesto"),
        "ultima_curacion": datos["ultima_curacion"],
        "retiradas": len(list(retiradas.glob("*.md"))) if retiradas.is_dir() else 0,
    }


def agregar(project_root: Path) -> dict:
    project_root = Path(project_root)
    ilegibles: list[str] = []

    lecciones = _leer_lecciones(project_root, ilegibles)
    curacion_datos = _curacion(project_root, ilegibles)
    implementadas, fallaron, deuda = _clasificar_lecciones(lecciones)

    tickets = _listar(project_root, harness.tickets_dir(project_root), ilegibles,
                      solo_dirs=True)
    n_fases = 0
    intentos_por_fase: dict[str, dict] = {}
    escaladas: list[str] = []
    origen_de_fallos: dict[str, int] = {}
    pausas_por_fase: dict[str, int] = {}
    reglas: dict[str, int] = {}
    repetidos: list[dict] = []
    propuestos: list[dict] = []
    rechazados: list[dict] = []
    tal_cual = editados = reincidencias = del_humano = 0

    for ticket in tickets:
        for carpeta in _listar(project_root, ticket, ilegibles, solo_dirs=True):
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
                    pausas = len(datos.get("pausas") or [])
                    if pausas:
                        pausas_por_fase[fase] = pausas
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

            for archivo in _listar(project_root, carpeta, ilegibles,
                                "intento_*/checks.json"):
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
            "origen_de_fallos": origen_de_fallos, "pausas_por_fase": pausas_por_fase,
            "reglas_mas_violadas": reglas,
            "rechazos_repetidos_del_esceptico": repetidos,
        },
        "curacion": curacion_datos,
        "ilegibles": sorted(ilegibles),
    }


_SIN_DATOS = "  Sin datos todavía."


def _veces(n: int) -> str:
    return f"{n}×"


def _seccion_resumen(datos: dict) -> list[str]:
    r = datos["resumen"]
    return [
        f"  Tickets: {r['tickets']}   Fases: {r['fases']} (escaladas: {r['fases_escaladas']})",
        f"  Lecciones aprobadas: {r['lecciones_aprobadas']}   "
        f"implementadas: {r['implementadas']}",
        f"  Fallaron estando implementadas: {r['fallaron_implementadas']}",
        f"  Volvieron sin pieza (histórico): {r['volvieron_sin_pieza']}",
    ]


def _seccion_fallaron(datos: dict) -> list[str]:
    lineas = []
    for e in datos["fallaron_implementadas"]:
        lineas.append(f"  {e['ref']} — {e['senal']} (pieza: {e['componente']}) "
                      f"(implementada {e['implementada']})")
        for f in e["fallas"]:
            lineas.append(f"    {f['fecha']} en {f['ref']}: {f['leccion']}")
    return lineas or [_SIN_DATOS]


def _seccion_deuda(datos: dict) -> list[str]:
    lineas = []
    for componente, grupo in datos["deuda"].items():
        lineas.append(f"  {componente}")
        for d in grupo:
            costo = (f" — costó otra vez {_veces(len(d['fallas']))}" if d["fallas"] else "")
            lineas.append(f"    {d['ref']} — {d['senal']}{costo}")
            for f in d["fallas"]:
                lineas.append(f"      {f['fecha']} en {f['ref']}: {f['leccion']}")
    return lineas or [_SIN_DATOS]


def _seccion_curacion(datos: dict) -> list[str]:
    c = datos["curacion"]
    if not (c["sin_uso"] or c["rutas_ausentes"] or c["pendientes"] or c["retiradas"]
            or c["ultima_curacion"]):
        return [_SIN_DATOS]
    lineas = [f"  Sin uso en los planes de este clon: {len(c['sin_uso'])}"]
    lineas += [f"    {l['ref']} — {l['senal']}" for l in c["sin_uso"]]
    lineas.append(f"  Con rutas que ya no existen: {len(c['rutas_ausentes'])}")
    lineas += [f"    {l['ref']} — {', '.join(l['rutas'])}" for l in c["rutas_ausentes"]]
    lineas += [f"  Acciones de curación sin resolver: {c['pendientes']}",
               f"  Última curación: {c['ultima_curacion'] or 'nunca'}",
               f"  Retiradas: {c['retiradas']}",
               '  Los usos cuentan los planes de este clon; "sin uso" no basta para retirar.']
    if c["sin_uso"] or c["rutas_ausentes"] or c["pendientes"]:
        lineas.append("  Sugerencia: /biblioteca-curar")
    return lineas


def _seccion_hallazgos(datos: dict) -> list[str]:
    h = datos["hallazgos"]
    contadores = (h["aprobados_tal_cual"], h["aprobados_editados"], h["reincidencias"],
                  h["del_humano"])
    if not (h["propuestos"] or h["rechazados"] or any(contadores)):
        return [_SIN_DATOS]
    lineas = [f"  Aprobados tal cual: {h['aprobados_tal_cual']}   "
              f"editados: {h['aprobados_editados']}   reincidencias: {h['reincidencias']}   "
              f"del humano: {h['del_humano']}",
              f"  Propuestos sin resolver: {len(h['propuestos'])}"]
    lineas += [f"    {p['ref']} — {p['senal']}" for p in h["propuestos"]]
    lineas.append(f"  Rechazados: {len(h['rechazados'])}")
    lineas += [f"    {r['ref']} — {r['motivo']}" for r in h["rechazados"]]
    return lineas


def _seccion_fases(datos: dict) -> list[str]:
    f = datos["fases"]
    if not f["intentos_por_fase"]:
        return [_SIN_DATOS]
    lineas = ["  Intentos por fase:"]
    for fase, i in f["intentos_por_fase"].items():
        lineas.append(f"    {fase}: {i['intentos']}/{i['max']} ({i['estado']})")
    if f["escaladas"]:
        lineas.append("  Escaladas: " + ", ".join(f["escaladas"]))
    if f["origen_de_fallos"]:
        lineas.append("  Origen de los fallos: " + ", ".join(
            f"{k} {_veces(v)}" for k, v in sorted(f["origen_de_fallos"].items())))
    if f["pausas_por_fase"]:
        lineas.append("  Pausas: " + ", ".join(
            f"{k} {_veces(v)}" for k, v in sorted(f["pausas_por_fase"].items())))
    if f["reglas_mas_violadas"]:
        lineas.append("  Reglas más violadas:")
        orden = sorted(f["reglas_mas_violadas"].items(), key=lambda kv: (-kv[1], kv[0]))
        lineas += [f"    {k}: {_veces(v)}" for k, v in orden]
    for r in f["rechazos_repetidos_del_esceptico"]:
        lineas.append(f"  El escéptico rechazó {_veces(r['veces'])} en {r['fase']}:")
        lineas += [f"    - {razon}" for razon in r["razones"]]
    return lineas


def render(datos: dict) -> str:
    """El reporte como texto plano."""
    secciones = [
        ("Resumen", _seccion_resumen(datos)),
        ("Fallaron estando implementadas", _seccion_fallaron(datos)),
        ("Deuda", _seccion_deuda(datos)),
        ("Curación", _seccion_curacion(datos)),
        ("Hallazgos", _seccion_hallazgos(datos)),
        ("Fases", _seccion_fases(datos)),
    ]
    if datos["ilegibles"]:
        secciones.append(("Archivos que no se pudieron leer",
                          [f"  {ruta}" for ruta in datos["ilegibles"]]))
    lineas = ["HARNESS · reporte"]
    for titulo, cuerpo in secciones:
        lineas += ["", titulo, *cuerpo]
    return "\n".join(lineas) + "\n"
