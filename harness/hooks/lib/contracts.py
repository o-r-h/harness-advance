"""Validación de los cinco contratos JSON del harness.

Escrito a mano y sin dependencias: el entorno no tiene jsonschema y el
harness no instala nada. Cada validate_* devuelve una lista de mensajes de
error en español; lista vacía significa dato válido.
"""
from __future__ import annotations

import re

ESTADOS_FASE = frozenset({
    "pendiente", "en_ejecucion", "en_verificacion",
    "esperando_humano", "en_correccion", "aprobada", "escalado", "pausada",
})
# Estados desde los que se puede pausar una fase (y a los que vuelve al reanudar).
ESTADOS_EN_CICLO = frozenset({"en_ejecucion", "en_correccion", "en_verificacion"})
CONFIANZAS = frozenset({"verificado", "por_confirmar"})
ORIGENES = frozenset({"check", "esceptico", "humano"})
SEVERIDADES = frozenset({"error", "warning"})
RESULTADOS_CHECK = frozenset({"ok", "fallo", "error_check"})
RESULTADOS_PRUEBA = frozenset({"ok", "fallo", "pendiente", "na"})

RE_FECHA = re.compile(r"^\d{2}-\d{2}-\d{4}$")
RE_FASE_ID = re.compile(r"^fase_\d+$")
# Nombre de un agente de <proyecto>/.claude/agents/<nombre>.md: nunca una ruta.
RE_AGENTE = re.compile(r"^[a-z0-9][a-z0-9_-]{0,63}$")

# Hallazgos: lo que el reflector propone y el humano decide.
DIMENSIONES = frozenset({"proceso", "dominio"})
COMPONENTES = frozenset({"regla", "check", "skill", "hook", "agente"})
CONFIANZAS_HALLAZGO = frozenset({"alta", "media", "baja"})
ESTADOS_HALLAZGO = frozenset({"propuesto", "aprobado", "rechazado"})
ORIGENES_HALLAZGO = frozenset({"reflector", "humano"})
RE_HALLAZGO_ID = re.compile(r"^h\d+$")
# Referencia a otro hallazgo: TICKET/fase_N/hN.
# El ticket no puede traer "\", "." ni "..": la referencia se convierte en una ruta.
RE_REFERENCIA = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]*/fase_\d+/h\d+$")


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


def _validar_agente_ejecutor(fase: dict, agentes: set[str] | None,
                             errores: list[str], prefijo: str) -> None:
    """Campo opcional: qué subagente ejecuta la fase cuando el perfil tiene varios.

    `agentes` son los nombres disponibles en <proyecto>/.claude/agents/; None
    significa que no hay proyecto contra el cual verificar la existencia.
    """
    if "agente_ejecutor" not in fase:
        return
    agente = fase.get("agente_ejecutor")
    if not isinstance(agente, str) or not agente.strip():
        errores.append(f"{prefijo}agente_ejecutor: si se indica, string no vacío")
    elif not RE_AGENTE.match(agente):
        errores.append(f"{prefijo}agente_ejecutor: se espera el nombre de un agente "
                       f"(minúsculas, dígitos, '-' o '_'), no una ruta: '{agente}'")
    elif agentes is not None and agente not in agentes:
        errores.append(f"{prefijo}agente_ejecutor: '{agente}' no existe en "
                       f".claude/agents/ del proyecto")


def validate_plan(data: dict, rules: dict | None = None,
                  agentes: set[str] | None = None) -> list[str]:
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

        _validar_agente_ejecutor(fase, agentes, errores, prefijo)

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


