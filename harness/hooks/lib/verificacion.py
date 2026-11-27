"""Aviso cuando una fase toca lo que la verifica.

Pasar un check debilitándolo, saltándolo o reescribiéndolo no es pasar. Un script
no sabe si el cambio a un test es legítimo, así que esto no bloquea: deja un
`warning` en checks.json por cada pieza de verificación que la fase tocó sin que el
plan la nombre, y el escéptico decide.

Las piezas del harness (`rules.json` y los checks del perfil) cuentan siempre. Las
del proyecto (sus tests) las declara el perfil en `rules.json`, porque el harness
genérico no conoce ningún stack:

    "rutas_de_verificacion": ["tests/*", "*.Tests/*"]
"""
from __future__ import annotations

import json
from fnmatch import fnmatchcase
from pathlib import Path

ID = "verificacion_tocada"
PROPIAS = (".claude/rules.json", ".claude/checks/*")


def _patrones(reglas: dict) -> tuple[str, ...]:
    declaradas = reglas.get("rutas_de_verificacion") if isinstance(reglas, dict) else None
    extra = [p for p in declaradas or [] if isinstance(p, str) and p.strip()] \
        if isinstance(declaradas, list) else []
    return PROPIAS + tuple(extra)


def _la_nombra_el_plan(relativo: str, fase: dict) -> bool:
    """El plan pide tocar el archivo si lo nombra, con su ruta o solo con su nombre."""
    texto = json.dumps({campo: fase.get(campo) for campo in
                        ("titulo", "pasos", "anclajes", "criterio_exito")},
                       ensure_ascii=False).replace("\\\\", "/").lower()
    return relativo.lower() in texto or Path(relativo).name.lower() in texto


def hallazgos(raiz: Path, archivos: list[Path], fase: dict, reglas: dict) -> list[dict]:
    patrones = _patrones(reglas)
    encontrados = []
    for archivo in archivos:
        try:
            relativo = Path(archivo).resolve().relative_to(Path(raiz).resolve()).as_posix()
        except ValueError:
            continue
        if not any(fnmatchcase(relativo.lower(), p.lower()) for p in patrones):
            continue
        if _la_nombra_el_plan(relativo, fase):
            continue
        encontrados.append({
            "id": ID, "resultado": "fallo", "severidad": "warning", "archivo": relativo,
            "detalle": f"la fase tocó {relativo}, que es parte de la verificación, y el "
                       f"plan no lo nombra: confirma que no se debilitó, saltó ni "
                       f"reescribió una comprobación para pasar"})
    return encontrados
