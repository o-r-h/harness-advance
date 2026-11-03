#!/usr/bin/env python3
"""Único punto de mutación del estado del harness.

Todo lo que cambie un contador, un estado o un archivo de estado pasa por
aquí. El modelo invoca estos subcomandos; no escribe el estado a mano.
"""
from __future__ import annotations

import argparse
import json
import re
from datetime import date
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from lib import (biblioteca, checks, contracts, curacion as lib_curacion, gitdiff,
                 hallazgos as lib_hallazgos,  # noqa: E402
                 harness, plugins, prueba_manual, senales, state)
import report  # noqa: E402

VALIDADORES = {
    "ticket_context": contracts.validate_ticket_context,
    "plan": contracts.validate_plan,
    "checks": contracts.validate_checks_result,
    "veredicto": contracts.validate_veredicto,
    "fase_state": contracts.validate_fase_state,
    "hallazgos": contracts.validate_hallazgos,
}


def _forzar_utf8_en_salidas() -> None:
    """Los mensajes del harness van en español y salen por tuberías.

    En Windows la tubería hereda cp1252 y un acento se vuelve ilegible —o
    indescifrable— para quien lea la salida. Esto reconfigura solo stdout y
    stderr del CLI; nunca la lectura de archivos del proyecto, que conserva
    su respaldo cp1252.
    """
    for flujo in (sys.stdout, sys.stderr):
        try:
            flujo.reconfigure(encoding="utf-8")
        except (AttributeError, ValueError):
            pass


def _error(mensaje: str) -> int:
    sys.stderr.write(f"HARNESS · {mensaje}\n")
    return 1


def resolver_proyecto(valor: str | None) -> Path:
    """Raíz del proyecto: la indicada, o la deducida del directorio actual."""
    base = Path(valor) if valor else Path.cwd()
    raiz = harness.find_project_root(base)
    return raiz if raiz is not None else base.resolve()


def _leer_ticket_activo(raiz: Path) -> tuple[str, dict] | None:
    actual = harness.read_current(raiz)
    if not actual or not actual.get("ticket_id"):
        return None
    ruta = harness.ticket_dir(raiz, actual["ticket_id"]) / "ticket_context.json"
    if not ruta.is_file():
        return None
    return actual["ticket_id"], harness.read_json(ruta)


# Estados en que el ejecutor está trabajando la fase y los checks tienen sentido.
EN_CICLO = contracts.ESTADOS_EN_CICLO


def _fase_corriendo(raiz: Path) -> tuple[str, str, str] | None:
    """(ticket_id, fase_id, estado) de la fase de current.json si está en ciclo."""
    actual = harness.read_current(raiz)
    if not actual or not actual.get("ticket_id") or not actual.get("fase_id"):
        return None
    ticket_id, fase_id = actual["ticket_id"], actual["fase_id"]
    estado = state.leer_fase(raiz, ticket_id, fase_id)
    if estado is None or estado["estado"] not in EN_CICLO:
        return None
    return ticket_id, fase_id, estado["estado"]


def cmd_open_ticket(args) -> int:
    raiz = resolver_proyecto(args.project)
    corriendo = _fase_corriendo(raiz)
    if corriendo:
        return _error(f"la fase '{corriendo[1]}' del ticket '{corriendo[0]}' está en estado "
                      f"'{corriendo[2]}': pausala con /fase-pausa o ciérrala antes de abrir "
                      f"un ticket")
    ctx = {
        "ticket_id": args.ticket_id,
        "nroticket": args.nroticket,
        "desarrollador": args.desarrollador,
        "fecha": args.fecha,
        "perfil": args.perfil,
    }
    errores = contracts.validate_ticket_context(ctx)
    if errores:
        return _error("ticket_context inválido: " + "; ".join(errores))

    carpeta = harness.ticket_dir(raiz, args.ticket_id)
    harness.write_json(carpeta / "ticket_context.json", ctx)
    if not (carpeta / "ticket_state.json").is_file():
        harness.write_json(carpeta / "ticket_state.json",
                           {"ticket_id": args.ticket_id, "fase_actual": None,
                            "fases_aprobadas": []})
    harness.write_current(raiz, args.ticket_id, None)
    print(f"Ticket {args.ticket_id} abierto en {carpeta}")
    return 0


def cmd_open_fase(args) -> int:
    raiz = resolver_proyecto(args.project)
    activo = _leer_ticket_activo(raiz)
    if activo is None:
        return _error("no hay ticket activo: corre primero 'open-ticket'")
    ticket_id, _ = activo

    corriendo = _fase_corriendo(raiz)
    if corriendo and corriendo[1] != args.fase:
        return _error(f"la fase '{corriendo[1]}' está en estado '{corriendo[2]}': pausala "
                      f"con /fase-pausa o ciérrala antes de abrir '{args.fase}'")

    ruta_plan = harness.ticket_dir(raiz, ticket_id) / "plan.json"
    if not ruta_plan.is_file():
        return _error(f"falta {ruta_plan}: el planner debe emitir plan.json "
                      f"antes de abrir una fase")
    plan = harness.read_json(ruta_plan)
    con_perfil = harness.find_project_root(raiz) is not None
    reglas = harness.load_rules(raiz) if con_perfil else None
    agentes = harness.list_agents(raiz) if con_perfil else None
    errores = contracts.validate_plan(plan, reglas, agentes)
    if errores:
        return _error("plan.json inválido: " + "; ".join(errores))

    fase = next((f for f in plan["fases"] if f["id"] == args.fase), None)
    if fase is None:
        return _error(f"la fase '{args.fase}' no existe en plan.json")

    for dependencia in fase.get("depende_de") or []:
        previo = state.leer_fase(raiz, ticket_id, dependencia)
        if previo is None or previo["estado"] != "aprobada":
            actual = previo["estado"] if previo else "sin abrir"
            return _error(f"la fase '{args.fase}' depende de '{dependencia}', "
                          f"que está en estado '{actual}' y no 'aprobada'")

    existente = state.leer_fase(raiz, ticket_id, fase["id"])
    if existente is not None and existente["estado"] == "pausada":
        estado = state.reanudar_fase(raiz, ticket_id, fase["id"])
        resumen = f"reanudada en estado '{estado['estado']}'"
    else:
        estado = state.abrir_fase(raiz, ticket_id, fase)
        resumen = f"en estado '{estado['estado']}'"
    harness.write_current(raiz, ticket_id, fase["id"])
    print(f"Fase {fase['id']} {resumen}, "
          f"intento {estado['intento_actual']}/{estado['max_reintentos']}")
    print(f"Ejecutor: {fase.get('agente_ejecutor') or 'el agente del perfil'}")
    return 0


