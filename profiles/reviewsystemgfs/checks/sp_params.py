"""Check estructural: los |Vn= que el VB envía contra los que el SP parsea.

El fallo más caro del stack: el VB envía V21, el SP nunca lo parsea con
SepararCadena, nada falla en ninguna capa y el dato desaparece. Sin este check
solo se descubre haciendo los pasos en la aplicación.

Dónde están los SPs lo decide el perfil, no este código: `rules.json` declara
`sp_params.carpetas_sp` en orden de prioridad (rutas relativas a la raíz del
proyecto, absolutas o con variables de entorno). La primera carpeta que tenga
el SP manda; así una copia vieja en el repo no tapa la versión vigente.

Atribución: los Vn escritos dentro de la llamada son de esa llamada; si los
parámetros vienen en una variable, se toman los Vn de todo el método. Solo se
revisa lo agregado en la fase: una llamada nueva, o un Vn nuevo que alimenta
una llamada que ya existía.
"""
from __future__ import annotations

import os
import re
import traceback
from pathlib import Path

from lib import gitdiff, harness

CHECK_ID = "sp_params"

RE_INICIO_METODO = re.compile(
    r"^\s*(?:(?:Private|Public|Protected|Friend|Shared|Overrides|Overridable|Overloads|"
    r"Static)\s+)*(?:Sub|Function)\s+\w+", re.IGNORECASE)
RE_FIN_METODO = re.compile(r"^\s*End\s+(?:Sub|Function)\b", re.IGNORECASE)
RE_LLAMADA = re.compile(r"\bEjecutarSp\s*\(", re.IGNORECASE)
RE_VN_ENVIADO = re.compile(r"\|\s*(?P<vn>V\d+)\s*=", re.IGNORECASE)
RE_NOMBRE_LITERAL = re.compile(r'^"(?P<sp>[\w.\[\]]+)"$')
RE_VALIDAR_LITERAL = re.compile(r'^"?(?P<n>\d+)"?$')
RE_COMENTARIO_SQL = re.compile(r"/\*.*?\*/|--[^\n]*", re.DOTALL)
# Incluye las variantes (SepararCadenaxml en ReviewInsUpd, ISR 102840).
RE_VN_PARSEADO = re.compile(r"SepararCadena\w*\s+N?'(?P<vn>V\d+)'", re.IGNORECASE)
RE_RAMA = re.compile(r"@Validar\s*=\s*(?P<n>\d+)", re.IGNORECASE)
RE_RAMA_IN = re.compile(r"@Validar\s+IN\s*\((?P<lista>[\d\s,]+)\)", re.IGNORECASE)


class Llamada:
    # Clase simple y no dataclass: el cargador de plugins no registra el módulo en
    # sys.modules, y @dataclass lo necesita.
    def __init__(self, sp: str, validar: str | None, linea: int, nueva: bool,
                 vns: dict[str, int]):
        self.sp = sp
        self.validar = validar
        self.linea = linea
        self.nueva = nueva
        self.vns = vns  # vn -> línea donde se reporta


def _hallazgo(severidad: str, detalle: str, resultado: str = "fallo") -> dict:
    return {"id": CHECK_ID, "resultado": resultado, "severidad": severidad,
            "detalle": detalle}


def _sin_comentario(linea: str) -> str:
    """La línea de VB sin su comentario; las cadenas se conservan (llevan los Vn)."""
    en_cadena = False
    for posicion, caracter in enumerate(linea):
        if caracter == '"':
            en_cadena = not en_cadena
        elif caracter == "'" and not en_cadena:
            return linea[:posicion]
    if re.match(r"\s*REM\b", linea, re.IGNORECASE):
        return ""
    return linea


def _argumentos(texto: str, apertura: int) -> list[str] | None:
    """Argumentos de primer nivel de la llamada cuyo '(' está en `apertura`."""
    profundidad = 0
    en_cadena = False
    actual: list[str] = []
    argumentos: list[str] = []
    for caracter in texto[apertura:]:
        if en_cadena:
            actual.append(caracter)
            if caracter == '"':
                en_cadena = False
            continue
        if caracter == '"':
            en_cadena = True
        elif caracter == "(":
            profundidad += 1
            if profundidad == 1:
                continue
        elif caracter == ")":
            profundidad -= 1
            if profundidad == 0:
                argumentos.append("".join(actual).strip())
                return argumentos
        elif caracter == "," and profundidad == 1:
            argumentos.append("".join(actual).strip())
            actual = []
            continue
        actual.append(caracter)
    return None


