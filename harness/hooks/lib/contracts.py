"""Validación de los cinco contratos JSON del harness.

Escrito a mano y sin dependencias: el entorno no tiene jsonschema y el
harness no instala nada. Cada validate_* devuelve una lista de mensajes de
error en español; lista vacía significa dato válido.
"""
from __future__ import annotations

import re

ESTADOS_FASE = frozenset({
    "pendiente", "en_ejecucion", "en_verificacion",
    "esperando_humano", "en_correccion", "aprobada", "escalado",
})
CONFIANZAS = frozenset({"verificado", "por_confirmar"})
ORIGENES = frozenset({"check", "esceptico", "humano"})
SEVERIDADES = frozenset({"error", "warning"})
RESULTADOS_CHECK = frozenset({"ok", "fallo", "error_check"})
RESULTADOS_PRUEBA = frozenset({"ok", "fallo", "pendiente", "na"})

RE_FECHA = re.compile(r"^\d{2}-\d{2}-\d{4}$")
RE_FASE_ID = re.compile(r"^fase_\d+$")


def _texto(data: dict, campo: str, errores: list[str], prefijo: str = "") -> None:
    valor = data.get(campo)
    if not isinstance(valor, str) or not valor.strip():
        errores.append(f"{prefijo}{campo}: requerido, string no vacío")


def _lista(data: dict, campo: str, errores: list[str], prefijo: str = "",
           permite_vacia: bool = True) -> None:
    valor = data.get(campo)
    if not isinstance(valor, list):
        errores.append(f"{prefijo}{campo}: requerido, lista")
    elif not permite_vacia and not valor:
        errores.append(f"{prefijo}{campo}: no puede estar vacía")


def validate_ticket_context(data: dict) -> list[str]:
    if not isinstance(data, dict):
        return ["ticket_context: requerido, objeto JSON"]
    errores: list[str] = []
    for campo in ("ticket_id", "nroticket", "desarrollador", "fecha", "perfil"):
        _texto(data, campo, errores)
    fecha = data.get("fecha")
    if isinstance(fecha, str) and not RE_FECHA.match(fecha):
        errores.append("fecha: formato esperado DD-MM-YYYY")
    return errores


def resolve_check_names(nombres: list[str], rules: dict) -> tuple[list[str], list[str]]:
    """Expande grupos a checks individuales. Devuelve (resueltos, desconocidos)."""
    if not isinstance(rules, dict):
        return [], list(nombres)
    grupos = rules.get("grupos") or {}
    individuales = {r["id"] for r in rules.get("prohibido", []) if isinstance(r, dict) and "id" in r}
    individuales.update(rules.get("checks_estructurales") or [])
    if (rules.get("audit_comments") or {}).get("requerido") is not None:
        individuales.add("audit_comments")
    if rules.get("no_new_deps") is not None:
        individuales.add("no_new_deps")

    resueltos: list[str] = []
    desconocidos: list[str] = []
    for nombre in nombres:
        if nombre in grupos:
            resueltos.extend(grupos[nombre])
        elif nombre in individuales:
            resueltos.append(nombre)
        else:
            desconocidos.append(nombre)
    return resueltos, desconocidos


def validate_plan(data: dict, rules: dict | None = None) -> list[str]:
    if not isinstance(data, dict):
        return ["plan: requerido, objeto JSON"]
    errores: list[str] = []
    for campo in ("ticket_id", "perfil"):
        _texto(data, campo, errores)
    fases = data.get("fases")
    if not isinstance(fases, list) or not fases:
        errores.append("fases: requerido, lista no vacía")
        return errores

    ids = [f.get("id") for f in fases if isinstance(f, dict)]
    for indice, fase in enumerate(fases):
        prefijo = f"fases[{indice}]."
        if not isinstance(fase, dict):
            errores.append(f"fases[{indice}]: debe ser objeto")
            continue
        _texto(fase, "id", errores, prefijo)
        if isinstance(fase.get("id"), str) and not RE_FASE_ID.match(fase["id"]):
            errores.append(f"{prefijo}id: formato esperado fase_N")
        _texto(fase, "titulo", errores, prefijo)
        _texto(fase, "criterio_exito", errores, prefijo)
        _lista(fase, "pasos", errores, prefijo, permite_vacia=False)
        _lista(fase, "anclajes", errores, prefijo)
        _lista(fase, "checks_deterministas", errores, prefijo)
        _lista(fase, "herramientas_permitidas", errores, prefijo, permite_vacia=False)
        _lista(fase, "depende_de", errores, prefijo)

        for j, ancla in enumerate(fase.get("anclajes") or []):
            if not isinstance(ancla, dict):
                errores.append(f"{prefijo}anclajes[{j}]: debe ser objeto")
                continue
            _texto(ancla, "ref", errores, f"{prefijo}anclajes[{j}].")
            if ancla.get("confianza") not in CONFIANZAS:
                errores.append(f"{prefijo}anclajes[{j}].confianza: "
                               f"esperado uno de {sorted(CONFIANZAS)}")

        prueba = fase.get("prueba_manual")
        if not isinstance(prueba, dict) or not isinstance(prueba.get("requerida"), bool):
            errores.append(f"{prefijo}prueba_manual.requerida: requerido, booleano")

        maximo = fase.get("max_reintentos")
        if not isinstance(maximo, int) or isinstance(maximo, bool) or not 1 <= maximo <= 10:
            errores.append(f"{prefijo}max_reintentos: entero entre 1 y 10")

        for dependencia in fase.get("depende_de") or []:
            if dependencia not in ids:
                errores.append(f"{prefijo}depende_de: '{dependencia}' no es una fase del plan")

        if rules is not None:
            _, desconocidos = resolve_check_names(
                [c for c in (fase.get("checks_deterministas") or []) if isinstance(c, str)], rules)
            for nombre in desconocidos:
                errores.append(f"{prefijo}checks_deterministas: '{nombre}' no existe "
                               f"como check ni como grupo en rules.json")
    return errores