def cmd_validate(args) -> int:
    validador = VALIDADORES[args.contrato]
    datos = harness.read_json(Path(args.archivo))
    if args.contrato == "plan":
        raiz = resolver_proyecto(args.project)
        con_perfil = harness.find_project_root(raiz) is not None
        reglas = harness.load_rules(raiz) if con_perfil else None
        agentes = harness.list_agents(raiz) if con_perfil else None
        errores = validador(datos, reglas, agentes)
    else:
        errores = validador(datos)
    if errores:
        return _error(f"{args.contrato} inválido: " + "; ".join(errores))
    print(f"{args.contrato}: válido")
    return 0


def _fase_activa(raiz: Path) -> tuple[str, dict, dict, dict] | None:
    """(ticket_id, ctx, fase_del_plan, fase_state) de la fase activa."""
    actual = harness.read_current(raiz)
    if not actual or not actual.get("ticket_id") or not actual.get("fase_id"):
        return None
    ticket_id, fase_id = actual["ticket_id"], actual["fase_id"]
    carpeta = harness.ticket_dir(raiz, ticket_id)
    if not (carpeta / "ticket_context.json").is_file() or not (carpeta / "plan.json").is_file():
        return None
    ctx = harness.read_json(carpeta / "ticket_context.json")
    plan = harness.read_json(carpeta / "plan.json")
    fase = next((f for f in plan["fases"] if f["id"] == fase_id), None)
    estado = state.leer_fase(raiz, ticket_id, fase_id)
    if fase is None or estado is None:
        return None
    return ticket_id, ctx, fase, estado


def cmd_pausar_fase(args) -> int:
    raiz = resolver_proyecto(args.project)
    activa = _fase_activa(raiz)
    if activa is None:
        return _error("no hay fase activa que pausar: corre 'open-fase'")
    ticket_id, _, fase, _ = activa
    estado = state.pausar_fase(raiz, ticket_id, fase["id"],
                               motivo=args.motivo or "sin motivo", fecha=_hoy())
    print(f"Fase {fase['id']} pausada, intento {estado['intento_actual']}/"
          f"{estado['max_reintentos']}")
    print(f"Para retomarla: /fase {fase['id']} (ticket {ticket_id})")
    return 0


def cmd_run_checks(args) -> int:
    raiz = resolver_proyecto(args.project)
    activa = _fase_activa(raiz)
    if activa is None:
        return _error("no hay fase activa con plan y contexto: corre 'open-fase'")
    ticket_id, ctx, fase, estado = activa
    if estado["estado"] not in EN_CICLO:
        return _error(f"la fase '{fase['id']}' está en estado '{estado['estado']}': los "
                      f"checks se corren mientras la fase está en ejecución o en corrección")
    reglas = harness.load_rules(raiz)

    pedidos = [c for c in fase.get("checks_deterministas") or [] if isinstance(c, str)]
    resueltos, desconocidos = contracts.resolve_check_names(pedidos, reglas)
    hallazgos: list[dict] = []
    for nombre in desconocidos:
        hallazgos.append({"id": nombre, "resultado": "error_check", "severidad": "error",
                          "detalle": f"'{nombre}' no existe como check ni como grupo "
                                     f"en rules.json"})

    archivos = gitdiff.archivos_modificados(raiz)
    declarativos = [c for c in resueltos if c not in (reglas.get("checks_estructurales") or [])]
    for archivo in archivos:
        hallazgos += checks.run_file_checks(raiz, archivo, reglas, ctx, solo=declarativos)

    estructurales = plugins.cargar_checks_estructurales(raiz)
    for nombre in resueltos:
        if nombre in estructurales:
            hallazgos += plugins.ejecutar(nombre, estructurales[nombre], raiz, archivos, ctx)
        elif nombre in (reglas.get("checks_estructurales") or []):
            hallazgos.append({"id": nombre, "resultado": "error_check", "severidad": "error",
                              "detalle": f"rules.json declara el check estructural "
                                         f"'{nombre}' pero no existe .claude/checks/"
                                         f"{nombre}.py: no se verificó"})

    bloqueantes = [h for h in hallazgos
                   if h.get("resultado") == "fallo" and h.get("severidad") == "error"]
    resultado = {
        "fase_id": fase["id"],
        "intento": estado["intento_actual"],
        "resultado": "fallo" if bloqueantes else "ok",
        "checks": hallazgos if hallazgos else [{"id": "sin_hallazgos", "resultado": "ok"}],
    }
    errores_contrato = contracts.validate_checks_result(resultado)
    if errores_contrato:
        return _error("checks.json generado es inválido (bug del harness): "
                      + "; ".join(errores_contrato))

    destino = harness.intento_dir(raiz, ticket_id, fase["id"], estado["intento_actual"])
    harness.write_json(destino / "checks.json", resultado)
    print(f"checks: {resultado['resultado']} — {len(bloqueantes)} error(es) bloqueante(s), "
          f"{len(hallazgos) - len(bloqueantes)} no bloqueante(s) → {destino / 'checks.json'}")

    # Un fallo de checks es un intento perdido, igual que un rechazo del escéptico:
    # el contador lo lleva el CLI, no la memoria del modelo.
    if not bloqueantes:
        state.set_estado(raiz, ticket_id, fase["id"], "en_verificacion")
        return 0
    razon = "; ".join(f"{h['id']}: {h.get('detalle', '')}" for h in bloqueantes)
    nuevo = state.registrar_fallo(raiz, ticket_id, fase["id"], "check", razon)
    print(f"Fallo registrado. Estado: {nuevo['estado']}, "
          f"intento {nuevo['intento_actual']}/{nuevo['max_reintentos']}")
    return 1


