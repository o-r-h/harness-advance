"""Hallazgos por fase: ruta, guardado validado y render para el humano."""
from __future__ import annotations

from pathlib import Path

from . import contracts, harness


def ruta(project_root: Path, ticket_id: str, fase_id: str) -> Path:
    return harness.fase_dir(project_root, ticket_id, fase_id) / "hallazgos.json"


def leer(project_root: Path, ticket_id: str, fase_id: str) -> dict | None:
    destino = ruta(project_root, ticket_id, fase_id)
    if not destino.exists():
        return None
    return harness.read_json(destino)


def guardar(project_root: Path, datos: dict) -> Path:
    errores = contracts.validate_hallazgos(datos)
    if errores:
        raise ValueError("hallazgos inválido: " + "; ".join(errores))
    destino = ruta(project_root, datos["ticket_id"], datos["fase_id"])
    harness.write_json(destino, datos)
    md = destino.with_suffix(".md")
    md.parent.mkdir(parents=True, exist_ok=True)
    md.write_text(render(datos), encoding="utf-8")
    return md


def _encabezado(h: dict) -> str:
    partes = [h["id"]]
    if h.get("dimension") and h.get("componente"):
        partes.append(f"{h['dimension']} → {h['componente']}")
    if h.get("confianza"):
        partes.append(f"confianza {h['confianza']}")
    partes.append(h.get("estado", "propuesto"))
    return "## " + " · ".join(partes)


def render(datos: dict) -> str:
    lineas = [f"# Hallazgos — {datos['ticket_id']} / {datos['fase_id']}", "",
              "Lecciones que propone el reflector para la biblioteca del proyecto. "
              "**No bloquean:**",
              "puedes seguir con la siguiente fase y resolverlas después.", ""]
    items = datos.get("hallazgos", [])
    if not items:
        lineas.append("El reflector no encontró lecciones que valga la pena guardar "
                      "en esta fase.")
        return "\n".join(lineas) + "\n"
    for h in items:
        lineas.append(_encabezado(h))
        for etiqueta, campo in (("Señal", "senal"), ("Lección", "leccion"),
                                ("Evidencia", "evidencia")):
            if h.get(campo):
                lineas.append(f"- **{etiqueta}:** {h[campo]}")
        lineas.append("")
    lineas += ["Responder por cada hallazgo:"]
    for h in items:
        i = h["id"]
        lineas += [f"- Aprobar → `/hallazgo-ok {i}`",
                   f"- Corregir y aprobar → `/hallazgo-editar {i} \"<lección corregida>\"`",
                   f"- Rechazar → `/hallazgo-no {i} \"<motivo>\"`"]
    return "\n".join(lineas) + "\n"
