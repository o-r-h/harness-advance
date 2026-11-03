"""Curación de la biblioteca: estado en .harness/curacion.json y su render para el humano.

Es estado de proyecto, no de ticket. Los rechazos se escriben además en la
biblioteca versionada (curacion-rechazada.md), para que viajen con el repo.
"""
from __future__ import annotations

from pathlib import Path

from . import biblioteca, contracts, harness

ENCABEZADO_RECHAZOS = "# Curaciones rechazadas — no volver a proponer"


def ruta(project_root: Path) -> Path:
    return harness.harness_dir(project_root) / "curacion.json"


def ruta_rechazos(project_root: Path) -> Path:
    return biblioteca.biblioteca_dir(project_root) / "curacion-rechazada.md"


def leer(project_root: Path) -> dict | None:
    """curacion.json validado; None si no existe; ValueError si está mal formado."""
    destino = ruta(project_root)
    if not destino.exists():
        return None
    datos = harness.read_json(destino)
    errores = contracts.validate_curacion(datos)
    if errores:
        raise ValueError(f"{destino} está mal formado: " + "; ".join(errores))
    return datos


def guardar(project_root: Path, datos: dict) -> Path:
    errores = contracts.validate_curacion(datos)
    if errores:
        raise ValueError("curación inválida: " + "; ".join(errores))
    destino = ruta(project_root)
    harness.write_json(destino, datos)
    md = destino.with_suffix(".md")
    md.write_text(render(datos), encoding="utf-8")
    return md


def refs_de(accion: dict) -> list[str]:
    return list(accion["refs"]) if accion["tipo"] == "fusionar" else [accion["ref"]]


def _una_linea(valor) -> str:
    return " ".join(str(valor).split())


def render(datos: dict) -> str:
    lineas = ["# Curación de la biblioteca", "",
              "Acciones que propone el curador. **Nada se aplica sin tu decisión**, y nada",
              "se borra: lo retirado pasa a `retiradas/` con su motivo.", ""]
    acciones = datos.get("acciones", [])
    if not acciones:
        lineas.append("El curador no propuso acciones.")
        return "\n".join(lineas) + "\n"
    for a in acciones:
        lineas.append(f"## {a['id']} · {a['tipo']} · {a['estado']}")
        if a["tipo"] == "fusionar":
            otras = [r for r in a["refs"] if r != a["destino"]]
            lineas.append(f"- **Fusionar en:** {a['destino']} ← {', '.join(otras)}")
            if a.get("senal"):
                lineas.append(f"- **Señal nueva:** {_una_linea(a['senal'])}")
            lineas.append(f"- **Lección nueva:** {_una_linea(a['leccion'])}")
        else:
            lineas.append(f"- **Retirar:** {a['ref']}")
        lineas.append(f"- **Motivo:** {_una_linea(a['motivo'])}")
        if a.get("motivo_rechazo"):
            lineas.append(f"- **Rechazada:** {_una_linea(a['motivo_rechazo'])}")
        lineas.append("")
    propuestas = [a for a in acciones if a["estado"] == "propuesto"]
    if not propuestas:
        lineas.append("No queda ninguna acción por decidir.")
        return "\n".join(lineas) + "\n"
    lineas.append("Responder por cada acción propuesta:")
    for a in propuestas:
        lineas += [f"- Aprobar → `/curacion-ok {a['id']}`",
                   f"- Corregir y aprobar → `/curacion-editar {a['id']} ...`",
                   f"- Rechazar → `/curacion-no {a['id']} \"<motivo>\"`"]
    return "\n".join(lineas) + "\n"


def registrar_rechazo(project_root: Path, accion: dict, fecha: str) -> Path:
    """Agrega el rechazo a la biblioteca versionada, creando el archivo si hace falta."""
    destino = ruta_rechazos(project_root)
    destino.parent.mkdir(parents=True, exist_ok=True)
    linea = (f"- {fecha} · {accion['id']} · {accion['tipo']} · "
             f"{', '.join(refs_de(accion))} — {_una_linea(accion['motivo_rechazo'])}\n")
    if destino.is_file():
        texto = destino.read_text(encoding="utf-8")
        if not texto.endswith("\n"):
            texto += "\n"
    else:
        texto = f"{ENCABEZADO_RECHAZOS}\n\n"
    destino.write_text(texto + linea, encoding="utf-8")
    return destino
