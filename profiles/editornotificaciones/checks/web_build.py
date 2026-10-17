"""Check estructural: lint, pruebas y build del frontend Vue 2 si la fase lo tocó.

Corre los scripts de npm que existan en src/Web/package.json, en este orden:
lint → test:unit → build. Un script ausente se omite; uno que falla bloquea.
"""
from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

CHECK_ID = "web_build"
CARPETA_WEB = Path("src") / "Web"
EXTENSIONES = {".vue", ".js", ".mjs", ".ts", ".json", ".css", ".scss", ".html"}
SCRIPTS = ("lint", "test:unit", "build")
TIMEOUT_S = 900


def _toca_frontend(raiz: Path, archivos) -> bool:
    web = (raiz / CARPETA_WEB).resolve()
    for archivo in archivos:
        ruta = Path(archivo)
        ruta = (ruta if ruta.is_absolute() else raiz / ruta).resolve()
        if ruta.suffix.lower() in EXTENSIONES and (ruta == web or web in ruta.parents):
            return True
    return False


def _cola(proceso: subprocess.CompletedProcess, lineas: int = 40) -> str:
    salida = ((proceso.stdout or "") + "\n" + (proceso.stderr or "")).strip().splitlines()
    return "\n".join(salida[-lineas:])


def run(project_root, archivos, ctx) -> list[dict]:
    raiz = Path(project_root)
    if not _toca_frontend(raiz, archivos):
        return [{"id": CHECK_ID, "resultado": "ok",
                 "detalle": "la fase no tocó el frontend: build omitido"}]
    npm = shutil.which("npm")
    if npm is None:
        return [{"id": CHECK_ID, "resultado": "error_check", "severidad": "error",
                 "detalle": "npm no está en el PATH: no se pudo construir el frontend"}]
    web = raiz / CARPETA_WEB
    paquete = web / "package.json"
    if not paquete.is_file():
        return [{"id": CHECK_ID, "resultado": "error_check", "severidad": "error",
                 "detalle": f"no existe {CARPETA_WEB.as_posix()}/package.json"}]

    disponibles = (json.loads(paquete.read_text(encoding="utf-8")).get("scripts") or {})
    corridos = []
    for script in SCRIPTS:
        if script not in disponibles:
            continue
        proceso = subprocess.run([npm, "run", script], cwd=web, capture_output=True, text=True,
                                 encoding="utf-8", errors="replace", timeout=TIMEOUT_S)
        if proceso.returncode != 0:
            return [{"id": CHECK_ID, "resultado": "fallo", "severidad": "error",
                     "detalle": f"npm run {script} falló:\n{_cola(proceso)}"}]
        corridos.append(script)

    if "build" not in corridos:
        return [{"id": CHECK_ID, "resultado": "fallo", "severidad": "error",
                 "detalle": "package.json no define el script 'build'"}]
    return [{"id": CHECK_ID, "resultado": "ok",
             "detalle": "npm run " + ", ".join(corridos) + ": OK"}]
