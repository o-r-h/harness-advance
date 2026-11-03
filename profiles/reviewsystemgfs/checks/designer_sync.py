"""Check estructural: coherencia markup <-> .designer.vb <-> code-behind.

Sin VS2008 en el ciclo, el error de compilación más común de Web Forms es que
el code-behind use un control que nadie declaró: ni el designer ni el propio
code-behind. Eso es `error`.

Un control del markup que falta en el designer, en cambio, compila: el runtime
genera la declaración en la clase de la página (verificado en el repo real:
frmGFSScope tiene en HEAD cinco controles runat="server" sin declarar). Solo
indica un designer desactualizado, así que es `warning`.

Igual que los checks declarativos, solo se revisa lo agregado en la fase. La
excepción es un designer modificado: quitar una declaración rompe usos que ya
existían, y entonces se revisa el code-behind completo.
"""
from __future__ import annotations

import re
import traceback
from pathlib import Path

from lib import gitdiff

CHECK_ID = "designer_sync"
EXTENSIONES = (".aspx", ".ascx", ".master")

RE_COMENTARIO_MARKUP = re.compile(r"<%--.*?--%>|<!--.*?-->", re.DOTALL)
# Los controles de un template se instancian por fila: el designer no los declara.
# ContentTemplate (UpdatePanel) es de instancia única y sí se declara.
RE_TAG_TEMPLATE = re.compile(
    r"<(?P<cierre>/)?(?P<tag>(?:\w+:)?(?!Content)\w*Template)\b[^>]*?(?P<auto>/)?>",
    re.IGNORECASE)
RE_TAG = re.compile(r"<(?P<tag>[\w:.-]+)\b(?P<atributos>[^>]*)>", re.DOTALL)
RE_RUNAT = re.compile(r"\brunat\s*=\s*[\"']?server\b", re.IGNORECASE)
RE_ID = re.compile(r"\bID\s*=\s*[\"'](?P<id>\w+)[\"']", re.IGNORECASE)
RE_DIRECTIVA = re.compile(r"<%@\s*(?:Page|Control|Master)\b(?P<atributos>.*?)%>",
                          re.IGNORECASE | re.DOTALL)
SIN_DECLARACION = {"asp:content"}

RE_DECLARACION_VB = re.compile(
    r"\b(?:Dim|ByVal|ByRef|Each|Using|Catch|Const|Static|WithEvents|Protected|Private|"
    r"Public|Friend|Shared|ReadOnly|Optional)\s+(?P<id>\w+)\s*(?:As\b|=|,|\(|$)"
    # For i As..., For Each x In...; parámetros sin ByVal y declaradores tras coma.
    r"|\bFor\s+(?:Each\s+)?(?P<id_for>\w+)\b|[(,]\s*(?P<id_lista>\w+)\s+As\b", re.IGNORECASE)
# Un identificador suelto, no miembro de otro objeto (objRet.hdnX no es el control).
RE_IDENTIFICADOR_VB = re.compile(r"(?<![\w.])(?P<id>[A-Za-z_]\w*)(?P<miembro>\s*\.)?")
# Prefijos de control usados en el proyecto; la heurística de warning solo mira estos.
RE_PREFIJO_CONTROL = re.compile(
    r"^(?:hdn|txt|btn|lbl|ddl|grd|chk|rdb|pnl|lnk|img|rpt|div)[A-Z0-9_]")


def _hallazgo(severidad: str, detalle: str, resultado: str = "fallo") -> dict:
    return {"id": CHECK_ID, "resultado": resultado, "severidad": severidad,
            "detalle": detalle}


def _en_blanco(encontrado: re.Match) -> str:
    """Borra un fragmento conservando los saltos de línea (y con ellos los números)."""
    return re.sub(r"[^\n]", " ", encontrado.group(0))


def _codigo_vb(linea: str) -> str:
    """La línea sin cadenas ni comentario: lo que el compilador ve como código."""
    salida: list[str] = []
    en_cadena = False
    for caracter in linea:
        if en_cadena:
            if caracter == '"':
                en_cadena = False
            continue
        if caracter == '"':
            en_cadena = True
            salida.append('""')
            continue
        if caracter == "'":
            break
        salida.append(caracter)
    codigo = "".join(salida)
    if re.match(r"\s*REM\b", codigo, re.IGNORECASE):
        return ""
    return re.sub(r"\bMe\s*\.\s*", "", codigo, flags=re.IGNORECASE)


def _sin_templates(texto: str) -> str:
    """Borra el contenido de los templates, contando anidados: un regex no codicioso
    cerraría el externo en el </ItemTemplate> del interno."""
    partes: list[str] = []
    abiertos = 0
    inicio = 0
    cursor = 0
    for tag in RE_TAG_TEMPLATE.finditer(texto):
        if tag.group("auto"):
            continue
        if tag.group("cierre"):
            if abiertos == 0:
                continue
            abiertos -= 1
            if abiertos == 0:
                partes.append(texto[cursor:inicio])
                partes.append(re.sub(r"[^\n]", " ", texto[inicio:tag.end()]))
                cursor = tag.end()
        else:
            if abiertos == 0:
                inicio = tag.start()
            abiertos += 1
    partes.append(texto[cursor:])
    return "".join(partes)