def _lineas_logicas(fisicas: list[str]) -> list[tuple[str, list[int]]]:
    """Une las continuaciones ' _' de VB. Devuelve (texto, números de línea físicos)."""
    logicas: list[tuple[str, list[int]]] = []
    partes: list[str] = []
    numeros: list[int] = []
    for numero, linea in enumerate(fisicas, start=1):
        codigo = _sin_comentario(linea).rstrip()
        numeros.append(numero)
        if codigo.endswith(" _") or codigo == "_":
            partes.append(codigo[:-1])
            continue
        partes.append(codigo)
        logicas.append((" ".join(partes), numeros))
        partes, numeros = [], []
    if partes:
        logicas.append((" ".join(partes), numeros))
    return logicas


def _metodos(logicas):
    """Agrupa las líneas lógicas por método; lo que queda fuera va en su propio bloque."""
    bloques: list[list[tuple[str, list[int]]]] = [[]]
    for logica in logicas:
        if RE_INICIO_METODO.match(logica[0]):
            bloques.append([])
        bloques[-1].append(logica)
        if RE_FIN_METODO.match(logica[0]):
            bloques.append([])
    return [b for b in bloques if b]


def _vns_de_variable(metodo, variable: str) -> dict[str, list[int]]:
    """Vn de las asignaciones a `variable` dentro del método: Dim v ... =, v =, v &=, v +=.

    Solo esas: los Vn escritos en otra llamada o en otra variable no son de esta.
    """
    asignacion = re.compile(
        r"^\s*(?:Dim\s+)?" + re.escape(variable) + r"\b(?:\s+As\s+[\w.]+)?\s*(?:&=|\+=|=)",
        re.IGNORECASE)
    vns: dict[str, list[int]] = {}
    for codigo, numeros in metodo:
        encontrada = asignacion.match(codigo)
        if encontrada is None:
            continue
        for vn in RE_VN_ENVIADO.finditer(codigo[encontrada.end():]):
            vns.setdefault(vn.group("vn").upper(), []).extend(numeros)
    return vns


def _llamadas(texto: str, agregadas: set[int]) -> list[Llamada]:
    llamadas: list[Llamada] = []
    for metodo in _metodos(_lineas_logicas(texto.splitlines())):
        for codigo, numeros in metodo:
            for encontrada in RE_LLAMADA.finditer(codigo):
                argumentos = _argumentos(codigo, encontrada.end() - 1)
                if not argumentos or len(argumentos) < 2:
                    continue
                nombre = RE_NOMBRE_LITERAL.match(argumentos[0])
                if nombre is None:
                    continue  # SP en una variable: no se puede saber cuál es
                validar = RE_VALIDAR_LITERAL.match(argumentos[1])
                nueva = any(n in agregadas for n in numeros)
                parametros = argumentos[2] if len(argumentos) > 2 else ""

                if RE_VN_ENVIADO.search(parametros):
                    fuentes = {m.group("vn").upper(): numeros
                               for m in RE_VN_ENVIADO.finditer(parametros)}
                elif re.fullmatch(r"\w+", parametros):
                    fuentes = _vns_de_variable(metodo, parametros)
                else:
                    fuentes = {}

                vns: dict[str, int] = {}
                for vn, lineas in fuentes.items():
                    nuevas = [n for n in lineas if n in agregadas]
                    if nueva or nuevas:
                        vns[vn] = (nuevas or numeros)[0]
                if nueva or vns:
                    llamadas.append(Llamada(nombre.group("sp"),
                                            validar.group("n") if validar else None,
                                            numeros[0], nueva, vns))
    return llamadas


def _clave(nombre: str) -> str:
    """ReviewInsUpd, dbo.ReviewInsUpd y dbo.ReviewInsUpd.StoredProcedure -> reviewinsupd."""
    partes = nombre.replace("[", "").replace("]", "").lower().split(".")
    if len(partes) > 1 and partes[-1] == "storedprocedure":
        partes = partes[:-1]
    return partes[-1]