def _validar_pausas(data: dict, errores: list[str]) -> None:
    """`pausas` es opcional, salvo en una fase pausada, donde no puede faltar ni ir vacía."""
    if "pausas" not in data:
        if data.get("estado") == "pausada":
            errores.append("pausas: requerido en una fase pausada, lista no vacía")
        return
    pausas = data["pausas"]
    if not isinstance(pausas, list):
        errores.append("pausas: debe ser lista")
        return
    if data.get("estado") == "pausada" and not pausas:
        errores.append("pausas: no puede estar vacía en una fase pausada")
    for indice, pausa in enumerate(pausas):
        prefijo = f"pausas[{indice}]."
        if not isinstance(pausa, dict):
            errores.append(f"pausas[{indice}]: debe ser objeto")
            continue
        if pausa.get("desde") not in ESTADOS_EN_CICLO:
            errores.append(f"{prefijo}desde: esperado uno de {sorted(ESTADOS_EN_CICLO)}")
        fecha = pausa.get("fecha")
        if not isinstance(fecha, str) or not RE_FECHA.match(fecha):
            errores.append(f"{prefijo}fecha: formato esperado dd-mm-aaaa")
        _texto(pausa, "motivo", errores, prefijo)


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

    _validar_pausas(data, errores)

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


def _validar_reincide(item: dict, errores: list[str], prefijo: str) -> None:
    """Campo opcional: referencia al hallazgo anterior del que éste es reincidencia."""
    if "reincide" not in item:
        return
    valor = item["reincide"]
    if not isinstance(valor, str) or not RE_REFERENCIA.fullmatch(valor):
        errores.append(f"{prefijo}reincide: formato esperado TICKET/fase_N/hN")


def _validar_item_reflector(item: dict, errores: list[str], prefijo: str) -> None:
    """Campos que comparten la propuesta del reflector y el hallazgo guardado."""
    for campo in ("senal", "leccion", "evidencia"):
        _texto(item, campo, errores, prefijo)
    for campo, valores in (("confianza", CONFIANZAS_HALLAZGO),
                           ("dimension", DIMENSIONES),
                           ("componente", COMPONENTES)):
        if item.get(campo) not in valores:
            errores.append(f"{prefijo}{campo}: esperado uno de {sorted(valores)}")
    _validar_reincide(item, errores, prefijo)


def validate_propuesta_hallazgos(data: dict) -> list[str]:
    if not isinstance(data, dict):
        return ["hallazgos: requerido, objeto JSON"]
    errores: list[str] = []
    _texto(data, "fase_id", errores)
    fase_id = data.get("fase_id")
    if isinstance(fase_id, str) and fase_id.strip() and not RE_FASE_ID.match(fase_id):
        errores.append("fase_id: formato esperado fase_N")
    hallazgos = data.get("hallazgos")
    if not isinstance(hallazgos, list):
        errores.append("hallazgos: requerido, lista (puede venir vacía)")
        return errores
    for indice, item in enumerate(hallazgos):
        prefijo = f"hallazgos[{indice}]."
        if not isinstance(item, dict):
            errores.append(f"hallazgos[{indice}]: debe ser objeto")
            continue
        _validar_item_reflector(item, errores, prefijo)
    return errores


def validate_hallazgos(data: dict) -> list[str]:
    if not isinstance(data, dict):
        return ["hallazgos: requerido, objeto JSON"]
    errores: list[str] = []
    for campo in ("ticket_id", "fase_id"):
        _texto(data, campo, errores)
    hallazgos = data.get("hallazgos")
    if not isinstance(hallazgos, list):
        errores.append("hallazgos: requerido, lista")
        return errores

    vistos: set[str] = set()
    for indice, item in enumerate(hallazgos):
        prefijo = f"hallazgos[{indice}]."
        if not isinstance(item, dict):
            errores.append(f"hallazgos[{indice}]: debe ser objeto")
            continue
        identificador = item.get("id")
        if not isinstance(identificador, str) or not RE_HALLAZGO_ID.match(identificador):
            errores.append(f"{prefijo}id: requerido, formato esperado hN")
        elif identificador in vistos:
            errores.append(f"{prefijo}id: '{identificador}' duplicado")
        else:
            vistos.add(identificador)
        if item.get("origen") not in ORIGENES_HALLAZGO:
            errores.append(f"{prefijo}origen: esperado uno de {sorted(ORIGENES_HALLAZGO)}")
        if item.get("estado") not in ESTADOS_HALLAZGO:
            errores.append(f"{prefijo}estado: esperado uno de {sorted(ESTADOS_HALLAZGO)}")

        if item.get("origen") == "humano":
            _texto(item, "leccion", errores, prefijo)
            if "dimension" in item and item["dimension"] not in DIMENSIONES:
                errores.append(f"{prefijo}dimension: esperado uno de {sorted(DIMENSIONES)}")
            if "componente" in item and item["componente"] not in COMPONENTES:
                errores.append(f"{prefijo}componente: esperado uno de {sorted(COMPONENTES)}")
            _validar_reincide(item, errores, prefijo)
        elif item.get("origen") == "reflector":
            _validar_item_reflector(item, errores, prefijo)

        if item.get("estado") == "rechazado":
            _texto(item, "motivo", errores, prefijo)
    return errores


