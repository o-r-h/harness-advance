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

from lib import checks, contracts, gitdiff, harness, plugins, state  # noqa: E402

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
    reglas = harness.load_rules(raiz) if harness.find_project_root(raiz) else None
    errores = contracts.validate_plan(plan, reglas)
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
    return 0


def cmd_validate(args) -> int:
    validador = VALIDADORES[args.contrato]
    datos = harness.read_json(Path(args.archivo))
    if args.contrato == "plan":
        raiz = resolver_proyecto(args.project)
        reglas = harness.load_rules(raiz) if harness.find_project_root(raiz) else None
        errores = validador(datos, reglas)
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
