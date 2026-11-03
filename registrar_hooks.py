"""Registra los hooks del harness en el settings.json de Claude Code.

Corre solo al desplegar (lo llama deploy.ps1). Va en Python y no en
PowerShell porque el ConvertTo-Json de PS 5.1 corta lo anidado y escapa los
acentos: reescribiría el settings.json del usuario dañándolo.

Fusiona dos entradas sin tocar nada más: ni hooks ajenos, ni otras claves, ni
su orden, ni sus acentos. Nunca borra entradas. Un settings.json roto no se
escribe.
"""
import argparse
import copy
import json
import os
import shutil
import sys
import tempfile
from datetime import datetime
from pathlib import Path

# (evento, matcher, archivo) de cada hook del harness.
TABLA = (
    ("PostToolUse", "Edit|Write|MultiEdit", "check_rules.py"),
    ("Stop", "", "gate_phase.py"),
)


def _forzar_utf8_en_salidas() -> None:
    """Los mensajes van en español y salen por tuberías que en Windows
    heredan cp1252; esto reconfigura solo stdout y stderr."""
    for flujo in (sys.stdout, sys.stderr):
        try:
            flujo.reconfigure(encoding="utf-8")
        except (AttributeError, ValueError):
            pass


def _es_nuestro(hook: dict, archivo: str) -> bool:
    return isinstance(hook, dict) and archivo in str(hook.get("command", ""))


def registrar(settings: dict, hooks_dir: str) -> tuple[dict, list[str]]:
    """Devuelve una copia con los hooks del harness registrados y las líneas
    a imprimir. No muta la entrada."""
    datos = copy.deepcopy(settings)
    lineas: list[str] = []
    for evento, matcher, archivo in TABLA:
        comando = f'python "{Path(hooks_dir) / archivo}"'
        lista = datos.setdefault("hooks", {}).setdefault(evento, [])
        nuestras = [entrada for entrada in lista
                    if any(_es_nuestro(h, archivo) for h in entrada.get("hooks", []))]
        if not nuestras:
            lista.append({"matcher": matcher,
                          "hooks": [{"type": "command", "command": comando}]})
            lineas.append(f"{evento} ({archivo}): registrado")
            continue
        cambio = False
        avisos: list[str] = []
        for entrada in nuestras:
            propios = [h for h in entrada["hooks"] if _es_nuestro(h, archivo)]
            for hook in propios:
                if hook["command"] != comando:
                    hook["command"] = comando
                    cambio = True
            if len(propios) == len(entrada["hooks"]):
                if entrada.get("matcher") != matcher:
                    entrada["matcher"] = matcher
                    cambio = True
            elif entrada.get("matcher") != matcher:
                avisos.append(f"{evento} ({archivo}): entrada mixta, matcher sin tocar")
        lineas.append(f"{evento} ({archivo}): "
                      + ("ruta actualizada" if cambio else "ya estaba"))
        lineas.extend(avisos)
        if len(nuestras) > 1:
            lineas.append(f"{evento} ({archivo}): {len(nuestras)} entradas del harness")
    return datos, lineas


def _escribir_atomico(ruta: Path, datos: dict) -> None:
    descriptor, temporal = tempfile.mkstemp(dir=ruta.parent, prefix=ruta.name + ".")
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8", newline="\n") as f:
            f.write(json.dumps(datos, indent=2, ensure_ascii=False) + "\n")
        os.replace(temporal, ruta)
    except BaseException:
        Path(temporal).unlink(missing_ok=True)
        raise


def main(argv: list[str] | None = None) -> int:
    _forzar_utf8_en_salidas()
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--settings", required=True, help="ruta del settings.json")
    parser.add_argument("--hooks-dir", required=True,
                        help="carpeta donde quedaron desplegados los hooks")
    args = parser.parse_args(argv)
    ruta = Path(args.settings)

    existe = ruta.exists()
    if existe:
        try:
            original = json.loads(ruta.read_text(encoding="utf-8-sig"))
        except json.JSONDecodeError as error:
            print(f"HARNESS · {ruta} no es JSON válido (línea {error.lineno}, "
                  f"columna {error.colno}): {error.msg}. No se tocó nada.",
                  file=sys.stderr)
            return 1
        if not isinstance(original, dict):
            print(f"HARNESS · {ruta} debe ser un objeto JSON. No se tocó nada.",
                  file=sys.stderr)
            return 1
    else:
        original = {}

    nuevo, lineas = registrar(original, args.hooks_dir)
    for linea in lineas:
        print(linea)
    if existe and nuevo == original:
        return 0
    if existe:
        sello = datetime.now().strftime("%d-%m-%Y-%H%M%S")
        shutil.copy2(ruta, ruta.with_name(f"{ruta.name}.bak-{sello}"))
    else:
        ruta.parent.mkdir(parents=True, exist_ok=True)
    _escribir_atomico(ruta, nuevo)
    return 0


if __name__ == "__main__":
    sys.exit(main())
