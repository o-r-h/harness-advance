"""Motor genérico de checks: aplica un rules.json a un archivo modificado.

Este módulo no conoce ningún lenguaje concreto. Lo único que sabe es leer
reglas declarativas y aplicarlas a las líneas agregadas. Los checks que
requieren entender un stack (designer_sync, sp_params) son plugins del
perfil y viven en profiles/<perfil>/checks/.
"""
from __future__ import annotations

import re
import traceback
from pathlib import Path

from . import gitdiff

# Cubre los cuatro formatos del proyecto: '--[B], //--[B], --[B] y <%--[B].
RE_MARCADOR = re.compile(
    r"--\s*\[(?P<tipo>[BE])\]\s*ISR\s+(?P<ticket>\S+)\s+(?P<dev>.+?)\s+"
    r"(?P<fecha>\d{2}-\d{2}-\d{4})")


def _hallazgo(check_id: str, severidad: str, detalle: str,
              resultado: str = "fallo") -> dict:
    return {"id": check_id, "resultado": resultado,
            "severidad": severidad, "detalle": detalle}


def audit_regions(lines: list[str]):
    """Regiones [B]...[E] de un archivo y los [B] que quedaron sin cerrar."""
    pila: list[tuple[int, dict]] = []
    regiones: list[tuple[int, int, dict]] = []
    for numero, linea in enumerate(lines, start=1):
        encontrado = RE_MARCADOR.search(linea)
        if not encontrado:
            continue
        datos = encontrado.groupdict()
        if datos["tipo"] == "B":
            pila.append((numero, datos))
        elif pila:
            inicio, meta = pila.pop()
            regiones.append((inicio, numero, meta))
    return regiones, pila


def check_audit_comments(rel_path: str, texto_nuevo: str,
                         agregadas: list[tuple[int, str]],
                         ctx: dict, cfg: dict) -> list[dict]:
    """Verifica que todo lo agregado viva en un bloque [B]/[E] de ESTE ticket."""
    if not agregadas or not cfg.get("requerido"):
        return []
    aplica_a = [e.lower() for e in cfg.get("aplica_a") or []]
    if aplica_a and not any(rel_path.lower().endswith(e) for e in aplica_a):
        return []

    severidad = cfg.get("severidad", "error")
    hallazgos: list[dict] = []
    lineas = texto_nuevo.splitlines()
    regiones, sin_cerrar = audit_regions(lineas)
    numeros_agregados = {numero for numero, _ in agregadas}

    for numero, _ in sin_cerrar:
        hallazgos.append(_hallazgo("audit_comments", severidad,
                                   f"{rel_path}:{numero} marcador [B] sin su [E] de cierre"))

    cubiertas: set[int] = set()
    for inicio, fin, meta in regiones:
        rango = set(range(inicio, fin + 1))
        cubiertas |= rango
        if not (rango & numeros_agregados):
            continue  # bloque de un ticket anterior que esta tarea no tocó
        if meta["ticket"] != ctx["nroticket"]:
            hallazgos.append(_hallazgo(
                "audit_comments", severidad,
                f"{rel_path}:{inicio} el bloque declara el ticket {meta['ticket']} "
                f"pero el ticket activo es {ctx['nroticket']}"))
        if meta["dev"].strip().upper() != ctx["desarrollador"].strip().upper():
            hallazgos.append(_hallazgo(
                "audit_comments", severidad,
                f"{rel_path}:{inicio} el bloque declara al desarrollador "
                f"'{meta['dev'].strip()}' pero el contexto dice '{ctx['desarrollador']}'"))
        if meta["fecha"] != ctx["fecha"]:
            hallazgos.append(_hallazgo(
                "audit_comments", severidad,
                f"{rel_path}:{inicio} el bloque declara la fecha {meta['fecha']} "
                f"pero el ticket activo usa {ctx['fecha']}"))

    huerfanas = sorted(numeros_agregados - cubiertas)
    if huerfanas:
        hallazgos.append(_hallazgo(
            "audit_comments", severidad,
            f"{rel_path}: líneas agregadas fuera de un bloque [B]/[E]: "
            f"{gitdiff.compress_line_numbers(huerfanas)}"))
    return hallazgos


def _ruta_normalizada(ruta: str) -> str:
    """Ruta relativa con / y sin segmentos '.' ni '..' (no se puede escapar de un prefijo)."""
    partes: list[str] = []
    for parte in ruta.replace("\\", "/").split("/"):
        if parte in ("", "."):
            continue
        if parte == "..":
            if partes:
                partes.pop()
            continue
        partes.append(parte)
    return "/".join(partes)