def cmd_record_veredicto(args) -> int:
    raiz = resolver_proyecto(args.project)
    activa = _fase_activa(raiz)
    if activa is None:
        return _error("no hay fase activa: corre 'open-fase'")
    ticket_id, _, fase, estado = activa
    if estado["estado"] == "pausada":
        return _error(f"la fase '{fase['id']}' está pausada: reanúdala con "
                      f"/fase {fase['id']}")

    veredicto = harness.read_json(Path(args.archivo))
    errores = contracts.validate_veredicto(veredicto)
    if errores:
        return _error("veredicto inválido: " + "; ".join(errores))
    if veredicto["fase_id"] != fase["id"]:
        return _error(f"el veredicto dice fase '{veredicto['fase_id']}' pero la fase "
                      f"activa es '{fase['id']}'")

    destino = harness.intento_dir(raiz, ticket_id, fase["id"], estado["intento_actual"])
    harness.write_json(destino / "veredicto.json", veredicto)

    if not veredicto["juicio_esceptico"]["aprobado"]:
        razon = "; ".join(veredicto["juicio_esceptico"]["razones_rechazo"])
        nuevo = state.registrar_fallo(raiz, ticket_id, fase["id"], "esceptico", razon)
        print(f"Escéptico rechazó. Estado: {nuevo['estado']}, "
              f"intento {nuevo['intento_actual']}/{nuevo['max_reintentos']}")
        return 0

    if (fase.get("prueba_manual") or {}).get("requerida"):
        state.set_estado(raiz, ticket_id, fase["id"], "esperando_humano")
        print("Escéptico aprobó. Falta la prueba manual: responde con "
              "/fase-ok o /fase-fallo <paso> \"<observación>\".")
        return 0

    state.aprobar_fase(raiz, ticket_id, fase["id"])
    print("Escéptico aprobó y la fase no requería prueba manual: fase aprobada.")
    return 0


def cmd_generar_prueba(args) -> int:
    raiz = resolver_proyecto(args.project)
    activa = _fase_activa(raiz)
    if activa is None:
        return _error("no hay fase activa: corre 'open-fase'")
    ticket_id, _, fase, estado = activa
    if estado["estado"] == "pausada":
        return _error(f"la fase '{fase['id']}' está pausada: reanúdala con "
                      f"/fase {fase['id']}")
    pasos = harness.read_json(Path(args.pasos_json))
    if not isinstance(pasos, list) or not pasos:
        return _error("--pasos-json debe contener una lista no vacía de "
                      "objetos {paso, esperado}")
    destino = harness.intento_dir(raiz, ticket_id, fase["id"], estado["intento_actual"])
    destino.mkdir(parents=True, exist_ok=True)
    archivo = destino / "prueba_manual.md"
    archivo.write_text(prueba_manual.render(fase, estado["intento_actual"], pasos),
                       encoding="utf-8")
    print(f"Guion de prueba escrito en {archivo}")
    return 0


def cmd_record_manual(args) -> int:
    raiz = resolver_proyecto(args.project)
    activa = _fase_activa(raiz)
    if activa is None:
        return _error("no hay fase activa: corre 'open-fase'")
    ticket_id, _, fase, estado = activa

    if estado["estado"] != "esperando_humano":
        return _error(f"la fase está en estado '{estado['estado']}': solo se registra la "
                      f"prueba manual cuando está en 'esperando_humano'")
    if args.resultado == "fallo" and (args.paso is None or not args.observacion):
        return _error("un fallo exige --paso y --observacion: sin eso el intento "
                      "siguiente no sabe qué corregir")

    carpeta = harness.intento_dir(raiz, ticket_id, fase["id"], estado["intento_actual"])
    ruta_veredicto = carpeta / "veredicto.json"
    if not ruta_veredicto.is_file():
        return _error(f"falta {ruta_veredicto}: el escéptico debe emitir su veredicto antes "
                      f"de la prueba manual")
    veredicto = harness.read_json(ruta_veredicto)

    veredicto["prueba_manual"].update({
        "requerida": True, "ejecutada": True, "resultado": args.resultado})
    if args.resultado == "fallo":
        veredicto["prueba_manual"]["fallo_en_paso"] = args.paso
        veredicto["prueba_manual"]["observacion"] = args.observacion
        veredicto["aprobado"] = False
    else:
        veredicto["prueba_manual"].pop("fallo_en_paso", None)
        veredicto["prueba_manual"].pop("observacion", None)
        veredicto["aprobado"] = bool(veredicto["juicio_esceptico"]["aprobado"])

    errores = contracts.validate_veredicto(veredicto)
    if errores:
        return _error("el veredicto resultante es inválido: " + "; ".join(errores))
    harness.write_json(ruta_veredicto, veredicto)

    if args.resultado == "ok":
        state.aprobar_fase(raiz, ticket_id, fase["id"])
        print(f"Prueba manual OK. Fase {fase['id']} aprobada.")
        return 0

    razon = f"prueba manual: falló en el paso {args.paso} — {args.observacion}"
    nuevo = state.registrar_fallo(raiz, ticket_id, fase["id"], "humano", razon)
    print(f"Prueba manual falló. Estado: {nuevo['estado']}, "
          f"intento {nuevo['intento_actual']}/{nuevo['max_reintentos']}")
    return 0


