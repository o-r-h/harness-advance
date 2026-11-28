"""Extracción de las líneas agregadas de un archivo respecto a HEAD.

La unidad de verificación del harness es el cambio, no el archivo: validar
un archivo legacy completo produciría miles de falsos positivos.
"""
from __future__ import annotations

import codecs
import difflib
import hashlib
import os
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


def commit_actual(project_root: Path) -> str | None:
    """El commit en que está HEAD; None sin git usable o sin ningún commit."""
    salida = _git(Path(project_root), "rev-parse", "--verify", "--quiet", "HEAD^{commit}")
    if salida is None or salida.returncode != 0:
        return None
    return salida.stdout.strip() or None


def existe_commit(project_root: Path, commit: str) -> bool:
    salida = _git(Path(project_root), "cat-file", "-e", f"{commit}^{{commit}}")
    return salida is not None and salida.returncode == 0


INSTANTANEA_MAXIMA = 2_000_000  # bytes; un sucio más grande se mide contra el commit


def base_de_fase(project_root: Path, excluir: tuple[str, ...] = (),
                 instantaneas: Path | None = None) -> dict:
    """Punto de partida de una fase: el commit en que se abrió y lo que ya estaba
    sin commitear en ese momento ({archivo: sha256}).

    El cambio de la fase se mide contra esto y no contra HEAD: así un commit a
    mitad de fase no lo esconde, y lo que quedó sin commitear de una fase anterior
    no se le cuenta a ésta. Con `instantaneas`, guarda ahí una copia de cada archivo
    sucio: si la fase lo vuelve a tocar, se compara contra esa copia y no contra el
    commit, y solo cuenta lo que la fase agregó.
    """
    raiz = Path(project_root).resolve()
    sucios = huella_cambio(raiz, excluir) or {}
    if instantaneas is not None:
        for relativo in sucios:
            origen = raiz / relativo
            try:
                if origen.is_file() and origen.stat().st_size <= INSTANTANEA_MAXIMA:
                    destino = Path(instantaneas) / relativo
                    destino.parent.mkdir(parents=True, exist_ok=True)
                    destino.write_bytes(origen.read_bytes())
            except OSError:
                continue  # sin copia, ese archivo se mide contra el commit
    return {"commit": commit_actual(raiz), "sucios": sucios}


def _instantanea(base: dict | None, relativo: str) -> bytes | None:
    """Cómo estaba al abrir la fase un archivo que ya tenía cambios sin commitear;
    None si no era uno de esos o no se guardó copia. Un sucio que al abrir estaba
    borrado vale como vacío."""
    if not isinstance(base, dict) or not isinstance(base.get("sucios"), dict):
        return None
    if relativo not in base["sucios"]:
        return None
    if base["sucios"][relativo] == "ausente":
        return b""
    carpeta = base.get("instantaneas")
    if not carpeta:
        return None
    try:
        return (Path(carpeta) / relativo).read_bytes()
    except OSError:
        return None


def _agregadas_entre(anterior: bytes, actual: bytes) -> list[tuple[int, str]]:
    anteriores = _decodificar_con_respaldo(anterior).splitlines()
    nuevas = _decodificar_con_respaldo(actual).splitlines()
    agregadas: list[tuple[int, str]] = []
    comparador = difflib.SequenceMatcher(None, anteriores, nuevas, autojunk=False)
    for operacion, _, _, desde, hasta in comparador.get_opcodes():
        if operacion in ("replace", "insert"):
            agregadas += [(i + 1, nuevas[i]) for i in range(desde, hasta)]
    return agregadas


def _commit_base(raiz: Path, base: dict | None) -> str | None:
    """El commit de la base si sigue existiendo; None manda a comparar contra HEAD."""
    commit = base.get("commit") if isinstance(base, dict) else None
    return commit if isinstance(commit, str) and existe_commit(raiz, commit) else None