def _controles_markup(texto: str) -> list[tuple[str, int]]:
    """(id, línea) de cada control runat="server" que el designer debe declarar."""
    limpio = RE_COMENTARIO_MARKUP.sub(_en_blanco, texto)
    limpio = _sin_templates(limpio)
    controles: list[tuple[str, int]] = []
    for tag in RE_TAG.finditer(limpio):
        if tag.group("tag").lower() in SIN_DECLARACION:
            continue
        atributos = tag.group("atributos")
        identificador = RE_ID.search(atributos)
        if identificador and RE_RUNAT.search(atributos):
            linea = limpio.count("\n", 0, tag.start() + identificador.start()) + 1
            controles.append((identificador.group("id"), linea))
    return controles


def _declarados(texto_vb: str) -> set[str]:
    declarados: set[str] = set()
    for linea in texto_vb.splitlines():
        declarados |= {(m.group("id") or m.group("id_for") or m.group("id_lista")).lower()
                       for m in RE_DECLARACION_VB.finditer(_codigo_vb(linea))}
    return declarados


def _grupo_de(ruta: Path) -> tuple[Path, str] | None:
    """(ruta del markup, tipo) para cualquiera de los tres archivos de una página."""
    nombre = ruta.name.lower()
    for extension in EXTENSIONES:
        for sufijo, tipo in ((extension + ".designer.vb", "designer"),
                             (extension + ".vb", "codebehind"), (extension, "markup")):
            if nombre.endswith(sufijo):
                return ruta.with_name(ruta.name[: len(ruta.name) - len(sufijo) + len(extension)]), tipo
    return None


def run(project_root: Path, archivos_modificados: list[Path], ctx: dict | None) -> list[dict]:
    grupos: dict[Path, set[str]] = {}
    for archivo in archivos_modificados:
        grupo = _grupo_de(Path(archivo))
        if grupo is not None:
            grupos.setdefault(grupo[0], set()).add(grupo[1])

    hallazgos: list[dict] = []
    for markup in sorted(grupos):
        try:
            hallazgos += _revisar_pagina(Path(project_root), markup, grupos[markup])
        except Exception:
            hallazgos.append(_hallazgo("error", traceback.format_exc(), "error_check"))
    return hallazgos


def _revisar_pagina(raiz: Path, markup: Path, tocados: set[str]) -> list[dict]:
    designer = markup.with_name(markup.name + ".designer.vb")
    codebehind = markup.with_name(markup.name + ".vb")
    texto_markup = gitdiff.read_text(markup) if markup.is_file() else ""

    directiva = RE_DIRECTIVA.search(texto_markup)
    if directiva and re.search(r"\bCodeFile\s*=", directiva.group("atributos"), re.IGNORECASE):
        return []  # modelo Web Site: el runtime genera las declaraciones
    if not designer.is_file():
        return [_hallazgo("warning", f"{markup.name}: no se encontró {designer.name}; no se "
                                     f"pudo verificar la declaración de controles",
                          "error_check")]

    declarados = _declarados(gitdiff.read_text(designer))
    texto_cb = gitdiff.read_text(codebehind) if codebehind.is_file() else ""
    declarados |= _declarados(texto_cb)
    controles = _controles_markup(texto_markup)
    ids_markup = {control.lower() for control, _ in controles}

    hallazgos: list[dict] = []
    if "markup" in tocados:
        agregadas = gitdiff.added_lines(raiz, markup)
        if agregadas is None:
            hallazgos.append(_sin_diff(markup))
        else:
            numeros = {numero for numero, _ in agregadas}
            for control, linea in controles:
                if linea in numeros and control.lower() not in declarados:
                    hallazgos.append(_hallazgo(
                        "warning",
                        f"{markup.name}:{linea} el control '{control}' no está declarado en "
                        f"{designer.name}. Compila, pero el designer quedó desactualizado: "
                        f"si el code-behind lo usa, no compilará en VS2008"))

    if codebehind.is_file() and tocados & {"codebehind", "designer"}:
        if "designer" in tocados:
            lineas = list(enumerate(texto_cb.splitlines(), start=1))
        else:
            lineas = gitdiff.added_lines(raiz, codebehind)
        if lineas is None:
            hallazgos.append(_sin_diff(codebehind))
        else:
            hallazgos += _revisar_usos(codebehind, designer, lineas, declarados, ids_markup)
    return hallazgos


def _revisar_usos(codebehind: Path, designer: Path, lineas, declarados: set[str],
                  ids_markup: set[str]) -> list[dict]:
    hallazgos: list[dict] = []
    vistos: set[str] = set()
    for numero, linea in lineas:
        for uso in RE_IDENTIFICADOR_VB.finditer(_codigo_vb(linea)):
            control = uso.group("id")
            clave = control.lower()
            if clave in declarados or clave in vistos:
                continue
            if clave in ids_markup:
                vistos.add(clave)
                hallazgos.append(_hallazgo(
                    "error",
                    f"{codebehind.name}:{numero} usa el control '{control}' del markup, pero "
                    f"no está declarado en {designer.name} ni en el code-behind: no compila "
                    f"en VS2008. Agrega 'Protected WithEvents {control} As ...' al designer"))
            elif uso.group("miembro") and RE_PREFIJO_CONTROL.match(control):
                vistos.add(clave)
                hallazgos.append(_hallazgo(
                    "warning",
                    f"{codebehind.name}:{numero} '{control}' parece un control por su prefijo, "
                    f"pero no está en el markup ni declarado. Si es un miembro de otra clase, "
                    f"ignora este aviso"))
    return hallazgos


def _sin_diff(ruta: Path) -> dict:
    return _hallazgo("warning", f"{ruta.name}: no se pudo obtener el diff (¿repo git?); "
                                f"no se verificó", "error_check")