# --- Curación de la biblioteca -------------------------------------------------

TIPOS_CURACION = {"retirar", "fusionar"}
ESTADOS_CURACION = {"propuesto", "aprobado", "rechazado"}
RE_CURACION_ID = re.compile(r"^c\d+$")


def _ref(valor, errores: list[str], campo: str) -> None:
    if not isinstance(valor, str) or not RE_REFERENCIA.fullmatch(valor):
        errores.append(f"{campo}: esperado una referencia TICKET/fase_N/hN")


def _validar_accion_curacion(accion, errores: list[str], prefijo: str) -> None:
    if not isinstance(accion, dict):
        errores.append(f"{prefijo[:-1]}: debe ser objeto")
        return
    tipo = accion.get("tipo")
    if tipo not in TIPOS_CURACION:
        errores.append(f"{prefijo}tipo: esperado uno de {sorted(TIPOS_CURACION)}")
        return
    _texto(accion, "motivo", errores, prefijo)
    if tipo == "retirar":
        _ref(accion.get("ref"), errores, f"{prefijo}ref")
        return
    refs = accion.get("refs")
    if not isinstance(refs, list) or len(refs) < 2:
        errores.append(f"{prefijo}refs: requerido, lista de 2 referencias o más")
        return
    for j, ref in enumerate(refs):
        _ref(ref, errores, f"{prefijo}refs[{j}]")
    if len(set(map(str, refs))) != len(refs):
        errores.append(f"{prefijo}refs: hay referencias repetidas")
    if accion.get("destino") not in refs:
        errores.append(f"{prefijo}destino: debe ser una de refs")
    _texto(accion, "leccion", errores, prefijo)
    if "senal" in accion:
        _texto(accion, "senal", errores, prefijo)


def validate_propuesta_curacion(data: dict) -> list[str]:
    """Lo que devuelve el curador: {"acciones": [...]}, lista que puede ir vacía."""
    if not isinstance(data, dict) or not isinstance(data.get("acciones"), list):
        return ["acciones: requerido, lista"]
    errores: list[str] = []
    for i, accion in enumerate(data["acciones"]):
        _validar_accion_curacion(accion, errores, f"acciones[{i}].")
    return errores


def validate_curacion(data: dict) -> list[str]:
    """El estado en .harness/curacion.json: las acciones con id, estado y fechas."""
    errores = validate_propuesta_curacion(data)
    if errores:
        return errores
    vistos: set[str] = set()
    for i, accion in enumerate(data["acciones"]):
        prefijo = f"acciones[{i}]."
        identificador = accion.get("id")
        if not isinstance(identificador, str) or not RE_CURACION_ID.match(identificador):
            errores.append(f"{prefijo}id: requerido, formato esperado cN")
        elif identificador in vistos:
            errores.append(f"{prefijo}id: '{identificador}' duplicado")
        else:
            vistos.add(identificador)
        if accion.get("estado") not in ESTADOS_CURACION:
            errores.append(f"{prefijo}estado: esperado uno de {sorted(ESTADOS_CURACION)}")
        for campo in ("fecha_propuesta", "fecha_resuelta"):
            valor = accion.get(campo)
            if (campo == "fecha_propuesta" or valor is not None) and (
                    not isinstance(valor, str) or not RE_FECHA.match(valor)):
                errores.append(f"{prefijo}{campo}: formato esperado DD-MM-YYYY")
        if accion.get("estado") == "rechazado":
            _texto(accion, "motivo_rechazo", errores, prefijo)
    return errores
