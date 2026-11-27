"""Diagnóstico de solo lectura: qué le falta a la instalación o al proyecto, y cómo arreglarlo.

No escribe nada, no corre ningún check del perfil y no importa su código: solo mira
archivos. Cada comprobación devuelve (nivel, qué se vio, remedio). `falla` es algo
que rompe el ciclo; `aviso`, algo que conviene saber.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import sys
from pathlib import Path

from . import contracts, gitdiff, harness, prueba_asistida, state

OK, AVISO, FALLA = "ok", "aviso", "falla"
Linea = tuple[str, str, str]

HOOKS = (("PostToolUse", "check_rules.py"), ("Stop", "gate_phase.py"))
PIEZAS = ("hooks/cli.py", "hooks/check_rules.py", "hooks/gate_phase.py",
          "agents/skeptic.md", "agents/reflector.md", "agents/curador.md",
          "agents/probador.md", "skills/ticket-loop/SKILL.md",
          "skills/task-planner/SKILL.md", "commands/fase.md", "commands/ticket-abrir.md")
CARPETAS = ("hooks", "agents", "skills", "commands")
NO_SE_DESPLIEGA = ("probe_hook.py",)
DESPLIEGA = "vuelve a correr deploy.ps1 desde la carpeta del harness"


def raiz_global() -> Path:
    """Donde vive el harness instalado: ~/.claude, o harness/ si se corre desde el repo."""
    return Path(__file__).resolve().parents[2]


def _entorno() -> list[Linea]:
    version = ".".join(str(n) for n in sys.version_info[:3])
    lineas = [(OK, f"Python {version}", "") if sys.version_info >= (3, 12) else
              (FALLA, f"Python {version}: el harness necesita 3.12 o más",
               "instala Python 3.12 y deja 'python' apuntando a él")]
    lineas.append((OK, "git está en el PATH", "") if shutil.which("git") else
                  (FALLA, "git no está en el PATH: los checks no ven qué cambió",
                   "instala git o agrégalo al PATH"))
    if os.environ.get("HARNESS_STOP", "").strip().lower() == "off":
        lineas.append((AVISO, "HARNESS_STOP=off: el hook Stop está apagado en esta sesión",
                       "quita la variable cuando termine la emergencia"))
    return lineas


def _instalacion(raiz: Path) -> list[Linea]:
    faltan = [p for p in PIEZAS if not (raiz / p).is_file()]
    if faltan:
        return [(FALLA, f"faltan piezas del harness en {raiz}: {', '.join(faltan)}", DESPLIEGA)]
    return [(OK, f"las piezas del harness están en {raiz}", "")]


def _hooks(settings: Path) -> list[Linea]:
    if not settings.is_file():
        return [(AVISO, f"no hay {settings}: no se puede ver si los hooks están registrados",
                 "si el harness está desplegado, " + DESPLIEGA)]
    try:
        datos = json.loads(settings.read_text(encoding="utf-8-sig"))
    except (OSError, ValueError) as error:
        return [(FALLA, f"{settings} no es JSON válido ({error})",
                 "corrígelo a mano o restaura el respaldo que deja el deploy")]
    registrados = datos.get("hooks") if isinstance(datos, dict) else None
    lineas: list[Linea] = []
    for evento, archivo in HOOKS:
        patron = re.compile(r"""hooks[/\\]""" + re.escape(archivo) + r"""(?=$|[\s"'])""")
        comandos = [h.get("command") for entrada in (registrados or {}).get(evento) or []
                    if isinstance(entrada, dict)
                    for h in entrada.get("hooks") or []
                    if isinstance(h, dict) and isinstance(h.get("command"), str)
                    and patron.search(h["command"])]
        if not comandos:
            lineas.append((FALLA, f"el hook {evento} ({archivo}) no está registrado en "
                                  f"{settings}", DESPLIEGA))
            continue
        ruta = re.search(r'"([^"]+)"', comandos[0])
        if ruta and not Path(ruta.group(1)).is_file():
            lineas.append((FALLA, f"el hook {evento} apunta a {ruta.group(1)}, que no existe",
                           DESPLIEGA))
        else:
            lineas.append((OK, f"hook {evento} registrado ({archivo})", ""))
    return lineas


def _sha(archivo: Path) -> str:
    # Sin distinguir finales de línea: git puede convertirlos al clonar.
    return hashlib.sha256(archivo.read_bytes().replace(b"\r\n", b"\n")).hexdigest()


def _contra_la_fuente(raiz: Path, fuente: Path) -> list[Linea]:
    origen = fuente / "harness"
    if not origen.is_dir():
        return [(FALLA, f"{fuente} no es la carpeta del harness (no tiene harness/)",
                 "pasa en --fuente la carpeta donde está deploy.ps1")]
    if origen.resolve() == raiz.resolve():
        return [(OK, "se está corriendo desde la fuente: no hay copia que comparar", "")]
    distintos = []
    for carpeta in CARPETAS:
        for archivo in sorted((origen / carpeta).rglob("*")):
            if (not archivo.is_file() or "__pycache__" in archivo.parts
                    or archivo.name in NO_SE_DESPLIEGA):
                continue
            relativo = archivo.relative_to(origen)
            instalado = raiz / relativo
            if not instalado.is_file():
                distintos.append(f"{relativo.as_posix()} (falta)")
            elif _sha(instalado) != _sha(archivo):
                distintos.append(f"{relativo.as_posix()} (distinto)")
    if not distintos:
        return [(OK, f"lo instalado es igual a la fuente ({fuente})", "")]
    muestra = ", ".join(distintos[:6]) + (f" y {len(distintos) - 6} más"
                                          if len(distintos) > 6 else "")
    return [(AVISO, f"lo instalado no es igual a la fuente: {muestra}",
             DESPLIEGA + "; si editaste a mano lo instalado, el deploy lo pisa")]


def _proyecto(inicio: Path) -> list[Linea]:
    raiz = harness.find_project_root(inicio)
    if raiz is None:
        return [(AVISO, f"{inicio} no está dentro de un proyecto con perfil "
                        f"(.claude/{harness.PROFILE_MARKER})",
                 "corre deploy.ps1 -Proyecto <ruta>, o pasa --project")]
    lineas: list[Linea] = [(OK, f"proyecto: {raiz}", "")]
    try:
        reglas = harness.load_rules(raiz)
        if not isinstance(reglas, dict):
            raise ValueError("debe ser un objeto JSON")
    except (OSError, ValueError) as error:
        return lineas + [(FALLA, f".claude/{harness.PROFILE_MARKER} no se puede leer ({error})",
                          "corrige el JSON o vuelve a desplegar el perfil")]
    lineas.append((OK, f"perfil '{reglas.get('perfil', '?')}': rules.json se lee", ""))

    declarados = [c for c in reglas.get("checks_estructurales") or [] if isinstance(c, str)]
    faltan = [c for c in declarados if not (raiz / ".claude" / "checks" / f"{c}.py").is_file()]
    if faltan:
        lineas.append((FALLA, "rules.json declara checks estructurales sin archivo: "
                       + ", ".join(faltan), "agrega .claude/checks/<nombre>.py o quítalos "
                                            "de checks_estructurales"))
    elif declarados:
        lineas.append((OK, f"checks estructurales presentes: {', '.join(declarados)}", ""))

    if gitdiff.huella_cambio(raiz) is None:
        lineas.append((AVISO, "el proyecto no es un repositorio git usable: los checks no "
                              "ven qué cambió y la evidencia no queda atada al cambio",
                       "inicia git en el proyecto (git init y un primer commit)"))
    else:
        lineas.append((OK, "el proyecto es un repositorio git", ""))
        gitignore = raiz / ".gitignore"
        ignorado = gitignore.is_file() and any(
            linea.strip().rstrip("/") in (".harness", "/.harness")
            for linea in gitdiff.read_text(gitignore).splitlines())
        lineas.append((OK, ".harness/ está en .gitignore", "") if ignorado else
                      (AVISO, ".harness/ no está en .gitignore: el estado del ciclo "
                              "aparecería como cambio", "agrega la línea '.harness/'"))
    return lineas + _prueba_asistida(raiz) + _fase_actual(raiz)


def _prueba_asistida(raiz: Path) -> list[Linea]:
    config, errores = prueba_asistida.estado(raiz)
    if errores:
        return [(FALLA, f"{prueba_asistida.ARCHIVO} inválido: {'; '.join(errores)}",
                 "corre /harness-setup")]
    if config is None:
        return [(AVISO, "la prueba asistida no está configurada: todos los pasos del "
                        "guion son del humano", "corre /harness-setup una vez")]
    lineas: list[Linea] = [(OK, "prueba asistida configurada", "")]
    extra = prueba_asistida.prohibidas(config)
    if not extra:
        return lineas
    archivo = prueba_asistida.ruta_agente(raiz)
    texto = archivo.read_text(encoding="utf-8") if archivo.is_file() else None
    remedio = "corre /harness-setup, o abre un ticket: open-ticket lo regenera"
    if texto is None:
        return lineas + [(FALLA, f"hay herramientas prohibidas y falta {archivo}: el "
                                 f"bloqueo no es técnico", remedio)]
    if prueba_asistida.MARCA not in texto:
        bloqueadas = next((l for l in texto.splitlines()
                           if l.startswith("disallowedTools:")), "")
        sin_bloquear = [h for h in extra if h not in bloqueadas]
        return lineas + ([(FALLA, f"{archivo} es propio del proyecto y no bloquea: "
                                  f"{', '.join(sin_bloquear)}",
                           "agrégalas a su disallowedTools")] if sin_bloquear else
                         [(OK, "el probador propio del proyecto bloquea las prohibidas", "")])
    try:
        esperado = prueba_asistida.agente_con_prohibidas(
            prueba_asistida.ruta_generico().read_text(encoding="utf-8"), extra)
    except (OSError, ValueError) as error:
        return lineas + [(AVISO, f"no se pudo comparar el probador del proyecto ({error})",
                          DESPLIEGA)]
    return lineas + ([(OK, "el probador del proyecto bloquea las prohibidas", "")]
                     if texto == esperado else
                     [(AVISO, f"{archivo} quedó distinto del probador genérico", remedio)])


def _fase_actual(raiz: Path) -> list[Linea]:
    try:
        actual = harness.read_current(raiz)
        if not actual or not actual.get("ticket_id"):
            return [(OK, "sin ticket activo", "")]
        if not actual.get("fase_id"):
            return [(OK, f"ticket activo {actual['ticket_id']}, sin fase abierta", "")]
        estado = state.leer_fase(raiz, actual["ticket_id"], actual["fase_id"])
    except (OSError, ValueError, KeyError) as error:
        return [(FALLA, f"el estado en .harness/ no se puede leer ({error})",
                 "no lo edites a mano: revisa qué subcomando falló y repórtalo")]
    if estado is None:
        return [(AVISO, f"current.json apunta a {actual['fase_id']}, que no tiene estado",
                 f"abre la fase con /fase {actual['fase_id']}")]
    errores = contracts.validate_fase_state(estado)
    if errores:
        return [(FALLA, f"fase_state.json de {actual['fase_id']} es inválido: "
                        f"{'; '.join(errores)}", "alguien lo editó a mano: restáuralo")]
    return [(OK, f"{actual['ticket_id']}/{actual['fase_id']}: {estado['estado']}, intento "
                 f"{estado['intento_actual']}/{estado['max_reintentos']}", "")]


def revisar(inicio: Path, settings: Path | None = None,
            fuente: Path | None = None) -> list[Linea]:
    raiz = raiz_global()
    lineas = _entorno() + _instalacion(raiz) + _hooks(settings or raiz / "settings.json")
    if fuente is not None:
        lineas += _contra_la_fuente(raiz, Path(fuente))
    return lineas + _proyecto(Path(inicio))


def render(lineas: list[Linea]) -> str:
    salida = []
    for nivel, texto, remedio in lineas:
        salida.append(f"[{nivel:^5}] {texto}")
        if remedio and nivel != OK:
            salida.append(f"        → {remedio}")
    fallas = sum(1 for nivel, _, _ in lineas if nivel == FALLA)
    avisos = sum(1 for nivel, _, _ in lineas if nivel == AVISO)
    salida.append(f"\n{fallas} falla(s), {avisos} aviso(s).")
    return "\n".join(salida)
