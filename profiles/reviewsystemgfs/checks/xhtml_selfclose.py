"""Check estructural: tags vacíos sin autocerrar en páginas XHTML 1.0.

En el repo conviven páginas XHTML 1.0 Transitional y páginas HTML5; la regla
solo aplica a las primeras, según el DOCTYPE de la página o, en una página de
contenido, el de su master. Solo se miran las líneas agregadas: el markup
existente está lleno de estos casos y marcarlos sería ruido. Es `warning`
porque los navegadores lo toleran en la práctica.
"""
from __future__ import annotations

import re
import traceback
from pathlib import Path

from lib import gitdiff

CHECK_ID = "xhtml_selfclose"
EXTENSIONES = (".aspx", ".master")
VACIOS = ("br", "img", "input", "hr", "meta", "link", "area", "base", "col", "param")
RE_TAG_VACIO = re.compile(
    r"<(?P<tag>" + "|".join(VACIOS) + r")(?![\w-])(?P<cuerpo>[^>]*)>", re.IGNORECASE)
RE_XHTML = re.compile(r"<!DOCTYPE\s+html\s+PUBLIC\s+[\"']-//W3C//DTD\s+XHTML", re.IGNORECASE)
RE_DOCTYPE = re.compile(r"<!DOCTYPE\b", re.IGNORECASE)
RE_MASTER = re.compile(r"<%@[^%]*?\bMasterPageFile\s*=\s*[\"'](?P<ruta>[^\"']+)[\"']",
                       re.IGNORECASE)
# Lo que no es markup que vaya al parser XHTML: comentarios, código de servidor,
# contenido de <script> y <style>.
RE_NO_MARKUP = re.compile(
    r"<%--.*?--%>|<!--.*?-->|<%.*?%>|"
    r"(?<=<script)[^>]*>.*?(?=</script)|(?<=<style)[^>]*>.*?(?=</style)",
    re.IGNORECASE | re.DOTALL)


def _hallazgo(severidad: str, detalle: str, resultado: str = "fallo") -> dict:
    return {"id": CHECK_ID, "resultado": resultado, "severidad": severidad,
            "detalle": detalle}


def _en_blanco(encontrado: re.Match) -> str:
    return re.sub(r"[^\n]", " ", encontrado.group(0))


def _master(raiz: Path, pagina: Path, ruta: str) -> Path | None:
    """Resuelve MasterPageFile: '~/' es la raíz de la aplicación, que no se conoce;
    se busca subiendo desde la carpeta de la página hasta la raíz del proyecto."""
    relativa = ruta[2:] if ruta.startswith("~/") else ruta
    if not ruta.startswith("~/"):
        candidato = pagina.parent / relativa
        return candidato if candidato.is_file() else None
    raiz = raiz.resolve()
    carpeta = pagina.resolve().parent
    while True:
        candidato = carpeta / relativa
        if candidato.is_file():
            return candidato
        if carpeta == raiz or carpeta.parent == carpeta:
            return None
        carpeta = carpeta.parent


def _es_xhtml(raiz: Path, pagina: Path, texto: str) -> bool:
    if RE_DOCTYPE.search(texto):
        return bool(RE_XHTML.search(texto))
    master = RE_MASTER.search(texto)
    if master is None:
        return False
    ruta = _master(raiz, pagina, master.group("ruta"))
    return ruta is not None and bool(RE_XHTML.search(gitdiff.read_text(ruta)))


def run(project_root: Path, archivos_modificados: list[Path], ctx: dict | None) -> list[dict]:
    raiz = Path(project_root)
    hallazgos: list[dict] = []
    for archivo in archivos_modificados:
        archivo = Path(archivo)
        if not archivo.name.lower().endswith(EXTENSIONES):
            continue
        try:
            hallazgos += _revisar(raiz, archivo)
        except Exception:
            hallazgos.append(_hallazgo("warning", traceback.format_exc(), "error_check"))
    return hallazgos


def _revisar(raiz: Path, archivo: Path) -> list[dict]:
    texto = gitdiff.read_text(archivo)
    if not _es_xhtml(raiz, archivo, texto):
        return []
    agregadas = gitdiff.added_lines(raiz, archivo)
    if agregadas is None:
        return [_hallazgo("warning", f"{archivo.name}: no se pudo obtener el diff "
                                     f"(¿repo git?); no se verificó", "error_check")]
    numeros = {numero for numero, _ in agregadas}
    lineas = RE_NO_MARKUP.sub(_en_blanco, texto).splitlines()

    hallazgos: list[dict] = []
    for numero in sorted(numeros):
        if numero > len(lineas):
            continue
        for tag in RE_TAG_VACIO.finditer(lineas[numero - 1]):
            if tag.group("cuerpo").rstrip().endswith("/"):
                continue
            nombre = tag.group("tag")
            hallazgos.append(_hallazgo(
                "warning", f"{archivo.name}:{numero} <{nombre}> sin autocerrar; la página es "
                           f"XHTML 1.0 y exige <{nombre} ... />"))
    return hallazgos