# Referencia completa de un hallazgo, tal como la imprime 'hallazgos-pendientes'.
RE_REF_HALLAZGO = re.compile(r"^([A-Za-z0-9][\w.-]*)/(fase_\d+)/(h\d+)$")
RE_TICKET_ID = re.compile(r"^[A-Za-z0-9][\w.-]*$")


def _validar_ticket_y_fase(ticket: str | None, fase: str | None) -> str | None:
    """Mensaje de error si --ticket/--fase vienen mal formados; None si están bien."""
    if ticket is not None and not RE_TICKET_ID.match(ticket):
        return f"--ticket '{ticket}' no es un id de ticket válido"
    if fase is not None and not contracts.RE_FASE_ID.match(fase):
        return f"--fase '{fase}' no tiene el formato esperado fase_N"
    return None


def _fase_objetivo(raiz: Path, ref: str, ticket: str | None,
                   fase: str | None) -> tuple[str, str, str] | str:
    """(ticket_id, fase_id, hallazgo_id) del hallazgo pedido, o el mensaje de error.

    La referencia completa TICKET/fase_N/hN manda sobre --ticket y --fase. Con un id
    suelto, --ticket exige --fase, y --fase sin --ticket solo vale para la fase de
    current.json: si no, el mismo hN de otro ticket se resolvería sin aviso.
    """
    completa = RE_REF_HALLAZGO.match(ref)
    if completa:
        return completa.group(1), completa.group(2), completa.group(3)
    if not contracts.RE_HALLAZGO_ID.match(ref):
        return (f"'{ref}' no es un hallazgo: usa el id (h1) o la referencia completa "
                f"TICKET/fase_N/hN que imprime 'hallazgos-pendientes'")
    error = _validar_ticket_y_fase(ticket, fase)
    if error:
        return error
    if ticket and not fase:
        return "--ticket exige --fase, o usa la referencia completa TICKET/fase_N/hN"
    if ticket:
        return ticket, fase, ref

    actual = harness.read_current(raiz) or {}
    ticket_activo, fase_activa = actual.get("ticket_id"), actual.get("fase_id")
    if fase and (not ticket_activo or fase != fase_activa):
        ejemplo = f"{ticket_activo or 'TICKET'}/{fase}/{ref}"
        return (f"--fase {fase} no es la fase activa ({fase_activa or 'ninguna'}): usa la "
                f"referencia completa, por ejemplo {ejemplo}, o indica también --ticket")
    if not ticket_activo or not fase_activa:
        return ("no se sabe qué fase resolver: usa la referencia completa TICKET/fase_N/hN "
                "que imprime 'hallazgos-pendientes'")
    return ticket_activo, fase_activa, ref


def _hoy() -> str:
    return date.today().strftime("%d-%m-%Y")


def cmd_record_hallazgos(args) -> int:
    raiz = resolver_proyecto(args.project)
    if bool(args.ticket) != bool(args.fase):
        return _error("--ticket y --fase van juntos: indica los dos o ninguno")
    if args.ticket:
        error = _validar_ticket_y_fase(args.ticket, args.fase)
        if error:
            return _error(error)
        ticket_id, fase_id = args.ticket, args.fase
        estado = state.leer_fase(raiz, ticket_id, fase_id)
        if estado is None:
            return _error(f"la fase '{fase_id}' del ticket '{ticket_id}' no se ha abierto")
    else:
        activa = _fase_activa(raiz)
        if activa is None:
            return _error("no hay fase activa: corre 'open-fase'")
        ticket_id, _, fase, estado = activa
        fase_id = fase["id"]
    if estado["estado"] not in ("aprobada", "escalado"):
        return _error(f"la fase '{fase_id}' está en estado '{estado['estado']}': los "
                      f"hallazgos se proponen cuando está 'aprobada' o 'escalado'")

    propuesta = harness.read_json(Path(args.archivo))
    errores = contracts.validate_propuesta_hallazgos(propuesta)
    if errores:
        return _error("propuesta de hallazgos inválida: " + "; ".join(errores))
    if propuesta["fase_id"] != fase_id:
        return _error(f"la propuesta dice fase '{propuesta['fase_id']}' pero se registra "
                      f"en '{fase_id}'")

    for i, h in enumerate(propuesta["hallazgos"]):
        ref = h.get("reincide")
        if ref and biblioteca.leer_entrada(raiz, ref) is None:
            return _error(f"la propuesta dice que hallazgos[{i}] reincide en "
                          f"{_fuera_de_entradas(raiz, ref)}")

    previo = lib_hallazgos.leer(raiz, ticket_id, fase_id)
    existentes = (previo or {}).get("hallazgos", [])
    if any(h.get("origen") != "humano" and h.get("estado") != "propuesto" for h in existentes):
        return _error(f"la fase '{fase_id}' ya tiene hallazgos resueltos: no se "
                      f"reescriben para no pisar tus decisiones")

    # Los del humano se conservan; los del reflector aún propuestos se reemplazan.
    # La numeración sigue al id más alto que hubo, incluso de los reemplazados: un hN
    # que el humano ya vio nunca pasa a nombrar otra lección.
    items = [h for h in existentes if h.get("origen") == "humano"]
    siguiente = max((int(h["id"][1:]) for h in existentes), default=0) + 1
    nuevos = propuesta["hallazgos"]
    for numero, h in enumerate(nuevos, start=siguiente):
        item = {"id": f"h{numero}", "origen": "reflector", "estado": "propuesto"}
        for campo in ("senal", "leccion", "evidencia", "confianza", "dimension", "componente"):
            item[campo] = h[campo]
        if h.get("reincide"):
            item["reincide"] = h["reincide"]
        items.append(item)
    datos = {"ticket_id": ticket_id, "fase_id": fase_id, "hallazgos": items}
    md = lib_hallazgos.guardar(raiz, datos)
    if not nuevos:
        print("Sin hallazgos nuevos del reflector en esta fase.")
    else:
        print(f"{len(nuevos)} hallazgo(s) propuesto(s) en {md}")
    return 0


