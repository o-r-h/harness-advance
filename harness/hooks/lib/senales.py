"""Señales deterministas de la biblioteca, para el reporte y para el curador.

Solo lectura. Ninguna señal decide nada: "sin uso" o "ruta ausente" son pistas
que el curador pesa y el humano aprueba.
"""
from __future__ import annotations

import re
from pathlib import Path

from . import biblioteca, gitdiff, harness

# Lo que rodea a una ruta en un texto y no es parte de ella.
_BORDES = "'\"`()¿?¡!,;"
RE_BACKTICKS = re.compile(r"`([^`]+)`")
RE_NUMERO_DE_LINEA = re.compile(r":\d+(?:-\d+)?$")
RE_SEGMENTO = re.compile(r"^[\w.\-]+$")
RE_EXTENSION = re.compile(r"\.[A-Za-z0-9]{1,6}$")
RE_FUSIONADA = re.compile(r"^- \*\*fusionada\*\*: \S+ · (\S+)", re.MULTILINE)


def _parece_ruta(token: str) -> str | None:
    """La ruta normalizada si el token lo parece; None si no.

    Al menos dos segmentos de letras, dígitos, `.`, `_` o `-`; y extensión en el
    último o todos de 3 caracteres o más. Así `src/scss` cuenta y `y/o`, `[B]/[E]`,
    `global.api` o una URL no."""
    token = token.strip(_BORDES).rstrip(".:")
    token = RE_NUMERO_DE_LINEA.sub("", token)
    if "://" in token or " " in token:
        return None
    segmentos = token.strip("/").split("/")
    # '../../global/x.vue' se compara como 'global/x.vue': el sufijo basta.
    while segmentos and segmentos[0] in (".", ".."):
        segmentos.pop(0)
    token = "/".join(segmentos)
    if len(segmentos) < 2 or not all(RE_SEGMENTO.match(s) for s in segmentos):
        return None
    if RE_EXTENSION.search(segmentos[-1]) or all(len(s) >= 3 for s in segmentos):
        return token
    return None


def rutas_mencionadas(texto: str) -> list[str]:
    candidatos = RE_BACKTICKS.findall(texto) + texto.split()
    rutas: list[str] = []
    for candidato in candidatos:
        ruta = _parece_ruta(candidato)
        if ruta and ruta not in rutas:
            rutas.append(ruta)
    return rutas


def _sufijos_rastreados(project_root: Path) -> set[str] | None:
    """Todo sufijo de segmentos completos de cada archivo y carpeta rastreados."""
    rastreados = gitdiff.archivos_rastreados(project_root)
    if rastreados is None:
        return None
    sufijos: set[str] = set()
    for ruta in rastreados:
        segmentos = ruta.lower().split("/")
        for fin in range(1, len(segmentos) + 1):
            for inicio in range(fin):
                sufijos.add("/".join(segmentos[inicio:fin]))
    return sufijos


def _fecha_orden(fecha: str | None) -> tuple:
    m = re.fullmatch(r"(\d{2})-(\d{2})-(\d{4})", fecha or "")
    return (int(m.group(3)), int(m.group(2)), int(m.group(1))) if m else ()


def _anclajes(project_root: Path) -> dict[str, list[tuple[tuple, str]]]:
    """{nombre de archivo de la entrada: [(orden, ticket), ...]}, un ticket por plan."""
    usos: dict[str, list[tuple[tuple, str]]] = {}
    try:
        planes = sorted(harness.tickets_dir(project_root).glob("*/plan.json"))
    except OSError:
        return usos  # el reporte ya nombra la carpeta como ilegible
    for plan in planes:
        try:
            datos = harness.read_json(plan)
            contexto = plan.parent / "ticket_context.json"
            fecha = harness.read_json(contexto).get("fecha") if contexto.is_file() else None
        except (OSError, ValueError, AttributeError):
            continue
        ticket = plan.parent.name
        nombres: set[str] = set()
        for fase in (datos.get("fases") or []) if isinstance(datos, dict) else []:
            for ancla in (fase.get("anclajes") or []) if isinstance(fase, dict) else []:
                ref = str(ancla.get("ref", "")) if isinstance(ancla, dict) else ""
                ref = ref.replace("\\", "/")
                if "biblioteca/entradas/" in ref:
                    nombres.add(ref.rsplit("/", 1)[1])
        for nombre in nombres:
            usos.setdefault(nombre, []).append(((_fecha_orden(fecha), ticket), ticket))
    return usos


def _ultima_curacion(project_root: Path) -> str | None:
    try:
        datos = harness.read_json(harness.harness_dir(project_root) / "curacion.json")
        fechas = [a["fecha_resuelta"] for a in datos.get("acciones", [])
                  if isinstance(a, dict) and a.get("fecha_resuelta")]
    except (OSError, ValueError, AttributeError, TypeError):
        return None
    return max(fechas, key=_fecha_orden, default=None)


def senales(project_root: Path) -> dict:
    project_root = Path(project_root)
    carpeta = biblioteca.biblioteca_dir(project_root) / "entradas"
    archivos = sorted(carpeta.glob("*.md")) if carpeta.is_dir() else []
    sufijos = _sufijos_rastreados(project_root) if archivos else None
    anclajes = _anclajes(project_root)

    lecciones: list[dict] = []
    for archivo in archivos:
        try:
            texto = archivo.read_text(encoding="utf-8")
        except (OSError, ValueError):
            continue  # ilegible: el reporte la lista aparte; aquí no hay señal que dar
        primera = texto.split("\n", 1)[0].strip()
        ref = primera[2:].strip() if primera.startswith("# ") else archivo.stem
        # Un ancla a una lección absorbida cuenta para el destino de la fusión.
        nombres = [archivo.name] + [biblioteca.entrada_path(project_root, r).name
                                    for r in RE_FUSIONADA.findall(texto)]
        usos = sorted({u for n in nombres for u in anclajes.get(n, [])})
        rutas = None
        if sufijos is not None:
            mencion = " ".join((biblioteca._campo(texto, "señal"),
                                biblioteca._campo(texto, "lección")))
            rutas = [r for r in rutas_mencionadas(mencion) if r.lower() not in sufijos]
        lecciones.append({
            "ref": ref, "archivo": f"entradas/{archivo.name}",
            "senal": biblioteca._resumen(texto),
            "usos": len({ticket for _, ticket in usos}),
            "ultimo_uso": usos[-1][1] if usos else None,
            "rutas_ausentes": rutas,
            "fallas": len(biblioteca._fallas(texto)),
            "implementada": bool(biblioteca._campo(texto, "implementada")),
        })
    lecciones.sort(key=lambda l: l["ref"])
    return {"lecciones": lecciones, "ultima_curacion": _ultima_curacion(project_root)}
