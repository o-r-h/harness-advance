"""Generación del guion de prueba manual.

El gate humano es la única fuente de verdad funcional del proyecto. El harness no
intenta eliminarlo: lo vuelve rápido, guiado y registrable.

Cada paso dice quién lo ejecuta. Los de "agente" los corre el subagente `probador`
antes del gate y deja la evidencia en el intento; los de "humano" (login, pagos,
atajos del navegador, fidelidad visual) siguen siendo del humano. El veredicto,
en los dos casos, lo da el humano con /fase-ok o /fase-fallo.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

QUIENES = ("agente", "humano")
# Una celda de tabla cuyo contenido es solo "falla", con o sin énfasis de markdown.
RE_CELDA_FALLA = re.compile(r"\|\s*[*_`]*falla[*_`]*\s*(?=\|)", re.IGNORECASE)

PLANTILLA = """# Prueba manual — {fase_id} / intento_{intento}

**Fase:** {titulo}
**Criterio de éxito:** {criterio}
**URL:** {url}  ·  **Datos:** {datos}

| # | Quién | Paso | Qué deberías ver |
|---|-------|------|------------------|
{filas}
{asistida}
Responder cuando termines:

- Todo bien → `/fase-ok`
- Algo falló → `/fase-fallo <número de paso> "<qué pasó en realidad>"`

Tu respuesta queda en `historial_fallos` con `origen: "humano"`, así que el
intento siguiente arranca sabiendo qué falló y en qué paso.
"""

ASISTIDA = """
**Prueba asistida.** Los pasos *agente* ({n_agente}) los corre el subagente `probador`
antes de que te llegue el turno: deja `prueba_asistida.md` y la carpeta `evidencia/`
junto a este guion. Revisa esa evidencia y ejecuta tú los pasos *humano* ({n_humano}).
Un paso que el probador marque **simulado** o **no ejecutado** no cuenta como
pasado: hazlo tú. El veredicto sigue siendo tuyo.
"""


def validar_pasos(pasos) -> list[str]:
    """Errores del JSON de pasos; lista vacía si está bien."""
    if not isinstance(pasos, list) or not pasos:
        return ["--pasos-json debe contener una lista no vacía de objetos "
                "{paso, esperado, quien}"]
    errores = []
    for numero, paso in enumerate(pasos, start=1):
        if not isinstance(paso, dict) or not paso.get("paso"):
            errores.append(f"paso {numero}: debe ser un objeto con 'paso'")
            continue
        quien = paso.get("quien", "humano")
        if quien not in QUIENES:
            errores.append(f"paso {numero}: 'quien' debe ser uno de {list(QUIENES)}, "
                           f"no '{quien}'")
        elif quien == "agente" and not str(paso.get("esperado") or "").strip():
            errores.append(f"paso {numero}: un paso 'agente' lleva 'esperado' (sin eso "
                           f"el probador no tiene contra qué comparar)")
        elif quien == "humano" and paso.get("quien") and not paso.get("motivo"):
            errores.append(f"paso {numero}: un paso 'humano' explícito lleva 'motivo' "
                           f"(por qué el agente no puede correrlo)")
    return errores


def contar(pasos: list[dict]) -> tuple[int, int]:
    agente = sum(1 for paso in pasos if paso.get("quien", "humano") == "agente")
    return agente, len(pasos) - agente


def aviso_del_probador(carpeta: Path) -> str | None:
    """Lo que el humano debería saber del probador al dar un OK; None si no hay nada.

    Es un aviso y no un rechazo: el veredicto es del humano, que pudo ver el fallo y
    descartarlo. El reporte es markdown libre, así que solo se busca la celda 'falla'.
    """
    archivo_pasos = carpeta / "prueba_pasos.json"
    if not archivo_pasos.is_file():
        return None
    try:
        pasos = json.loads(archivo_pasos.read_text(encoding="utf-8"))
    except ValueError:
        return None
    if not isinstance(pasos, list) or not contar([p for p in pasos if isinstance(p, dict)])[0]:
        return None
    reporte = carpeta / "prueba_asistida.md"
    if not reporte.is_file():
        return ("Aviso: el guion tenía pasos del probador y no hay prueba_asistida.md: "
                "nadie dejó evidencia de esos pasos.")
    fallas = len(RE_CELDA_FALLA.findall(reporte.read_text(encoding="utf-8")))
    if fallas:
        return (f"Aviso: el probador marcó {fallas} paso(s) como 'falla' en {reporte} "
                f"y la prueba se registró como OK.")
    return None


def _celda(texto) -> str:
    return str(texto or "").replace("|", "\\|").replace("\n", " ")


def render(fase: dict, intento: int, pasos: list[dict]) -> str:
    configuracion = fase.get("prueba_manual") or {}
    filas = []
    for numero, paso in enumerate(pasos, start=1):
        quien = paso.get("quien", "humano")
        if quien == "humano" and paso.get("motivo"):
            quien = f"humano: {paso['motivo']}"
        filas.append(f"| {numero} | {_celda(quien)} | {_celda(paso.get('paso'))} | "
                     f"{_celda(paso.get('esperado'))} |")
    n_agente, n_humano = contar(pasos)
    return PLANTILLA.format(
        fase_id=fase["id"], intento=intento, titulo=fase.get("titulo", ""),
        criterio=fase.get("criterio_exito", ""),
        url=configuracion.get("url", "(sin URL declarada)"),
        datos=configuracion.get("datos", "(sin datos declarados)"),
        filas="\n".join(filas) or "| 1 | | (sin pasos declarados) | |",
        asistida=ASISTIDA.format(n_agente=n_agente, n_humano=n_humano) if n_agente else "")