def cmd_resolver_hallazgo(args) -> int:
    raiz = resolver_proyecto(args.project)
    objetivo = _fase_objetivo(raiz, args.id, args.ticket, args.fase)
    if isinstance(objetivo, str):
        return _error(objetivo)
    ticket_id, fase_id, hallazgo_id = objetivo
    ref = lib_hallazgos.referencia(ticket_id, fase_id, hallazgo_id)

    if args.decision == "no" and not args.motivo:
        return _error("rechazar un hallazgo exige --motivo: el reflector lo lee para no "
                      "volver a proponerlo")
    if args.decision == "editar" and not (args.texto or "").strip():
        return _error("editar un hallazgo exige --texto con la lección corregida")

    if args.decision == "no" and (args.nueva or args.reincide):
        return _error("--nueva y --reincide solo valen al aprobar (--decision ok|editar)")
    if args.nueva and args.reincide:
        return _error("--nueva y --reincide se excluyen: elige una")
    if args.reincide and not contracts.RE_REFERENCIA.fullmatch(args.reincide):
        return _error(f"--reincide '{args.reincide}' no tiene la forma TICKET/fase_N/hN")

    datos = lib_hallazgos.leer(raiz, ticket_id, fase_id)
    if datos is None:
        return _error(f"la fase '{fase_id}' del ticket '{ticket_id}' no tiene hallazgos")
    hallazgo = next((h for h in datos["hallazgos"] if h["id"] == hallazgo_id), None)
    if hallazgo is None:
        validos = ", ".join(h["id"] for h in datos["hallazgos"]) or "ninguno"
        return _error(f"el hallazgo '{ref}' no existe; ids válidos en "
                      f"{ticket_id}/{fase_id}: {validos}")
    if hallazgo["estado"] != "propuesto":
        return _error(f"el hallazgo {ref} ya está '{hallazgo['estado']}'")

    ref_efectiva = None
    if args.decision != "no" and not args.nueva:
        ref_efectiva = args.reincide or hallazgo.get("reincide")
        if ref_efectiva and biblioteca.leer_entrada(raiz, ref_efectiva) is None:
            return _error(f"el hallazgo {ref} reincide en {_fuera_de_entradas(raiz, ref_efectiva)}: "
                          "usa --nueva si no es reincidencia, o --reincide <ref> con "
                          "otra lección")

    if args.decision == "no":
        hallazgo["estado"] = "rechazado"
        hallazgo["motivo"] = args.motivo
    else:
        if args.decision == "editar":
            hallazgo["leccion_original"] = hallazgo.get("leccion", "")
            hallazgo["leccion"] = args.texto
        hallazgo["estado"] = "aprobado"
        if ref_efectiva:
            hallazgo["reincide"] = ref_efectiva
        else:
            hallazgo.pop("reincide", None)

    # La biblioteca se escribe antes que el hallazgo: si falla, el hallazgo sigue
    # 'propuesto' y se puede reintentar, en vez de quedar aprobado sin su entrada.
    if ref_efectiva:
        entrada = biblioteca.registrar_falla(raiz, ref_efectiva, ref,
                                             hallazgo.get("leccion", ""), _hoy())
        lib_hallazgos.guardar(raiz, datos)
        print(f"Hallazgo {ref} aprobado como reincidencia de {ref_efectiva}: {entrada}")
        return 0
    entrada = biblioteca.escribir_entrada(raiz, ticket_id, fase_id, hallazgo, fecha=_hoy())
    lib_hallazgos.guardar(raiz, datos)
    print(f"Hallazgo {ref} {hallazgo['estado']}: {entrada}")
    return 0


def cmd_hallazgo(args) -> int:
    raiz = resolver_proyecto(args.project)
    activa = _fase_activa(raiz)
    if activa is None:
        return _error("no hay fase activa: corre 'open-fase'")
    ticket_id, _, fase, _ = activa
    if not args.texto.strip():
        return _error("--texto no puede estar vacío")

    datos = lib_hallazgos.leer(raiz, ticket_id, fase["id"]) or {
        "ticket_id": ticket_id, "fase_id": fase["id"], "hallazgos": []}
    numeros = [int(h["id"][1:]) for h in datos["hallazgos"]]
    nuevo = {"id": f"h{max(numeros, default=0) + 1}", "origen": "humano",
             "estado": "aprobado", "leccion": args.texto}
    if args.dimension:
        nuevo["dimension"] = args.dimension
    if args.componente:
        nuevo["componente"] = args.componente
    datos["hallazgos"].append(nuevo)

    entrada = biblioteca.escribir_entrada(raiz, ticket_id, fase["id"], nuevo, fecha=_hoy())
    lib_hallazgos.guardar(raiz, datos)
    print(f"Hallazgo {nuevo['id']} aprobado: {entrada}")
    return 0


def cmd_hallazgo_hecho(args) -> int:
    raiz = resolver_proyecto(args.project)
    if not contracts.RE_REFERENCIA.fullmatch(args.id):
        return _error(f"--id '{args.id}' no tiene la forma TICKET/fase_N/hN: "
                      "este comando solo acepta la referencia completa")
    if not args.nota.strip():
        return _error("--nota no puede estar vacía: di qué pieza se hizo (commit, archivo)")
    if biblioteca.leer_entrada(raiz, args.id) is None:
        return _error(f"no se puede marcar {_fuera_de_entradas(raiz, args.id)}")
    fecha = _hoy()
    anterior = biblioteca.marcar_implementada(raiz, args.id, args.nota, fecha)
    print(f"Lección {args.id} implementada: {fecha} · {' '.join(args.nota.split())}")
    if anterior:
        print(f"Reemplaza la marca anterior: {anterior}")
    return 0