def added_lines(project_root: Path, file_path: Path,
                base: dict | None = None) -> list[tuple[int, str]] | None:
    """Líneas agregadas respecto a HEAD, incluyendo lo que ya está en el index.

    Con `base` (ver `base_de_fase`) se comparan contra el commit en que se abrió la
    fase, para que lo commiteado a mitad de fase siga contando como agregado.

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

    previo_sucio = _instantanea(base, relativo)
    if previo_sucio is not None and archivo.is_file():
        # Ya tenía cambios sin commitear al abrir la fase: solo cuenta lo de la fase.
        return _agregadas_entre(previo_sucio, archivo.read_bytes())

    desde = _commit_base(raiz, base) or "HEAD"
    entrada = next((e for e in _estado(raiz) or [] if _misma(e[1], archivo)), None)
    if entrada is not None and entrada[0] == "??":
        return [(i, linea) for i, linea in enumerate(read_text(archivo).splitlines(), start=1)]

    actual = archivo.read_bytes()
    if entrada is not None and entrada[2] is not None:
        # Renombrado (git mv): lo agregado es contra el archivo de origen en HEAD, no
        # todo el archivo como si fuera nuevo.
        origen = Path(os.path.relpath(entrada[2], raiz)).as_posix()
        return _agregadas_por_comparacion(raiz, origen, actual, desde)
    if actual.startswith(BOMS_ANCHOS):
        return _agregadas_por_comparacion(raiz, relativo, actual, desde)

    diff = _git(raiz, "diff", desde, "--unified=0", "--no-color", "--", relativo)
    if diff is None or diff.returncode != 0:
        return None
    if RE_BINARIO.search(diff.stdout):
        # Era UTF-16 en HEAD y ya no lo es: git lo sigue viendo binario.
        previo = _git(raiz, "show", f"{desde}:./{relativo}", crudo=True)
        if previo is not None and previo.returncode == 0 and previo.stdout.startswith(BOMS_ANCHOS):
            return _agregadas_por_comparacion(raiz, relativo, actual, desde)

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


def _agregadas_por_comparacion(raiz: Path, relativo: str, actual: bytes,
                               desde: str = "HEAD") -> list[tuple[int, str]] | None:
    """Líneas agregadas de un archivo que git trata como binario (UTF-16).

    `git diff` solo diría "Binary files differ" y el cambio quedaría sin
    verificar en silencio; aquí se compara el texto decodificado contra `desde`.
    """
    # "./" hace que git resuelva la ruta desde project_root y no desde el toplevel
    # del repo: el proyecto puede vivir en una subcarpeta.
    previo = _git(raiz, "show", f"{desde}:./{relativo}", crudo=True)
    if previo is None:
        return None
    return _agregadas_entre(previo.stdout if previo.returncode == 0 else b"", actual)


def diff_de_fase(project_root: Path, relativos: list[str], base: dict | None = None) -> str:
    """El diff de la fase, archivo por archivo, en formato unificado.

    Lo genera el harness y no el agente: es lo que juzga el escéptico, y tiene que
    ser el mismo cambio que midió la huella. Cada archivo se compara contra cómo
    estaba al abrir la fase: su copia si ya tenía cambios sin commitear, y si no el
    commit de apertura (HEAD sin `base`). Un archivo que no existía sale completo.
    """
    raiz = Path(project_root).resolve()
    desde = _commit_base(raiz, base) or "HEAD"
    partes: list[str] = []
    for relativo in relativos:
        anterior = _instantanea(base, relativo)
        if anterior is None:
            previo = _git(raiz, "show", f"{desde}:./{relativo}", crudo=True)
            anterior = previo.stdout if previo is not None and previo.returncode == 0 else b""
        try:
            actual = (raiz / relativo).read_bytes()
        except OSError:
            actual = b""  # borrado en la fase
        if anterior == actual:
            continue
        if any(b"\0" in datos and not datos.startswith(BOMS_ANCHOS + (codecs.BOM_UTF32_LE,
                                                                     codecs.BOM_UTF32_BE))
               for datos in (anterior, actual)):
            partes.append(f"Binary file {relativo} differs")
            continue
        lineas = list(difflib.unified_diff(
            _decodificar_con_respaldo(anterior).splitlines(),
            _decodificar_con_respaldo(actual).splitlines(),
            f"a/{relativo}" if anterior else "/dev/null",
            f"b/{relativo}" if actual else "/dev/null", lineterm=""))
        partes.append("\n".join(lineas) if lineas else
                      f"--- a/{relativo}\n+++ b/{relativo}\n"
                      f"(solo cambian los finales de línea o la codificación)")
    return "\n".join(partes) + ("\n" if partes else "")


def archivos_rastreados(project_root: Path) -> list[str] | None:
    """Rutas que git rastrea bajo project_root, relativas a él; None sin git usable."""
    salida = _git(Path(project_root), "ls-files", "-z", crudo=True)
    if salida is None or salida.returncode != 0:
        return None
    return [_decodificar_con_respaldo(r) for r in salida.stdout.split(b"\0") if r]


def _misma(a: Path, b: Path) -> bool:
    return os.path.normcase(str(Path(a).resolve())) == os.path.normcase(str(Path(b).resolve()))


def _estado(raiz: Path) -> list[tuple[str, Path, Path | None]] | None:
    """(XY, ruta, origen si es renombrado o copia) de `git status --porcelain -z`.

    Con -z git no cita las rutas: sin él, una ruta con acentos o espacios sale entre
    comillas y en octal, no coincide con ningún archivo y se queda sin revisar.
    Las rutas vienen relativas a la raíz del repo; se devuelven absolutas."""
    tope = _git(raiz, "rev-parse", "--show-toplevel")
    estado = _git(raiz, "status", "--porcelain", "-z", "--untracked-files=all", crudo=True)
    if tope is None or tope.returncode != 0 or estado is None or estado.returncode != 0:
        return None
    base = Path(tope.stdout.strip())
    partes = [_decodificar_con_respaldo(p) for p in estado.stdout.split(b"\0")]
    entradas: list[tuple[str, Path, Path | None]] = []
    i = 0
    while i < len(partes):
        parte = partes[i]
        i += 1
        if len(parte) < 4:
            continue
        xy, ruta = parte[:2], base / parte[3:]
        origen = None
        if "R" in xy or "C" in xy:  # en -z el origen viene en el campo siguiente
            origen = base / partes[i]
            i += 1
        entradas.append((xy, ruta, origen))
    return entradas


def _commiteados_desde(raiz: Path, commit: str) -> list[Path]:
    """Rutas absolutas de lo que cambió entre `commit` y HEAD (commits a mitad de fase)."""
    tope = _git(raiz, "rev-parse", "--show-toplevel")
    salida = _git(raiz, "diff", "--name-only", "--no-renames", "-z", commit, "HEAD",
                  crudo=True)
    if tope is None or tope.returncode != 0 or salida is None or salida.returncode != 0:
        return []
    base = Path(tope.stdout.strip())
    return [base / _decodificar_con_respaldo(r) for r in salida.stdout.split(b"\0") if r]


def _sha256(archivo: Path) -> str:
    try:
        return hashlib.sha256(archivo.read_bytes()).hexdigest()
    except OSError:
        return "ausente"  # borrado, o un directorio (submódulo)


def _relativos_del_cambio(raiz: Path, base: dict | None) -> list[str] | None:
    """Rutas relativas al proyecto que forman el cambio; None sin git usable.

    Sin `base`: lo que difiere de HEAD. Con `base`: lo que difiere del commit en que
    se abrió la fase, menos lo que ya estaba sin commitear entonces y sigue igual.
    """
    entradas = _estado(raiz)
    if entradas is None:
        return None
    rutas = [ruta for _, ruta, _ in entradas]
    commit = _commit_base(raiz, base)
    if commit:
        rutas += _commiteados_desde(raiz, commit)
    sucios = base.get("sucios") if isinstance(base, dict) else None
    sucios = sucios if isinstance(sucios, dict) else {}
    relativos: list[str] = []
    for ruta in rutas:
        try:
            relativo = ruta.resolve().relative_to(raiz).as_posix()
        except ValueError:
            continue  # fuera del proyecto
        if relativo in relativos:
            continue
        if relativo in sucios and sucios[relativo] == _sha256(raiz / relativo):
            continue  # ya estaba así al abrir la fase: no es de esta fase
        relativos.append(relativo)
    return relativos


def archivos_modificados(project_root: Path, base: dict | None = None) -> list[Path]:
    """Archivos con cambios respecto a HEAD, incluidos los sin rastrear.

    Con `base` (ver `base_de_fase`), los del cambio de la fase."""
    raiz = Path(project_root).resolve()
    return [raiz / relativo for relativo in _relativos_del_cambio(raiz, base) or []
            if (raiz / relativo).is_file()]


def huella_cambio(project_root: Path, excluir: tuple[str, ...] = (),
                  base: dict | None = None) -> dict[str, str] | None:
    """Huella del cambio respecto a HEAD: {archivo que difiere: sha256 de su contenido}.

    Ata la evidencia (checks, veredicto, prueba manual) al código que se revisó: si
    la huella ya no coincide, lo que se juzgó no es lo que hay. `excluir` son rutas
    relativas al proyecto ('carpeta/' o un archivo) que no cuentan como cambio de la
    fase. Con `base` (ver `base_de_fase`) el cambio es el de la fase, no el que hay
    contra HEAD. None si no hay git usable: sin huella no se compara nada.
    """
    raiz = Path(project_root).resolve()
    relativos = _relativos_del_cambio(raiz, base)
    if relativos is None:
        return None
    huella: dict[str, str] = {}
    for relativo in relativos:
        if any(relativo == e or (e.endswith("/") and relativo.startswith(e)) for e in excluir):
            continue
        huella[relativo] = _sha256(raiz / relativo)
    return dict(sorted(huella.items()))


def diferencias_de_huella(antes: dict[str, str], ahora: dict[str, str]) -> list[str]:
    """Archivos que distinguen dos huellas, cada uno con lo que le pasó."""
    cambios = []
    for ruta in sorted(set(antes) | set(ahora)):
        if ruta not in antes:
            cambios.append(f"{ruta} (nuevo en el cambio)")
        elif ruta not in ahora:
            cambios.append(f"{ruta} (volvió a como estaba antes del cambio)")
        elif antes[ruta] != ahora[ruta]:
            cambios.append(f"{ruta} (modificado)")
    return cambios


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