def validate_checks_result(data: dict) -> list[str]:
    if not isinstance(data, dict):
        return ["checks_result: requerido, objeto JSON"]
    errores: list[str] = []
    _texto(data, "fase_id", errores)
    if not isinstance(data.get("intento"), int) or isinstance(data.get("intento"), bool):
        errores.append("intento: requerido, entero")
    checks = data.get("checks")
    if not isinstance(checks, list):
        errores.append("checks: requerido, lista")
        return errores

    for indice, check in enumerate(checks):
        prefijo = f"checks[{indice}]."
        if not isinstance(check, dict):
            errores.append(f"checks[{indice}]: debe ser objeto")
            continue
        _texto(check, "id", errores, prefijo)
        if check.get("resultado") not in RESULTADOS_CHECK:
            errores.append(f"{prefijo}resultado: esperado uno de {sorted(RESULTADOS_CHECK)}")
        if check.get("resultado") != "ok":
            if check.get("severidad") not in SEVERIDADES:
                errores.append(f"{prefijo}severidad: esperado uno de {sorted(SEVERIDADES)}")
            _texto(check, "detalle", errores, prefijo)

    bloqueantes = [c for c in checks if isinstance(c, dict)
                   and c.get("resultado") == "fallo" and c.get("severidad") == "error"]
    esperado = "fallo" if bloqueantes else "ok"
    if data.get("resultado") != esperado:
        errores.append(f"resultado: se esperaba '{esperado}' — un check con severidad "
                       f"'error' y resultado 'fallo' obliga a 'fallo'; los 'warning' y "
                       f"'error_check' no bloquean")
    return errores


def validate_veredicto(data: dict) -> list[str]:
    if not isinstance(data, dict):
        return ["veredicto: requerido, objeto JSON"]
    errores: list[str] = []
    _texto(data, "fase_id", errores)
    if not isinstance(data.get("intento"), int) or isinstance(data.get("intento"), bool):
        errores.append("intento: requerido, entero")
    if not isinstance(data.get("aprobado"), bool):
        errores.append("aprobado: requerido, booleano")

    juicio = data.get("juicio_esceptico")
    if not isinstance(juicio, dict):
        errores.append("juicio_esceptico: requerido, objeto")
        return errores
    if not isinstance(juicio.get("aprobado"), bool):
        errores.append("juicio_esceptico.aprobado: requerido, booleano")
    for campo in ("razones_rechazo", "claims_sin_evidencia", "anclajes_sin_resolver"):
        _lista(juicio, campo, errores, "juicio_esceptico.")
    if juicio.get("aprobado") is False and not (juicio.get("razones_rechazo") or []):
        errores.append("juicio_esceptico.razones_rechazo: un rechazo exige al menos una razón")

    prueba = data.get("prueba_manual")
    if not isinstance(prueba, dict):
        errores.append("prueba_manual: requerido, objeto")
        return errores
    if not isinstance(prueba.get("requerida"), bool):
        errores.append("prueba_manual.requerida: requerido, booleano")
    if prueba.get("resultado") not in RESULTADOS_PRUEBA:
        errores.append(f"prueba_manual.resultado: esperado uno de {sorted(RESULTADOS_PRUEBA)}")

    prueba_ok = (prueba.get("resultado") == "ok") or (prueba.get("requerida") is False)
    if data.get("aprobado") is True and not (juicio.get("aprobado") and prueba_ok):
        errores.append("aprobado: no puede ser true si el escéptico rechazó o si la "
                       "prueba manual requerida no resultó 'ok'")
    return errores


def validate_fase_state(data: dict) -> list[str]:
    if not isinstance(data, dict):
        return ["fase_state: requerido, objeto JSON"]
    errores: list[str] = []
    _texto(data, "fase_id", errores)
    if data.get("estado") not in ESTADOS_FASE:
        errores.append(f"estado: esperado uno de {sorted(ESTADOS_FASE)}")

    intento = data.get("intento_actual")
    maximo = data.get("max_reintentos")
    for campo, valor in (("intento_actual", intento), ("max_reintentos", maximo)):
        if not isinstance(valor, int) or isinstance(valor, bool) or valor < 1:
            errores.append(f"{campo}: entero mayor o igual a 1")
    if isinstance(intento, int) and isinstance(maximo, int) and not isinstance(intento, bool):
        if intento > maximo:
            errores.append("intento_actual: no puede exceder max_reintentos "
                           "(al excederlo la fase pasa a 'escalado')")

    historial = data.get("historial_fallos")
    if not isinstance(historial, list):
        errores.append("historial_fallos: requerido, lista")
        return errores
    for indice, fallo in enumerate(historial):
        prefijo = f"historial_fallos[{indice}]."
        if not isinstance(fallo, dict):
            errores.append(f"historial_fallos[{indice}]: debe ser objeto")
            continue
        if not isinstance(fallo.get("intento"), int) or isinstance(fallo.get("intento"), bool):
            errores.append(f"{prefijo}intento: requerido, entero")
        if fallo.get("origen") not in ORIGENES:
            errores.append(f"{prefijo}origen: esperado uno de {sorted(ORIGENES)}")
        _texto(fallo, "razon", errores, prefijo)
    return errores
