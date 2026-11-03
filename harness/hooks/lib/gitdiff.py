"""Extracción de las líneas agregadas de un archivo respecto a HEAD.

La unidad de verificación del harness es el cambio, no el archivo: validar
un archivo legacy completo produciría miles de falsos positivos.
"""
from __future__ import annotations

import codecs
import difflib
import re
import subprocess
from pathlib import Path

RE_HUNK = re.compile(r"^@@ -\d+(?:,\d+)? \+(?P<inicio>\d+)(?:,\d+)? @@")
# El orden importa: el BOM de UTF-32 LE empieza con el de UTF-16 LE.
BOMS = ((codecs.BOM_UTF32_LE, "utf-32-le"), (codecs.BOM_UTF32_BE, "utf-32-be"),
        (codecs.BOM_UTF8, "utf-8"), (codecs.BOM_UTF16_LE, "utf-16-le"),
        (codecs.BOM_UTF16_BE, "utf-16-be"))
BOMS_ANCHOS = (codecs.BOM_UTF16_LE, codecs.BOM_UTF16_BE)
RE_BINARIO = re.compile(r"^Binary files .* differ$", re.MULTILINE)


def _decodificar_con_respaldo(datos: bytes) -> str:
    """Decodifica bytes intentando UTF-8, luego cp1252 (legacy Windows-1252),
    y solo como último recurso reemplaza los bytes irreconocibles.

    El código legacy de este proyecto (15 años) suele estar en cp1252; decodificar
    directo con errors="replace" produce texto corrupto en vez de un error, lo cual
    genera hallazgos falsos aguas abajo cuando se comparan acentos/ñ en el texto.

    Un BOM manda sobre todo lo demás: los scripts que exportan algunas
    herramientas salen en UTF-16, y leídos como cp1252 cada carácter queda
    separado por un NUL y ningún regex acierta.
    """
    for bom, codificacion in BOMS:
        if datos.startswith(bom):
            return datos[len(bom):].decode(codificacion, errors="replace")
    try:
        return datos.decode("utf-8")
    except UnicodeDecodeError:
        pass
    try:
        return datos.decode("cp1252")
    except UnicodeDecodeError:
        return datos.decode("utf-8", errors="replace")


def _git(project_root: Path, *args: str, crudo: bool = False
         ) -> subprocess.CompletedProcess | None:
    try:
        resultado = subprocess.run(["git", *args], cwd=str(project_root), capture_output=True)
    except (OSError, ValueError):
        return None
    if crudo:
        return resultado
    resultado.stdout = _decodificar_con_respaldo(resultado.stdout)
    resultado.stderr = _decodificar_con_respaldo(resultado.stderr)
    return resultado


def read_text(path: Path) -> str:
    """Lee un archivo del proyecto sin forzar UTF-8 (ver `_decodificar_con_respaldo`).

    Público porque todo módulo que lea archivos del proyecto —checks.py y los
    checks estructurales del perfil— debe usar el mismo respaldo cp1252.
    """
    return _decodificar_con_respaldo(Path(path).read_bytes())