def cmd_reconstruir_biblioteca(args) -> int:
    raiz = resolver_proyecto(args.project)
    print(f"Índice reconstruido en {biblioteca.reconstruir_indice(raiz)}")
    return 0


def cmd_senales_biblioteca(args) -> int:
    raiz = resolver_proyecto(args.project)
    datos = senales.senales(raiz)
    if args.json:
        print(json.dumps(datos, ensure_ascii=False, indent=2))
        return 0
    if not datos["lecciones"]:
        print("La biblioteca no tiene lecciones aprobadas.")
    for leccion in datos["lecciones"]:
        ultimo = f" (último {leccion['ultimo_uso']})" if leccion["ultimo_uso"] else ""
        rutas = leccion["rutas_ausentes"]
        texto_rutas = ("desconocido" if rutas is None else ", ".join(rutas) or "ninguna")
        print(f"{leccion['ref']} — usos {leccion['usos']}{ultimo} — rutas ausentes: "
              f"{texto_rutas}")
    return 0


def _fuera_de_entradas(raiz: Path, ref: str) -> str:
    """Por qué una ref no es una lección aprobada; si se retiró, adónde fue."""
    donde, motivo = biblioteca.ubicacion(raiz, ref)
    if donde != "retiradas":
        return f"'{ref}', que no es una lección aprobada de la biblioteca"
    texto = f"'{ref}', que se retiró de la biblioteca ({motivo})"
    if motivo.startswith("fusionada en "):
        texto += f": usa {motivo[len('fusionada en '):]}"
    return texto


def cmd_record_curacion(args) -> int:
    raiz = resolver_proyecto(args.project)
    propuesta = harness.read_json(Path(args.archivo))
    errores = contracts.validate_propuesta_curacion(propuesta)
    if errores:
        return _error("propuesta de curación inválida: " + "; ".join(errores))

    vistas: set[str] = set()
    for i, accion in enumerate(propuesta["acciones"]):
        refs = lib_curacion.refs_de(accion)
        for ref in refs:
            if biblioteca.leer_entrada(raiz, ref) is None:
                return _error(f"acciones[{i}] nombra {_fuera_de_entradas(raiz, ref)}")
            if ref in vistas:
                return _error(f"acciones[{i}]: '{ref}' ya está en otra acción de esta "
                              f"propuesta; una lección va en una sola acción")
            vistas.add(ref)
        if accion["tipo"] == "fusionar":
            estados = {bool(biblioteca.leer_entrada(raiz, r)["implementada"]) for r in refs}
            if len(estados) > 1:
                return _error(f"acciones[{i}] fusiona lecciones implementadas con no "
                              f"implementadas: sus fallas quedarían fuera del reporte")

    previo = lib_curacion.leer(raiz) or {"acciones": []}
    # Las pendientes se reemplazan; las resueltas quedan como historia. Los ids siguen
    # al mayor que hubo: un cN que el humano ya vio nunca nombra otra acción.
    resueltas = [a for a in previo["acciones"] if a["estado"] != "propuesto"]
    siguiente = max((int(a["id"][1:]) for a in previo["acciones"]), default=0) + 1
    # Solo los campos del contrato: la propuesta la escribe un modelo, y un campo de
    # más (una fecha_resuelta inventada) falsearía el estado y el reporte.
    campos = {"retirar": ("tipo", "ref", "motivo"),
              "fusionar": ("tipo", "refs", "destino", "leccion", "senal", "motivo")}
    nuevas = [{**{c: accion[c] for c in campos[accion["tipo"]] if c in accion},
               "id": f"c{n}", "estado": "propuesto", "fecha_propuesta": _hoy()}
              for n, accion in enumerate(propuesta["acciones"], start=siguiente)]
    md = lib_curacion.guardar(raiz, {"acciones": resueltas + nuevas})
    if nuevas:
        print(f"{len(nuevas)} acción(es) propuesta(s) en {md}")
    else:
        print("El curador no propuso acciones.")
    return 0


def _anclada_por_el_ticket_abierto(raiz: Path, refs: list[str]) -> tuple[str, str] | None:
    """(ref, ticket) si el plan del ticket de current.json ancla alguna de las refs y
    ese ticket sigue abierto: alguna de sus fases no está aprobada. current.json no se
    limpia al terminar, así que un ticket con todo aprobado ya no cuenta."""
    actual = harness.read_current(raiz) or {}
    ticket = actual.get("ticket_id")
    plan = harness.ticket_dir(raiz, ticket) / "plan.json" if ticket else None
    if plan is None or not plan.is_file():
        return None
    datos = harness.read_json(plan)
    fases = [f for f in (datos.get("fases") if isinstance(datos, dict) else None) or []
             if isinstance(f, dict)]
    abierto = any(((state.leer_fase(raiz, ticket, str(f.get("id"))) or {}).get("estado")
                   != "aprobada") for f in fases if f.get("id"))
    if not abierto:
        return None
    nombres = set()
    for fase in fases:
        anclajes = fase.get("anclajes")
        for ancla in anclajes if isinstance(anclajes, list) else []:
            if isinstance(ancla, dict):
                nombres.add(str(ancla.get("ref", "")).replace("\\", "/").rsplit("/", 1)[-1])
    for ref in refs:
        if biblioteca.entrada_path(raiz, ref).name in nombres:
            return ref, ticket
    return None


