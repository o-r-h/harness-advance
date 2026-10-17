#!/usr/bin/env python3
"""Único punto de mutación del estado del harness.

Todo lo que cambie un contador, un estado o un archivo de estado pasa por
aquí. El modelo invoca estos subcomandos; no escribe el estado a mano.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from lib import checks, contracts, gitdiff, harness, plugins, prueba_manual, state  # noqa: E402

VALIDADORES = {
    "ticket_context": contracts.validate_ticket_context,
    "plan": contracts.validate_plan,
    "checks": contracts.validate_checks_result,
    "veredicto": contracts.validate_veredicto,
    "fase_state": contracts.validate_fase_state,
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


def cmd_open_ticket(args) -> int:
    raiz = resolver_proyecto(args.project)
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

    estado = state.abrir_fase(raiz, ticket_id, fase)
    harness.write_current(raiz, ticket_id, fase["id"])
    print(f"Fase {fase['id']} en estado '{estado['estado']}', "
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


def cmd_run_checks(args) -> int:
    raiz = resolver_proyecto(args.project)
    activa = _fase_activa(raiz)
    if activa is None:
        return _error("no hay fase activa con plan y contexto: corre 'open-fase'")
    ticket_id, ctx, fase, estado = activa
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
    return 1 if bloqueantes else 0


def cmd_record_veredicto(args) -> int:
    raiz = resolver_proyecto(args.project)
    activa = _fase_activa(raiz)
    if activa is None:
        return _error("no hay fase activa: corre 'open-fase'")
    ticket_id, _, fase, estado = activa

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