def _indice(raiz: Path, carpetas: list[str]) -> tuple[dict[str, Path], list[dict]]:
    indice: dict[str, Path] = {}
    avisos: list[dict] = []
    for carpeta in carpetas:
        ruta = Path(os.path.expandvars(str(carpeta)))
        if not ruta.is_absolute():
            ruta = raiz / ruta
        if not ruta.is_dir():
            avisos.append(_hallazgo(
                "warning", f"la carpeta de SPs '{carpeta}' (sp_params.carpetas_sp en "
                           f"rules.json) no existe en esta máquina: se omitió", "error_check"))
            continue
        for sql in sorted(ruta.rglob("*.sql")):
            indice.setdefault(_clave(sql.name[:-4]), sql)
    return indice, avisos


def _leer_sp(ruta: Path) -> tuple[set[str], set[str]]:
    texto = RE_COMENTARIO_SQL.sub("", gitdiff.read_text(ruta))
    parseados = {m.group("vn").upper() for m in RE_VN_PARSEADO.finditer(texto)}
    ramas = {m.group("n") for m in RE_RAMA.finditer(texto)}
    for lista in RE_RAMA_IN.finditer(texto):
        ramas |= set(re.findall(r"\d+", lista.group("lista")))
    return parseados, ramas


def _mostrar(raiz: Path, ruta: Path) -> str:
    resuelta = ruta.resolve()
    try:
        return resuelta.relative_to(raiz.resolve()).as_posix()
    except ValueError:
        return str(resuelta)


# Convención "VN=<SP>|V0=<validar>|V1=...": la cadena que despachan LlenaCombos/LlenaGrid
# hacia EjecutarSp(Sp, Validar, ...). El SP y el @Validar van dentro de la cadena.
RE_VN_SP = re.compile(r"(?<![\w|])VN=(?P<sp>[\w.\[\]]+)\|", re.IGNORECASE)
RE_V0_LITERAL = re.compile(r"\|\s*V0=(?P<n>\d+)\s*\|", re.IGNORECASE)
RE_COMENTARIO_JS = re.compile(
    r"//[^\n]*|/\*.*?\*/|(?P<cadena>\"(?:\\.|[^\"\\\n])*\"|'(?:\\.|[^'\\\n])*')", re.DOTALL)


def _sentencias_js(texto: str) -> list[tuple[str, list[int]]]:
    """Líneas de JS sin comentarios (las cadenas se conservan: llevan los Vn).

    Por línea física: en el repo cada cadena VN= se arma en una sola línea."""
    def blanquear(encontrado: re.Match) -> str:
        if encontrado.group("cadena"):
            return encontrado.group(0)
        return re.sub(r"[^\n]", " ", encontrado.group(0))
    limpio = RE_COMENTARIO_JS.sub(blanquear, texto)
    return [(linea, [n]) for n, linea in enumerate(limpio.splitlines(), start=1)]


def _llamadas_vn(sentencias, agregadas: set[int]) -> list[Llamada]:
    llamadas: list[Llamada] = []
    for codigo, numeros in sentencias:
        if not any(n in agregadas for n in numeros):
            continue  # solo lo agregado, igual que las llamadas directas
        inicios = list(RE_VN_SP.finditer(codigo))
        for i, encontrada in enumerate(inicios):
            # Cada VN= lleva solo lo de su tramo, hasta el siguiente VN= de la línea: un
            # ternario o dos argumentos no deben cruzar los Vn ni el V0 de otro SP.
            fin = inicios[i + 1].start() if i + 1 < len(inicios) else len(codigo)
            tramo = codigo[encontrada.end() - 1:fin]
            validar = RE_V0_LITERAL.search("|" + tramo)
            vns = {m.group("vn").upper(): numeros[0] for m in RE_VN_ENVIADO.finditer(tramo)}
            llamadas.append(Llamada(encontrada.group("sp"),
                                    validar.group("n") if validar else None,
                                    numeros[0], True, vns))
    return llamadas