def cmd_resolver_curacion(args) -> int:
    raiz = resolver_proyecto(args.project)
    datos = lib_curacion.leer(raiz)
    acciones = (datos or {}).get("acciones", [])
    accion = next((a for a in acciones if a["id"] == args.id), None)
    if accion is None:
        validos = ", ".join(a["id"] for a in acciones) or "ninguno"
        return _error(f"la acción '{args.id}' no existe; ids válidos: {validos}")
    if accion["estado"] != "propuesto":
        return _error(f"la acción {args.id} ya está '{accion['estado']}'")

    de_fusion = args.texto or args.senal or args.quitar
    if args.decision != "editar" and (de_fusion or (args.motivo and args.decision == "ok")):
        return _error("--texto, --senal, --quitar y --motivo solo valen al editar "
                      "(y --motivo también al rechazar)")
    if args.decision == "no":
        if not (args.motivo or "").strip():
            return _error("rechazar una acción exige --motivo: el curador lo lee para no "
                          "volver a proponerla")
        accion.update(estado="rechazado", motivo_rechazo=args.motivo, fecha_resuelta=_hoy())
        rechazos = lib_curacion.registrar_rechazo(raiz, accion, _hoy())
        lib_curacion.guardar(raiz, datos)
        print(f"Acción {args.id} rechazada: {rechazos}")
        return 0

    if args.decision == "editar":
        if accion["tipo"] == "retirar":
            if de_fusion:
                return _error("--texto, --senal y --quitar solo valen al editar una fusión")
            if not (args.motivo or "").strip():
                return _error("editar una retirada exige --motivo con el motivo corregido")
            accion["motivo"] = args.motivo
        else:
            if not de_fusion:
                return _error("editar una fusión exige --texto, --senal o --quitar")
            for ref in args.quitar or []:
                if ref == accion["destino"]:
                    return _error(f"no se puede quitar el destino {ref}: rechaza la acción "
                                  f"si no es esa la lección que queda")
                if ref not in accion["refs"]:
                    return _error(f"'{ref}' no está en la fusión {args.id}")
            refs = [r for r in accion["refs"] if r not in (args.quitar or [])]
            if len(refs) < 2:
                return _error("quitando esas refs queda una sola lección: no hay fusión; "
                              "rechaza la acción")
            accion["refs"] = refs
            if args.texto:
                accion["leccion"] = args.texto
            if args.senal:
                accion["senal"] = args.senal

    errores = contracts.validate_propuesta_curacion({"acciones": [accion]})
    if errores:  # lo editado se valida antes de tocar la biblioteca
        return _error(f"la acción {args.id} editada no es válida: " + "; ".join(errores))
    refs = lib_curacion.refs_de(accion)
    # Un intento anterior que falló a mitad pudo dejar absorbidas ya retiradas como
    # "fusionada en <destino>": esas ya están hechas, el reintento sigue con el resto.
    hechas = [r for r in refs if accion["tipo"] == "fusionar" and r != accion["destino"]
              and biblioteca.ubicacion(raiz, r) == ("retiradas",
                                                    f"fusionada en {accion['destino']}")]
    refs = [r for r in refs if r not in hechas]
    for ref in refs:
        if biblioteca.leer_entrada(raiz, ref) is None:
            return _error(f"la acción {args.id} nombra {_fuera_de_entradas(raiz, ref)}")
    anclada = _anclada_por_el_ticket_abierto(raiz, refs)
    if anclada:
        return _error(f"la lección {anclada[0]} la ancla el ticket abierto {anclada[1]}: "
                      f"resuélvela cuando todas sus fases estén aprobadas")

    # La biblioteca se escribe antes que curacion.json: si falla, la acción sigue
    # 'propuesto' y se puede reintentar.
    if accion["tipo"] == "retirar":
        ruta = biblioteca.retirar(raiz, accion["ref"], accion["motivo"], _hoy())
    else:
        otras = [r for r in refs if r != accion["destino"]]
        if otras:
            ruta = biblioteca.fusionar(raiz, accion["destino"], otras, accion["leccion"],
                                       accion.get("senal"), _hoy())
        else:  # todas quedaron absorbidas en el intento anterior
            biblioteca.reconstruir_indice(raiz)
            ruta = biblioteca.entrada_path(raiz, accion["destino"])
    accion.update(estado="aprobado", fecha_resuelta=_hoy())
    lib_curacion.guardar(raiz, datos)
    print(f"Acción {args.id} aplicada: {ruta}")
    return 0


def cmd_hallazgos_pendientes(args) -> int:
    raiz = resolver_proyecto(args.project)
    lineas = []
    for archivo in sorted(harness.tickets_dir(raiz).glob("*/fase_*/hallazgos.json")):
        try:
            datos = harness.read_json(archivo)
            if contracts.validate_hallazgos(datos):
                raise ValueError("contrato inválido")
        except (OSError, ValueError):
            sys.stderr.write(f"HARNESS · se omite {archivo}: ilegible o inválido\n")
            continue
        for h in datos.get("hallazgos", []):
            if h.get("estado") == "propuesto":
                lineas.append(f"{archivo.parent.parent.name}/{archivo.parent.name}/"
                              f"{h['id']} — {h.get('senal', h.get('leccion', ''))}")
    print("\n".join(lineas) if lineas else "Sin hallazgos pendientes.")
    return 0


def cmd_report(args) -> int:
    raiz = resolver_proyecto(args.project)
    datos = report.agregar(raiz)
    if args.json:
        print(json.dumps(datos, ensure_ascii=False, indent=2))
    else:
        sys.stdout.write(report.render(datos))
    return 0


