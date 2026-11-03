"""Biblioteca de lecciones del proyecto: entradas aprobadas/rechazadas e INDEX.md derivado.

Vive en <proyecto>/.claude/biblioteca/ y se versiona con el proyecto (DA6).
"""
from __future__ import annotations

import re
from pathlib import Path

# (campo en el JSON, etiqueta en la entrada), en el orden de la entrada.
_CAMPOS = (("senal", "señal"), ("leccion", "lección"), ("evidencia", "evidencia"),
           ("confianza", "confianza"), ("dimension", "dimension"),
           ("componente", "componente"), ("origen", "origen"),
           ("leccion_original", "lección original"), ("motivo", "motivo"))

_INTRO = ("Índice derivado: se reconstruye desde las entradas en disco. **Toda lección es "
          "hipótesis hasta re-verificarla en el código (DA8).**")


def biblioteca_dir(project_root: Path) -> Path:
    return Path(project_root) / ".claude" / "biblioteca"


def entrada_path(project_root: Path, ref: str, subdir: str = "entradas") -> Path:
    return biblioteca_dir(project_root) / subdir / f"{ref.replace('/', '-')}.md"


def escribir_entrada(project_root: Path, ticket_id: str, fase_id: str, hallazgo: dict,
                     fecha: str | None = None) -> Path:
    estado = hallazgo.get("estado")
    if estado == "aprobado":
        subdir = "entradas"
    elif estado == "rechazado":
        subdir = "rechazados"
    else:
        raise ValueError(f"solo se guardan hallazgos aprobados o rechazados, no '{estado}'")
    destino = biblioteca_dir(project_root) / subdir / f"{ticket_id}-{fase_id}-{hallazgo['id']}.md"
    destino.parent.mkdir(parents=True, exist_ok=True)
    lineas = [f"# {ticket_id}/{fase_id}/{hallazgo['id']}", ""]
    for clave, etiqueta in _CAMPOS:
        valor = hallazgo.get(clave)
        if valor:
            lineas.append(f"- **{etiqueta}**: {' '.join(str(valor).split())}")
    if estado == "aprobado" and fecha:
        lineas.append(f"- **aprobada**: {fecha}")
    destino.write_text("\n".join(lineas) + "\n", encoding="utf-8")
    reconstruir_indice(project_root)
    return destino


def _campo(texto: str, etiqueta: str) -> str:
    m = re.search(rf"^- \*\*{re.escape(etiqueta)}\*\*: (.*)$", texto, re.MULTILINE)
    return m.group(1).strip() if m else ""


_RE_FALLA = re.compile(r"^- \*\*falló\*\*: (\S+) · (\S+) · (implementada|sin pieza) — (.*)$",
                       re.MULTILINE)


def _fallas(texto: str) -> list[dict]:
    return [{"fecha": f, "ref": r, "tipo": t, "leccion": l.strip()}
            for f, r, t, l in _RE_FALLA.findall(texto)]


def leer_entrada(project_root: Path, ref: str) -> dict | None:
    ruta = entrada_path(project_root, ref)
    if not ruta.is_file():
        return None
    texto = ruta.read_text(encoding="utf-8")
    entrada = {"ref": ref}
    for clave, etiqueta in (("senal", "señal"), ("leccion", "lección"),
                            ("componente", "componente"), ("dimension", "dimension"),
                            ("origen", "origen"), ("aprobada", "aprobada"),
                            ("implementada", "implementada")):
        entrada[clave] = _campo(texto, etiqueta)
    entrada["fallas"] = _fallas(texto)
    return entrada


def _editar_lineas(project_root: Path, ref: str) -> tuple[Path, list[str]]:
    ruta = entrada_path(project_root, ref)
    if not ruta.is_file():
        raise ValueError(f"no hay una entrada aprobada para '{ref}'")
    return ruta, ruta.read_text(encoding="utf-8").split("\n")


def _guardar_lineas(project_root: Path, ruta: Path, lineas: list[str]) -> Path:
    ruta.write_text("\n".join(lineas), encoding="utf-8")
    reconstruir_indice(project_root)
    return ruta


def _agregar_al_final(lineas: list[str], nueva: str) -> None:
    # El texto termina en "\n", así que el último elemento es "": la línea nueva va antes.
    if lineas and lineas[-1] == "":
        lineas.insert(len(lineas) - 1, nueva)
    else:
        lineas.append(nueva)


def registrar_falla(project_root: Path, ref_original: str, ref_nueva: str, leccion: str,
                    fecha: str) -> Path:
    ruta, lineas = _editar_lineas(project_root, ref_original)
    tipo = "implementada" if _campo("\n".join(lineas), "implementada") else "sin pieza"
    _agregar_al_final(lineas, f"- **falló**: {fecha} · {ref_nueva} · {tipo} — "
                              f"{' '.join(leccion.split())}")
    return _guardar_lineas(project_root, ruta, lineas)


def marcar_implementada(project_root: Path, ref: str, nota: str, fecha: str) -> str | None:
    ruta, lineas = _editar_lineas(project_root, ref)
    nueva = f"- **implementada**: {fecha} · {' '.join(nota.split())}"
    anterior = None
    for i, linea in enumerate(lineas):
        if linea.startswith("- **implementada**: "):
            anterior = linea[len("- **implementada**: "):].strip()
            lineas[i] = nueva
            break
    else:
        _agregar_al_final(lineas, nueva)
    _guardar_lineas(project_root, ruta, lineas)
    return anterior


def _marcas(texto: str) -> str:
    """` (implementada <fecha>) (falló N×)`, solo con las marcas que la entrada trae."""
    marcas = ""
    implementada = _campo(texto, "implementada")
    if implementada:
        marcas += f" (implementada {implementada.split(' · ')[0]})"
    fallas = len(_fallas(texto))
    if fallas:
        marcas += f" (falló {fallas}×)"
    return marcas


def _archivos(carpeta: Path) -> list[Path]:
    return sorted(carpeta.glob("*.md"), key=lambda p: p.name) if carpeta.is_dir() else []


def _resumen(texto: str) -> str:
    """Señal de la entrada; una lección humana puede no traerla y entonces va la lección."""
    return _campo(texto, "señal") or _campo(texto, "lección")


def _clasificacion(texto: str) -> str:
    """`[dimension · componente] `, solo con lo que la entrada trae; vacío si no trae nada."""
    partes = [v for v in (_campo(texto, "dimension"), _campo(texto, "componente")) if v]
    return f"[{' · '.join(partes)}] " if partes else ""


def reconstruir_indice(project_root: Path) -> Path:
    base = biblioteca_dir(project_root)
    aprobadas = []
    for f in _archivos(base / "entradas"):
        t = f.read_text(encoding="utf-8")
        aprobadas.append(f"- {_clasificacion(t)}{_resumen(t)} — entradas/{f.name}"
                         f"{_marcas(t)}")
    rechazadas = []
    for f in _archivos(base / "rechazados"):
        t = f.read_text(encoding="utf-8")
        rechazadas.append(f"- {_resumen(t)} — motivo: {_campo(t, 'motivo')}")
    lineas = ["# Biblioteca de lecciones", "", _INTRO, "", "## Aprobadas", "",
              *(aprobadas or ["_(vacía)_"]), "",
              "## Rechazadas — no volver a proponer", "",
              *(rechazadas or ["_(vacía)_"])]
    destino = base / "INDEX.md"
    destino.parent.mkdir(parents=True, exist_ok=True)
    destino.write_text("\n".join(lineas) + "\n", encoding="utf-8")
    return destino
