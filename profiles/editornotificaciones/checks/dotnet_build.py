"""Check estructural: compila y prueba el backend .NET si la fase lo tocó.

A diferencia del código legacy, este proyecto sí tiene compilador y pruebas:
el build y `dotnet test` son la verificación más barata y más confiable que
existe, así que corren antes que el escéptico.
"""
from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

CHECK_ID = "dotnet_build"
EXTENSIONES = {".cs", ".csproj", ".props", ".targets", ".sln", ".slnx"}
TIMEOUT_S = 900


def _toca_backend(archivos) -> bool:
    return any(Path(a).suffix.lower() in EXTENSIONES for a in archivos)


def _solucion(raiz: Path) -> Path | None:
    for patron in ("*.sln", "*.slnx"):
        encontradas = sorted(raiz.glob(patron))
        if encontradas:
            return encontradas[0]
    return None


def _cola(proceso: subprocess.CompletedProcess, lineas: int = 40) -> str:
    salida = ((proceso.stdout or "") + "\n" + (proceso.stderr or "")).strip().splitlines()
    return "\n".join(salida[-lineas:])


def _correr(comando: list[str], raiz: Path) -> subprocess.CompletedProcess:
    return subprocess.run(comando, cwd=raiz, capture_output=True, text=True,
                          encoding="utf-8", errors="replace", timeout=TIMEOUT_S)


def run(project_root, archivos, ctx) -> list[dict]:
    raiz = Path(project_root)
    if not _toca_backend(archivos):
        return [{"id": CHECK_ID, "resultado": "ok",
                 "detalle": "la fase no tocó el backend: build omitido"}]
    dotnet = shutil.which("dotnet")
    if dotnet is None:
        return [{"id": CHECK_ID, "resultado": "error_check", "severidad": "error",
                 "detalle": "dotnet no está en el PATH: no se pudo compilar"}]
    solucion = _solucion(raiz)
    if solucion is None:
        return [{"id": CHECK_ID, "resultado": "error_check", "severidad": "error",
                 "detalle": "no hay .sln ni .slnx en la raíz del proyecto"}]

    build = _correr([dotnet, "build", str(solucion), "-nologo", "-v", "q"], raiz)
    if build.returncode != 0:
        return [{"id": CHECK_ID, "resultado": "fallo", "severidad": "error",
                 "detalle": f"dotnet build falló:\n{_cola(build)}"}]

    pruebas = _correr([dotnet, "test", str(solucion), "--no-build", "-nologo", "-v", "q"], raiz)
    if pruebas.returncode != 0:
        return [{"id": "dotnet_test", "resultado": "fallo", "severidad": "error",
                 "detalle": f"dotnet test falló:\n{_cola(pruebas)}"}]

    return [{"id": CHECK_ID, "resultado": "ok",
             "detalle": f"build y pruebas OK ({solucion.name})\n{_cola(pruebas, 6)}"}]