def _excluida(rel_path: str, excluir: list[str]) -> bool:
    """True si la ruta cae dentro de alguno de los prefijos de carpeta de `excluir`."""
    ruta = _ruta_normalizada(rel_path).lower()
    for prefijo in excluir:
        carpeta = _ruta_normalizada(prefijo).lower()
        if carpeta and (ruta == carpeta or ruta.startswith(carpeta + "/")):
            return True
    return False


def check_prohibited(rel_path: str, agregadas: list[tuple[int, str]],
                     rules: dict) -> list[dict]:
    extension = Path(rel_path).suffix.lower()
    hallazgos: list[dict] = []
    for regla in rules.get("prohibido") or []:
        if extension not in [e.lower() for e in regla.get("archivos") or []]:
            continue
        # `excluir`: carpetas (relativas a la raíz del proyecto) donde la regla no aplica.
        # Es una excepción explícita y visible en rules.json; una lista mal formada es un
        # error de configuración, nunca un permiso silencioso.
        excluir = regla.get("excluir")
        if excluir is not None:
            if not isinstance(excluir, list) or not all(isinstance(e, str) for e in excluir):
                hallazgos.append(_hallazgo(regla.get("id", "?"), "error",
                                           "'excluir' en rules.json debe ser una lista de rutas",
                                           resultado="error_check"))
                continue
            if _excluida(rel_path, excluir):
                continue
        try:
            patron = re.compile(regla["patron"])
        except re.error as error:
            hallazgos.append(_hallazgo(regla.get("id", "?"), "error",
                                       f"patrón inválido en rules.json: {error}",
                                       resultado="error_check"))
            continue
        for numero, texto in agregadas:
            if patron.search(texto):
                hallazgos.append(_hallazgo(
                    regla["id"], regla.get("severidad", "warning"),
                    f"{rel_path}:{numero} {regla.get('mensaje', 'regla violada')}"))
    return hallazgos


def check_no_new_deps(rel_path: str, agregadas: list[tuple[int, str]],
                      rules: dict) -> list[dict]:
    cfg = rules.get("no_new_deps")
    if not cfg:
        return []
    vigilados = [v.lower() for v in cfg.get("vigilar") or []]
    if Path(rel_path).name.lower() not in vigilados:
        return []
    try:
        patron = re.compile(cfg["patron"])
    except re.error as error:
        return [_hallazgo("no_new_deps", "error",
                          f"patrón inválido en rules.json: {error}", resultado="error_check")]
    hallazgos: list[dict] = []
    for numero, texto in agregadas:
        if patron.search(texto):
            hallazgos.append(_hallazgo(
                "no_new_deps", cfg.get("severidad", "error"),
                f"{rel_path}:{numero} {cfg.get('mensaje', 'dependencia nueva detectada')}"))
    return hallazgos


def run_file_checks(project_root: Path, file_path: Path, rules: dict,
                    ctx: dict | None, solo: list[str] | None = None) -> list[dict]:
    """Corre los checks declarativos sobre un archivo. `solo` los filtra por id."""
    raiz = Path(project_root)
    archivo = Path(file_path)
    try:
        relativo = archivo.resolve().relative_to(raiz.resolve()).as_posix()
    except ValueError:
        return []

    agregadas = gitdiff.added_lines(raiz, archivo)
    if agregadas is None:
        return [_hallazgo("git_diff", "error",
                          f"{relativo}: no se pudo obtener el diff (¿repo git?); "
                          f"los checks basados en el cambio quedaron sin correr",
                          resultado="error_check")]
    if not agregadas:
        return []

    def habilitado(check_id: str) -> bool:
        return solo is None or check_id in solo

    hallazgos: list[dict] = []
    try:
        if habilitado("audit_comments") and ctx:
            hallazgos += check_audit_comments(
                relativo, gitdiff.read_text(archivo),
                agregadas, ctx, rules.get("audit_comments") or {})
        if habilitado("no_new_deps"):
            hallazgos += check_no_new_deps(relativo, agregadas, rules)
        prohibidos = [r for r in (rules.get("prohibido") or []) if habilitado(r.get("id", ""))]
        if prohibidos:
            hallazgos += check_prohibited(relativo, agregadas, {"prohibido": prohibidos})
    except Exception:  # un bug del harness no debe parecer un bug del código
        hallazgos.append(_hallazgo("motor_de_checks", "error",
                                   traceback.format_exc(), resultado="error_check"))
    return hallazgos