def construir_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="harness-cli", description=__doc__)
    sub = parser.add_subparsers(dest="comando", required=True)

    p = sub.add_parser("open-ticket", help="Abre un ticket y fija el contexto")
    p.add_argument("--project")
    p.add_argument("--ticket-id", required=True)
    p.add_argument("--nroticket", required=True)
    p.add_argument("--desarrollador", required=True)
    p.add_argument("--fecha", required=True, help="DD-MM-YYYY")
    p.add_argument("--perfil", required=True)
    p.set_defaults(func=cmd_open_ticket)

    p = sub.add_parser("open-fase", help="Abre una fase del plan activo")
    p.add_argument("--project")
    p.add_argument("--fase", required=True)
    p.set_defaults(func=cmd_open_fase)

    p = sub.add_parser("validate", help="Valida un archivo contra su contrato")
    p.add_argument("--project")
    p.add_argument("--contrato", required=True, choices=sorted(VALIDADORES))
    p.add_argument("--archivo", required=True)
    p.set_defaults(func=cmd_validate)

    p = sub.add_parser("pausar-fase", help="Pausa la fase activa; se retoma con open-fase")
    p.add_argument("--project")
    p.add_argument("--motivo")
    p.set_defaults(func=cmd_pausar_fase)

    p = sub.add_parser("run-checks", help="Corre los checks de la fase activa")
    p.add_argument("--project")
    p.set_defaults(func=cmd_run_checks)

    p = sub.add_parser("record-veredicto", help="Registra el veredicto del escéptico")
    p.add_argument("--project")
    p.add_argument("--archivo", required=True)
    p.set_defaults(func=cmd_record_veredicto)

    p = sub.add_parser("generar-prueba", help="Escribe el guion de prueba manual")
    p.add_argument("--project")
    p.add_argument("--pasos-json", required=True)
    p.set_defaults(func=cmd_generar_prueba)

    p = sub.add_parser("record-manual", help="Registra el resultado de la prueba manual")
    p.add_argument("--project")
    p.add_argument("--resultado", required=True, choices=["ok", "fallo"])
    p.add_argument("--paso", type=int)
    p.add_argument("--observacion")
    p.set_defaults(func=cmd_record_manual)

    p = sub.add_parser("record-hallazgos", help="Registra los hallazgos del reflector")
    p.add_argument("--project")
    p.add_argument("--archivo", required=True)
    p.add_argument("--ticket", help="Con --fase: registra en esa fase aunque no sea la activa")
    p.add_argument("--fase", help="Con --ticket: la fase cerrada a la que va la propuesta")
    p.set_defaults(func=cmd_record_hallazgos)

    p = sub.add_parser("resolver-hallazgo", help="Aprueba, edita o rechaza un hallazgo")
    p.add_argument("--project")
    p.add_argument("--id", required=True,
                   help="hN de la fase activa, o la referencia completa TICKET/fase_N/hN")
    p.add_argument("--decision", required=True, choices=["ok", "no", "editar"])
    p.add_argument("--texto")
    p.add_argument("--motivo")
    p.add_argument("--nueva", action="store_true",
                   help="No es reincidencia: ignora el reincide del hallazgo")
    p.add_argument("--reincide", metavar="REF",
                   help="Es reincidencia de esta lección aprobada (TICKET/fase_N/hN)")
    p.add_argument("--ticket")
    p.add_argument("--fase")
    p.set_defaults(func=cmd_resolver_hallazgo)

    p = sub.add_parser("hallazgo", help="El humano propone un hallazgo, que entra aprobado")
    p.add_argument("--project")
    p.add_argument("--texto", required=True)
    p.add_argument("--dimension", choices=sorted(contracts.DIMENSIONES))
    p.add_argument("--componente", choices=sorted(contracts.COMPONENTES))
    p.set_defaults(func=cmd_hallazgo)

    p = sub.add_parser("hallazgo-hecho", help="Marca una lección como implementada")
    p.add_argument("--project")
    p.add_argument("--id", required=True, help="Referencia completa TICKET/fase_N/hN")
    p.add_argument("--nota", required=True, help="Qué pieza se hizo (commit, archivo)")
    p.set_defaults(func=cmd_hallazgo_hecho)

    p = sub.add_parser("reconstruir-biblioteca", help="Regenera INDEX.md desde las entradas")
    p.add_argument("--project")
    p.set_defaults(func=cmd_reconstruir_biblioteca)

    p = sub.add_parser("senales-biblioteca",
                       help="Usos, último uso y rutas ausentes de cada lección")
    p.add_argument("--project")
    p.add_argument("--json", action="store_true")
    p.set_defaults(func=cmd_senales_biblioteca)

    p = sub.add_parser("record-curacion", help="Registra la propuesta del curador")
    p.add_argument("--project")
    p.add_argument("--archivo", required=True)
    p.set_defaults(func=cmd_record_curacion)

    p = sub.add_parser("resolver-curacion", help="Aplica, edita o rechaza una acción de curación")
    p.add_argument("--project")
    p.add_argument("--id", required=True, help="cN")
    p.add_argument("--decision", required=True, choices=["ok", "no", "editar"])
    p.add_argument("--texto", help="editar una fusión: la lección corregida")
    p.add_argument("--senal", help="editar una fusión: la señal corregida")
    p.add_argument("--quitar", action="append", help="editar una fusión: ref a sacar")
    p.add_argument("--motivo", help="rechazar, o editar una retirada")
    p.set_defaults(func=cmd_resolver_curacion)

    p = sub.add_parser("hallazgos-pendientes", help="Lista los hallazgos sin resolver")
    p.add_argument("--project")
    p.set_defaults(func=cmd_hallazgos_pendientes)

    p = sub.add_parser("report", help="Reporte de solo lectura de lecciones, hallazgos y fases")
    p.add_argument("--project")
    p.add_argument("--json", action="store_true", help="Imprime los datos en JSON")
    p.set_defaults(func=cmd_report)

    return parser


def main(argv: list[str] | None = None) -> int:
    _forzar_utf8_en_salidas()
    args = construir_parser().parse_args(argv)
    try:
        return args.func(args)
    except state.TransicionInvalida as error:
        return _error(str(error))
    except (OSError, ValueError) as error:
        return _error(f"{type(error).__name__}: {error}")


if __name__ == "__main__":
    sys.exit(main())
