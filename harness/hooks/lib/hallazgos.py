"""Hallazgos por fase: ruta, guardado validado y render para el humano."""
from __future__ import annotations

from pathlib import Path

from . import contracts, harness


def ruta(project_root: Path, ticket_id: str, fase_id: str) -> Path:
    return harness.fase_dir(project_root, ticket_id, fase_id) / "hallazgos.json"


def referencia(ticket_id: str, fase_id: str, hallazgo_id: str) -> str:
    """`TICKET/fase_N/hN`: identifica un hallazgo sin depender de la fase activa."""
    return f"{ticket_id}/{fase_id}/{hallazgo_id}"


def leer(project_root: Path, ticket_id: str, fase_id: str) -> dict | None:
    """hallazgos.json de la fase, validado; ValueError si está mal formado."""
    destino = ruta(project_root, ticket_id, fase_id)
    if not destino.exists():
        return None
    datos = harness.read_json(destino)
    errores = contracts.validate_hallazgos(datos)
    if errores:
        raise ValueError(f"{destino} está mal formado: " + "; ".join(errores))
    return datos


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


def _una_linea(valor) -> str:
    return " ".join(str(valor).split())


def _encabezado(h: dict) -> str:
    partes = [h["id"], h.get("origen", "reflector")]
    if h.get("dimension") and h.get("componente"):
        partes.append(f"{h['dimension']} → {h['componente']}")
    if h.get("confianza"):
        partes.append(f"confianza {h['confianza']}")
    if h.get("reincide"):
        partes.append(f"reincide en {h['reincide']}")
    partes.append(h.get("estado", "propuesto"))
    return "## " + " · ".join(partes)


def render(datos: dict) -> str:
    lineas = [f"# Hallazgos — {datos['ticket_id']} / {datos['fase_id']}", "",
              "Lecciones de esta fase para la biblioteca del proyecto. **No bloquean:**",
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
                lineas.append(f"- **{etiqueta}:** {_una_linea(h[campo])}")
        lineas.append("")
    propuestos = [h for h in items if h.get("estado", "propuesto") == "propuesto"]
    if not propuestos:
        lineas.append("No queda ningún hallazgo por decidir en esta fase.")
        return "\n".join(lineas) + "\n"
    lineas += ["Responder por cada hallazgo propuesto:"]
    for h in propuestos:
        ref = referencia(datos["ticket_id"], datos["fase_id"], h["id"])
        lineas += [f"- Aprobar → `/hallazgo-ok {ref}`",
                   f"- Corregir y aprobar → `/hallazgo-editar {ref} \"<lección corregida>\"`",
                   f"- Rechazar → `/hallazgo-no {ref} \"<motivo>\"`"]
    return "\n".join(lineas) + "\n"