def added_lines(project_root: Path, file_path: Path) -> list[tuple[int, str]] | None:
    """Líneas agregadas respecto a HEAD, incluyendo lo que ya está en el index.

    Devuelve None si no hay git usable: el llamador debe registrarlo como
    error_check y no como violación de una regla.
    """
    raiz = Path(project_root).resolve()
    archivo = Path(file_path).resolve()
    try:
        relativo = archivo.relative_to(raiz).as_posix()
    except ValueError:
        # Un archivo fuera de project_root tampoco es verificable: None, igual
        # que "no hay git usable".
        return None

    dentro = _git(raiz, "rev-parse", "--is-inside-work-tree")
    if dentro is None or dentro.returncode != 0 or dentro.stdout.strip() != "true":
        return None

    estado = _git(raiz, "status", "--porcelain", "--", relativo)
    if estado is not None and estado.returncode == 0 and estado.stdout.startswith("??"):
        return [(i, linea) for i, linea in enumerate(read_text(archivo).splitlines(), start=1)]

    actual = archivo.read_bytes()
    if actual.startswith(BOMS_ANCHOS):
        return _agregadas_por_comparacion(raiz, relativo, actual)

    diff = _git(raiz, "diff", "HEAD", "--unified=0", "--no-color", "--", relativo)
    if diff is None or diff.returncode != 0:
        return None
    if RE_BINARIO.search(diff.stdout):
        # Era UTF-16 en HEAD y ya no lo es: git lo sigue viendo binario.
        previo = _git(raiz, "show", f"HEAD:./{relativo}", crudo=True)
        if previo is not None and previo.returncode == 0 and previo.stdout.startswith(BOMS_ANCHOS):
            return _agregadas_por_comparacion(raiz, relativo, actual)

    agregadas: list[tuple[int, str]] = []
    linea_actual = 0
    for linea in diff.stdout.splitlines():
        encabezado = RE_HUNK.match(linea)
        if encabezado:
            linea_actual = int(encabezado.group("inicio"))
            continue
        if linea.startswith("+") and not linea.startswith("+++"):
            agregadas.append((linea_actual, linea[1:]))
            linea_actual += 1
    return agregadas


def _agregadas_por_comparacion(raiz: Path, relativo: str,
                               actual: bytes) -> list[tuple[int, str]] | None:
    """Líneas agregadas de un archivo que git trata como binario (UTF-16).

    `git diff` solo diría "Binary files differ" y el cambio quedaría sin
    verificar en silencio; aquí se compara el texto decodificado contra HEAD.
    """
    # "./" hace que git resuelva la ruta desde project_root y no desde el toplevel
    # del repo: el proyecto puede vivir en una subcarpeta.
    previo = _git(raiz, "show", f"HEAD:./{relativo}", crudo=True)
    if previo is None:
        return None
    anteriores = (_decodificar_con_respaldo(previo.stdout).splitlines()
                  if previo.returncode == 0 else [])
    nuevas = _decodificar_con_respaldo(actual).splitlines()
    agregadas: list[tuple[int, str]] = []
    comparador = difflib.SequenceMatcher(None, anteriores, nuevas, autojunk=False)
    for operacion, _, _, desde, hasta in comparador.get_opcodes():
        if operacion in ("replace", "insert"):
            agregadas += [(i + 1, nuevas[i]) for i in range(desde, hasta)]
    return agregadas


def archivos_modificados(project_root: Path) -> list[Path]:
    """Archivos con cambios respecto a HEAD, incluidos los sin rastrear."""
    raiz = Path(project_root).resolve()
    estado = _git(raiz, "status", "--porcelain", "--untracked-files=all")
    if estado is None or estado.returncode != 0:
        return []
    rutas: list[Path] = []
    for linea in estado.stdout.splitlines():
        if len(linea) < 4:
            continue
        relativo = linea[3:].strip().strip('"')
        if " -> " in relativo:  # renombrado: interesa el destino
            relativo = relativo.split(" -> ", 1)[1]
        candidato = raiz / relativo
        if candidato.is_file():
            rutas.append(candidato)
    return rutas


def compress_line_numbers(numeros: list[int]) -> str:
    """[3,4,5,9] -> '3-5, 9'."""
    if not numeros:
        return ""
    ordenados = sorted(set(numeros))
    tramos: list[str] = []
    inicio = previo = ordenados[0]
    for numero in ordenados[1:]:
        if numero == previo + 1:
            previo = numero
            continue
        tramos.append(str(inicio) if inicio == previo else f"{inicio}-{previo}")
        inicio = previo = numero
    tramos.append(str(inicio) if inicio == previo else f"{inicio}-{previo}")
    return ", ".join(tramos)