def run(project_root: Path, archivos_modificados: list[Path], ctx: dict | None) -> list[dict]:
    raiz = Path(project_root)
    hallazgos: list[dict] = []
    por_archivo: list[tuple[Path, list[Llamada]]] = []
    for archivo in archivos_modificados:
        archivo = Path(archivo)
        nombre = archivo.name.lower()
        es_vb = nombre.endswith(".vb") and not nombre.endswith(".designer.vb")
        if not (es_vb or nombre.endswith(".js")):
            continue
        try:
            agregadas = gitdiff.added_lines(raiz, archivo)
            if agregadas is None:
                hallazgos.append(_hallazgo("warning", f"{archivo.name}: no se pudo obtener el "
                                                      f"diff (¿repo git?); no se verificó",
                                           "error_check"))
                continue
            texto = gitdiff.read_text(archivo)
            numeros = {n for n, _ in agregadas}
            if es_vb:
                sentencias = _lineas_logicas(texto.splitlines())
                llamadas = _llamadas(texto, numeros)
            else:
                sentencias = _sentencias_js(texto)
                llamadas = []
            llamadas += _llamadas_vn(sentencias, numeros)
            if llamadas:
                por_archivo.append((archivo, llamadas))
        except Exception:
            hallazgos.append(_hallazgo("error", traceback.format_exc(), "error_check"))
    if not por_archivo:
        return hallazgos

    try:
        reglas = harness.load_rules(raiz)
    except Exception:
        reglas = {}
    config = (reglas.get("sp_params") or {}) if isinstance(reglas, dict) else {}
    carpetas = config.get("carpetas_sp") or []
    # Vn que el VB envía por convención y ningún SP parsea (V0 repite @Validar).
    ignorados = {str(vn).upper() for vn in config.get("vn_ignorados") or []}
    if not carpetas:
        return hallazgos + [_hallazgo(
            "warning", "hay llamadas a SPs nuevas pero rules.json no declara "
                       "sp_params.carpetas_sp: no se sabe dónde buscar los SPs", "error_check")]

    indice, avisos = _indice(raiz, carpetas)
    hallazgos += avisos
    for archivo, llamadas in por_archivo:
        for llamada in llamadas:
            try:
                llamada.vns = {vn: n for vn, n in llamada.vns.items() if vn not in ignorados}
                hallazgos += _verificar(raiz, archivo, llamada, indice, carpetas)
            except Exception:
                hallazgos.append(_hallazgo("error", traceback.format_exc(), "error_check"))
    return hallazgos


def _verificar(raiz: Path, archivo: Path, llamada: Llamada, indice: dict[str, Path],
               carpetas: list[str]) -> list[dict]:
    ruta_sp = indice.get(_clave(llamada.sp))
    if ruta_sp is None:
        return [_hallazgo(
            "warning", f"{archivo.name}:{llamada.linea} se llama al SP '{llamada.sp}' pero "
                       f"no hay un .sql suyo en {', '.join(map(str, carpetas))}: no se "
                       f"pudo verificar sus parámetros")]

    parseados, ramas = _leer_sp(ruta_sp)
    mostrado = _mostrar(raiz, ruta_sp)
    hallazgos: list[dict] = []
    if llamada.vns and not parseados:
        hallazgos.append(_hallazgo(
            "warning", f"{archivo.name}:{llamada.linea} '{llamada.sp}' no parsea ningún Vn con "
                       f"SepararCadena ({mostrado}): no se pudo verificar qué recibe"))
    elif parseados:
        for vn in sorted(set(llamada.vns) - parseados, key=lambda v: int(v[1:])):
            hallazgos.append(_hallazgo(
                "error", f"{archivo.name}:{llamada.vns[vn]} se envía {vn} a '{llamada.sp}' pero "
                         f"el SP no lo parsea con SepararCadena ({mostrado}): el valor se "
                         f"perdería en silencio, sin error en ninguna capa"))

    if llamada.nueva and llamada.validar is not None and ramas and llamada.validar not in ramas:
        # Con solo "If @Validar = 0" el SP no despacha por @Validar: corre igual y solo
        # cambia @Resul (bOk). Puede estar bien si el llamador solo lee el DataSet.
        sin_despacho = ramas == {"0"}
        hallazgos.append(_hallazgo(
            "warning" if sin_despacho else "error", f"{archivo.name}:{llamada.linea} se llama a '{llamada.sp}' con @Validar = "
                     f"{llamada.validar} pero el SP no tiene esa rama (tiene: "
                     f"{', '.join(sorted(ramas, key=int))}; {mostrado}): "
                     + ("el SP corre igual, pero @Resul queda vacío y bOk sale False"
                        if sin_despacho else "el SP no haría nada")))
    return hallazgos
