"""Generación del guion de prueba manual.

El gate humano es la única fuente de verdad funcional del proyecto (no hay
build ni tests automatizables). El harness no intenta eliminarlo: lo vuelve
rápido, guiado y registrable.
"""
from __future__ import annotations

PLANTILLA = """# Prueba manual — {fase_id} / intento_{intento}

**Fase:** {titulo}
**Criterio de éxito:** {criterio}
**URL:** {url}  ·  **Datos:** {datos}

| # | Paso | Qué deberías ver |
|---|------|------------------|
{filas}

Responder cuando termines:

- Todo bien → `/fase-ok`
- Algo falló → `/fase-fallo <número de paso> "<qué pasó en realidad>"`

Tu respuesta queda en `historial_fallos` con `origen: "humano"`, así que el
intento siguiente arranca sabiendo qué falló y en qué paso.
"""


def render(fase: dict, intento: int, pasos: list[dict]) -> str:
    configuracion = fase.get("prueba_manual") or {}
    filas = "\n".join(
        f"| {numero} | {paso.get('paso', '')} | {paso.get('esperado', '')} |"
        for numero, paso in enumerate(pasos, start=1))
    return PLANTILLA.format(
        fase_id=fase["id"], intento=intento, titulo=fase.get("titulo", ""),
        criterio=fase.get("criterio_exito", ""),
        url=configuracion.get("url", "(sin URL declarada)"),
        datos=configuracion.get("datos", "(sin datos declarados)"),
        filas=filas or "| 1 | (sin pasos declarados) | |")
