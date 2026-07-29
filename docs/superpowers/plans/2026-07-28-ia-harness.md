# IA Harness Engineering — Plan de Implementación

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Construir el harness nativo de Claude Code descrito en `docs/superpowers/specs/2026-07-28-ia-harness-engineering-design.md`, hasta que un ticket ISR real de ReviewSystemGFS se ejecute fase por fase con reintentos acotados, verificación determinista y gate humano registrado.

**Architecture:** Tres planos separados por frecuencia de cambio — harness genérico (`harness/` → `~/.claude/`), perfil de proyecto (`profiles/reviewsystemgfs/` → `<proyecto>/.claude/`), y estado de ejecución (`<proyecto>/.harness/tickets/`). La skill orquestadora conduce el flujo (juicio); los hooks de Claude Code hacen cumplir lo insaltable (hechos). Todas las mutaciones de estado pasan por un único CLI determinista.

**Tech Stack:** Python 3.12 (solo stdlib), `unittest`, Windows PowerShell 5.1 para el deploy, Git 2.54, hooks de Claude Code (`PostToolUse`, `Stop`).

## Global Constraints

Aplican a **todas** las tareas, sin excepción:

- **Solo stdlib de Python 3.12.** No hay `pytest` ni `jsonschema` instalados y no se instalan: los validadores se escriben a mano y las pruebas usan `unittest`. Verificado en el entorno.
- **Pruebas con `python -m unittest`**, nunca `pytest`.
- **El harness genérico (`harness/`) no contiene ningún conocimiento del stack legacy.** Cualquier cosa que mencione VB.NET, `.aspx`, `EjecutarSp` o jQuery pertenece a `profiles/`.
- **Los contadores (`intento_actual`, `max_reintentos`) los escribe solo el CLI**, nunca el modelo (D5 del spec).
- **Severidad por naturaleza de la regla, no por antigüedad del check.** `error` para dos clases: los **hechos de la plataforma** (`Async`/`Await` no compila en FW 3.5, `EntityFramework` no está referenciado, IE11 no tiene `fetch` — no pueden dar falso positivo sobre código legacy válido, porque ese código no existiría) y las **reglas propias del usuario sin ambigüedad** (`audit_comments`, `no_new_deps`). Todo lo demás —convenciones y heurísticas, como `no_raw_sql` o `no_es6`— entra como `warning` y se promueve solo cuando se lo haya visto acertar contra el repo real (D9 del spec).
- **Un bug del harness no debe parecer un bug del código:** si un check crashea se registra como `"resultado": "error_check"` con el traceback y **no** bloquea la fase.
- **Los hooks son inertes sin perfil:** sin `./.claude/rules.json` salen con código 0 y sin salida.
- **Nada se aprueba por omisión.** No hay timeouts que cierren fases.
- **Comentarios y mensajes del harness en español** (es la lengua de trabajo del usuario). **Superficie pública en inglés** — nombres de funciones, parámetros y constantes exportadas (`added_lines`, `project_root`, `ESTADOS_FASE`); **variables locales en español**, como en todo el código de ejemplo de este plan. Los términos del dominio (`fase`, `intento`, `veredicto`, `ticket`, `anclaje`) van en español incluso en la superficie pública, porque así se llaman los campos de los contratos JSON y renombrarlos rompería la correspondencia.
- **Nunca forzar UTF-8 sobre archivos del proyecto.** El código legacy suele estar en Windows-1252: decodificar con `errors="replace"` no crashea pero devuelve texto corrupto, y un acento mutilado produce un hallazgo inventado sobre el código del usuario. Leer bytes y decodificar con UTF-8 y respaldo a cp1252.
- **Formato de fecha del proyecto:** `DD-MM-YYYY`, exacto.
- **Ruta del repo fuente:** `C:\AZZULE\IA harness`. Remoto del proyecto objetivo: `http://10.10.50.37:3000/AzzuleNew/ReviewSystemGFS`.

## Estructura de archivos

| Archivo | Responsabilidad única |
|---|---|
| `harness/hooks/lib/harness.py` | Resolver rutas, perfil activo, puntero de estado, lectura/escritura atómica de JSON |
| `harness/hooks/lib/contracts.py` | Validar los cinco contratos JSON. Sin I/O |
| `harness/hooks/lib/gitdiff.py` | Obtener las líneas agregadas de un archivo respecto a HEAD |
| `harness/hooks/lib/checks.py` | Motor de checks genérico: aplica `rules.json` a un archivo. Sin conocimiento de stack |
| `harness/hooks/lib/state.py` | Máquina de estados de fase: transiciones, contador de intentos, `historial_fallos` |
| `harness/hooks/check_rules.py` | Hook `PostToolUse`: valida el archivo recién tocado, exit 2 si hay error |
| `harness/hooks/gate_phase.py` | Hook `Stop`: bloquea el cierre si el ciclo está a mitad de vuelo |
| `harness/hooks/cli.py` | Único punto de mutación de estado: `open-ticket`, `open-fase`, `run-checks`, `record-veredicto`, `record-manual`, `report`, `validate` |
| `harness/hooks/report.py` | Agregación para observabilidad. Lo invoca `cli.py report` |
| `harness/agents/skeptic.md` | Escéptico genérico: exige evidencia, emite `veredicto.json`. Sin reglas de proyecto |
| `harness/skills/ticket-loop/SKILL.md` | Orquestadora del ciclo de fase |
| `harness/skills/task-planner/SKILL.md` | Planner v3: emite `plan.md` + `plan.json` |
| `harness/commands/*.md` | Entradas finas: `/ticket-abrir`, `/fase`, `/fase-ok`, `/fase-fallo` |
| `profiles/reviewsystemgfs/rules.json` | Reglas declarativas del stack legacy |
| `profiles/reviewsystemgfs/agents/agent-rsgfs.md` | El agente actual, cirugía mínima |
| `profiles/reviewsystemgfs/checks/designer_sync.py` | `.aspx` ↔ `.designer.vb` ↔ `.aspx.vb` |
| `profiles/reviewsystemgfs/checks/sp_params.py` | `|Vn=` del VB ↔ `SepararCadena 'Vn'` del SP |
| `profiles/reviewsystemgfs/checks/xhtml_selfclose.py` | Tags sin cerrar en `.aspx` |
| `tests/*.py` | Un módulo de prueba por módulo de producción |
| `deploy.ps1` | Copiar a `~/.claude` y al proyecto, con respaldo de `settings.json` |

Separación deliberada: `checks.py` es el motor genérico y vive en `harness/`; los tres checks estructurales son plugins del perfil y viven en `profiles/`, porque saben de Web Forms.

---

### Task 1: Bootstrap del repo y sonda de payloads de hooks

Esta tarea existe porque el resto del plan depende de la forma exacta del JSON que Claude Code envía a los hooks. En lugar de asumirla, se observa.

**Files:**
- Create: `.gitignore`
- Create: `harness/hooks/probe_hook.py`
- Create: `docs/hook-payloads.md`

**Interfaces:**
- Consumes: nada.
- Produces: `docs/hook-payloads.md` con los nombres de campo reales de los payloads de `PostToolUse` y `Stop`. Las tareas 7 y 11 leen ese documento antes de tocar código.

- [ ] **Step 1: Inicializar el repo y el .gitignore**

```bash
cd "C:/AZZULE/IA harness"
git init
git config user.name "Omar Rodriguez"
git config user.email "Omar.Rodriguez@azzule.com"
```

Crear `.gitignore`:

```gitignore
__pycache__/
*.pyc
.harness/
probe-out/
```

- [ ] **Step 2: Escribir la sonda**

Crear `harness/hooks/probe_hook.py`:

```python
#!/usr/bin/env python3
"""Sonda temporal: registra el payload real que Claude Code envía a un hook.

Se usa una sola vez, para documentar la forma de los payloads antes de
escribir los hooks de verdad. No forma parte del harness final.
"""
import json
import sys
from datetime import datetime
from pathlib import Path

OUT = Path(__file__).resolve().parents[2] / "probe-out"


def main() -> int:
    raw = sys.stdin.read()
    OUT.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%H%M%S%f")
    try:
        data = json.loads(raw)
        event = data.get("hook_event_name", "sin_evento")
        text = json.dumps(data, indent=2, ensure_ascii=False)
    except json.JSONDecodeError:
        event = "no_json"
        text = raw
    (OUT / f"{event}-{stamp}.json").write_text(text, encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 3: Registrar la sonda en `~/.claude/settings.json`**

Respaldar primero. Añadir al objeto `hooks` existente (no reemplazar el archivo):

```json
{
  "hooks": {
    "PostToolUse": [
      { "matcher": "Edit|Write|MultiEdit",
        "hooks": [{ "type": "command",
                    "command": "python \"C:\\AZZULE\\IA harness\\harness\\hooks\\probe_hook.py\"" }] }
    ],
    "Stop": [
      { "matcher": "",
        "hooks": [{ "type": "command",
                    "command": "python \"C:\\AZZULE\\IA harness\\harness\\hooks\\probe_hook.py\"" }] }
    ]
  }
}
```

- [ ] **Step 4: Provocar los dos eventos y verificar la captura**

Editar cualquier archivo de prueba con la herramienta Edit y terminar un turno. Luego:

Run: `ls "C:/AZZULE/IA harness/probe-out"`
Expected: al menos un `PostToolUse-*.json` y un `Stop-*.json`.

- [ ] **Step 5: Documentar los campos observados**

Crear `docs/hook-payloads.md` transcribiendo los campos reales de cada payload capturado, con especial atención a: la ruta del archivo dentro de `tool_input` (¿`file_path`?), el directorio de trabajo (¿`cwd`?), y el indicador de reentrada del hook `Stop` (¿`stop_hook_active`?). Si algún nombre difiere de lo asumido en este plan, anotarlo en una sección **"Desvíos respecto al plan"** — las tareas 7 y 11 deben usar los nombres reales, no los de este documento.

- [ ] **Step 6: Desregistrar la sonda y commitear**

Quitar de `~/.claude/settings.json` las dos entradas de `probe_hook.py`.

```bash
git add .gitignore harness/hooks/probe_hook.py docs/
git commit -m "chore: bootstrap del repo y sonda de payloads de hooks"
```

---

### Task 2: `lib/harness.py` — rutas, perfil y estado

**Files:**
- Create: `harness/hooks/lib/__init__.py` (vacío)
- Create: `harness/hooks/lib/harness.py`
- Test: `tests/test_harness_lib.py`

**Interfaces:**
- Consumes: nada.
- Produces:
  - `find_project_root(start: str | Path) -> Path | None`
  - `load_rules(project_root: Path) -> dict`
  - `harness_dir/tickets_dir(project_root) -> Path`
  - `ticket_dir(project_root, ticket_id) -> Path`
  - `fase_dir(project_root, ticket_id, fase_id) -> Path`
  - `intento_dir(project_root, ticket_id, fase_id, intento: int) -> Path`
  - `read_current(project_root) -> dict | None` · `write_current(project_root, ticket_id, fase_id=None) -> None`
  - `read_json(path: Path) -> dict` · `write_json(path: Path, data: dict) -> None` (atómica)

- [ ] **Step 1: Escribir las pruebas que fallan**

Crear `tests/test_harness_lib.py`:

```python
import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "harness" / "hooks"))
from lib import harness  # noqa: E402


class TestFindProjectRoot(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def test_encuentra_la_raiz_desde_un_subdirectorio_profundo(self):
        (self.root / ".claude").mkdir()
        (self.root / ".claude" / "rules.json").write_text("{}", encoding="utf-8")
        profundo = self.root / "Scripts" / "sub" / "otro"
        profundo.mkdir(parents=True)
        self.assertEqual(harness.find_project_root(profundo), self.root.resolve())

    def test_devuelve_none_sin_perfil(self):
        profundo = self.root / "a" / "b"
        profundo.mkdir(parents=True)
        self.assertIsNone(harness.find_project_root(profundo))


class TestJsonAtomico(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def test_write_json_crea_los_directorios_padre(self):
        destino = self.root / "a" / "b" / "estado.json"
        harness.write_json(destino, {"acentúa": "sí"})
        self.assertEqual(json.loads(destino.read_text(encoding="utf-8"))["acentúa"], "sí")

    def test_write_json_no_deja_archivos_temporales(self):
        destino = self.root / "estado.json"
        harness.write_json(destino, {"a": 1})
        self.assertEqual([p.name for p in self.root.iterdir()], ["estado.json"])


class TestPunteroActual(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def test_read_current_devuelve_none_si_no_existe(self):
        self.assertIsNone(harness.read_current(self.root))

    def test_write_y_read_current_hacen_ida_y_vuelta(self):
        harness.write_current(self.root, "ISR-110722", "fase_1")
        actual = harness.read_current(self.root)
        self.assertEqual(actual["ticket_id"], "ISR-110722")
        self.assertEqual(actual["fase_id"], "fase_1")


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Correr las pruebas para verificar que fallan**

Run: `cd "C:/AZZULE/IA harness" && python -m unittest tests.test_harness_lib -v`
Expected: FAIL con `ModuleNotFoundError: No module named 'lib'`.

- [ ] **Step 3: Implementar el módulo**

Crear `harness/hooks/lib/__init__.py` vacío y `harness/hooks/lib/harness.py`:

```python
"""Resolución de rutas, perfil activo y estado del harness.

Este módulo no sabe nada de ningún stack concreto: solo de la estructura de
carpetas del harness. Todo conocimiento de un lenguaje o framework
pertenece a profiles/, nunca aquí.
"""
from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path

PROFILE_MARKER = "rules.json"


def find_project_root(start: str | Path) -> Path | None:
    """Primer ancestro (incluido `start`) que contenga .claude/rules.json."""
    inicio = Path(start).resolve()
    for candidato in [inicio, *inicio.parents]:
        if (candidato / ".claude" / PROFILE_MARKER).is_file():
            return candidato
    return None


def load_rules(project_root: Path) -> dict:
    return read_json(Path(project_root) / ".claude" / PROFILE_MARKER)


def harness_dir(project_root: Path) -> Path:
    return Path(project_root) / ".harness"


def tickets_dir(project_root: Path) -> Path:
    return harness_dir(project_root) / "tickets"


def ticket_dir(project_root: Path, ticket_id: str) -> Path:
    return tickets_dir(project_root) / ticket_id


def fase_dir(project_root: Path, ticket_id: str, fase_id: str) -> Path:
    return ticket_dir(project_root, ticket_id) / fase_id


def intento_dir(project_root: Path, ticket_id: str, fase_id: str, intento: int) -> Path:
    return fase_dir(project_root, ticket_id, fase_id) / f"intento_{intento}"


def current_pointer_path(project_root: Path) -> Path:
    return harness_dir(project_root) / "current.json"


def read_current(project_root: Path) -> dict | None:
    ruta = current_pointer_path(project_root)
    return read_json(ruta) if ruta.is_file() else None


def write_current(project_root: Path, ticket_id: str, fase_id: str | None = None) -> None:
    write_json(current_pointer_path(project_root),
               {"ticket_id": ticket_id, "fase_id": fase_id})


def read_json(path: Path) -> dict:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def write_json(path: Path, data: dict) -> None:
    """Escritura atómica: nunca deja un JSON a medio escribir."""
    destino = Path(path)
    destino.parent.mkdir(parents=True, exist_ok=True)
    fd, temporal = tempfile.mkstemp(dir=str(destino.parent), suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            json.dump(data, fh, ensure_ascii=False, indent=2)
        os.replace(temporal, destino)
    except BaseException:
        Path(temporal).unlink(missing_ok=True)
        raise
```

- [ ] **Step 4: Correr las pruebas para verificar que pasan**

Run: `python -m unittest tests.test_harness_lib -v`
Expected: PASS, 6 pruebas.

- [ ] **Step 5: Commit**

```bash
git add harness/hooks/lib/ tests/test_harness_lib.py
git commit -m "feat(lib): resolución de rutas, perfil activo y escritura atómica de estado"
```

---

### Task 2b: Ajustar `find_project_root` para el caso del propio harness

Un detalle que muerde en la práctica: si algún día `C:\AZZULE\IA harness` recibe un `.claude/rules.json`, los hooks empezarían a validar el propio harness. La defensa es explícita.

**Files:**
- Modify: `harness/hooks/lib/harness.py`
- Test: `tests/test_harness_lib.py`

**Interfaces:**
- Produces: `is_harness_source(project_root: Path) -> bool`

- [ ] **Step 1: Escribir la prueba que falla**

Añadir a `tests/test_harness_lib.py`:

```python
class TestAutoexclusion(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def test_reconoce_el_repo_fuente_del_harness(self):
        (self.root / "harness" / "hooks").mkdir(parents=True)
        (self.root / "profiles").mkdir()
        self.assertTrue(harness.is_harness_source(self.root))

    def test_un_proyecto_normal_no_es_el_repo_fuente(self):
        (self.root / "Scripts").mkdir()
        self.assertFalse(harness.is_harness_source(self.root))
```

- [ ] **Step 2: Correr para verificar que falla**

Run: `python -m unittest tests.test_harness_lib -v`
Expected: FAIL con `AttributeError: module 'lib.harness' has no attribute 'is_harness_source'`.

- [ ] **Step 3: Implementar**

Añadir a `harness/hooks/lib/harness.py`:

```python
def is_harness_source(project_root: Path) -> bool:
    """True si esta carpeta es el repo fuente del harness y no un proyecto.

    Evita que el harness se valide a sí mismo si alguien le pone un perfil.
    """
    raiz = Path(project_root)
    return (raiz / "harness" / "hooks").is_dir() and (raiz / "profiles").is_dir()
```

- [ ] **Step 4: Correr para verificar que pasa**

Run: `python -m unittest tests.test_harness_lib -v`
Expected: PASS, 8 pruebas.

- [ ] **Step 5: Commit**

```bash
git add harness/hooks/lib/harness.py tests/test_harness_lib.py
git commit -m "feat(lib): autoexclusión del repo fuente del harness"
```

---

### Task 3: `lib/contracts.py` — validación de los cinco contratos

**Files:**
- Create: `harness/hooks/lib/contracts.py`
- Test: `tests/test_contracts.py`

**Interfaces:**
- Consumes: nada (sin I/O; recibe dicts).
- Produces — cada función devuelve `list[str]` de errores, vacía si el dato es válido:
  - `validate_ticket_context(data: dict) -> list[str]`
  - `validate_plan(data: dict, rules: dict | None = None) -> list[str]`
  - `validate_checks_result(data: dict) -> list[str]`
  - `validate_veredicto(data: dict) -> list[str]`
  - `validate_fase_state(data: dict) -> list[str]`
  - `resolve_check_names(nombres: list[str], rules: dict) -> tuple[list[str], list[str]]` → `(resueltos, desconocidos)`
  - Constantes: `ESTADOS_FASE: frozenset[str]`, `CONFIANZAS: frozenset[str]`, `ORIGENES: frozenset[str]`

- [ ] **Step 1: Escribir las pruebas que fallan**

Crear `tests/test_contracts.py`:

```python
import copy
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "harness" / "hooks"))
from lib import contracts  # noqa: E402

CONTEXTO_OK = {
    "ticket_id": "ISR-110722",
    "nroticket": "110722",
    "desarrollador": "OMAR RODRIGUEZ",
    "fecha": "28-07-2026",
    "perfil": "reviewsystemgfs",
}

PLAN_OK = {
    "ticket_id": "ISR-110722",
    "perfil": "reviewsystemgfs",
    "generado_por": "task-planner-v3",
    "fases": [{
        "id": "fase_1",
        "titulo": "Agregar campo de comentario en Other Q",
        "pasos": ["Agregar el HiddenField", "Guardar vía SP"],
        "anclajes": [{"ref": "frmReviewReport.aspx.vb:412", "confianza": "verificado"}],
        "criterio_exito": "El comentario se guarda y se relee al reabrir la review",
        "checks_deterministas": ["audit_comments", "fw35_syntax"],
        "prueba_manual": {"requerida": True, "url": "frmReviewReport.aspx",
                          "datos": "review 4471, idioma EN"},
        "herramientas_permitidas": ["read", "edit"],
        "max_reintentos": 3,
        "depende_de": [],
    }],
}

REGLAS_OK = {
    "perfil": "reviewsystemgfs",
    "prohibido": [{"id": "no_async", "archivos": [".vb"], "severidad": "error",
                   "patron": r"\b(Async|Await)\b", "mensaje": "FW 3.5 no soporta async/await"}],
    "audit_comments": {"requerido": True, "severidad": "error"},
    "checks_estructurales": ["designer_sync"],
    "grupos": {"fw35_syntax": ["no_async"]},
}


class TestTicketContext(unittest.TestCase):
    def test_contexto_valido_no_produce_errores(self):
        self.assertEqual(contracts.validate_ticket_context(CONTEXTO_OK), [])

    def test_rechaza_fecha_en_formato_iso(self):
        malo = dict(CONTEXTO_OK, fecha="2026-07-28")
        errores = contracts.validate_ticket_context(malo)
        self.assertTrue(any("DD-MM-YYYY" in e for e in errores))

    def test_rechaza_desarrollador_vacio(self):
        malo = dict(CONTEXTO_OK, desarrollador="   ")
        self.assertTrue(contracts.validate_ticket_context(malo))


class TestPlan(unittest.TestCase):
    def test_plan_valido_no_produce_errores(self):
        self.assertEqual(contracts.validate_plan(PLAN_OK, REGLAS_OK), [])

    def test_rechaza_lista_de_fases_vacia(self):
        malo = dict(PLAN_OK, fases=[])
        self.assertTrue(contracts.validate_plan(malo))

    def test_rechaza_confianza_no_reconocida(self):
        malo = copy.deepcopy(PLAN_OK)
        malo["fases"][0]["anclajes"][0]["confianza"] = "quiza"
        errores = contracts.validate_plan(malo)
        self.assertTrue(any("confianza" in e for e in errores))

    def test_rechaza_max_reintentos_fuera_de_rango(self):
        malo = copy.deepcopy(PLAN_OK)
        malo["fases"][0]["max_reintentos"] = 0
        self.assertTrue(contracts.validate_plan(malo))

    def test_rechaza_dependencia_a_una_fase_inexistente(self):
        malo = copy.deepcopy(PLAN_OK)
        malo["fases"][0]["depende_de"] = ["fase_9"]
        errores = contracts.validate_plan(malo)
        self.assertTrue(any("fase_9" in e for e in errores))

    def test_rechaza_check_que_no_existe_ni_como_grupo(self):
        malo = copy.deepcopy(PLAN_OK)
        malo["fases"][0]["checks_deterministas"] = ["no_existe"]
        errores = contracts.validate_plan(malo, REGLAS_OK)
        self.assertTrue(any("no_existe" in e for e in errores))

    def test_sin_reglas_no_valida_nombres_de_checks(self):
        raro = copy.deepcopy(PLAN_OK)
        raro["fases"][0]["checks_deterministas"] = ["no_existe"]
        self.assertEqual(contracts.validate_plan(raro), [])


class TestResolucionDeChecks(unittest.TestCase):
    def test_expande_un_grupo_a_sus_checks(self):
        resueltos, desconocidos = contracts.resolve_check_names(["fw35_syntax"], REGLAS_OK)
        self.assertEqual(resueltos, ["no_async"])
        self.assertEqual(desconocidos, [])

    def test_reporta_los_nombres_desconocidos(self):
        resueltos, desconocidos = contracts.resolve_check_names(["fantasma"], REGLAS_OK)
        self.assertEqual(resueltos, [])
        self.assertEqual(desconocidos, ["fantasma"])

    def test_acepta_audit_comments_y_los_estructurales(self):
        resueltos, desconocidos = contracts.resolve_check_names(
            ["audit_comments", "designer_sync"], REGLAS_OK)
        self.assertEqual(desconocidos, [])
        self.assertEqual(sorted(resueltos), ["audit_comments", "designer_sync"])


class TestFaseState(unittest.TestCase):
    def test_estado_valido(self):
        estado = {"fase_id": "fase_1", "estado": "en_correccion", "intento_actual": 2,
                  "max_reintentos": 3,
                  "historial_fallos": [{"intento": 1, "origen": "check",
                                        "razon": "designer_sync falló",
                                        "correccion_aplicada": "se declaró el control"}]}
        self.assertEqual(contracts.validate_fase_state(estado), [])

    def test_rechaza_estado_desconocido(self):
        estado = {"fase_id": "fase_1", "estado": "meditando", "intento_actual": 1,
                  "max_reintentos": 3, "historial_fallos": []}
        self.assertTrue(contracts.validate_fase_state(estado))

    def test_rechaza_origen_de_fallo_desconocido(self):
        estado = {"fase_id": "fase_1", "estado": "en_correccion", "intento_actual": 2,
                  "max_reintentos": 3,
                  "historial_fallos": [{"intento": 1, "origen": "intuicion",
                                        "razon": "x", "correccion_aplicada": "y"}]}
        self.assertTrue(contracts.validate_fase_state(estado))

    def test_rechaza_intento_mayor_al_maximo(self):
        estado = {"fase_id": "fase_1", "estado": "en_correccion", "intento_actual": 5,
                  "max_reintentos": 3, "historial_fallos": []}
        errores = contracts.validate_fase_state(estado)
        self.assertTrue(any("max_reintentos" in e for e in errores))


class TestVeredicto(unittest.TestCase):
    def test_veredicto_valido(self):
        v = {"fase_id": "fase_1", "intento": 2, "aprobado": False,
             "juicio_esceptico": {"aprobado": True, "razones_rechazo": [],
                                  "claims_sin_evidencia": [], "anclajes_sin_resolver": []},
             "prueba_manual": {"requerida": True, "ejecutada": True, "resultado": "fallo",
                               "fallo_en_paso": 3, "observacion": "el campo volvió vacío"}}
        self.assertEqual(contracts.validate_veredicto(v), [])

    def test_no_puede_estar_aprobado_si_el_esceptico_rechazo(self):
        v = {"fase_id": "fase_1", "intento": 1, "aprobado": True,
             "juicio_esceptico": {"aprobado": False, "razones_rechazo": ["falta validación"],
                                  "claims_sin_evidencia": [], "anclajes_sin_resolver": []},
             "prueba_manual": {"requerida": False, "ejecutada": False, "resultado": "na"}}
        errores = contracts.validate_veredicto(v)
        self.assertTrue(any("aprobado" in e for e in errores))

    def test_no_puede_estar_aprobado_si_la_prueba_manual_requerida_no_paso(self):
        v = {"fase_id": "fase_1", "intento": 1, "aprobado": True,
             "juicio_esceptico": {"aprobado": True, "razones_rechazo": [],
                                  "claims_sin_evidencia": [], "anclajes_sin_resolver": []},
             "prueba_manual": {"requerida": True, "ejecutada": False, "resultado": "pendiente"}}
        self.assertTrue(contracts.validate_veredicto(v))

    def test_rechazo_del_esceptico_exige_al_menos_una_razon(self):
        v = {"fase_id": "fase_1", "intento": 1, "aprobado": False,
             "juicio_esceptico": {"aprobado": False, "razones_rechazo": [],
                                  "claims_sin_evidencia": [], "anclajes_sin_resolver": []},
             "prueba_manual": {"requerida": False, "ejecutada": False, "resultado": "na"}}
        errores = contracts.validate_veredicto(v)
        self.assertTrue(any("razones_rechazo" in e for e in errores))


class TestChecksResult(unittest.TestCase):
    def test_resultado_agregado_debe_coincidir_con_los_checks(self):
        malo = {"fase_id": "fase_1", "intento": 1, "resultado": "ok",
                "checks": [{"id": "designer_sync", "resultado": "fallo", "severidad": "error",
                            "detalle": "control sin declarar"}]}
        errores = contracts.validate_checks_result(malo)
        self.assertTrue(any("resultado" in e for e in errores))

    def test_un_warning_no_vuelve_fallido_el_agregado(self):
        bueno = {"fase_id": "fase_1", "intento": 1, "resultado": "ok",
                 "checks": [{"id": "no_es6", "resultado": "fallo", "severidad": "warning",
                             "detalle": "arrow function"}]}
        self.assertEqual(contracts.validate_checks_result(bueno), [])

    def test_error_check_no_vuelve_fallido_el_agregado(self):
        bueno = {"fase_id": "fase_1", "intento": 1, "resultado": "ok",
                 "checks": [{"id": "sp_params", "resultado": "error_check",
                             "severidad": "error", "detalle": "Traceback..."}]}
        self.assertEqual(contracts.validate_checks_result(bueno), [])


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Correr las pruebas para verificar que fallan**

Run: `python -m unittest tests.test_contracts -v`
Expected: FAIL con `ImportError: cannot import name 'contracts'`.

- [ ] **Step 3: Implementar el módulo**

Crear `harness/hooks/lib/contracts.py`:

```python
"""Validación de los cinco contratos JSON del harness.

Escrito a mano y sin dependencias: el entorno no tiene jsonschema y el
harness no instala nada. Cada validate_* devuelve una lista de mensajes de
error en español; lista vacía significa dato válido.
"""
from __future__ import annotations

import re
from pathlib import PurePosixPath  # noqa: F401  (reservado para futuras validaciones de ref)

ESTADOS_FASE = frozenset({
    "pendiente", "en_ejecucion", "en_verificacion",
    "esperando_humano", "en_correccion", "aprobada", "escalado",
})
CONFIANZAS = frozenset({"verificado", "por_confirmar"})
ORIGENES = frozenset({"check", "esceptico", "humano"})
SEVERIDADES = frozenset({"error", "warning"})
RESULTADOS_CHECK = frozenset({"ok", "fallo", "error_check"})
RESULTADOS_PRUEBA = frozenset({"ok", "fallo", "pendiente", "na"})

RE_FECHA = re.compile(r"^\d{2}-\d{2}-\d{4}$")
RE_FASE_ID = re.compile(r"^fase_\d+$")


def _texto(data: dict, campo: str, errores: list[str], prefijo: str = "") -> None:
    valor = data.get(campo)
    if not isinstance(valor, str) or not valor.strip():
        errores.append(f"{prefijo}{campo}: requerido, string no vacío")


def _lista(data: dict, campo: str, errores: list[str], prefijo: str = "",
           permite_vacia: bool = True) -> None:
    valor = data.get(campo)
    if not isinstance(valor, list):
        errores.append(f"{prefijo}{campo}: requerido, lista")
    elif not permite_vacia and not valor:
        errores.append(f"{prefijo}{campo}: no puede estar vacía")


def validate_ticket_context(data: dict) -> list[str]:
    errores: list[str] = []
    for campo in ("ticket_id", "nroticket", "desarrollador", "fecha", "perfil"):
        _texto(data, campo, errores)
    fecha = data.get("fecha")
    if isinstance(fecha, str) and not RE_FECHA.match(fecha):
        errores.append("fecha: formato esperado DD-MM-YYYY")
    return errores


def resolve_check_names(nombres: list[str], rules: dict) -> tuple[list[str], list[str]]:
    """Expande grupos a checks individuales. Devuelve (resueltos, desconocidos)."""
    grupos = rules.get("grupos") or {}
    individuales = {r["id"] for r in rules.get("prohibido", []) if isinstance(r, dict) and "id" in r}
    individuales.update(rules.get("checks_estructurales") or [])
    if (rules.get("audit_comments") or {}).get("requerido") is not None:
        individuales.add("audit_comments")
    if rules.get("no_new_deps") is not None:
        individuales.add("no_new_deps")

    resueltos: list[str] = []
    desconocidos: list[str] = []
    for nombre in nombres:
        if nombre in grupos:
            resueltos.extend(grupos[nombre])
        elif nombre in individuales:
            resueltos.append(nombre)
        else:
            desconocidos.append(nombre)
    return resueltos, desconocidos


def validate_plan(data: dict, rules: dict | None = None) -> list[str]:
    errores: list[str] = []
    for campo in ("ticket_id", "perfil"):
        _texto(data, campo, errores)
    fases = data.get("fases")
    if not isinstance(fases, list) or not fases:
        errores.append("fases: requerido, lista no vacía")
        return errores

    ids = [f.get("id") for f in fases if isinstance(f, dict)]
    for indice, fase in enumerate(fases):
        prefijo = f"fases[{indice}]."
        if not isinstance(fase, dict):
            errores.append(f"fases[{indice}]: debe ser objeto")
            continue
        _texto(fase, "id", errores, prefijo)
        if isinstance(fase.get("id"), str) and not RE_FASE_ID.match(fase["id"]):
            errores.append(f"{prefijo}id: formato esperado fase_N")
        _texto(fase, "titulo", errores, prefijo)
        _texto(fase, "criterio_exito", errores, prefijo)
        _lista(fase, "pasos", errores, prefijo, permite_vacia=False)
        _lista(fase, "anclajes", errores, prefijo)
        _lista(fase, "checks_deterministas", errores, prefijo)
        _lista(fase, "herramientas_permitidas", errores, prefijo, permite_vacia=False)
        _lista(fase, "depende_de", errores, prefijo)

        for j, ancla in enumerate(fase.get("anclajes") or []):
            if not isinstance(ancla, dict):
                errores.append(f"{prefijo}anclajes[{j}]: debe ser objeto")
                continue
            _texto(ancla, "ref", errores, f"{prefijo}anclajes[{j}].")
            if ancla.get("confianza") not in CONFIANZAS:
                errores.append(f"{prefijo}anclajes[{j}].confianza: "
                               f"esperado uno de {sorted(CONFIANZAS)}")

        prueba = fase.get("prueba_manual")
        if not isinstance(prueba, dict) or not isinstance(prueba.get("requerida"), bool):
            errores.append(f"{prefijo}prueba_manual.requerida: requerido, booleano")

        maximo = fase.get("max_reintentos")
        if not isinstance(maximo, int) or isinstance(maximo, bool) or not 1 <= maximo <= 10:
            errores.append(f"{prefijo}max_reintentos: entero entre 1 y 10")

        for dependencia in fase.get("depende_de") or []:
            if dependencia not in ids:
                errores.append(f"{prefijo}depende_de: '{dependencia}' no es una fase del plan")

        if rules is not None:
            _, desconocidos = resolve_check_names(
                [c for c in (fase.get("checks_deterministas") or []) if isinstance(c, str)], rules)
            for nombre in desconocidos:
                errores.append(f"{prefijo}checks_deterministas: '{nombre}' no existe "
                               f"como check ni como grupo en rules.json")
    return errores


def validate_checks_result(data: dict) -> list[str]:
    errores: list[str] = []
    _texto(data, "fase_id", errores)
    if not isinstance(data.get("intento"), int) or isinstance(data.get("intento"), bool):
        errores.append("intento: requerido, entero")
    checks = data.get("checks")
    if not isinstance(checks, list):
        errores.append("checks: requerido, lista")
        return errores

    for indice, check in enumerate(checks):
        prefijo = f"checks[{indice}]."
        if not isinstance(check, dict):
            errores.append(f"checks[{indice}]: debe ser objeto")
            continue
        _texto(check, "id", errores, prefijo)
        if check.get("resultado") not in RESULTADOS_CHECK:
            errores.append(f"{prefijo}resultado: esperado uno de {sorted(RESULTADOS_CHECK)}")
        if check.get("resultado") != "ok":
            if check.get("severidad") not in SEVERIDADES:
                errores.append(f"{prefijo}severidad: esperado uno de {sorted(SEVERIDADES)}")
            _texto(check, "detalle", errores, prefijo)

    bloqueantes = [c for c in checks if isinstance(c, dict)
                   and c.get("resultado") == "fallo" and c.get("severidad") == "error"]
    esperado = "fallo" if bloqueantes else "ok"
    if data.get("resultado") != esperado:
        errores.append(f"resultado: se esperaba '{esperado}' — un check con severidad "
                       f"'error' y resultado 'fallo' obliga a 'fallo'; los 'warning' y "
                       f"'error_check' no bloquean")
    return errores


def validate_veredicto(data: dict) -> list[str]:
    errores: list[str] = []
    _texto(data, "fase_id", errores)
    if not isinstance(data.get("intento"), int) or isinstance(data.get("intento"), bool):
        errores.append("intento: requerido, entero")
    if not isinstance(data.get("aprobado"), bool):
        errores.append("aprobado: requerido, booleano")

    juicio = data.get("juicio_esceptico")
    if not isinstance(juicio, dict):
        errores.append("juicio_esceptico: requerido, objeto")
        return errores
    if not isinstance(juicio.get("aprobado"), bool):
        errores.append("juicio_esceptico.aprobado: requerido, booleano")
    for campo in ("razones_rechazo", "claims_sin_evidencia", "anclajes_sin_resolver"):
        _lista(juicio, campo, errores, "juicio_esceptico.")
    if juicio.get("aprobado") is False and not (juicio.get("razones_rechazo") or []):
        errores.append("juicio_esceptico.razones_rechazo: un rechazo exige al menos una razón")

    prueba = data.get("prueba_manual")
    if not isinstance(prueba, dict):
        errores.append("prueba_manual: requerido, objeto")
        return errores
    if not isinstance(prueba.get("requerida"), bool):
        errores.append("prueba_manual.requerida: requerido, booleano")
    if prueba.get("resultado") not in RESULTADOS_PRUEBA:
        errores.append(f"prueba_manual.resultado: esperado uno de {sorted(RESULTADOS_PRUEBA)}")

    prueba_ok = (prueba.get("resultado") == "ok") or (prueba.get("requerida") is False)
    if data.get("aprobado") is True and not (juicio.get("aprobado") and prueba_ok):
        errores.append("aprobado: no puede ser true si el escéptico rechazó o si la "
                       "prueba manual requerida no resultó 'ok'")
    return errores


def validate_fase_state(data: dict) -> list[str]:
    errores: list[str] = []
    _texto(data, "fase_id", errores)
    if data.get("estado") not in ESTADOS_FASE:
        errores.append(f"estado: esperado uno de {sorted(ESTADOS_FASE)}")

    intento = data.get("intento_actual")
    maximo = data.get("max_reintentos")
    for campo, valor in (("intento_actual", intento), ("max_reintentos", maximo)):
        if not isinstance(valor, int) or isinstance(valor, bool) or valor < 1:
            errores.append(f"{campo}: entero mayor o igual a 1")
    if isinstance(intento, int) and isinstance(maximo, int) and not isinstance(intento, bool):
        if intento > maximo:
            errores.append("intento_actual: no puede exceder max_reintentos "
                           "(al excederlo la fase pasa a 'escalado')")

    historial = data.get("historial_fallos")
    if not isinstance(historial, list):
        errores.append("historial_fallos: requerido, lista")
        return errores
    for indice, fallo in enumerate(historial):
        prefijo = f"historial_fallos[{indice}]."
        if not isinstance(fallo, dict):
            errores.append(f"historial_fallos[{indice}]: debe ser objeto")
            continue
        if not isinstance(fallo.get("intento"), int) or isinstance(fallo.get("intento"), bool):
            errores.append(f"{prefijo}intento: requerido, entero")
        if fallo.get("origen") not in ORIGENES:
            errores.append(f"{prefijo}origen: esperado uno de {sorted(ORIGENES)}")
        _texto(fallo, "razon", errores, prefijo)
    return errores
```

- [ ] **Step 4: Correr las pruebas para verificar que pasan**

Run: `python -m unittest tests.test_contracts -v`
Expected: PASS, 22 pruebas.

- [ ] **Step 5: Commit**

```bash
git add harness/hooks/lib/contracts.py tests/test_contracts.py
git commit -m "feat(lib): validadores de los cinco contratos JSON, sin dependencias"
```

---

### Task 4: `lib/gitdiff.py` — líneas agregadas

Sin esto, validar `[B]/[E]` sobre el archivo completo daría miles de falsos positivos en un repo legacy. La unidad de verificación es el cambio, no el archivo.

**Files:**
- Create: `harness/hooks/lib/gitdiff.py`
- Test: `tests/test_gitdiff.py`

**Interfaces:**
- Consumes: nada.
- Produces:
  - `added_lines(project_root: Path, file_path: Path) -> list[tuple[int, str]] | None` — pares `(nro_linea_en_el_archivo_nuevo, texto)`. `None` si el directorio no es un repo git o git falla (el llamador debe tratarlo como `error_check`, no como violación).
  - `compress_line_numbers(numeros: list[int]) -> str` — `[3,4,5,9]` → `"3-5, 9"`, para mensajes legibles.

- [ ] **Step 1: Escribir las pruebas que fallan**

Crear `tests/test_gitdiff.py`:

```python
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "harness" / "hooks"))
from lib import gitdiff  # noqa: E402


def _git(root: Path, *args: str) -> None:
    subprocess.run(["git", *args], cwd=root, check=True,
                   capture_output=True, text=True)


class TestAddedLines(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        _git(self.root, "init")
        _git(self.root, "config", "user.email", "t@t.t")
        _git(self.root, "config", "user.name", "t")
        self.archivo = self.root / "frmReviewReport.aspx.vb"
        self.archivo.write_text("Linea1\nLinea2\nLinea3\n", encoding="utf-8")
        _git(self.root, "add", ".")
        _git(self.root, "commit", "-m", "base")

    def tearDown(self):
        self.tmp.cleanup()

    def test_sin_cambios_devuelve_lista_vacia(self):
        self.assertEqual(gitdiff.added_lines(self.root, self.archivo), [])

    def test_detecta_una_linea_insertada_con_su_numero_nuevo(self):
        self.archivo.write_text("Linea1\nNUEVA\nLinea2\nLinea3\n", encoding="utf-8")
        self.assertEqual(gitdiff.added_lines(self.root, self.archivo), [(2, "NUEVA")])

    def test_detecta_cambios_ya_agregados_al_index(self):
        self.archivo.write_text("Linea1\nNUEVA\nLinea2\nLinea3\n", encoding="utf-8")
        _git(self.root, "add", ".")
        self.assertEqual(gitdiff.added_lines(self.root, self.archivo), [(2, "NUEVA")])

    def test_un_archivo_nuevo_sin_rastrear_cuenta_completo(self):
        nuevo = self.root / "frmNuevo.js"
        nuevo.write_text("var a = 1;\nvar b = 2;\n", encoding="utf-8")
        self.assertEqual(gitdiff.added_lines(self.root, nuevo),
                         [(1, "var a = 1;"), (2, "var b = 2;")])

    def test_devuelve_none_si_no_es_un_repo_git(self):
        with tempfile.TemporaryDirectory() as sin_git:
            raiz = Path(sin_git)
            suelto = raiz / "x.vb"
            suelto.write_text("algo\n", encoding="utf-8")
            self.assertIsNone(gitdiff.added_lines(raiz, suelto))


class TestCompresionDeNumeros(unittest.TestCase):
    def test_agrupa_rangos_contiguos(self):
        self.assertEqual(gitdiff.compress_line_numbers([3, 4, 5, 9]), "3-5, 9")

    def test_numero_suelto(self):
        self.assertEqual(gitdiff.compress_line_numbers([7]), "7")

    def test_lista_vacia(self):
        self.assertEqual(gitdiff.compress_line_numbers([]), "")


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Correr las pruebas para verificar que fallan**

Run: `python -m unittest tests.test_gitdiff -v`
Expected: FAIL con `ImportError: cannot import name 'gitdiff'`.

- [ ] **Step 3: Implementar el módulo**

Crear `harness/hooks/lib/gitdiff.py`:

```python
"""Extracción de las líneas agregadas de un archivo respecto a HEAD.

La unidad de verificación del harness es el cambio, no el archivo: validar
un archivo legacy completo produciría miles de falsos positivos.
"""
from __future__ import annotations

import re
import subprocess
from pathlib import Path

RE_HUNK = re.compile(r"^@@ -\d+(?:,\d+)? \+(?P<inicio>\d+)(?:,(?P<cuenta>\d+))? @@")


def _git(project_root: Path, *args: str) -> subprocess.CompletedProcess | None:
    try:
        return subprocess.run(["git", *args], cwd=str(project_root), capture_output=True,
                              text=True, encoding="utf-8", errors="replace")
    except (OSError, ValueError):
        return None


def _leer_texto(path: Path) -> str:
    return path.read_text(encoding="utf-8", errors="replace")


def added_lines(project_root: Path, file_path: Path) -> list[tuple[int, str]] | None:
    """Líneas agregadas respecto a HEAD, incluyendo lo que ya está en el index.

    Devuelve None si no hay git usable: el llamador debe registrarlo como
    error_check y no como violación de una regla.
    """
    raiz = Path(project_root).resolve()
    archivo = Path(file_path).resolve()
    try:
        relativo = archivo.relative_to(raiz).as_posix()
    except ValueError:
        return None

    dentro = _git(raiz, "rev-parse", "--is-inside-work-tree")
    if dentro is None or dentro.returncode != 0 or dentro.stdout.strip() != "true":
        return None

    estado = _git(raiz, "status", "--porcelain", "--", relativo)
    if estado is not None and estado.returncode == 0 and estado.stdout.startswith("??"):
        return [(i, linea) for i, linea in enumerate(_leer_texto(archivo).splitlines(), start=1)]

    diff = _git(raiz, "diff", "HEAD", "--unified=0", "--no-color", "--", relativo)
    if diff is None or diff.returncode != 0:
        return None

    agregadas: list[tuple[int, str]] = []
    linea_actual = 0
    for linea in diff.stdout.splitlines():
        encabezado = RE_HUNK.match(linea)
        if encabezado:
            linea_actual = int(encabezado.group("inicio"))
            continue
        if linea.startswith("+") and not linea.startswith("+++"):
            agregadas.append((linea_actual, linea[1:]))
            linea_actual += 1
    return agregadas


def compress_line_numbers(numeros: list[int]) -> str:
    """[3,4,5,9] -> '3-5, 9'."""
    if not numeros:
        return ""
    ordenados = sorted(set(numeros))
    tramos: list[str] = []
    inicio = previo = ordenados[0]
    for numero in ordenados[1:]:
        if numero == previo + 1:
            previo = numero
            continue
        tramos.append(str(inicio) if inicio == previo else f"{inicio}-{previo}")
        inicio = previo = numero
    tramos.append(str(inicio) if inicio == previo else f"{inicio}-{previo}")
    return ", ".join(tramos)
```

- [ ] **Step 4: Correr las pruebas para verificar que pasan**

Run: `python -m unittest tests.test_gitdiff -v`
Expected: PASS, 8 pruebas.

- [ ] **Step 5: Commit**

```bash
git add harness/hooks/lib/gitdiff.py tests/test_gitdiff.py
git commit -m "feat(lib): extracción de líneas agregadas vía git diff"
```

---

### Task 5: `profiles/reviewsystemgfs/rules.json`

**Files:**
- Create: `profiles/reviewsystemgfs/rules.json`
- Test: `tests/test_rules_perfil.py`

**Interfaces:**
- Consumes: `contracts.resolve_check_names` (Task 3).
- Produces: el archivo `rules.json` del perfil, con los ids `audit_comments`, `no_new_deps`, `no_async`, `no_fetch`, `no_raw_sql`, `no_orm`, `no_es6`, `no_fw_moderno`, los estructurales `designer_sync`/`sp_params`/`xhtml_selfclose`, y los grupos `fw35_syntax`/`ie11_syntax`.

- [ ] **Step 1: Escribir la prueba que falla**

Crear `tests/test_rules_perfil.py`:

```python
import json
import re
import sys
import unittest
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ / "harness" / "hooks"))
from lib import contracts  # noqa: E402

RULES_PATH = RAIZ / "profiles" / "reviewsystemgfs" / "rules.json"


class TestRulesDelPerfil(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.rules = json.loads(RULES_PATH.read_text(encoding="utf-8"))

    def test_todos_los_patrones_compilan(self):
        for regla in self.rules["prohibido"]:
            with self.subTest(regla=regla["id"]):
                re.compile(regla["patron"])

    def test_audit_comments_y_no_new_deps_son_error(self):
        self.assertEqual(self.rules["audit_comments"]["severidad"], "error")
        self.assertEqual(self.rules["no_new_deps"]["severidad"], "error")

    def test_los_grupos_solo_referencian_checks_existentes(self):
        for grupo, miembros in self.rules["grupos"].items():
            with self.subTest(grupo=grupo):
                _, desconocidos = contracts.resolve_check_names(miembros, self.rules)
                self.assertEqual(desconocidos, [])

    def test_cada_regla_prohibida_tiene_mensaje_util(self):
        for regla in self.rules["prohibido"]:
            with self.subTest(regla=regla["id"]):
                self.assertGreater(len(regla["mensaje"]), 15)

    def test_no_async_detecta_await_en_vb_y_no_marca_codigo_valido(self):
        regla = next(r for r in self.rules["prohibido"] if r["id"] == "no_async")
        rx = re.compile(regla["patron"])
        self.assertTrue(rx.search("Dim x = Await LlamarApi()"))
        self.assertIsNone(rx.search("Dim awaited As String = \"ok\""))

    def test_no_raw_sql_detecta_select_inline_y_no_marca_ejecutarsp(self):
        regla = next(r for r in self.rules["prohibido"] if r["id"] == "no_raw_sql")
        rx = re.compile(regla["patron"])
        self.assertTrue(rx.search('Dim cmd As New SqlCommand("SELECT * FROM ReviewHeader")'))
        self.assertIsNone(rx.search('objRet = lConsulta.EjecutarSp("ReviewGetFilters", 4, p)'))

    def test_no_fetch_detecta_fetch_y_no_marca_consultardatos(self):
        regla = next(r for r in self.rules["prohibido"] if r["id"] == "no_fetch")
        rx = re.compile(regla["patron"])
        self.assertTrue(rx.search("fetch('/api/x')"))
        self.assertIsNone(rx.search("Azzule.ConsultarDatos({ url: 'x.aspx' })"))


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Correr la prueba para verificar que falla**

Run: `python -m unittest tests.test_rules_perfil -v`
Expected: FAIL con `FileNotFoundError` sobre `profiles/reviewsystemgfs/rules.json`.

- [ ] **Step 3: Crear el archivo de reglas**

Crear `profiles/reviewsystemgfs/rules.json`:

```json
{
  "perfil": "reviewsystemgfs",
  "audit_comments": {
    "requerido": true,
    "severidad": "error",
    "aplica_a": [".vb", ".js", ".sql", ".aspx"],
    "fecha_formato": "DD-MM-YYYY",
    "valores_desde": "ticket_context.json"
  },
  "prohibido": [
    { "id": "no_async", "archivos": [".vb"], "severidad": "error",
      "patron": "\\b(Async|Await)\\s",
      "mensaje": "El .NET Framework 3.5 no soporta async/await: usar llamadas síncronas o HttpWebRequest bloqueante" },
    { "id": "no_orm", "archivos": [".vb"], "severidad": "error",
      "patron": "(DbContext|EntityFramework|LinqToSql|\\.AsQueryable\\()",
      "mensaje": "Prohibido ORM en este proyecto: acceso directo con SqlConnection/SqlCommand vía EjecutarSp()" },
    { "id": "no_raw_sql", "archivos": [".vb"], "severidad": "error",
      "patron": "SqlCommand\\(\\s*\"\\s*(SELECT|INSERT|UPDATE|DELETE)",
      "mensaje": "El acceso a datos va por Global_asax.InstanciarConsulta() + EjecutarSp(), no con SQL embebido" },
    { "id": "no_fetch", "archivos": [".js"], "severidad": "error",
      "patron": "\\bfetch\\s*\\(",
      "mensaje": "IE11 no soporta fetch: usar Azzule.ConsultarDatos() o __doPostBack()" },
    { "id": "no_es6", "archivos": [".js"], "severidad": "warning",
      "patron": "(=>|\\b(let|const)\\s|\\bPromise\\b|`)",
      "mensaje": "jQuery 1.7.2 e IE11: preferir var, function y concatenación de cadenas" },
    { "id": "no_fw_moderno", "archivos": [".vb"], "severidad": "warning",
      "patron": "(IsNullOrWhiteSpace|\\bTuple\\b|\\bdynamic\\b)",
      "mensaje": "No disponible en el Framework 3.5: usar el equivalente de la época" }
  ],
  "no_new_deps": {
    "severidad": "error",
    "vigilar": ["ReviewSystem.vbproj", "Web.config", "packages.config"],
    "patron": "(<Reference\\s+Include=|<package\\s+id=|HintPath|\\.dll)",
    "mensaje": "Ninguna Reference, DLL o paquete nuevo sin aprobación humana explícita"
  },
  "checks_estructurales": ["designer_sync", "sp_params", "xhtml_selfclose"],
  "grupos": {
    "fw35_syntax": ["no_async", "no_orm", "no_raw_sql", "no_fw_moderno"],
    "ie11_syntax": ["no_fetch", "no_es6"]
  }
}
```

- [ ] **Step 4: Correr la prueba para verificar que pasa**

Run: `python -m unittest tests.test_rules_perfil -v`
Expected: PASS, 7 pruebas.

- [ ] **Step 5: Commit**

```bash
git add profiles/reviewsystemgfs/rules.json tests/test_rules_perfil.py
git commit -m "feat(perfil): reglas declarativas del stack legacy de ReviewSystemGFS"
```

---

### Task 6: `lib/checks.py` — motor de checks

**Files:**
- Create: `harness/hooks/lib/checks.py`
- Test: `tests/test_checks.py`

**Interfaces:**
- Consumes: `gitdiff.added_lines`, `gitdiff.compress_line_numbers` (Task 4); `contracts.resolve_check_names` (Task 3).
- Produces:
  - `Finding = dict` con claves `id`, `resultado` (`"fallo"` | `"error_check"`), `severidad`, `detalle`.
  - `audit_regions(lines: list[str]) -> tuple[list[tuple[int, int, dict]], list[tuple[int, dict]]]` → `(regiones_cerradas, marcadores_sin_cerrar)`; cada región es `(linea_inicio, linea_fin, metadatos)` y los metadatos traen `ticket`, `dev`, `fecha`.
  - `check_audit_comments(rel_path, texto_nuevo, agregadas, ctx, cfg) -> list[Finding]`
  - `check_prohibited(rel_path, agregadas, rules) -> list[Finding]`
  - `check_no_new_deps(rel_path, agregadas, rules) -> list[Finding]`
  - `run_file_checks(project_root, file_path, rules, ctx, solo: list[str] | None = None) -> list[Finding]`

- [ ] **Step 1: Escribir las pruebas que fallan**

Crear `tests/test_checks.py`:

```python
import sys
import unittest
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ / "harness" / "hooks"))
from lib import checks  # noqa: E402

CTX = {"ticket_id": "ISR-110722", "nroticket": "110722",
       "desarrollador": "OMAR RODRIGUEZ", "fecha": "28-07-2026",
       "perfil": "reviewsystemgfs"}
CFG = {"requerido": True, "severidad": "error", "aplica_a": [".vb", ".js", ".sql", ".aspx"]}

VB_CORRECTO = """Public Class Reporte
    '--[B] ISR 110722 OMAR RODRIGUEZ 28-07-2026
    Private Sub Guardar()
        Dim x As Integer = 1
    End Sub
    '--[E] ISR 110722 OMAR RODRIGUEZ 28-07-2026
End Class
"""


class TestRegionesDeAuditoria(unittest.TestCase):
    def test_reconoce_una_region_con_sus_metadatos(self):
        regiones, sin_cerrar = checks.audit_regions(VB_CORRECTO.splitlines())
        self.assertEqual(len(regiones), 1)
        self.assertEqual(sin_cerrar, [])
        inicio, fin, meta = regiones[0]
        self.assertEqual((inicio, fin), (2, 6))
        self.assertEqual(meta["ticket"], "110722")
        self.assertEqual(meta["dev"], "OMAR RODRIGUEZ")
        self.assertEqual(meta["fecha"], "28-07-2026")

    def test_reconoce_el_formato_de_javascript(self):
        regiones, _ = checks.audit_regions([
            "//--[B] ISR 110722 OMAR RODRIGUEZ 28-07-2026",
            "var total = 1;",
            "//--[E] ISR 110722 OMAR RODRIGUEZ 28-07-2026"])
        self.assertEqual(len(regiones), 1)

    def test_reconoce_el_formato_de_aspx(self):
        regiones, _ = checks.audit_regions([
            "<%--[B] ISR 110722 OMAR RODRIGUEZ 28-07-2026--%>",
            "<asp:HiddenField ID=\"hdnX\" runat=\"server\" />",
            "<%--[E] ISR 110722 OMAR RODRIGUEZ 28-07-2026--%>"])
        self.assertEqual(len(regiones), 1)

    def test_detecta_un_bloque_abierto_sin_cerrar(self):
        regiones, sin_cerrar = checks.audit_regions([
            "'--[B] ISR 110722 OMAR RODRIGUEZ 28-07-2026", "Dim x = 1"])
        self.assertEqual(regiones, [])
        self.assertEqual(len(sin_cerrar), 1)


class TestCheckAuditComments(unittest.TestCase):
    def test_lineas_dentro_de_un_bloque_correcto_no_producen_hallazgos(self):
        agregadas = [(2, ""), (3, ""), (4, ""), (5, ""), (6, "")]
        self.assertEqual(
            checks.check_audit_comments("x.aspx.vb", VB_CORRECTO, agregadas, CTX, CFG), [])

    def test_una_linea_agregada_fuera_de_todo_bloque_es_error(self):
        texto = VB_CORRECTO + "    Dim suelta As Integer = 9\n"
        hallazgos = checks.check_audit_comments("x.aspx.vb", texto, [(8, "    Dim suelta")], CTX, CFG)
        self.assertEqual(len(hallazgos), 1)
        self.assertEqual(hallazgos[0]["severidad"], "error")
        self.assertIn("8", hallazgos[0]["detalle"])

    def test_ticket_que_no_coincide_con_el_contexto_es_error(self):
        texto = VB_CORRECTO.replace("110722", "999999")
        hallazgos = checks.check_audit_comments("x.aspx.vb", texto, [(3, "")], CTX, CFG)
        self.assertTrue(any("999999" in h["detalle"] for h in hallazgos))

    def test_no_juzga_bloques_de_tickets_viejos_que_no_toco(self):
        texto = ("'--[B] ISR 100001 JUAN PEREZ 01-01-2020\n"
                 "Dim viejo As Integer = 1\n"
                 "'--[E] ISR 100001 JUAN PEREZ 01-01-2020\n"
                 + VB_CORRECTO)
        agregadas = [(5, ""), (6, "")]
        self.assertEqual(
            checks.check_audit_comments("x.aspx.vb", texto, agregadas, CTX, CFG), [])

    def test_fecha_distinta_a_la_del_contexto_es_error(self):
        texto = VB_CORRECTO.replace("28-07-2026", "01-01-2026")
        hallazgos = checks.check_audit_comments("x.aspx.vb", texto, [(3, "")], CTX, CFG)
        self.assertTrue(any("01-01-2026" in h["detalle"] for h in hallazgos))

    def test_sin_lineas_agregadas_no_hay_nada_que_juzgar(self):
        self.assertEqual(checks.check_audit_comments("x.aspx.vb", VB_CORRECTO, [], CTX, CFG), [])


class TestCheckProhibited(unittest.TestCase):
    def setUp(self):
        self.rules = {"prohibido": [
            {"id": "no_async", "archivos": [".vb"], "severidad": "error",
             "patron": r"\b(Async|Await)\s", "mensaje": "FW 3.5 no soporta async/await"},
            {"id": "no_fetch", "archivos": [".js"], "severidad": "error",
             "patron": r"\bfetch\s*\(", "mensaje": "IE11 no soporta fetch"}]}

    def test_detecta_la_violacion_solo_en_la_extension_declarada(self):
        hallazgos = checks.check_prohibited("frm.aspx.vb", [(10, "Dim x = Await Api()")], self.rules)
        self.assertEqual([h["id"] for h in hallazgos], ["no_async"])

    def test_no_aplica_reglas_de_vb_a_un_archivo_js(self):
        self.assertEqual(checks.check_prohibited("frm.js", [(10, "Await algo ")], self.rules), [])

    def test_el_detalle_incluye_archivo_linea_y_mensaje(self):
        hallazgos = checks.check_prohibited("frm.js", [(4, "fetch('/x')")], self.rules)
        self.assertIn("frm.js:4", hallazgos[0]["detalle"])
        self.assertIn("IE11", hallazgos[0]["detalle"])


class TestCheckNoNewDeps(unittest.TestCase):
    def setUp(self):
        self.rules = {"no_new_deps": {
            "severidad": "error", "vigilar": ["ReviewSystem.vbproj", "Web.config"],
            "patron": r"(<Reference\s+Include=|<package\s+id=|HintPath|\.dll)",
            "mensaje": "Ninguna dependencia nueva sin aprobación humana"}}

    def test_una_referencia_agregada_al_vbproj_es_error(self):
        hallazgos = checks.check_no_new_deps(
            "ReviewSystem.vbproj", [(40, '<Reference Include="Dapper" />')], self.rules)
        self.assertEqual(len(hallazgos), 1)
        self.assertEqual(hallazgos[0]["severidad"], "error")

    def test_ignora_archivos_que_no_estan_vigilados(self):
        self.assertEqual(checks.check_no_new_deps(
            "frm.aspx.vb", [(1, '<Reference Include="Dapper" />')], self.rules), [])

    def test_un_cambio_inocuo_en_un_archivo_vigilado_no_es_error(self):
        self.assertEqual(checks.check_no_new_deps(
            "Web.config", [(12, '<add key="Proyecto" value="Review System" />')], self.rules), [])


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Correr las pruebas para verificar que fallan**

Run: `python -m unittest tests.test_checks -v`
Expected: FAIL con `ImportError: cannot import name 'checks'`.

- [ ] **Step 3: Implementar el motor**

Crear `harness/hooks/lib/checks.py`:

```python
"""Motor genérico de checks: aplica un rules.json a un archivo modificado.

Este módulo no conoce ningún lenguaje concreto. Lo único que sabe es leer
reglas declarativas y aplicarlas a las líneas agregadas. Los checks que
requieren entender un stack (designer_sync, sp_params) son plugins del
perfil y viven en profiles/<perfil>/checks/.
"""
from __future__ import annotations

import re
import traceback
from pathlib import Path

from . import gitdiff

# Cubre los cuatro formatos del proyecto: '--[B], //--[B], --[B] y <%--[B].
RE_MARCADOR = re.compile(
    r"--\s*\[(?P<tipo>[BE])\]\s*ISR\s+(?P<ticket>\S+)\s+(?P<dev>.+?)\s+"
    r"(?P<fecha>\d{2}-\d{2}-\d{4})")


def _hallazgo(check_id: str, severidad: str, detalle: str,
              resultado: str = "fallo") -> dict:
    return {"id": check_id, "resultado": resultado,
            "severidad": severidad, "detalle": detalle}


def audit_regions(lines: list[str]):
    """Regiones [B]...[E] de un archivo y los [B] que quedaron sin cerrar."""
    pila: list[tuple[int, dict]] = []
    regiones: list[tuple[int, int, dict]] = []
    for numero, linea in enumerate(lines, start=1):
        encontrado = RE_MARCADOR.search(linea)
        if not encontrado:
            continue
        datos = encontrado.groupdict()
        if datos["tipo"] == "B":
            pila.append((numero, datos))
        elif pila:
            inicio, meta = pila.pop()
            regiones.append((inicio, numero, meta))
    return regiones, pila


def check_audit_comments(rel_path: str, texto_nuevo: str,
                         agregadas: list[tuple[int, str]],
                         ctx: dict, cfg: dict) -> list[dict]:
    """Verifica que todo lo agregado viva en un bloque [B]/[E] de ESTE ticket."""
    if not agregadas or not cfg.get("requerido"):
        return []
    aplica_a = [e.lower() for e in cfg.get("aplica_a") or []]
    if aplica_a and not any(rel_path.lower().endswith(e) for e in aplica_a):
        return []

    severidad = cfg.get("severidad", "error")
    hallazgos: list[dict] = []
    lineas = texto_nuevo.splitlines()
    regiones, sin_cerrar = audit_regions(lineas)
    numeros_agregados = {numero for numero, _ in agregadas}

    for numero, _ in sin_cerrar:
        hallazgos.append(_hallazgo("audit_comments", severidad,
                                   f"{rel_path}:{numero} marcador [B] sin su [E] de cierre"))

    cubiertas: set[int] = set()
    for inicio, fin, meta in regiones:
        rango = set(range(inicio, fin + 1))
        cubiertas |= rango
        if not (rango & numeros_agregados):
            continue  # bloque de un ticket anterior que esta tarea no tocó
        if meta["ticket"] != ctx["nroticket"]:
            hallazgos.append(_hallazgo(
                "audit_comments", severidad,
                f"{rel_path}:{inicio} el bloque declara el ticket {meta['ticket']} "
                f"pero el ticket activo es {ctx['nroticket']}"))
        if meta["dev"].strip().upper() != ctx["desarrollador"].strip().upper():
            hallazgos.append(_hallazgo(
                "audit_comments", severidad,
                f"{rel_path}:{inicio} el bloque declara al desarrollador "
                f"'{meta['dev'].strip()}' pero el contexto dice '{ctx['desarrollador']}'"))
        if meta["fecha"] != ctx["fecha"]:
            hallazgos.append(_hallazgo(
                "audit_comments", severidad,
                f"{rel_path}:{inicio} el bloque declara la fecha {meta['fecha']} "
                f"pero el ticket activo usa {ctx['fecha']}"))

    huerfanas = sorted(numeros_agregados - cubiertas)
    if huerfanas:
        hallazgos.append(_hallazgo(
            "audit_comments", severidad,
            f"{rel_path}: líneas agregadas fuera de un bloque [B]/[E]: "
            f"{gitdiff.compress_line_numbers(huerfanas)}"))
    return hallazgos


def check_prohibited(rel_path: str, agregadas: list[tuple[int, str]],
                     rules: dict) -> list[dict]:
    extension = Path(rel_path).suffix.lower()
    hallazgos: list[dict] = []
    for regla in rules.get("prohibido") or []:
        if extension not in [e.lower() for e in regla.get("archivos") or []]:
            continue
        try:
            patron = re.compile(regla["patron"])
        except re.error as error:
            hallazgos.append(_hallazgo(regla.get("id", "?"), "error",
                                       f"patrón inválido en rules.json: {error}",
                                       resultado="error_check"))
            continue
        for numero, texto in agregadas:
            if patron.search(texto):
                hallazgos.append(_hallazgo(
                    regla["id"], regla.get("severidad", "warning"),
                    f"{rel_path}:{numero} {regla.get('mensaje', 'regla violada')}"))
    return hallazgos


def check_no_new_deps(rel_path: str, agregadas: list[tuple[int, str]],
                      rules: dict) -> list[dict]:
    cfg = rules.get("no_new_deps")
    if not cfg:
        return []
    vigilados = [v.lower() for v in cfg.get("vigilar") or []]
    if Path(rel_path).name.lower() not in vigilados:
        return []
    try:
        patron = re.compile(cfg["patron"])
    except re.error as error:
        return [_hallazgo("no_new_deps", "error",
                          f"patrón inválido en rules.json: {error}", resultado="error_check")]
    hallazgos: list[dict] = []
    for numero, texto in agregadas:
        if patron.search(texto):
            hallazgos.append(_hallazgo(
                "no_new_deps", cfg.get("severidad", "error"),
                f"{rel_path}:{numero} {cfg.get('mensaje', 'dependencia nueva detectada')}"))
    return hallazgos


def run_file_checks(project_root: Path, file_path: Path, rules: dict,
                    ctx: dict | None, solo: list[str] | None = None) -> list[dict]:
    """Corre los checks declarativos sobre un archivo. `solo` los filtra por id."""
    raiz = Path(project_root)
    archivo = Path(file_path)
    try:
        relativo = archivo.resolve().relative_to(raiz.resolve()).as_posix()
    except ValueError:
        return []

    agregadas = gitdiff.added_lines(raiz, archivo)
    if agregadas is None:
        return [_hallazgo("git_diff", "error",
                          f"{relativo}: no se pudo obtener el diff (¿repo git?); "
                          f"los checks basados en el cambio quedaron sin correr",
                          resultado="error_check")]
    if not agregadas:
        return []

    def habilitado(check_id: str) -> bool:
        return solo is None or check_id in solo

    hallazgos: list[dict] = []
    try:
        if habilitado("audit_comments") and ctx:
            hallazgos += check_audit_comments(
                relativo, archivo.read_text(encoding="utf-8", errors="replace"),
                agregadas, ctx, rules.get("audit_comments") or {})
        if habilitado("no_new_deps"):
            hallazgos += check_no_new_deps(relativo, agregadas, rules)
        prohibidos = [r for r in (rules.get("prohibido") or []) if habilitado(r.get("id", ""))]
        if prohibidos:
            hallazgos += check_prohibited(relativo, agregadas, {"prohibido": prohibidos})
    except Exception:  # un bug del harness no debe parecer un bug del código
        hallazgos.append(_hallazgo("motor_de_checks", "error",
                                   traceback.format_exc(), resultado="error_check"))
    return hallazgos
```

- [ ] **Step 4: Correr las pruebas para verificar que pasan**

Run: `python -m unittest tests.test_checks -v`
Expected: PASS, 16 pruebas.

- [ ] **Step 5: Correr la suite completa**

Run: `python -m unittest discover -s tests -v`
Expected: PASS, 53 pruebas en total.

- [ ] **Step 6: Commit**

```bash
git add harness/hooks/lib/checks.py tests/test_checks.py
git commit -m "feat(lib): motor de checks declarativos sobre líneas agregadas"
```

---

### Task 7: `lib/state.py` — máquina de estados de fase

Aquí vive la decisión D5 del spec: los contadores son aritmética, no juicio. Ninguna otra parte del harness escribe `intento_actual`.

**Files:**
- Create: `harness/hooks/lib/state.py`
- Test: `tests/test_state.py`

**Interfaces:**
- Consumes: `harness.read_json/write_json/fase_dir/intento_dir` (Task 2), `contracts.validate_fase_state` (Task 3).
- Produces:
  - `abrir_fase(project_root, ticket_id, fase, ) -> dict` — crea `fase_state.json` en `intento 1`, estado `en_ejecucion`. `fase` es el dict de la fase tomado de `plan.json`. Idempotente: si ya existe, lo devuelve sin tocar.
  - `leer_fase(project_root, ticket_id, fase_id) -> dict | None`
  - `set_estado(project_root, ticket_id, fase_id, estado: str) -> dict`
  - `registrar_fallo(project_root, ticket_id, fase_id, origen: str, razon: str, correccion: str = "") -> dict` — agrega al `historial_fallos`, incrementa `intento_actual` y pasa a `en_correccion`; si el incremento excedería `max_reintentos`, deja el contador en el máximo y pone `escalado`.
  - `aprobar_fase(project_root, ticket_id, fase_id) -> dict`
  - Excepción `TransicionInvalida(Exception)`.

- [ ] **Step 1: Escribir las pruebas que fallan**

Crear `tests/test_state.py`:

```python
import sys
import tempfile
import unittest
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ / "harness" / "hooks"))
from lib import contracts, state  # noqa: E402

FASE = {"id": "fase_1", "titulo": "Agregar campo", "max_reintentos": 3,
        "prueba_manual": {"requerida": True}}


class TestMaquinaDeEstados(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def abrir(self):
        return state.abrir_fase(self.root, "ISR-110722", FASE)

    def test_abrir_fase_arranca_en_intento_1_y_en_ejecucion(self):
        estado = self.abrir()
        self.assertEqual(estado["intento_actual"], 1)
        self.assertEqual(estado["estado"], "en_ejecucion")
        self.assertEqual(estado["max_reintentos"], 3)
        self.assertEqual(estado["historial_fallos"], [])
        self.assertEqual(contracts.validate_fase_state(estado), [])

    def test_abrir_fase_es_idempotente(self):
        self.abrir()
        state.registrar_fallo(self.root, "ISR-110722", "fase_1", "check", "designer_sync falló")
        estado = self.abrir()
        self.assertEqual(estado["intento_actual"], 2)

    def test_registrar_fallo_incrementa_el_intento_y_deja_en_correccion(self):
        self.abrir()
        estado = state.registrar_fallo(self.root, "ISR-110722", "fase_1",
                                       "check", "designer_sync falló")
        self.assertEqual(estado["intento_actual"], 2)
        self.assertEqual(estado["estado"], "en_correccion")
        self.assertEqual(estado["historial_fallos"][0]["origen"], "check")
        self.assertEqual(estado["historial_fallos"][0]["intento"], 1)

    def test_al_agotar_los_reintentos_escala_y_no_pasa_del_maximo(self):
        self.abrir()
        for i in range(3):
            estado = state.registrar_fallo(self.root, "ISR-110722", "fase_1",
                                           "esceptico", f"rechazo {i}")
        self.assertEqual(estado["estado"], "escalado")
        self.assertEqual(estado["intento_actual"], 3)
        self.assertEqual(len(estado["historial_fallos"]), 3)
        self.assertEqual(contracts.validate_fase_state(estado), [])

    def test_una_fase_escalada_no_acepta_mas_fallos(self):
        self.abrir()
        for i in range(3):
            state.registrar_fallo(self.root, "ISR-110722", "fase_1", "check", f"x{i}")
        with self.assertRaises(state.TransicionInvalida):
            state.registrar_fallo(self.root, "ISR-110722", "fase_1", "check", "uno más")

    def test_registrar_fallo_guarda_el_origen_humano(self):
        self.abrir()
        estado = state.registrar_fallo(self.root, "ISR-110722", "fase_1", "humano",
                                       "falló en el paso 3: el campo volvió vacío")
        self.assertEqual(estado["historial_fallos"][0]["origen"], "humano")

    def test_rechaza_un_origen_desconocido(self):
        self.abrir()
        with self.assertRaises(state.TransicionInvalida):
            state.registrar_fallo(self.root, "ISR-110722", "fase_1", "intuicion", "porque sí")

    def test_aprobar_fase_deja_estado_aprobada(self):
        self.abrir()
        estado = state.aprobar_fase(self.root, "ISR-110722", "fase_1")
        self.assertEqual(estado["estado"], "aprobada")

    def test_no_se_puede_aprobar_una_fase_escalada(self):
        self.abrir()
        for i in range(3):
            state.registrar_fallo(self.root, "ISR-110722", "fase_1", "check", f"x{i}")
        with self.assertRaises(state.TransicionInvalida):
            state.aprobar_fase(self.root, "ISR-110722", "fase_1")

    def test_set_estado_rechaza_un_estado_fuera_del_contrato(self):
        self.abrir()
        with self.assertRaises(state.TransicionInvalida):
            state.set_estado(self.root, "ISR-110722", "fase_1", "meditando")

    def test_leer_fase_devuelve_none_si_no_existe(self):
        self.assertIsNone(state.leer_fase(self.root, "ISR-110722", "fase_9"))


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Correr las pruebas para verificar que fallan**

Run: `python -m unittest tests.test_state -v`
Expected: FAIL con `ImportError: cannot import name 'state'`.

- [ ] **Step 3: Implementar el módulo**

Crear `harness/hooks/lib/state.py`:

```python
"""Máquina de estados de fase: transiciones, contador y memoria de fallos.

Decisión D5 del spec: los contadores son aritmética, no juicio. Este módulo
es el único lugar del harness que escribe intento_actual.
"""
from __future__ import annotations

from pathlib import Path

from . import contracts, harness


class TransicionInvalida(Exception):
    """Se intentó una transición que el contrato no permite."""


TERMINALES = frozenset({"aprobada", "escalado"})


def _ruta_estado(project_root: Path, ticket_id: str, fase_id: str) -> Path:
    return harness.fase_dir(project_root, ticket_id, fase_id) / "fase_state.json"


def leer_fase(project_root: Path, ticket_id: str, fase_id: str) -> dict | None:
    ruta = _ruta_estado(project_root, ticket_id, fase_id)
    return harness.read_json(ruta) if ruta.is_file() else None


def _guardar(project_root: Path, ticket_id: str, estado: dict) -> dict:
    errores = contracts.validate_fase_state(estado)
    if errores:
        raise TransicionInvalida("estado de fase inválido: " + "; ".join(errores))
    harness.write_json(_ruta_estado(project_root, ticket_id, estado["fase_id"]), estado)
    return estado


def abrir_fase(project_root: Path, ticket_id: str, fase: dict) -> dict:
    """Crea el estado inicial de la fase. Idempotente."""
    existente = leer_fase(project_root, ticket_id, fase["id"])
    if existente is not None:
        return existente
    estado = {
        "fase_id": fase["id"],
        "estado": "en_ejecucion",
        "intento_actual": 1,
        "max_reintentos": int(fase.get("max_reintentos", 3)),
        "historial_fallos": [],
    }
    return _guardar(project_root, ticket_id, estado)


def set_estado(project_root: Path, ticket_id: str, fase_id: str, nuevo: str) -> dict:
    estado = leer_fase(project_root, ticket_id, fase_id)
    if estado is None:
        raise TransicionInvalida(f"la fase {fase_id} no está abierta")
    if nuevo not in contracts.ESTADOS_FASE:
        raise TransicionInvalida(f"estado desconocido: {nuevo}")
    estado["estado"] = nuevo
    return _guardar(project_root, ticket_id, estado)


def registrar_fallo(project_root: Path, ticket_id: str, fase_id: str, origen: str,
                    razon: str, correccion: str = "") -> dict:
    """Suma el fallo al historial, incrementa el intento y escala si se agotó."""
    if origen not in contracts.ORIGENES:
        raise TransicionInvalida(f"origen de fallo desconocido: {origen}")
    estado = leer_fase(project_root, ticket_id, fase_id)
    if estado is None:
        raise TransicionInvalida(f"la fase {fase_id} no está abierta")
    if estado["estado"] in TERMINALES:
        raise TransicionInvalida(
            f"la fase {fase_id} ya está en estado terminal '{estado['estado']}'")

    estado["historial_fallos"].append({
        "intento": estado["intento_actual"],
        "origen": origen,
        "razon": razon,
        "correccion_aplicada": correccion,
    })
    if estado["intento_actual"] >= estado["max_reintentos"]:
        estado["estado"] = "escalado"
    else:
        estado["intento_actual"] += 1
        estado["estado"] = "en_correccion"
    return _guardar(project_root, ticket_id, estado)


def aprobar_fase(project_root: Path, ticket_id: str, fase_id: str) -> dict:
    estado = leer_fase(project_root, ticket_id, fase_id)
    if estado is None:
        raise TransicionInvalida(f"la fase {fase_id} no está abierta")
    if estado["estado"] == "escalado":
        raise TransicionInvalida(
            f"la fase {fase_id} está escalada: requiere intervención humana explícita")
    estado["estado"] = "aprobada"
    return _guardar(project_root, ticket_id, estado)
```

- [ ] **Step 4: Correr las pruebas para verificar que pasan**

Run: `python -m unittest tests.test_state -v`
Expected: PASS, 11 pruebas.

- [ ] **Step 5: Commit**

```bash
git add harness/hooks/lib/state.py tests/test_state.py
git commit -m "feat(lib): máquina de estados de fase con contador y memoria de fallos"
```

---

### Task 8: `cli.py` — `open-ticket` y `open-fase`

**Files:**
- Create: `harness/hooks/cli.py`
- Test: `tests/test_cli_apertura.py`

**Interfaces:**
- Consumes: `harness`, `contracts`, `state` (Tasks 2, 3, 7).
- Produces:
  - CLI: `python cli.py open-ticket --project <ruta> --ticket-id ISR-110722 --nroticket 110722 --desarrollador "OMAR RODRIGUEZ" --fecha 28-07-2026 --perfil reviewsystemgfs`
  - CLI: `python cli.py open-fase --project <ruta> --fase fase_1`
  - CLI: `python cli.py validate --project <ruta> --contrato plan --archivo <ruta.json>`
  - Funciones reutilizables: `cmd_open_ticket(args) -> int`, `cmd_open_fase(args) -> int`, `cmd_validate(args) -> int`, `resolver_proyecto(valor: str | None) -> Path`
  - Convención de salida: código 0 = éxito; 1 = error de uso o de contrato, con el detalle en stderr.

- [ ] **Step 1: Escribir las pruebas que fallan**

Crear `tests/test_cli_apertura.py`:

```python
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
CLI = RAIZ / "harness" / "hooks" / "cli.py"
sys.path.insert(0, str(RAIZ / "harness" / "hooks"))
from lib import harness  # noqa: E402

PLAN = {
    "ticket_id": "ISR-110722", "perfil": "reviewsystemgfs",
    "generado_por": "task-planner-v3",
    "fases": [{
        "id": "fase_1", "titulo": "Agregar campo", "pasos": ["uno"],
        "anclajes": [{"ref": "frm.aspx.vb:412", "confianza": "verificado"}],
        "criterio_exito": "se guarda y se relee",
        "checks_deterministas": ["audit_comments"],
        "prueba_manual": {"requerida": True, "url": "frm.aspx", "datos": "review 4471"},
        "herramientas_permitidas": ["read", "edit"], "max_reintentos": 3, "depende_de": []}]}


def correr(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run([sys.executable, str(CLI), *args],
                          capture_output=True, text=True, encoding="utf-8")


class TestAperturaDeTicketYFase(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        (self.root / ".claude").mkdir()
        (self.root / ".claude" / "rules.json").write_text(
            json.dumps({"perfil": "reviewsystemgfs",
                        "audit_comments": {"requerido": True, "severidad": "error"}}),
            encoding="utf-8")

    def tearDown(self):
        self.tmp.cleanup()

    def abrir_ticket(self):
        return correr("open-ticket", "--project", str(self.root),
                      "--ticket-id", "ISR-110722", "--nroticket", "110722",
                      "--desarrollador", "OMAR RODRIGUEZ", "--fecha", "28-07-2026",
                      "--perfil", "reviewsystemgfs")

    def test_open_ticket_crea_contexto_y_puntero(self):
        resultado = self.abrir_ticket()
        self.assertEqual(resultado.returncode, 0, resultado.stderr)
        ctx = harness.read_json(
            harness.ticket_dir(self.root, "ISR-110722") / "ticket_context.json")
        self.assertEqual(ctx["nroticket"], "110722")
        self.assertEqual(harness.read_current(self.root)["ticket_id"], "ISR-110722")

    def test_open_ticket_rechaza_una_fecha_en_formato_iso(self):
        resultado = correr("open-ticket", "--project", str(self.root),
                           "--ticket-id", "ISR-1", "--nroticket", "1",
                           "--desarrollador", "OMAR RODRIGUEZ", "--fecha", "2026-07-28",
                           "--perfil", "reviewsystemgfs")
        self.assertEqual(resultado.returncode, 1)
        self.assertIn("DD-MM-YYYY", resultado.stderr)

    def test_open_fase_exige_un_plan_valido(self):
        self.abrir_ticket()
        resultado = correr("open-fase", "--project", str(self.root), "--fase", "fase_1")
        self.assertEqual(resultado.returncode, 1)
        self.assertIn("plan.json", resultado.stderr)

    def test_open_fase_crea_el_estado_y_actualiza_el_puntero(self):
        self.abrir_ticket()
        harness.write_json(
            harness.ticket_dir(self.root, "ISR-110722") / "plan.json", PLAN)
        resultado = correr("open-fase", "--project", str(self.root), "--fase", "fase_1")
        self.assertEqual(resultado.returncode, 0, resultado.stderr)
        estado = harness.read_json(
            harness.fase_dir(self.root, "ISR-110722", "fase_1") / "fase_state.json")
        self.assertEqual(estado["intento_actual"], 1)
        self.assertEqual(harness.read_current(self.root)["fase_id"], "fase_1")

    def test_open_fase_rechaza_una_fase_inexistente_en_el_plan(self):
        self.abrir_ticket()
        harness.write_json(
            harness.ticket_dir(self.root, "ISR-110722") / "plan.json", PLAN)
        resultado = correr("open-fase", "--project", str(self.root), "--fase", "fase_7")
        self.assertEqual(resultado.returncode, 1)
        self.assertIn("fase_7", resultado.stderr)

    def test_open_fase_bloquea_si_una_dependencia_no_esta_aprobada(self):
        self.abrir_ticket()
        plan = json.loads(json.dumps(PLAN))
        plan["fases"].append({
            "id": "fase_2", "titulo": "Depende de la 1", "pasos": ["uno"], "anclajes": [],
            "criterio_exito": "x", "checks_deterministas": ["audit_comments"],
            "prueba_manual": {"requerida": False},
            "herramientas_permitidas": ["read"], "max_reintentos": 3,
            "depende_de": ["fase_1"]})
        harness.write_json(harness.ticket_dir(self.root, "ISR-110722") / "plan.json", plan)
        resultado = correr("open-fase", "--project", str(self.root), "--fase", "fase_2")
        self.assertEqual(resultado.returncode, 1)
        self.assertIn("fase_1", resultado.stderr)

    def test_validate_reporta_los_errores_del_contrato(self):
        malo = self.root / "plan_malo.json"
        malo.write_text(json.dumps({"ticket_id": "ISR-1", "perfil": "x", "fases": []}),
                        encoding="utf-8")
        resultado = correr("validate", "--project", str(self.root),
                           "--contrato", "plan", "--archivo", str(malo))
        self.assertEqual(resultado.returncode, 1)
        self.assertIn("fases", resultado.stderr)


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Correr las pruebas para verificar que fallan**

Run: `python -m unittest tests.test_cli_apertura -v`
Expected: FAIL — `cli.py` no existe, `returncode` 2 con "can't open file".

- [ ] **Step 3: Implementar el CLI**

Crear `harness/hooks/cli.py`:

```python
#!/usr/bin/env python3
"""Único punto de mutación del estado del harness.

Todo lo que cambie un contador, un estado o un archivo de estado pasa por
aquí. El modelo invoca estos subcomandos; no escribe el estado a mano.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from lib import contracts, harness, state  # noqa: E402

VALIDADORES = {
    "ticket_context": contracts.validate_ticket_context,
    "plan": contracts.validate_plan,
    "checks": contracts.validate_checks_result,
    "veredicto": contracts.validate_veredicto,
    "fase_state": contracts.validate_fase_state,
}


def _error(mensaje: str) -> int:
    sys.stderr.write(f"HARNESS · {mensaje}\n")
    return 1


def resolver_proyecto(valor: str | None) -> Path:
    """Raíz del proyecto: la indicada, o la deducida del directorio actual."""
    base = Path(valor) if valor else Path.cwd()
    raiz = harness.find_project_root(base)
    return raiz if raiz is not None else base.resolve()


def _leer_ticket_activo(raiz: Path) -> tuple[str, dict] | None:
    actual = harness.read_current(raiz)
    if not actual or not actual.get("ticket_id"):
        return None
    ruta = harness.ticket_dir(raiz, actual["ticket_id"]) / "ticket_context.json"
    if not ruta.is_file():
        return None
    return actual["ticket_id"], harness.read_json(ruta)


def cmd_open_ticket(args) -> int:
    raiz = resolver_proyecto(args.project)
    ctx = {
        "ticket_id": args.ticket_id,
        "nroticket": args.nroticket,
        "desarrollador": args.desarrollador,
        "fecha": args.fecha,
        "perfil": args.perfil,
    }
    errores = contracts.validate_ticket_context(ctx)
    if errores:
        return _error("ticket_context inválido: " + "; ".join(errores))

    carpeta = harness.ticket_dir(raiz, args.ticket_id)
    harness.write_json(carpeta / "ticket_context.json", ctx)
    if not (carpeta / "ticket_state.json").is_file():
        harness.write_json(carpeta / "ticket_state.json",
                           {"ticket_id": args.ticket_id, "fase_actual": None,
                            "fases_aprobadas": []})
    harness.write_current(raiz, args.ticket_id, None)
    print(f"Ticket {args.ticket_id} abierto en {carpeta}")
    return 0


def cmd_open_fase(args) -> int:
    raiz = resolver_proyecto(args.project)
    activo = _leer_ticket_activo(raiz)
    if activo is None:
        return _error("no hay ticket activo: corre primero 'open-ticket'")
    ticket_id, _ = activo

    ruta_plan = harness.ticket_dir(raiz, ticket_id) / "plan.json"
    if not ruta_plan.is_file():
        return _error(f"falta {ruta_plan}: el planner debe emitir plan.json "
                      f"antes de abrir una fase")
    plan = harness.read_json(ruta_plan)
    reglas = harness.load_rules(raiz) if harness.find_project_root(raiz) else None
    errores = contracts.validate_plan(plan, reglas)
    if errores:
        return _error("plan.json inválido: " + "; ".join(errores))

    fase = next((f for f in plan["fases"] if f["id"] == args.fase), None)
    if fase is None:
        return _error(f"la fase '{args.fase}' no existe en plan.json")

    for dependencia in fase.get("depende_de") or []:
        previo = state.leer_fase(raiz, ticket_id, dependencia)
        if previo is None or previo["estado"] != "aprobada":
            actual = previo["estado"] if previo else "sin abrir"
            return _error(f"la fase '{args.fase}' depende de '{dependencia}', "
                          f"que está en estado '{actual}' y no 'aprobada'")

    estado = state.abrir_fase(raiz, ticket_id, fase)
    harness.write_current(raiz, ticket_id, fase["id"])
    print(f"Fase {fase['id']} en estado '{estado['estado']}', "
          f"intento {estado['intento_actual']}/{estado['max_reintentos']}")
    return 0


def cmd_validate(args) -> int:
    validador = VALIDADORES[args.contrato]
    datos = harness.read_json(Path(args.archivo))
    if args.contrato == "plan":
        raiz = resolver_proyecto(args.project)
        reglas = harness.load_rules(raiz) if harness.find_project_root(raiz) else None
        errores = validador(datos, reglas)
    else:
        errores = validador(datos)
    if errores:
        return _error(f"{args.contrato} inválido: " + "; ".join(errores))
    print(f"{args.contrato}: válido")
    return 0


def construir_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="harness-cli", description=__doc__)
    sub = parser.add_subparsers(dest="comando", required=True)

    p = sub.add_parser("open-ticket", help="Abre un ticket y fija el contexto")
    p.add_argument("--project")
    p.add_argument("--ticket-id", required=True)
    p.add_argument("--nroticket", required=True)
    p.add_argument("--desarrollador", required=True)
    p.add_argument("--fecha", required=True, help="DD-MM-YYYY")
    p.add_argument("--perfil", required=True)
    p.set_defaults(func=cmd_open_ticket)

    p = sub.add_parser("open-fase", help="Abre una fase del plan activo")
    p.add_argument("--project")
    p.add_argument("--fase", required=True)
    p.set_defaults(func=cmd_open_fase)

    p = sub.add_parser("validate", help="Valida un archivo contra su contrato")
    p.add_argument("--project")
    p.add_argument("--contrato", required=True, choices=sorted(VALIDADORES))
    p.add_argument("--archivo", required=True)
    p.set_defaults(func=cmd_validate)

    return parser


def main(argv: list[str] | None = None) -> int:
    args = construir_parser().parse_args(argv)
    try:
        return args.func(args)
    except state.TransicionInvalida as error:
        return _error(str(error))
    except (OSError, ValueError) as error:
        return _error(f"{type(error).__name__}: {error}")


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 4: Correr las pruebas para verificar que pasan**

Run: `python -m unittest tests.test_cli_apertura -v`
Expected: PASS, 7 pruebas.

- [ ] **Step 5: Commit**

```bash
git add harness/hooks/cli.py tests/test_cli_apertura.py
git commit -m "feat(cli): apertura de ticket y de fase con validación de contratos"
```

---

### Task 9: `check_rules.py` — hook `PostToolUse`

**Files:**
- Create: `harness/hooks/check_rules.py`
- Test: `tests/test_hook_check_rules.py`
- Read first: `docs/hook-payloads.md` (Task 1) — usar los nombres de campo **observados**, no los asumidos aquí.

**Interfaces:**
- Consumes: `harness.find_project_root/load_rules/read_current/is_harness_source` (Tasks 2, 2b), `checks.run_file_checks` (Task 6).
- Produces: un ejecutable de hook. Contrato de salida: **exit 2 + stderr** cuando hay al menos un hallazgo de severidad `error` (así Claude Code devuelve el texto al modelo); **exit 0 y sin salida** en cualquier otro caso. Los `warning` no se emiten aquí — aparecen en `checks.json` (Task 10) —, porque en exit 0 el stderr no llega al modelo y un aviso invisible es peor que ninguno.

- [ ] **Step 1: Escribir las pruebas que fallan**

Crear `tests/test_hook_check_rules.py`:

```python
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
HOOK = RAIZ / "harness" / "hooks" / "check_rules.py"
sys.path.insert(0, str(RAIZ / "harness" / "hooks"))
from lib import harness  # noqa: E402

REGLAS = {
    "perfil": "reviewsystemgfs",
    "audit_comments": {"requerido": True, "severidad": "error",
                       "aplica_a": [".vb", ".js", ".sql", ".aspx"]},
    "prohibido": [{"id": "no_fetch", "archivos": [".js"], "severidad": "error",
                   "patron": r"\bfetch\s*\(", "mensaje": "IE11 no soporta fetch"},
                  {"id": "no_es6", "archivos": [".js"], "severidad": "warning",
                   "patron": r"=>", "mensaje": "preferir function"}],
}


def _git(root: Path, *args: str) -> None:
    subprocess.run(["git", *args], cwd=root, check=True, capture_output=True, text=True)


def lanzar(payload: dict) -> subprocess.CompletedProcess:
    return subprocess.run([sys.executable, str(HOOK)], input=json.dumps(payload),
                          capture_output=True, text=True, encoding="utf-8")


class TestHookCheckRules(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        (self.root / ".claude").mkdir()
        harness.write_json(self.root / ".claude" / "rules.json", REGLAS)
        _git(self.root, "init")
        _git(self.root, "config", "user.email", "t@t.t")
        _git(self.root, "config", "user.name", "t")
        (self.root / "frm.js").write_text("var a = 1;\n", encoding="utf-8")
        _git(self.root, "add", ".")
        _git(self.root, "commit", "-m", "base")
        harness.write_current(self.root, "ISR-110722", "fase_1")
        harness.write_json(
            harness.ticket_dir(self.root, "ISR-110722") / "ticket_context.json",
            {"ticket_id": "ISR-110722", "nroticket": "110722",
             "desarrollador": "OMAR RODRIGUEZ", "fecha": "28-07-2026",
             "perfil": "reviewsystemgfs"})

    def tearDown(self):
        self.tmp.cleanup()

    def payload(self, archivo: Path) -> dict:
        return {"hook_event_name": "PostToolUse", "tool_name": "Edit",
                "cwd": str(self.root), "tool_input": {"file_path": str(archivo)}}

    def test_bloquea_una_linea_sin_bloque_de_auditoria(self):
        (self.root / "frm.js").write_text("var a = 1;\nvar b = 2;\n", encoding="utf-8")
        resultado = lanzar(self.payload(self.root / "frm.js"))
        self.assertEqual(resultado.returncode, 2)
        self.assertIn("audit_comments", resultado.stderr)

    def test_no_bloquea_un_cambio_correctamente_comentado(self):
        (self.root / "frm.js").write_text(
            "var a = 1;\n"
            "//--[B] ISR 110722 OMAR RODRIGUEZ 28-07-2026\n"
            "var b = 2;\n"
            "//--[E] ISR 110722 OMAR RODRIGUEZ 28-07-2026\n", encoding="utf-8")
        resultado = lanzar(self.payload(self.root / "frm.js"))
        self.assertEqual(resultado.returncode, 0, resultado.stderr)
        self.assertEqual(resultado.stderr.strip(), "")

    def test_bloquea_fetch_aunque_este_bien_comentado(self):
        (self.root / "frm.js").write_text(
            "var a = 1;\n"
            "//--[B] ISR 110722 OMAR RODRIGUEZ 28-07-2026\n"
            "fetch('/api/x');\n"
            "//--[E] ISR 110722 OMAR RODRIGUEZ 28-07-2026\n", encoding="utf-8")
        resultado = lanzar(self.payload(self.root / "frm.js"))
        self.assertEqual(resultado.returncode, 2)
        self.assertIn("no_fetch", resultado.stderr)

    def test_un_warning_no_bloquea_y_no_ensucia_la_salida(self):
        (self.root / "frm.js").write_text(
            "var a = 1;\n"
            "//--[B] ISR 110722 OMAR RODRIGUEZ 28-07-2026\n"
            "var f = function(x) { return x; }; // sin arrow\n"
            "var g = (x) => x;\n"
            "//--[E] ISR 110722 OMAR RODRIGUEZ 28-07-2026\n", encoding="utf-8")
        resultado = lanzar(self.payload(self.root / "frm.js"))
        self.assertEqual(resultado.returncode, 0, resultado.stderr)
        self.assertEqual(resultado.stderr.strip(), "")

    def test_es_inerte_en_un_proyecto_sin_perfil(self):
        with tempfile.TemporaryDirectory() as sin_perfil:
            otro = Path(sin_perfil)
            archivo = otro / "cualquiera.js"
            archivo.write_text("fetch('/x');\n", encoding="utf-8")
            resultado = lanzar({"hook_event_name": "PostToolUse", "tool_name": "Edit",
                                "cwd": str(otro),
                                "tool_input": {"file_path": str(archivo)}})
            self.assertEqual(resultado.returncode, 0)
            self.assertEqual(resultado.stdout.strip(), "")
            self.assertEqual(resultado.stderr.strip(), "")

    def test_sin_ticket_activo_no_juzga_los_comentarios_de_auditoria(self):
        harness.write_json(harness.current_pointer_path(self.root),
                           {"ticket_id": None, "fase_id": None})
        (self.root / "frm.js").write_text("var a = 1;\nvar b = 2;\n", encoding="utf-8")
        resultado = lanzar(self.payload(self.root / "frm.js"))
        self.assertEqual(resultado.returncode, 0, resultado.stderr)

    def test_un_payload_ilegible_no_rompe_nada(self):
        resultado = subprocess.run([sys.executable, str(HOOK)], input="esto no es json",
                                   capture_output=True, text=True, encoding="utf-8")
        self.assertEqual(resultado.returncode, 0)

    def test_ignora_una_herramienta_sin_archivo(self):
        resultado = lanzar({"hook_event_name": "PostToolUse", "tool_name": "Bash",
                            "cwd": str(self.root), "tool_input": {"command": "ls"}})
        self.assertEqual(resultado.returncode, 0)


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Correr las pruebas para verificar que fallan**

Run: `python -m unittest tests.test_hook_check_rules -v`
Expected: FAIL — `check_rules.py` no existe.

- [ ] **Step 3: Implementar el hook**

Crear `harness/hooks/check_rules.py`:

```python
#!/usr/bin/env python3
"""Hook PostToolUse: valida el archivo recién tocado contra rules.json.

Contrato de salida de Claude Code: exit 2 devuelve el stderr al modelo. En
cualquier otro caso salimos con 0 y en silencio — los warning se reportan
en checks.json, porque un aviso que el modelo no ve no sirve de nada.

Antes de modificar este archivo, revisar docs/hook-payloads.md: los nombres
de campo del payload están documentados a partir de una captura real.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from lib import checks, harness  # noqa: E402


def _contexto_activo(raiz: Path) -> dict | None:
    actual = harness.read_current(raiz)
    if not actual or not actual.get("ticket_id"):
        return None
    ruta = harness.ticket_dir(raiz, actual["ticket_id"]) / "ticket_context.json"
    return harness.read_json(ruta) if ruta.is_file() else None


def main() -> int:
    try:
        payload = json.load(sys.stdin)
    except (json.JSONDecodeError, UnicodeDecodeError):
        return 0
    if not isinstance(payload, dict):
        return 0

    entrada = payload.get("tool_input") or {}
    ruta_archivo = entrada.get("file_path")
    if not ruta_archivo:
        return 0

    origen = payload.get("cwd") or Path(ruta_archivo).parent
    raiz = harness.find_project_root(origen)
    if raiz is None or harness.is_harness_source(raiz):
        return 0

    try:
        reglas = harness.load_rules(raiz)
    except (OSError, json.JSONDecodeError) as error:
        sys.stderr.write(f"HARNESS · rules.json ilegible: {error}\n")
        return 2

    hallazgos = checks.run_file_checks(raiz, Path(ruta_archivo), reglas,
                                       _contexto_activo(raiz))
    errores = [h for h in hallazgos
               if h["severidad"] == "error" and h["resultado"] == "fallo"]
    if not errores:
        return 0

    lineas = ["HARNESS · reglas del proyecto violadas en el archivo que acabas de escribir:"]
    for hallazgo in errores:
        lineas.append(f"  - [{hallazgo['id']}] {hallazgo['detalle']}")
    lineas.append("Corrige esto ahora, antes de continuar. No cuenta como reintento "
                  "de la fase: es autocorrección.")
    sys.stderr.write("\n".join(lineas) + "\n")
    return 2


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 4: Correr las pruebas para verificar que pasan**

Run: `python -m unittest tests.test_hook_check_rules -v`
Expected: PASS, 8 pruebas.

- [ ] **Step 5: Commit**

```bash
git add harness/hooks/check_rules.py tests/test_hook_check_rules.py
git commit -m "feat(hooks): PostToolUse que bloquea violaciones de las reglas del perfil"
```

---

### Task 10: `cli.py run-checks` — agregación a `checks.json`

**Files:**
- Modify: `harness/hooks/cli.py` (añadir subcomando)
- Create: `harness/hooks/lib/plugins.py`
- Test: `tests/test_cli_run_checks.py`

**Interfaces:**
- Consumes: `checks.run_file_checks` (Task 6), `contracts.resolve_check_names` / `validate_checks_result` (Task 3), `state` (Task 7), `gitdiff` (Task 4).
- Produces:
  - CLI: `python cli.py run-checks --project <ruta>` — corre los checks de la fase activa sobre todos los archivos modificados y escribe `intento_N/checks.json`. Exit 0 si el agregado es `ok`, 1 si es `fallo`.
  - `plugins.cargar_checks_estructurales(project_root) -> dict[str, callable]` — importa dinámicamente cada `.py` de `<proyecto>/.claude/checks/`; cada módulo debe exponer `run(project_root, archivos_modificados, ctx) -> list[Finding]`. Un módulo que falle al importar produce un `error_check`, no una caída.
  - `archivos_modificados(project_root) -> list[Path]` en `gitdiff`.

- [ ] **Step 1: Escribir la prueba que falla para `archivos_modificados`**

Añadir a `tests/test_gitdiff.py`:

```python
class TestArchivosModificados(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        _git(self.root, "init")
        _git(self.root, "config", "user.email", "t@t.t")
        _git(self.root, "config", "user.name", "t")
        (self.root / "a.vb").write_text("uno\n", encoding="utf-8")
        _git(self.root, "add", ".")
        _git(self.root, "commit", "-m", "base")

    def tearDown(self):
        self.tmp.cleanup()

    def test_lista_modificados_y_sin_rastrear(self):
        (self.root / "a.vb").write_text("uno\ndos\n", encoding="utf-8")
        (self.root / "b.js").write_text("var x;\n", encoding="utf-8")
        nombres = sorted(p.name for p in gitdiff.archivos_modificados(self.root))
        self.assertEqual(nombres, ["a.vb", "b.js"])

    def test_sin_cambios_devuelve_lista_vacia(self):
        self.assertEqual(gitdiff.archivos_modificados(self.root), [])
```

- [ ] **Step 2: Correr para verificar que falla**

Run: `python -m unittest tests.test_gitdiff -v`
Expected: FAIL con `AttributeError: module 'lib.gitdiff' has no attribute 'archivos_modificados'`.

- [ ] **Step 3: Implementar `archivos_modificados`**

Añadir a `harness/hooks/lib/gitdiff.py`:

```python
def archivos_modificados(project_root: Path) -> list[Path]:
    """Archivos con cambios respecto a HEAD, incluidos los sin rastrear."""
    raiz = Path(project_root).resolve()
    estado = _git(raiz, "status", "--porcelain", "--untracked-files=all")
    if estado is None or estado.returncode != 0:
        return []
    rutas: list[Path] = []
    for linea in estado.stdout.splitlines():
        if len(linea) < 4:
            continue
        relativo = linea[3:].strip().strip('"')
        if " -> " in relativo:  # renombrado: interesa el destino
            relativo = relativo.split(" -> ", 1)[1]
        candidato = raiz / relativo
        if candidato.is_file():
            rutas.append(candidato)
    return rutas
```

- [ ] **Step 4: Correr para verificar que pasa**

Run: `python -m unittest tests.test_gitdiff -v`
Expected: PASS, 10 pruebas.

- [ ] **Step 5: Escribir la prueba que falla para `run-checks`**

Crear `tests/test_cli_run_checks.py`:

```python
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
CLI = RAIZ / "harness" / "hooks" / "cli.py"
sys.path.insert(0, str(RAIZ / "harness" / "hooks"))
from lib import harness  # noqa: E402

REGLAS = {
    "perfil": "reviewsystemgfs",
    "audit_comments": {"requerido": True, "severidad": "error",
                       "aplica_a": [".vb", ".js"]},
    "prohibido": [{"id": "no_fetch", "archivos": [".js"], "severidad": "error",
                   "patron": r"\bfetch\s*\(", "mensaje": "IE11 no soporta fetch"},
                  {"id": "no_es6", "archivos": [".js"], "severidad": "warning",
                   "patron": r"=>", "mensaje": "preferir function"}],
    "checks_estructurales": [],
    "grupos": {"ie11_syntax": ["no_fetch", "no_es6"]},
}

PLAN = {
    "ticket_id": "ISR-110722", "perfil": "reviewsystemgfs",
    "fases": [{"id": "fase_1", "titulo": "t", "pasos": ["p"], "anclajes": [],
               "criterio_exito": "c", "checks_deterministas": ["audit_comments", "ie11_syntax"],
               "prueba_manual": {"requerida": True}, "herramientas_permitidas": ["edit"],
               "max_reintentos": 3, "depende_de": []}]}


def _git(root: Path, *args: str) -> None:
    subprocess.run(["git", *args], cwd=root, check=True, capture_output=True, text=True)


def correr(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run([sys.executable, str(CLI), *args],
                          capture_output=True, text=True, encoding="utf-8")


class TestRunChecks(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        (self.root / ".claude").mkdir()
        harness.write_json(self.root / ".claude" / "rules.json", REGLAS)
        _git(self.root, "init")
        _git(self.root, "config", "user.email", "t@t.t")
        _git(self.root, "config", "user.name", "t")
        (self.root / "frm.js").write_text("var a = 1;\n", encoding="utf-8")
        _git(self.root, "add", ".")
        _git(self.root, "commit", "-m", "base")
        harness.write_json(harness.ticket_dir(self.root, "ISR-110722") / "plan.json", PLAN)
        correr("open-ticket", "--project", str(self.root), "--ticket-id", "ISR-110722",
               "--nroticket", "110722", "--desarrollador", "OMAR RODRIGUEZ",
               "--fecha", "28-07-2026", "--perfil", "reviewsystemgfs")
        correr("open-fase", "--project", str(self.root), "--fase", "fase_1")

    def tearDown(self):
        self.tmp.cleanup()

    def leer_checks(self) -> dict:
        return harness.read_json(
            harness.intento_dir(self.root, "ISR-110722", "fase_1", 1) / "checks.json")

    def test_un_error_deja_el_agregado_en_fallo_y_exit_1(self):
        (self.root / "frm.js").write_text("var a = 1;\nvar b = 2;\n", encoding="utf-8")
        resultado = correr("run-checks", "--project", str(self.root))
        self.assertEqual(resultado.returncode, 1)
        datos = self.leer_checks()
        self.assertEqual(datos["resultado"], "fallo")
        self.assertTrue(any(c["id"] == "audit_comments" for c in datos["checks"]))

    def test_solo_warnings_deja_el_agregado_en_ok_y_exit_0(self):
        (self.root / "frm.js").write_text(
            "var a = 1;\n"
            "//--[B] ISR 110722 OMAR RODRIGUEZ 28-07-2026\n"
            "var g = (x) => x;\n"
            "//--[E] ISR 110722 OMAR RODRIGUEZ 28-07-2026\n", encoding="utf-8")
        resultado = correr("run-checks", "--project", str(self.root))
        self.assertEqual(resultado.returncode, 0, resultado.stderr)
        datos = self.leer_checks()
        self.assertEqual(datos["resultado"], "ok")
        self.assertTrue(any(c["id"] == "no_es6" and c["severidad"] == "warning"
                            for c in datos["checks"]))

    def test_sin_cambios_el_agregado_es_ok(self):
        resultado = correr("run-checks", "--project", str(self.root))
        self.assertEqual(resultado.returncode, 0, resultado.stderr)
        self.assertEqual(self.leer_checks()["resultado"], "ok")

    def test_el_checks_json_cumple_su_contrato(self):
        (self.root / "frm.js").write_text("var a = 1;\nvar b = 2;\n", encoding="utf-8")
        correr("run-checks", "--project", str(self.root))
        ruta = harness.intento_dir(self.root, "ISR-110722", "fase_1", 1) / "checks.json"
        resultado = correr("validate", "--project", str(self.root),
                           "--contrato", "checks", "--archivo", str(ruta))
        self.assertEqual(resultado.returncode, 0, resultado.stderr)

    def test_un_check_estructural_que_crashea_produce_error_check_sin_bloquear(self):
        destino = self.root / ".claude" / "checks"
        destino.mkdir()
        (destino / "roto.py").write_text(
            "def run(project_root, archivos, ctx):\n"
            "    raise RuntimeError('bug del harness')\n", encoding="utf-8")
        reglas = dict(REGLAS, checks_estructurales=["roto"])
        harness.write_json(self.root / ".claude" / "rules.json", reglas)
        plan = json.loads(json.dumps(PLAN))
        plan["fases"][0]["checks_deterministas"] = ["roto"]
        harness.write_json(harness.ticket_dir(self.root, "ISR-110722") / "plan.json", plan)
        (self.root / "frm.js").write_text("var a = 1;\nvar b = 2;\n", encoding="utf-8")
        resultado = correr("run-checks", "--project", str(self.root))
        datos = self.leer_checks()
        self.assertTrue(any(c["resultado"] == "error_check" for c in datos["checks"]))
        self.assertEqual(datos["resultado"], "ok")
        self.assertEqual(resultado.returncode, 0, resultado.stderr)

    def test_un_check_estructural_valido_se_ejecuta(self):
        destino = self.root / ".claude" / "checks"
        destino.mkdir()
        (destino / "siempre_falla.py").write_text(
            "def run(project_root, archivos, ctx):\n"
            "    return [{'id': 'siempre_falla', 'resultado': 'fallo',\n"
            "             'severidad': 'error', 'detalle': 'falla a propósito'}]\n",
            encoding="utf-8")
        reglas = dict(REGLAS, checks_estructurales=["siempre_falla"])
        harness.write_json(self.root / ".claude" / "rules.json", reglas)
        plan = json.loads(json.dumps(PLAN))
        plan["fases"][0]["checks_deterministas"] = ["siempre_falla"]
        harness.write_json(harness.ticket_dir(self.root, "ISR-110722") / "plan.json", plan)
        (self.root / "frm.js").write_text("var a = 1;\nvar b = 2;\n", encoding="utf-8")
        resultado = correr("run-checks", "--project", str(self.root))
        self.assertEqual(resultado.returncode, 1)
        self.assertTrue(any(c["id"] == "siempre_falla" for c in self.leer_checks()["checks"]))


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 6: Correr para verificar que falla**

Run: `python -m unittest tests.test_cli_run_checks -v`
Expected: FAIL — `argument comando: invalid choice: 'run-checks'`.

- [ ] **Step 7: Implementar el cargador de plugins**

Crear `harness/hooks/lib/plugins.py`:

```python
"""Carga de los checks estructurales del perfil.

Los checks que necesitan entender un stack (Web Forms, SPs) viven en
<proyecto>/.claude/checks/*.py y se cargan dinámicamente. Cada módulo debe
exponer:  run(project_root, archivos_modificados, ctx) -> list[Finding]
"""
from __future__ import annotations

import importlib.util
import traceback
from pathlib import Path


def _cargar_modulo(ruta: Path):
    especificacion = importlib.util.spec_from_file_location(f"harness_check_{ruta.stem}", ruta)
    if especificacion is None or especificacion.loader is None:
        raise ImportError(f"no se pudo preparar el módulo {ruta}")
    modulo = importlib.util.module_from_spec(especificacion)
    especificacion.loader.exec_module(modulo)
    return modulo


def cargar_checks_estructurales(project_root: Path) -> dict[str, object]:
    """{id: callable run}. Los ids que fallen al cargar quedan como excepción."""
    carpeta = Path(project_root) / ".claude" / "checks"
    cargados: dict[str, object] = {}
    if not carpeta.is_dir():
        return cargados
    for ruta in sorted(carpeta.glob("*.py")):
        if ruta.name.startswith("_"):
            continue
        try:
            modulo = _cargar_modulo(ruta)
            funcion = getattr(modulo, "run", None)
            if not callable(funcion):
                raise AttributeError(f"{ruta.name} no expone una función run()")
            cargados[ruta.stem] = funcion
        except Exception:
            cargados[ruta.stem] = ImportError(traceback.format_exc())
    return cargados


def ejecutar(check_id: str, funcion, project_root: Path, archivos: list[Path],
             ctx: dict | None) -> list[dict]:
    """Corre un check estructural aislando sus fallos como error_check."""
    if isinstance(funcion, BaseException):
        return [{"id": check_id, "resultado": "error_check", "severidad": "error",
                 "detalle": f"no se pudo cargar el check: {funcion}"}]
    try:
        resultado = funcion(project_root, archivos, ctx)
        return list(resultado or [])
    except Exception:
        return [{"id": check_id, "resultado": "error_check", "severidad": "error",
                 "detalle": traceback.format_exc()}]
```

- [ ] **Step 8: Añadir el subcomando `run-checks` a `cli.py`**

Añadir el import `from lib import checks, gitdiff, plugins` a la cabecera de imports existente, y estas funciones antes de `construir_parser`:

```python
def _fase_activa(raiz: Path) -> tuple[str, dict, dict, dict] | None:
    """(ticket_id, ctx, fase_del_plan, fase_state) de la fase activa."""
    actual = harness.read_current(raiz)
    if not actual or not actual.get("ticket_id") or not actual.get("fase_id"):
        return None
    ticket_id, fase_id = actual["ticket_id"], actual["fase_id"]
    carpeta = harness.ticket_dir(raiz, ticket_id)
    if not (carpeta / "ticket_context.json").is_file() or not (carpeta / "plan.json").is_file():
        return None
    ctx = harness.read_json(carpeta / "ticket_context.json")
    plan = harness.read_json(carpeta / "plan.json")
    fase = next((f for f in plan["fases"] if f["id"] == fase_id), None)
    estado = state.leer_fase(raiz, ticket_id, fase_id)
    if fase is None or estado is None:
        return None
    return ticket_id, ctx, fase, estado


def cmd_run_checks(args) -> int:
    raiz = resolver_proyecto(args.project)
    activa = _fase_activa(raiz)
    if activa is None:
        return _error("no hay fase activa con plan y contexto: corre 'open-fase'")
    ticket_id, ctx, fase, estado = activa
    reglas = harness.load_rules(raiz)

    pedidos = [c for c in fase.get("checks_deterministas") or [] if isinstance(c, str)]
    resueltos, desconocidos = contracts.resolve_check_names(pedidos, reglas)
    hallazgos: list[dict] = []
    for nombre in desconocidos:
        hallazgos.append({"id": nombre, "resultado": "error_check", "severidad": "error",
                          "detalle": f"'{nombre}' no existe como check ni como grupo "
                                     f"en rules.json"})

    archivos = gitdiff.archivos_modificados(raiz)
    declarativos = [c for c in resueltos if c not in (reglas.get("checks_estructurales") or [])]
    for archivo in archivos:
        hallazgos += checks.run_file_checks(raiz, archivo, reglas, ctx, solo=declarativos)

    estructurales = plugins.cargar_checks_estructurales(raiz)
    for nombre in resueltos:
        if nombre in estructurales:
            hallazgos += plugins.ejecutar(nombre, estructurales[nombre], raiz, archivos, ctx)

    bloqueantes = [h for h in hallazgos
                   if h.get("resultado") == "fallo" and h.get("severidad") == "error"]
    resultado = {
        "fase_id": fase["id"],
        "intento": estado["intento_actual"],
        "resultado": "fallo" if bloqueantes else "ok",
        "checks": hallazgos if hallazgos else [{"id": "sin_hallazgos", "resultado": "ok"}],
    }
    errores_contrato = contracts.validate_checks_result(resultado)
    if errores_contrato:
        return _error("checks.json generado es inválido (bug del harness): "
                      + "; ".join(errores_contrato))

    destino = harness.intento_dir(raiz, ticket_id, fase["id"], estado["intento_actual"])
    harness.write_json(destino / "checks.json", resultado)
    print(f"checks: {resultado['resultado']} — {len(bloqueantes)} error(es) bloqueante(s), "
          f"{len(hallazgos) - len(bloqueantes)} no bloqueante(s) → {destino / 'checks.json'}")
    return 1 if bloqueantes else 0
```

Y registrar el subcomando dentro de `construir_parser`, antes del `return parser`:

```python
    p = sub.add_parser("run-checks", help="Corre los checks de la fase activa")
    p.add_argument("--project")
    p.set_defaults(func=cmd_run_checks)
```

- [ ] **Step 9: Correr las pruebas para verificar que pasan**

Run: `python -m unittest tests.test_cli_run_checks -v`
Expected: PASS, 6 pruebas.

- [ ] **Step 10: Correr la suite completa**

Run: `python -m unittest discover -s tests -v`
Expected: PASS, 84 pruebas.

- [ ] **Step 11: Commit**

```bash
git add harness/hooks/cli.py harness/hooks/lib/plugins.py harness/hooks/lib/gitdiff.py tests/
git commit -m "feat(cli): run-checks con agregación a checks.json y plugins del perfil"
```

---

### Task 11: `agents/skeptic.md` y `cli.py record-veredicto`

El escéptico actual (`agente-esceptico.md`) juzga ReviewSystemGFS contra reglas de otro proyecto. Aquí se reescribe: exige evidencia, no conoce ningún stack, y emite JSON.

**Files:**
- Create: `harness/agents/skeptic.md`
- Modify: `harness/hooks/cli.py`
- Test: `tests/test_cli_veredicto.py`
- Reference: `agente-esceptico.md` (el original, para conservar su tono e intención)

**Interfaces:**
- Consumes: `contracts.validate_veredicto` (Task 3), `state` (Task 7).
- Produces:
  - `harness/agents/skeptic.md` con frontmatter `name: skeptic`, `model: opus`.
  - CLI: `python cli.py record-veredicto --project <ruta> --archivo <veredicto.json>` — valida, escribe `intento_N/veredicto.json`, y transiciona el estado: si el escéptico rechaza → `registrar_fallo(origen="esceptico")`; si aprueba y no hay prueba manual requerida → `aprobar_fase`; si aprueba y sí la hay → `esperando_humano`.

- [ ] **Step 1: Escribir el agente escéptico**

Crear `harness/agents/skeptic.md`:

```markdown
---
name: skeptic
description: >-
  Verificador escéptico de una fase del harness. Exige evidencia de cada
  afirmación, contrasta el trabajo contra el criterio de éxito de la fase y
  emite un veredicto estructurado. No conoce ningún stack: las reglas del
  proyecto llegan en checks.json y en rules.json.
model: opus
color: red
---

Eres el verificador escéptico del harness. Tu única salida es un `veredicto.json`
válido. No escribes código, no corriges nada, no felicitas a nadie.

Tu lema: **"Muéstrame la evidencia o no ocurrió."**

## Lo que recibes

- El **diff** de la fase (lo que realmente cambió).
- El **`criterio_exito`** de la fase, tomado de `plan.json`.
- Los **`anclajes`** de la fase, con su etiqueta `verificado` o `por_confirmar`.
- **`checks.json`**: los hechos que ya comprobaron los scripts, incluidos los
  `warning` que no bloquearon.
- El **`historial_fallos`** de los intentos anteriores.

Deliberadamente **NO** recibes la conversación del agente que ejecutó el trabajo.
Un verificador que leyó el razonamiento del ejecutor ya está contaminado por él.

## Cómo juzgas

1. **Contrasta el diff contra el `criterio_exito`, no contra tu gusto personal.**
   Si el cambio cumple el criterio, no lo rechaces por estilo. Si no lo cumple,
   dilo con precisión: qué falta, no "podría mejorarse".
2. **Toma los `warning` de `checks.json` y decide si importan en este contexto.**
   Los scripts no bloquearon; tú sí puedes, si en este cambio concreto el warning
   es un problema real. Explica por qué.
3. **Persigue los `anclajes` con `confianza: "por_confirmar"`.** Si el trabajo se
   apoyó en un supuesto que nadie verificó en el código, va a
   `anclajes_sin_resolver` y es motivo de rechazo.
4. **Caza afirmaciones sin respaldo.** Cualquier "ya funciona", "quedó guardando",
   "ya se validó" que no tenga evidencia en el diff o en `checks.json` va a
   `claims_sin_evidencia`.
5. **Revisa el `historial_fallos`.** Si este intento repite un fallo anterior, o si
   corrigió uno rompiendo algo que antes funcionaba, eso es rechazo inmediato: es
   una regresión, no un avance.
6. **No inventes verificación funcional.** No puedes probar la aplicación. No digas
   que algo "debería funcionar en runtime": eso lo decide la prueba manual del
   humano. Limítate a lo que el diff y los checks permiten afirmar.

## Salida — exactamente este formato

```json
{
  "fase_id": "fase_1",
  "intento": 2,
  "aprobado": false,
  "juicio_esceptico": {
    "aprobado": false,
    "razones_rechazo": ["el SP no parsea V21, el valor se guardaría vacío"],
    "claims_sin_evidencia": ["se afirmó que el campo se relee, sin nada en el diff que lo haga"],
    "anclajes_sin_resolver": ["Sps/dbo.ReviewInsUpd.StoredProcedure.sql:88 seguía por_confirmar"]
  },
  "prueba_manual": { "requerida": true, "ejecutada": false, "resultado": "pendiente" }
}
```

Reglas del formato, sin excepciones:

- `aprobado` (el de arriba) es `true` **solo** si `juicio_esceptico.aprobado` es
  `true` **y** la prueba manual ya resultó `"ok"` o no era requerida. Si apruebas
  tu parte pero la prueba manual sigue pendiente, `aprobado` va en `false`: lo
  completará el humano.
- Un `juicio_esceptico.aprobado: false` exige al menos una entrada en
  `razones_rechazo`. Rechazar sin razón es un veredicto inválido.
- Las tres listas siempre existen, aunque estén vacías.
- No agregues campos que no estén en el ejemplo.
- No escribas nada fuera del JSON.
```

- [ ] **Step 2: Escribir las pruebas que fallan**

Crear `tests/test_cli_veredicto.py`:

```python
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
CLI = RAIZ / "harness" / "hooks" / "cli.py"
sys.path.insert(0, str(RAIZ / "harness" / "hooks"))
from lib import harness, state  # noqa: E402

REGLAS = {"perfil": "p", "audit_comments": {"requerido": True, "severidad": "error"}}


def _plan(prueba_requerida: bool) -> dict:
    return {"ticket_id": "ISR-110722", "perfil": "p",
            "fases": [{"id": "fase_1", "titulo": "t", "pasos": ["p"], "anclajes": [],
                       "criterio_exito": "c", "checks_deterministas": ["audit_comments"],
                       "prueba_manual": {"requerida": prueba_requerida},
                       "herramientas_permitidas": ["edit"], "max_reintentos": 3,
                       "depende_de": []}]}


def correr(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run([sys.executable, str(CLI), *args],
                          capture_output=True, text=True, encoding="utf-8")


class TestRecordVeredicto(unittest.TestCase):
    def preparar(self, prueba_requerida=True):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        (self.root / ".claude").mkdir()
        harness.write_json(self.root / ".claude" / "rules.json", REGLAS)
        harness.write_json(harness.ticket_dir(self.root, "ISR-110722") / "plan.json",
                           _plan(prueba_requerida))
        correr("open-ticket", "--project", str(self.root), "--ticket-id", "ISR-110722",
               "--nroticket", "110722", "--desarrollador", "OMAR RODRIGUEZ",
               "--fecha", "28-07-2026", "--perfil", "p")
        correr("open-fase", "--project", str(self.root), "--fase", "fase_1")

    def escribir(self, veredicto: dict) -> Path:
        ruta = self.root / "veredicto_entrada.json"
        ruta.write_text(json.dumps(veredicto), encoding="utf-8")
        return ruta

    @staticmethod
    def _veredicto(aprobado_esceptico: bool, razones=None, prueba=None) -> dict:
        return {"fase_id": "fase_1", "intento": 1, "aprobado": False,
                "juicio_esceptico": {"aprobado": aprobado_esceptico,
                                     "razones_rechazo": razones or [],
                                     "claims_sin_evidencia": [],
                                     "anclajes_sin_resolver": []},
                "prueba_manual": prueba or {"requerida": True, "ejecutada": False,
                                            "resultado": "pendiente"}}

    def test_rechazo_incrementa_el_intento_y_deja_en_correccion(self):
        self.preparar()
        ruta = self.escribir(self._veredicto(False, ["falta validar el campo"]))
        resultado = correr("record-veredicto", "--project", str(self.root), "--archivo", str(ruta))
        self.assertEqual(resultado.returncode, 0, resultado.stderr)
        estado = state.leer_fase(self.root, "ISR-110722", "fase_1")
        self.assertEqual(estado["intento_actual"], 2)
        self.assertEqual(estado["estado"], "en_correccion")
        self.assertEqual(estado["historial_fallos"][0]["origen"], "esceptico")

    def test_aprobacion_con_prueba_requerida_deja_esperando_humano(self):
        self.preparar(prueba_requerida=True)
        ruta = self.escribir(self._veredicto(True))
        correr("record-veredicto", "--project", str(self.root), "--archivo", str(ruta))
        estado = state.leer_fase(self.root, "ISR-110722", "fase_1")
        self.assertEqual(estado["estado"], "esperando_humano")

    def test_aprobacion_sin_prueba_requerida_cierra_la_fase(self):
        self.preparar(prueba_requerida=False)
        ruta = self.escribir(self._veredicto(
            True, prueba={"requerida": False, "ejecutada": False, "resultado": "na"}))
        correr("record-veredicto", "--project", str(self.root), "--archivo", str(ruta))
        estado = state.leer_fase(self.root, "ISR-110722", "fase_1")
        self.assertEqual(estado["estado"], "aprobada")

    def test_rechaza_un_veredicto_que_viola_su_contrato(self):
        self.preparar()
        ruta = self.escribir(self._veredicto(False, []))  # rechazo sin razones
        resultado = correr("record-veredicto", "--project", str(self.root), "--archivo", str(ruta))
        self.assertEqual(resultado.returncode, 1)
        self.assertIn("razones_rechazo", resultado.stderr)

    def test_el_veredicto_queda_guardado_en_la_carpeta_del_intento(self):
        self.preparar()
        ruta = self.escribir(self._veredicto(True))
        correr("record-veredicto", "--project", str(self.root), "--archivo", str(ruta))
        destino = harness.intento_dir(self.root, "ISR-110722", "fase_1", 1) / "veredicto.json"
        self.assertTrue(destino.is_file())

    def test_al_tercer_rechazo_la_fase_escala(self):
        self.preparar()
        for _ in range(3):
            ruta = self.escribir(self._veredicto(False, ["sigue mal"]))
            correr("record-veredicto", "--project", str(self.root), "--archivo", str(ruta))
        estado = state.leer_fase(self.root, "ISR-110722", "fase_1")
        self.assertEqual(estado["estado"], "escalado")


class TestAgenteEsceptico(unittest.TestCase):
    def test_no_menciona_reglas_de_otro_proyecto(self):
        texto = (RAIZ / "harness" / "agents" / "skeptic.md").read_text(encoding="utf-8")
        for prohibido in ("Kilo Code", ".kilocode", "actor system", "TypeScript"):
            self.assertNotIn(prohibido, texto)

    def test_no_menciona_ningun_stack_concreto(self):
        texto = (RAIZ / "harness" / "agents" / "skeptic.md").read_text(encoding="utf-8")
        for prohibido in ("VB.NET", "Web Forms", "jQuery", "EjecutarSp"):
            self.assertNotIn(prohibido, texto)


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 3: Correr las pruebas para verificar que fallan**

Run: `python -m unittest tests.test_cli_veredicto -v`
Expected: FAIL — `invalid choice: 'record-veredicto'`.

- [ ] **Step 4: Añadir `record-veredicto` a `cli.py`**

Añadir antes de `construir_parser`:

```python
def cmd_record_veredicto(args) -> int:
    raiz = resolver_proyecto(args.project)
    activa = _fase_activa(raiz)
    if activa is None:
        return _error("no hay fase activa: corre 'open-fase'")
    ticket_id, _, fase, estado = activa

    veredicto = harness.read_json(Path(args.archivo))
    errores = contracts.validate_veredicto(veredicto)
    if errores:
        return _error("veredicto inválido: " + "; ".join(errores))
    if veredicto["fase_id"] != fase["id"]:
        return _error(f"el veredicto dice fase '{veredicto['fase_id']}' pero la fase "
                      f"activa es '{fase['id']}'")

    destino = harness.intento_dir(raiz, ticket_id, fase["id"], estado["intento_actual"])
    harness.write_json(destino / "veredicto.json", veredicto)

    if not veredicto["juicio_esceptico"]["aprobado"]:
        razon = "; ".join(veredicto["juicio_esceptico"]["razones_rechazo"])
        nuevo = state.registrar_fallo(raiz, ticket_id, fase["id"], "esceptico", razon)
        print(f"Escéptico rechazó. Estado: {nuevo['estado']}, "
              f"intento {nuevo['intento_actual']}/{nuevo['max_reintentos']}")
        return 0

    if (fase.get("prueba_manual") or {}).get("requerida"):
        state.set_estado(raiz, ticket_id, fase["id"], "esperando_humano")
        print("Escéptico aprobó. Falta la prueba manual: responde con "
              "/fase-ok o /fase-fallo <paso> \"<observación>\".")
        return 0

    state.aprobar_fase(raiz, ticket_id, fase["id"])
    print("Escéptico aprobó y la fase no requería prueba manual: fase aprobada.")
    return 0
```

Registrar en `construir_parser`:

```python
    p = sub.add_parser("record-veredicto", help="Registra el veredicto del escéptico")
    p.add_argument("--project")
    p.add_argument("--archivo", required=True)
    p.set_defaults(func=cmd_record_veredicto)
```

- [ ] **Step 5: Correr las pruebas para verificar que pasan**

Run: `python -m unittest tests.test_cli_veredicto -v`
Expected: PASS, 8 pruebas.

- [ ] **Step 6: Commit**

```bash
git add harness/agents/skeptic.md harness/hooks/cli.py tests/test_cli_veredicto.py
git commit -m "feat(esceptico): escéptico genérico sin reglas heredadas y registro de veredicto"
```

---

### Task 12: Gate humano — `prueba_manual.md`, `record-manual` y los comandos

**Files:**
- Create: `harness/hooks/lib/prueba_manual.py`
- Modify: `harness/hooks/cli.py`
- Create: `harness/commands/fase-ok.md`, `harness/commands/fase-fallo.md`
- Test: `tests/test_prueba_manual.py`

**Interfaces:**
- Consumes: `state`, `harness`, `contracts`.
- Produces:
  - `prueba_manual.render(fase: dict, intento: int, pasos: list[str]) -> str` — genera el markdown del guion.
  - CLI: `python cli.py generar-prueba --project <ruta> --pasos-json <archivo>` — donde `--pasos-json` es una lista de objetos `{"paso": "...", "esperado": "..."}` que produce el agente a partir del `criterio_exito`. Escribe `intento_N/prueba_manual.md`.
  - CLI: `python cli.py record-manual --project <ruta> --resultado ok`
  - CLI: `python cli.py record-manual --project <ruta> --resultado fallo --paso 3 --observacion "el campo volvió vacío"`
  - Comandos `/fase-ok` y `/fase-fallo`.

- [ ] **Step 1: Escribir las pruebas que fallan**

Crear `tests/test_prueba_manual.py`:

```python
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
CLI = RAIZ / "harness" / "hooks" / "cli.py"
sys.path.insert(0, str(RAIZ / "harness" / "hooks"))
from lib import harness, prueba_manual, state  # noqa: E402

FASE = {"id": "fase_1", "titulo": "Agregar campo de comentario",
        "criterio_exito": "El comentario se guarda y se relee",
        "prueba_manual": {"requerida": True, "url": "frmReviewReport.aspx",
                          "datos": "review 4471, idioma EN"},
        "max_reintentos": 3}
PASOS = [{"paso": "Abrir la review 4471 y entrar a Other Q", "esperado": "El campo aparece vacío"},
         {"paso": "Escribir 'prueba harness' y guardar", "esperado": "Mensaje de guardado"},
         {"paso": "Salir y reabrir la review", "esperado": "El campo conserva el texto"}]


def correr(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run([sys.executable, str(CLI), *args],
                          capture_output=True, text=True, encoding="utf-8")


class TestRender(unittest.TestCase):
    def test_incluye_url_datos_y_los_pasos_numerados(self):
        texto = prueba_manual.render(FASE, 2, PASOS)
        self.assertIn("frmReviewReport.aspx", texto)
        self.assertIn("review 4471", texto)
        self.assertIn("intento_2", texto)
        for numero in ("| 1 |", "| 2 |", "| 3 |"):
            self.assertIn(numero, texto)

    def test_recuerda_como_responder(self):
        texto = prueba_manual.render(FASE, 1, PASOS)
        self.assertIn("/fase-ok", texto)
        self.assertIn("/fase-fallo", texto)

    def test_incluye_el_criterio_de_exito_de_la_fase(self):
        self.assertIn("se relee", prueba_manual.render(FASE, 1, PASOS))


class TestRecordManual(unittest.TestCase):
    def preparar(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        (self.root / ".claude").mkdir()
        harness.write_json(self.root / ".claude" / "rules.json",
                           {"perfil": "p", "audit_comments": {"requerido": True,
                                                              "severidad": "error"}})
        plan = {"ticket_id": "ISR-110722", "perfil": "p",
                "fases": [dict(FASE, pasos=["uno"], anclajes=[],
                               checks_deterministas=["audit_comments"],
                               herramientas_permitidas=["edit"], depende_de=[])]}
        harness.write_json(harness.ticket_dir(self.root, "ISR-110722") / "plan.json", plan)
        correr("open-ticket", "--project", str(self.root), "--ticket-id", "ISR-110722",
               "--nroticket", "110722", "--desarrollador", "OMAR RODRIGUEZ",
               "--fecha", "28-07-2026", "--perfil", "p")
        correr("open-fase", "--project", str(self.root), "--fase", "fase_1")
        state.set_estado(self.root, "ISR-110722", "fase_1", "esperando_humano")
        veredicto = {"fase_id": "fase_1", "intento": 1, "aprobado": False,
                     "juicio_esceptico": {"aprobado": True, "razones_rechazo": [],
                                          "claims_sin_evidencia": [],
                                          "anclajes_sin_resolver": []},
                     "prueba_manual": {"requerida": True, "ejecutada": False,
                                       "resultado": "pendiente"}}
        harness.write_json(
            harness.intento_dir(self.root, "ISR-110722", "fase_1", 1) / "veredicto.json",
            veredicto)

    def test_ok_aprueba_la_fase_y_completa_el_veredicto(self):
        self.preparar()
        resultado = correr("record-manual", "--project", str(self.root), "--resultado", "ok")
        self.assertEqual(resultado.returncode, 0, resultado.stderr)
        self.assertEqual(state.leer_fase(self.root, "ISR-110722", "fase_1")["estado"], "aprobada")
        veredicto = harness.read_json(
            harness.intento_dir(self.root, "ISR-110722", "fase_1", 1) / "veredicto.json")
        self.assertTrue(veredicto["aprobado"])
        self.assertEqual(veredicto["prueba_manual"]["resultado"], "ok")
        self.assertTrue(veredicto["prueba_manual"]["ejecutada"])

    def test_fallo_registra_el_origen_humano_con_paso_y_observacion(self):
        self.preparar()
        resultado = correr("record-manual", "--project", str(self.root), "--resultado", "fallo",
                           "--paso", "3", "--observacion", "el campo volvió vacío")
        self.assertEqual(resultado.returncode, 0, resultado.stderr)
        estado = state.leer_fase(self.root, "ISR-110722", "fase_1")
        self.assertEqual(estado["intento_actual"], 2)
        fallo = estado["historial_fallos"][0]
        self.assertEqual(fallo["origen"], "humano")
        self.assertIn("paso 3", fallo["razon"])
        self.assertIn("volvió vacío", fallo["razon"])

    def test_fallo_exige_paso_y_observacion(self):
        self.preparar()
        resultado = correr("record-manual", "--project", str(self.root), "--resultado", "fallo")
        self.assertEqual(resultado.returncode, 1)
        self.assertIn("--paso", resultado.stderr)

    def test_rechaza_registrar_si_la_fase_no_espera_al_humano(self):
        self.preparar()
        state.set_estado(self.root, "ISR-110722", "fase_1", "en_ejecucion")
        resultado = correr("record-manual", "--project", str(self.root), "--resultado", "ok")
        self.assertEqual(resultado.returncode, 1)
        self.assertIn("esperando_humano", resultado.stderr)

    def test_generar_prueba_escribe_el_archivo_en_el_intento(self):
        self.preparar()
        entrada = self.root / "pasos.json"
        entrada.write_text(json.dumps(PASOS), encoding="utf-8")
        resultado = correr("generar-prueba", "--project", str(self.root),
                           "--pasos-json", str(entrada))
        self.assertEqual(resultado.returncode, 0, resultado.stderr)
        destino = (harness.intento_dir(self.root, "ISR-110722", "fase_1", 1)
                   / "prueba_manual.md")
        self.assertIn("review 4471", destino.read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Correr para verificar que falla**

Run: `python -m unittest tests.test_prueba_manual -v`
Expected: FAIL con `ImportError: cannot import name 'prueba_manual'`.

- [ ] **Step 3: Implementar el generador del guion**

Crear `harness/hooks/lib/prueba_manual.py`:

```python
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
```

- [ ] **Step 4: Añadir `generar-prueba` y `record-manual` a `cli.py`**

Añadir `prueba_manual` al import de `lib`, y estas funciones antes de `construir_parser`:

```python
def cmd_generar_prueba(args) -> int:
    raiz = resolver_proyecto(args.project)
    activa = _fase_activa(raiz)
    if activa is None:
        return _error("no hay fase activa: corre 'open-fase'")
    ticket_id, _, fase, estado = activa
    pasos = harness.read_json(Path(args.pasos_json))
    if not isinstance(pasos, list) or not pasos:
        return _error("--pasos-json debe contener una lista no vacía de "
                      "objetos {paso, esperado}")
    destino = harness.intento_dir(raiz, ticket_id, fase["id"], estado["intento_actual"])
    destino.mkdir(parents=True, exist_ok=True)
    archivo = destino / "prueba_manual.md"
    archivo.write_text(prueba_manual.render(fase, estado["intento_actual"], pasos),
                       encoding="utf-8")
    print(f"Guion de prueba escrito en {archivo}")
    return 0


def cmd_record_manual(args) -> int:
    raiz = resolver_proyecto(args.project)
    activa = _fase_activa(raiz)
    if activa is None:
        return _error("no hay fase activa: corre 'open-fase'")
    ticket_id, _, fase, estado = activa

    if estado["estado"] != "esperando_humano":
        return _error(f"la fase está en estado '{estado['estado']}': solo se registra la "
                      f"prueba manual cuando está en 'esperando_humano'")
    if args.resultado == "fallo" and (args.paso is None or not args.observacion):
        return _error("un fallo exige --paso y --observacion: sin eso el intento "
                      "siguiente no sabe qué corregir")

    carpeta = harness.intento_dir(raiz, ticket_id, fase["id"], estado["intento_actual"])
    ruta_veredicto = carpeta / "veredicto.json"
    if not ruta_veredicto.is_file():
        return _error(f"falta {ruta_veredicto}: el escéptico debe emitir su veredicto antes "
                      f"de la prueba manual")
    veredicto = harness.read_json(ruta_veredicto)

    veredicto["prueba_manual"].update({
        "requerida": True, "ejecutada": True, "resultado": args.resultado})
    if args.resultado == "fallo":
        veredicto["prueba_manual"]["fallo_en_paso"] = args.paso
        veredicto["prueba_manual"]["observacion"] = args.observacion
        veredicto["aprobado"] = False
    else:
        veredicto["prueba_manual"].pop("fallo_en_paso", None)
        veredicto["prueba_manual"].pop("observacion", None)
        veredicto["aprobado"] = bool(veredicto["juicio_esceptico"]["aprobado"])

    errores = contracts.validate_veredicto(veredicto)
    if errores:
        return _error("el veredicto resultante es inválido: " + "; ".join(errores))
    harness.write_json(ruta_veredicto, veredicto)

    if args.resultado == "ok":
        state.aprobar_fase(raiz, ticket_id, fase["id"])
        print(f"Prueba manual OK. Fase {fase['id']} aprobada.")
        return 0

    razon = f"prueba manual: falló en el paso {args.paso} — {args.observacion}"
    nuevo = state.registrar_fallo(raiz, ticket_id, fase["id"], "humano", razon)
    print(f"Prueba manual falló. Estado: {nuevo['estado']}, "
          f"intento {nuevo['intento_actual']}/{nuevo['max_reintentos']}")
    return 0
```

Registrar los subcomandos:

```python
    p = sub.add_parser("generar-prueba", help="Escribe el guion de prueba manual")
    p.add_argument("--project")
    p.add_argument("--pasos-json", required=True)
    p.set_defaults(func=cmd_generar_prueba)

    p = sub.add_parser("record-manual", help="Registra el resultado de la prueba manual")
    p.add_argument("--project")
    p.add_argument("--resultado", required=True, choices=["ok", "fallo"])
    p.add_argument("--paso", type=int)
    p.add_argument("--observacion")
    p.set_defaults(func=cmd_record_manual)
```

- [ ] **Step 5: Correr para verificar que pasa**

Run: `python -m unittest tests.test_prueba_manual -v`
Expected: PASS, 8 pruebas.

- [ ] **Step 6: Crear los comandos**

Crear `harness/commands/fase-ok.md`:

```markdown
---
description: Registra que la prueba manual de la fase activa pasó
---

Corre este comando y reporta su salida al usuario, sin agregar interpretación:

```bash
python "$HOME/.claude/hooks/cli.py" record-manual --resultado ok
```

Si el comando falla, muestra el error tal cual. No intentes aprobar la fase por
otro medio ni editar el estado a mano: el CLI es el único que escribe estado.
```

Crear `harness/commands/fase-fallo.md`:

```markdown
---
description: Registra que la prueba manual falló, con el paso y lo observado
argument-hint: <número de paso> "<qué pasó en realidad>"
---

El usuario reporta que la prueba manual falló. Sus argumentos: `$ARGUMENTS`

Extrae el número de paso y la observación, y córrelo:

```bash
python "$HOME/.claude/hooks/cli.py" record-manual --resultado fallo --paso <N> --observacion "<observación>"
```

Si falta el número de paso o la observación, pídeselos antes de correr nada: sin
esos dos datos el intento siguiente no sabe qué corregir.

Después de registrarlo, lee el `historial_fallos` de la fase y arranca el intento
siguiente teniendo presente **todos** los fallos anteriores, no solo el último.
```

- [ ] **Step 7: Commit**

```bash
git add harness/hooks/lib/prueba_manual.py harness/hooks/cli.py harness/commands/ tests/test_prueba_manual.py
git commit -m "feat(gate): guion de prueba manual y registro del veredicto humano"
```

---

### Task 13: `gate_phase.py` — hook `Stop`

**Files:**
- Create: `harness/hooks/gate_phase.py`
- Test: `tests/test_hook_gate_phase.py`
- Read first: `docs/hook-payloads.md` (Task 1) para el nombre real del indicador de reentrada.

**Interfaces:**
- Consumes: `harness`, `state`.
- Produces: hook ejecutable. **Exit 2 solo si la fase está a mitad de vuelo** (`en_ejecucion`, `en_verificacion`, `en_correccion`); exit 0 en todo lo demás.

> Detalle crítico: **`esperando_humano` NO debe bloquear.** El hook `Stop` corre cuando el modelo termina su turno; si bloqueáramos ahí, el harness impediría justamente lo que quiere lograr — devolverle el control al humano — y entraría en un bucle. `escalado` tampoco bloquea, por la misma razón: escalar significa ceder el turno.

- [ ] **Step 1: Escribir las pruebas que fallan**

Crear `tests/test_hook_gate_phase.py`:

```python
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
HOOK = RAIZ / "harness" / "hooks" / "gate_phase.py"
sys.path.insert(0, str(RAIZ / "harness" / "hooks"))
from lib import harness  # noqa: E402


def lanzar(payload: dict) -> subprocess.CompletedProcess:
    return subprocess.run([sys.executable, str(HOOK)], input=json.dumps(payload),
                          capture_output=True, text=True, encoding="utf-8")


class TestHookStop(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        (self.root / ".claude").mkdir()
        harness.write_json(self.root / ".claude" / "rules.json", {"perfil": "p"})
        harness.write_current(self.root, "ISR-110722", "fase_1")

    def tearDown(self):
        self.tmp.cleanup()

    def con_estado(self, estado: str, intento: int = 1, maximo: int = 3) -> None:
        harness.write_json(
            harness.fase_dir(self.root, "ISR-110722", "fase_1") / "fase_state.json",
            {"fase_id": "fase_1", "estado": estado, "intento_actual": intento,
             "max_reintentos": maximo, "historial_fallos": []})

    def payload(self, reentrada: bool = False) -> dict:
        return {"hook_event_name": "Stop", "cwd": str(self.root),
                "stop_hook_active": reentrada}

    def test_bloquea_si_la_fase_esta_en_ejecucion(self):
        self.con_estado("en_ejecucion")
        resultado = lanzar(self.payload())
        self.assertEqual(resultado.returncode, 2)
        self.assertIn("en_ejecucion", resultado.stderr)

    def test_bloquea_si_la_fase_esta_en_correccion(self):
        self.con_estado("en_correccion", intento=2)
        self.assertEqual(lanzar(self.payload()).returncode, 2)

    def test_bloquea_si_la_fase_esta_en_verificacion(self):
        self.con_estado("en_verificacion")
        self.assertEqual(lanzar(self.payload()).returncode, 2)

    def test_NO_bloquea_esperando_humano(self):
        self.con_estado("esperando_humano")
        resultado = lanzar(self.payload())
        self.assertEqual(resultado.returncode, 0, resultado.stderr)

    def test_NO_bloquea_una_fase_escalada(self):
        self.con_estado("escalado", intento=3)
        self.assertEqual(lanzar(self.payload()).returncode, 0)

    def test_NO_bloquea_una_fase_aprobada(self):
        self.con_estado("aprobada")
        self.assertEqual(lanzar(self.payload()).returncode, 0)

    def test_NO_bloquea_en_la_reentrada_del_propio_hook(self):
        self.con_estado("en_ejecucion")
        self.assertEqual(lanzar(self.payload(reentrada=True)).returncode, 0)

    def test_es_inerte_sin_perfil(self):
        with tempfile.TemporaryDirectory() as sin_perfil:
            resultado = lanzar({"hook_event_name": "Stop", "cwd": sin_perfil,
                                "stop_hook_active": False})
            self.assertEqual(resultado.returncode, 0)
            self.assertEqual(resultado.stderr.strip(), "")

    def test_es_inerte_sin_fase_activa(self):
        harness.write_json(harness.current_pointer_path(self.root),
                           {"ticket_id": "ISR-110722", "fase_id": None})
        self.assertEqual(lanzar(self.payload()).returncode, 0)

    def test_un_payload_ilegible_no_rompe_nada(self):
        resultado = subprocess.run([sys.executable, str(HOOK)], input="no json",
                                   capture_output=True, text=True, encoding="utf-8")
        self.assertEqual(resultado.returncode, 0)


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Correr para verificar que falla**

Run: `python -m unittest tests.test_hook_gate_phase -v`
Expected: FAIL — `gate_phase.py` no existe.

- [ ] **Step 3: Implementar el hook**

Crear `harness/hooks/gate_phase.py`:

```python
#!/usr/bin/env python3
"""Hook Stop: impide cerrar el turno con el ciclo de fase a mitad de vuelo.

Solo bloquea los estados en que el ciclo está corriendo. 'esperando_humano' y
'escalado' NO bloquean: en ambos el objetivo es precisamente devolverle el
turno al humano, y bloquear ahí produciría un bucle.

Antes de modificar este archivo, revisar docs/hook-payloads.md.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from lib import harness, state  # noqa: E402

BLOQUEANTES = frozenset({"en_ejecucion", "en_verificacion", "en_correccion"})

SIGUIENTE_PASO = {
    "en_ejecucion": "termina el trabajo de la fase y corre 'cli.py run-checks'",
    "en_verificacion": "invoca al escéptico y registra su veredicto con "
                       "'cli.py record-veredicto'",
    "en_correccion": "aplica la corrección leyendo el historial_fallos completo, "
                     "y vuelve a correr 'cli.py run-checks'",
}


def main() -> int:
    try:
        payload = json.load(sys.stdin)
    except (json.JSONDecodeError, UnicodeDecodeError):
        return 0
    if not isinstance(payload, dict) or payload.get("stop_hook_active"):
        return 0

    raiz = harness.find_project_root(payload.get("cwd") or Path.cwd())
    if raiz is None or harness.is_harness_source(raiz):
        return 0

    actual = harness.read_current(raiz)
    if not actual or not actual.get("ticket_id") or not actual.get("fase_id"):
        return 0

    try:
        estado = state.leer_fase(raiz, actual["ticket_id"], actual["fase_id"])
    except (OSError, json.JSONDecodeError):
        return 0
    if estado is None or estado["estado"] not in BLOQUEANTES:
        return 0

    sys.stderr.write(
        f"HARNESS · la fase {estado['fase_id']} está en estado '{estado['estado']}' "
        f"(intento {estado['intento_actual']}/{estado['max_reintentos']}): el ciclo "
        f"no terminó.\nSiguiente paso: {SIGUIENTE_PASO[estado['estado']]}.\n"
        f"Si de verdad hay que detenerse aquí, escala explícitamente al humano "
        f"explicando por qué.\n")
    return 2


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 4: Correr para verificar que pasa**

Run: `python -m unittest tests.test_hook_gate_phase -v`
Expected: PASS, 10 pruebas.

- [ ] **Step 5: Commit**

```bash
git add harness/hooks/gate_phase.py tests/test_hook_gate_phase.py
git commit -m "feat(hooks): Stop que bloquea el cierre con el ciclo a mitad de vuelo"
```

---

### Task 14: Skill orquestadora y migración de `agent-rsgfs`

**Files:**
- Create: `harness/skills/ticket-loop/SKILL.md`
- Create: `harness/commands/ticket-abrir.md`, `harness/commands/fase.md`
- Create: `profiles/reviewsystemgfs/agents/agent-rsgfs.md` (desde `agente-rsfgfs.md`)
- Test: `tests/test_documentos_del_harness.py`

**Interfaces:**
- Consumes: todos los subcomandos del CLI (Tasks 8, 10, 11, 12).
- Produces: la skill que conduce el ciclo, y el agente ejecutor del perfil.

- [ ] **Step 1: Escribir la skill orquestadora**

Crear `harness/skills/ticket-loop/SKILL.md`:

```markdown
---
name: ticket-loop
description: >-
  Conduce el ciclo de una fase del harness: ejecutar, verificar con scripts,
  verificar con el escéptico, generar el guion de prueba manual y detenerse en
  el gate humano. Usar cuando se trabaje un ticket bajo el harness — al abrir
  un ticket, al arrancar una fase, o al retomar tras un fallo.
---

# Ciclo de fase

`CLI` = `python "$HOME/.claude/hooks/cli.py"`. **Todo cambio de estado pasa por el
CLI.** No edites `fase_state.json`, `checks.json` ni `veredicto.json` a mano: si te
sientes tentado a hacerlo, es que falta un subcomando.

## Al abrir un ticket

1. Pide el requerimiento (pegado o en `.md`) y guárdalo en `.harness/tickets/<id>/ticket.md`.
2. Pregunta **una sola vez**: número de ticket ISR, nombre del desarrollador y fecha
   (`DD-MM-YYYY`). No los inventes ni los deduzcas del sistema.
3. `CLI open-ticket --ticket-id ISR-<nro> --nroticket <nro> --desarrollador "<NOMBRE>" --fecha <DD-MM-YYYY> --perfil <perfil>`
4. Invoca la skill `task-planner` para producir `plan.md` y `plan.json`.
5. `CLI validate --contrato plan --archivo .harness/tickets/<id>/plan.json`
   Si falla, corrige el plan. **No abras ninguna fase con un plan inválido.**

## El ciclo de una fase

1. **Abrir:** `CLI open-fase --fase fase_N`. Si una dependencia no está aprobada, el
   CLI lo rechaza — respeta ese orden, no lo saltes.
2. **Ejecutar:** delega el trabajo al **subagente ejecutor del perfil** (para
   ReviewSystemGFS, `agent-rsgfs`). Pásale:
   - la fase completa de `plan.json` (pasos, criterio de éxito, anclajes);
   - `ticket_context.json`, para que los comentarios de auditoría lleven los valores
     correctos;
   - el **`historial_fallos` completo** si `intento_actual > 1` — todos los fallos, no
     solo el último: corregir el más reciente reintroduciendo uno viejo es una regresión;
   - las `herramientas_permitidas` de la fase.

   Mientras trabaja, el hook `PostToolUse` puede devolverle violaciones de reglas.
   **Eso es autocorrección, no un reintento:** que las corrija y siga.
3. **Documentar:** el ejecutor escribe `intento_N/resultado.md` con lo que hizo y la
   evidencia (rutas, líneas, salidas de comando). Esto ya no se pide a mano.
4. **Checks:** `CLI run-checks`.
   - Exit 1 → hay errores bloqueantes. Registra el fallo y vuelve al paso 2 con el
     historial actualizado. **No invoques al escéptico**: es más caro y estos fallos
     son hechos, no opiniones.
   - Exit 0 → sigue. Lee los `warning` de `checks.json` y pásaselos al escéptico.
5. **Escéptico:** `CLI` no lo invoca; lo invocas tú como **subagente `skeptic`, con
   contexto aislado**. Dale el diff, el `criterio_exito`, los `anclajes`,
   `checks.json` y el `historial_fallos`. **No le pases tu conversación con el
   ejecutor** — un verificador que leyó el razonamiento ya está contaminado.
   Guarda su JSON y córrelo: `CLI record-veredicto --archivo <ruta>`.
   Si rechazó, el CLI ya incrementó el intento: vuelve al paso 2.
6. **Guion de prueba:** si el escéptico aprobó y la fase requiere prueba manual,
   deriva del `criterio_exito` una lista de pasos concretos —clic por clic, con qué
   debería verse en cada uno— y córrela:
   `CLI generar-prueba --pasos-json <archivo>`.
   Los pasos deben ser ejecutables por alguien que no leyó el código.
7. **Detente.** Muestra el contenido de `prueba_manual.md` y espera. El humano
   responde `/fase-ok` o `/fase-fallo`. **No aproximes, no supongas, no cierres la
   fase por tu cuenta:** no hay build ni tests en este proyecto, así que su
   navegador es la única prueba funcional que existe.

## Cuando una fase escala

Al agotarse los reintentos, la fase queda en `escalado`. No arranques otro intento
ni pases a la fase siguiente. Reporta al humano, en este orden:

1. Qué se intentó en cada intento y qué falló, tomado del `historial_fallos`.
2. Qué patrón se repite entre los fallos.
3. Si el patrón es un fallo del escéptico que ya apareció más de una vez,
   **propón el check determinista que lo habría atrapado.** Ese es el ciclo de
   mejora del harness: convertir juicio caro en verificación barata.
```

- [ ] **Step 2: Crear los comandos de entrada**

Crear `harness/commands/ticket-abrir.md`:

```markdown
---
description: Abre un ticket bajo el harness y genera su plan
argument-hint: [ruta al .md del requerimiento o el texto pegado]
---

Usa la skill `ticket-loop`, sección "Al abrir un ticket". Requerimiento: `$ARGUMENTS`

Si no viene requerimiento, pídelo antes de hacer nada. No inventes el número de
ticket, el desarrollador ni la fecha: pregúntalos.
```

Crear `harness/commands/fase.md`:

```markdown
---
description: Corre el ciclo completo de una fase del plan activo
argument-hint: fase_N
---

Usa la skill `ticket-loop`, sección "El ciclo de una fase", para `$ARGUMENTS`.

Recuerda: el ciclo se detiene en el gate humano. Tu turno termina mostrando el
guion de prueba manual, no aprobando la fase.
```

- [ ] **Step 3: Migrar el agente del perfil**

Copiar `agente-rsfgfs.md` a `profiles/reviewsystemgfs/agents/agent-rsgfs.md`, añadir el frontmatter y una sección nueva. El frontmatter al inicio del archivo:

```markdown
---
name: agent-rsgfs
description: >-
  Ejecutor del proyecto ReviewSystemGFS. Programa dentro del stack legacy
  (VB.NET, Web Forms, FW 3.5, jQuery 1.7.2) respetando sus patrones y la regla
  de comentarios de auditoría. Usar como subagente ejecutor de una fase del
  harness en este proyecto.
model: opus
---
```

Añadir esta sección antes de la §12 "Limitaciones Conocidas":

```markdown
## 11.b. Operación bajo el harness

Cuando te invoquen como ejecutor de una fase, recibes cuatro cosas y las tratas así:

1. **La fase de `plan.json`** — sus `pasos`, su `criterio_exito` y sus `anclajes`.
   Un ancla con `confianza: "por_confirmar"` es un supuesto sin verificar:
   confírmalo en el código antes de apoyarte en él, o repórtalo sin resolver.
2. **`ticket_context.json`** — de aquí salen `{nroticket}`, `{desarrollador}` y
   `{fechacorta}` de los comentarios `[B]/[E]` (§4). **Nunca los inventes ni los
   deduzcas:** un hook compara los valores exactos y bloqueará el cambio.
3. **`historial_fallos`** — si `intento_actual > 1`, léelo completo antes de tocar
   nada. Corregir el fallo más reciente reintroduciendo uno anterior es una
   regresión, y el escéptico la rechazará.
4. **`herramientas_permitidas`** — no uses herramientas fuera de esa lista. Si la
   fase las necesita, detente y dilo, no la amplíes por tu cuenta.

Al terminar escribes `intento_N/resultado.md` con: qué cambiaste (archivo y líneas),
por qué, y qué evidencia respalda cada afirmación. **No escribas "ya funciona":** no
puedes comprobarlo, no hay build ni tests. Describe lo que hiciste y deja el juicio
al escéptico y la prueba funcional al humano.

Tu checklist de la §10 ya no depende de tu memoria: el hook `PostToolUse` verifica
los `[B]/[E]`, las dependencias nuevas y la sintaxis prohibida en cada archivo que
guardas. Si te devuelve un error, corrígelo en el momento — eso es autocorrección y
no consume un reintento de la fase.
```

- [ ] **Step 4: Escribir las pruebas de los documentos**

Crear `tests/test_documentos_del_harness.py`:

```python
import re
import unittest
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]


def leer(*partes: str) -> str:
    return (RAIZ.joinpath(*partes)).read_text(encoding="utf-8")


def frontmatter(texto: str) -> dict:
    bloque = re.match(r"^---\n(.*?)\n---\n", texto, re.DOTALL)
    if not bloque:
        return {}
    campos = {}
    for linea in bloque.group(1).splitlines():
        if re.match(r"^\w+:", linea):
            clave, _, valor = linea.partition(":")
            campos[clave.strip()] = valor.strip()
    return campos


class TestSkillOrquestadora(unittest.TestCase):
    def setUp(self):
        self.texto = leer("harness", "skills", "ticket-loop", "SKILL.md")

    def test_tiene_frontmatter_con_nombre_y_descripcion(self):
        campos = frontmatter(self.texto)
        self.assertEqual(campos.get("name"), "ticket-loop")
        self.assertIn("description", campos)

    def test_menciona_todos_los_subcomandos_del_ciclo(self):
        for comando in ("open-ticket", "open-fase", "run-checks", "record-veredicto",
                        "generar-prueba", "validate"):
            with self.subTest(comando=comando):
                self.assertIn(comando, self.texto)

    def test_deja_claro_que_el_esceptico_va_aislado(self):
        self.assertIn("contexto aislado", self.texto)

    def test_deja_claro_que_el_ciclo_se_detiene_en_el_gate_humano(self):
        self.assertIn("/fase-ok", self.texto)
        self.assertIn("/fase-fallo", self.texto)


class TestAgenteDelPerfil(unittest.TestCase):
    def setUp(self):
        self.texto = leer("profiles", "reviewsystemgfs", "agents", "agent-rsgfs.md")

    def test_tiene_frontmatter_con_el_nombre_esperado(self):
        self.assertEqual(frontmatter(self.texto).get("name"), "agent-rsgfs")

    def test_conserva_la_regla_de_comentarios_de_auditoria(self):
        self.assertIn("[B]", self.texto)
        self.assertIn("[E]", self.texto)

    def test_conserva_los_patrones_del_stack(self):
        for patron in ("EjecutarSp", "InstanciarConsulta", "__doPostBack"):
            with self.subTest(patron=patron):
                self.assertIn(patron, self.texto)

    def test_documenta_la_operacion_bajo_el_harness(self):
        for concepto in ("ticket_context.json", "historial_fallos",
                         "herramientas_permitidas"):
            with self.subTest(concepto=concepto):
                self.assertIn(concepto, self.texto)


class TestSeparacionDePlanos(unittest.TestCase):
    def test_el_harness_generico_no_conoce_el_stack_legacy(self):
        prohibidos = ("VB.NET", "Web Forms", "aspx", "EjecutarSp", "jQuery",
                      "SepararCadena", "designer.vb")
        for ruta in (RAIZ / "harness").rglob("*"):
            if ruta.suffix not in {".py", ".md"} or not ruta.is_file():
                continue
            if ruta.name == "probe_hook.py":
                continue
            texto = ruta.read_text(encoding="utf-8")
            for termino in prohibidos:
                with self.subTest(archivo=ruta.name, termino=termino):
                    self.assertNotIn(termino, texto,
                                     f"{ruta.name} menciona '{termino}': eso pertenece "
                                     f"a profiles/, no al harness genérico")


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 5: Correr las pruebas**

Run: `python -m unittest tests.test_documentos_del_harness -v`
Expected: PASS, 9 pruebas. Si `test_el_harness_generico_no_conoce_el_stack_legacy` falla, mover el texto ofensor a `profiles/` — no relajar la prueba.

- [ ] **Step 6: Correr la suite completa**

Run: `python -m unittest discover -s tests -v`
Expected: PASS, 119 pruebas.

- [ ] **Step 7: Commit**

```bash
git add harness/skills/ harness/commands/ profiles/reviewsystemgfs/agents/ tests/test_documentos_del_harness.py
git commit -m "feat: skill orquestadora del ciclo y migración de agent-rsgfs al perfil"
```

---

### Task 15: CHECKPOINT — validar con un ticket ISR real

**No hay código en esta tarea.** Es el punto de la §14 del spec donde se decide si el diseño aguanta. Construir los checks estructurales antes de esto sería adelantar trabajo sobre supuestos no probados.

**Files:**
- Create: `deploy.ps1`
- Create: `docs/hallazgos-primer-ticket.md`

**Interfaces:**
- Consumes: todo lo construido en las tareas 1-14.
- Produces: `docs/hallazgos-primer-ticket.md`, la entrada de las tareas 16-20.

- [ ] **Step 1: Escribir el deploy**

Crear `deploy.ps1`:

```powershell
<#
.SYNOPSIS
  Despliega el harness genérico a ~/.claude y el perfil al proyecto destino.
.EXAMPLE
  .\deploy.ps1 -Proyecto "C:\ruta\a\ReviewSystemGFS" -Perfil reviewsystemgfs
#>
param(
  [Parameter(Mandatory = $true)][string]$Proyecto,
  [string]$Perfil = "reviewsystemgfs"
)

$ErrorActionPreference = "Stop"
$Fuente = $PSScriptRoot
$Global = Join-Path $env:USERPROFILE ".claude"

if (-not (Test-Path $Proyecto)) { throw "No existe el proyecto: $Proyecto" }
$RutaPerfil = Join-Path $Fuente "profiles\$Perfil"
if (-not (Test-Path $RutaPerfil)) { throw "No existe el perfil: $RutaPerfil" }

# --- Harness genérico -> ~/.claude ---
foreach ($sub in @("hooks", "agents", "skills", "commands")) {
  $origen = Join-Path $Fuente "harness\$sub"
  if (-not (Test-Path $origen)) { continue }
  $destino = Join-Path $Global $sub
  New-Item -ItemType Directory -Force -Path $destino | Out-Null
  Copy-Item -Path (Join-Path $origen "*") -Destination $destino -Recurse -Force
  Write-Host "harness/$sub -> $destino"
}

# --- Perfil -> <proyecto>/.claude ---
$DestinoPerfil = Join-Path $Proyecto ".claude"
New-Item -ItemType Directory -Force -Path $DestinoPerfil | Out-Null
Copy-Item -Path (Join-Path $RutaPerfil "*") -Destination $DestinoPerfil -Recurse -Force
Write-Host "profiles/$Perfil -> $DestinoPerfil"

# --- .gitignore del proyecto: el estado arranca sin versionar ---
$GitIgnore = Join-Path $Proyecto ".gitignore"
$Linea = ".harness/"
if (-not (Test-Path $GitIgnore)) { New-Item -ItemType File -Path $GitIgnore | Out-Null }
if (-not (Select-String -Path $GitIgnore -SimpleMatch $Linea -Quiet)) {
  Add-Content -Path $GitIgnore -Value $Linea -Encoding utf8
  Write-Host "Agregado '$Linea' al .gitignore del proyecto"
}

# --- Respaldo de settings.json y recordatorio de los hooks ---
$Settings = Join-Path $Global "settings.json"
if (Test-Path $Settings) {
  $Respaldo = "$Settings.bak"
  Copy-Item $Settings $Respaldo -Force
  Write-Host "Respaldo de settings.json en $Respaldo"
}

$HookCheck = (Join-Path $Global "hooks\check_rules.py") -replace '\\', '\\'
$HookGate  = (Join-Path $Global "hooks\gate_phase.py")  -replace '\\', '\\'

Write-Host ""
Write-Host "Falta un paso manual: registrar los hooks en $Settings"
Write-Host "Fusiona esto dentro del objeto 'hooks' existente (no reemplaces el archivo):"
Write-Host ""
Write-Host @"
"PostToolUse": [
  { "matcher": "Edit|Write|MultiEdit",
    "hooks": [{ "type": "command", "command": "python \"$HookCheck\"" }] }
],
"Stop": [
  { "matcher": "",
    "hooks": [{ "type": "command", "command": "python \"$HookGate\"" }] }
]
"@
```

El registro de hooks queda manual a propósito: fusionar JSON automáticamente en el `settings.json` real del usuario es justo el tipo de acción irreversible que un harness no debería hacer sin que alguien mire.

- [ ] **Step 2: Desplegar contra el proyecto real**

Run: `.\deploy.ps1 -Proyecto "<ruta local de tu copia de ReviewSystemGFS>" -Perfil reviewsystemgfs`
Expected: las cuatro carpetas copiadas a `~/.claude`, `.claude/` creado en el proyecto, `.harness/` agregado al `.gitignore`, y el bloque de hooks impreso.

Luego registrar los hooks a mano en `~/.claude/settings.json` y verificar:

Run: `python "$HOME/.claude/hooks/cli.py" --help`
Expected: la lista de subcomandos.

- [ ] **Step 3: Correr un ticket ISR real de punta a punta**

Con un ticket pequeño y real (idealmente de una o dos fases):

1. `/ticket-abrir <requerimiento>` → verificar que `plan.json` pasa `validate`.
2. `/fase fase_1` → dejar que el ciclo corra.
3. Provocar a propósito **una** violación de regla (guardar un cambio sin `[B]/[E]`) y confirmar que el hook la devuelve al agente **durante** la ejecución, no al final.
4. Llegar al guion de prueba manual y ejecutarlo en el navegador de verdad.
5. Responder `/fase-fallo <paso> "<observación>"` al menos una vez, aunque haya pasado, para comprobar que el intento siguiente **cita el fallo anterior**.
6. Cerrar la fase con `/fase-ok`.

- [ ] **Step 4: Registrar los hallazgos**

Crear `docs/hallazgos-primer-ticket.md` con:

- **Falsos positivos**: qué check marcó algo que no era un problema. Cada uno es candidato a bajar de `error` a `warning` o a afinar su patrón.
- **Falsos negativos**: qué se te escapó y llegó hasta la prueba manual o hasta VS2008. Cada uno es candidato a check nuevo.
- **Fricción**: dónde el ciclo te hizo perder tiempo, o dónde el modelo se peleó con el harness en vez de trabajar.
- **Reintentos reales**: ¿3 fue el número correcto? ¿Se agotaron? ¿Sobraron?
- **Calidad del guion de prueba**: ¿los pasos eran ejecutables, o tuviste que interpretarlos?
- **Veredicto**: ¿el diseño aguanta como está, o hay que ajustar algo antes de seguir con las tareas 16-20?

- [ ] **Step 5: Commit**

```bash
git add deploy.ps1 docs/hallazgos-primer-ticket.md
git commit -m "chore: deploy del harness y hallazgos del primer ticket real"
```

- [ ] **Step 6: Decidir antes de continuar**

Revisar los hallazgos con el usuario y acordar qué se ajusta. **Las tareas 16-20 se planifican con esa información encima.** Si el checkpoint reveló un problema estructural, corregirlo aquí es mucho más barato que después de haber construido tres checks más sobre él.

---

### Task 16: `task-planner` v3 — emitir `plan.json`

**Files:**
- Create: `harness/skills/task-planner/SKILL.md` (desde `task-plannerv2.md`)
- Test: `tests/test_planner_v3.py`

**Interfaces:**
- Consumes: `contracts.validate_plan` (Task 3).
- Produces: la skill del planner, que además del `.md` emite un `plan.json` válido.

- [ ] **Step 1: Escribir la prueba que falla**

Crear `tests/test_planner_v3.py`:

```python
import json
import re
import sys
import unittest
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ / "harness" / "hooks"))
from lib import contracts  # noqa: E402

SKILL = RAIZ / "harness" / "skills" / "task-planner" / "SKILL.md"


class TestPlannerV3(unittest.TestCase):
    def setUp(self):
        self.texto = SKILL.read_text(encoding="utf-8")

    def test_conserva_la_fase_0_de_anclaje(self):
        self.assertIn("Fase 0", self.texto)
        self.assertIn("archivo:línea", self.texto)

    def test_exige_emitir_plan_json_ademas_del_md(self):
        self.assertIn("plan.json", self.texto)
        self.assertIn("plan.md", self.texto)

    def test_documenta_los_campos_nuevos_por_fase(self):
        for campo in ("checks_deterministas", "prueba_manual", "herramientas_permitidas",
                      "max_reintentos", "anclajes", "depende_de", "criterio_exito"):
            with self.subTest(campo=campo):
                self.assertIn(campo, self.texto)

    def test_manda_validar_el_plan_antes_de_entregarlo(self):
        self.assertIn("validate --contrato plan", self.texto)

    def test_el_ejemplo_de_plan_json_es_valido_contra_el_contrato(self):
        bloques = re.findall(r"```json\n(.*?)```", self.texto, re.DOTALL)
        planes = []
        for bloque in bloques:
            try:
                datos = json.loads(bloque)
            except json.JSONDecodeError:
                continue
            if isinstance(datos, dict) and "fases" in datos:
                planes.append(datos)
        self.assertTrue(planes, "la skill debe incluir un ejemplo completo de plan.json")
        for plan in planes:
            self.assertEqual(contracts.validate_plan(plan), [])


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Correr para verificar que falla**

Run: `python -m unittest tests.test_planner_v3 -v`
Expected: FAIL con `FileNotFoundError` sobre `harness/skills/task-planner/SKILL.md`.

- [ ] **Step 3: Crear la skill v3**

Copiar `task-plannerv2.md` a `harness/skills/task-planner/SKILL.md` y aplicar tres cambios:

1. En el frontmatter, cambiar `name: task-planner-v2` por `name: task-planner`, y añadir a la `description`: *"Emite el plan en dos formatos: un .md legible y un plan.json consumible por el harness."*

2. Reemplazar la sección `## Salida` para que además del `.md` (que se conserva tal cual) exija el JSON:

```markdown
## Salida — dos archivos hermanos

### 1. `plan.md` — para el humano

El mismo documento de 12 secciones de la v2, sin cambios. Es lo que el usuario lee.

### 2. `plan.json` — para el harness

El mismo plan en forma consumible por código. Va en
`.harness/tickets/<ticket_id>/plan.json`. El `.md` y el `.json` describen el mismo
plan: si difieren, el `.json` es el que ejecuta el harness, así que revísalo con el
mismo cuidado.

```json
{
  "ticket_id": "ISR-110722",
  "perfil": "reviewsystemgfs",
  "generado_por": "task-planner-v3",
  "fases": [
    {
      "id": "fase_1",
      "titulo": "Agregar campo de comentario en la sección Other Q",
      "pasos": [
        "Declarar el control nuevo en el markup y en el designer",
        "Guardar el valor mediante el SP existente",
        "Releer el valor al cargar la sección"
      ],
      "anclajes": [
        { "ref": "frmReviewReport.aspx.vb:412", "confianza": "verificado" },
        { "ref": "Sps/dbo.ReviewInsUpd.StoredProcedure.sql:88", "confianza": "por_confirmar" }
      ],
      "criterio_exito": "El comentario se guarda al presionar Save y se relee al reabrir la review",
      "checks_deterministas": ["audit_comments", "no_new_deps", "fw35_syntax", "designer_sync"],
      "prueba_manual": { "requerida": true, "url": "frmReviewReport.aspx", "datos": "review 4471, idioma EN" },
      "herramientas_permitidas": ["read", "edit"],
      "max_reintentos": 3,
      "depende_de": []
    }
  ]
}
```

Cómo llenar cada campo nuevo:

- **`anclajes`**: los hallazgos de la Fase 0, con la misma etiqueta de confianza que
  usaste en el `.md` — `✅ Verificado` → `"verificado"`, `⚠️ Por confirmar` →
  `"por_confirmar"`. No inventes anclas: si no leíste el archivo, es `por_confirmar`.
- **`criterio_exito`**: verificable, no aspiracional. "El campo se guarda y se relee"
  sirve; "el guardado funciona correctamente" no, porque nadie puede juzgarlo.
- **`checks_deterministas`**: nombres de checks o de grupos declarados en el
  `rules.json` del perfil. **Léelo antes de escribirlos** — un nombre inexistente hace
  fallar la validación del plan, no se ignora en silencio.
- **`prueba_manual.requerida`**: `false` solo si el cambio no tiene efecto observable
  en la aplicación (por ejemplo, únicamente documentación). En un proyecto sin build ni
  tests, casi todo cambio de código la requiere.
- **`herramientas_permitidas`**: lo mínimo que la fase necesita. Si una fase solo lee,
  no le des permiso de escribir.
- **`max_reintentos`**: 3 por defecto. Súbelo solo en fases donde el acierto al primer
  intento sea improbable; bájalo a 1 en fases de alto riesgo, donde prefieres escalar
  a un humano antes que dejar al agente insistir.
- **`depende_de`**: ids de fases del mismo plan. El harness rechaza abrir una fase
  cuya dependencia no esté aprobada, así que estas dependencias son ejecutables, no
  decorativas.
```

3. Añadir al final del `## Checklist antes de entregar el plan`:

```markdown
- [ ] Se emitió `plan.json` además de `plan.md`, y ambos describen el mismo plan.
- [ ] Se leyó el `rules.json` del perfil y todos los `checks_deterministas` existen ahí.
- [ ] `plan.json` pasa la validación:
      `python "$HOME/.claude/hooks/cli.py" validate --contrato plan --archivo <ruta>`
- [ ] Cada `criterio_exito` es comprobable por alguien que no leyó el código.
```

- [ ] **Step 4: Correr para verificar que pasa**

Run: `python -m unittest tests.test_planner_v3 -v`
Expected: PASS, 5 pruebas.

- [ ] **Step 5: Commit**

```bash
git add harness/skills/task-planner/SKILL.md tests/test_planner_v3.py
git commit -m "feat(planner): v3 que emite plan.json validado además del plan.md"
```

---

### Task 17: `designer_sync.py` — el error #1 de Web Forms

**Files:**
- Create: `profiles/reviewsystemgfs/checks/designer_sync.py`
- Test: `tests/test_designer_sync.py`

**Interfaces:**
- Consumes: la interfaz de plugin de Task 10 — `run(project_root, archivos_modificados, ctx) -> list[Finding]`.
- Produces: hallazgos con `id: "designer_sync"`. Dos direcciones: control declarado en el `.aspx` pero ausente del `.designer.vb` → `error` (no compila); identificador con prefijo de control usado en el `.aspx.vb` pero no declarado → `warning` (es heurística por nombre y puede equivocarse).

- [ ] **Step 1: Escribir las pruebas que fallan**

Crear `tests/test_designer_sync.py`:

```python
import importlib.util
import tempfile
import unittest
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
MODULO = RAIZ / "profiles" / "reviewsystemgfs" / "checks" / "designer_sync.py"


def cargar():
    especificacion = importlib.util.spec_from_file_location("designer_sync", MODULO)
    modulo = importlib.util.module_from_spec(especificacion)
    especificacion.loader.exec_module(modulo)
    return modulo


ASPX = """<%@ Page Language="vb" %>
<asp:HiddenField ID="hdnExistente" runat="server" />
<asp:HiddenField ID="hdnNuevoCampo" runat="server" />
<div id="soloHtml"></div>
"""

DESIGNER = """Partial Class frmReviewReport
    Protected WithEvents hdnExistente As Global.System.Web.UI.WebControls.HiddenField
End Class
"""

CODEBEHIND = """Partial Class frmReviewReport
    Private Sub Guardar()
        Dim valor As String = hdnExistente.Value
        Dim otro As String = hdnSinDeclarar.Value
    End Sub
End Class
"""


class TestDesignerSync(unittest.TestCase):
    def setUp(self):
        self.modulo = cargar()
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        (self.root / "frmReviewReport.aspx").write_text(ASPX, encoding="utf-8")
        (self.root / "frmReviewReport.aspx.designer.vb").write_text(DESIGNER, encoding="utf-8")
        (self.root / "frmReviewReport.aspx.vb").write_text(CODEBEHIND, encoding="utf-8")

    def correr(self, *nombres: str):
        archivos = [self.root / n for n in nombres]
        return self.modulo.run(self.root, archivos, None)

    def test_control_del_aspx_sin_declarar_es_error(self):
        hallazgos = self.correr("frmReviewReport.aspx")
        errores = [h for h in hallazgos if h["severidad"] == "error"]
        self.assertTrue(any("hdnNuevoCampo" in h["detalle"] for h in errores))

    def test_no_marca_el_control_que_si_esta_declarado(self):
        hallazgos = self.correr("frmReviewReport.aspx")
        self.assertFalse(any("hdnExistente" in h["detalle"] for h in hallazgos))

    def test_ignora_un_div_html_sin_runat_server(self):
        hallazgos = self.correr("frmReviewReport.aspx")
        self.assertFalse(any("soloHtml" in h["detalle"] for h in hallazgos))

    def test_identificador_del_codebehind_sin_declarar_es_warning(self):
        hallazgos = self.correr("frmReviewReport.aspx.vb")
        avisos = [h for h in hallazgos if h["severidad"] == "warning"]
        self.assertTrue(any("hdnSinDeclarar" in h["detalle"] for h in avisos))

    def test_todo_declarado_no_produce_hallazgos(self):
        (self.root / "frmReviewReport.aspx.designer.vb").write_text(
            DESIGNER.replace("End Class",
                             "    Protected WithEvents hdnNuevoCampo As "
                             "Global.System.Web.UI.WebControls.HiddenField\n"
                             "    Protected WithEvents hdnSinDeclarar As "
                             "Global.System.Web.UI.WebControls.HiddenField\nEnd Class"),
            encoding="utf-8")
        self.assertEqual(self.correr("frmReviewReport.aspx", "frmReviewReport.aspx.vb"), [])

    def test_ignora_archivos_de_otro_tipo(self):
        (self.root / "otro.js").write_text("var hdnFalso = 1;\n", encoding="utf-8")
        self.assertEqual(self.correr("otro.js"), [])

    def test_un_designer_ausente_es_error_check_y_no_falso_positivo(self):
        (self.root / "frmReviewReport.aspx.designer.vb").unlink()
        hallazgos = self.correr("frmReviewReport.aspx")
        self.assertTrue(any(h["resultado"] == "error_check" for h in hallazgos))
        self.assertFalse(any(h["resultado"] == "fallo" for h in hallazgos))


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Correr para verificar que falla**

Run: `python -m unittest tests.test_designer_sync -v`
Expected: FAIL con `FileNotFoundError` sobre `designer_sync.py`.

- [ ] **Step 3: Implementar el check**

Crear `profiles/reviewsystemgfs/checks/designer_sync.py`:

```python
"""Check estructural: coherencia .aspx <-> .aspx.designer.vb <-> .aspx.vb.

Sin VS2008 en el ciclo, el error de compilación más común de Web Forms es un
control usado sin declarar en el designer. Esto lo atrapa antes de que llegue
al humano.
"""
from __future__ import annotations

import re
import traceback
from pathlib import Path

CHECK_ID = "designer_sync"

RE_CONTROL_ASPX = re.compile(
    r"<asp:[\w.]+[^>]*?\bID\s*=\s*[\"'](?P<id>\w+)[\"'][^>]*?>", re.IGNORECASE | re.DOTALL)
RE_RUNAT = re.compile(
    r"<[^>]*?\bID\s*=\s*[\"'](?P<id>\w+)[\"'][^>]*?runat\s*=\s*[\"']server[\"'][^>]*?>",
    re.IGNORECASE | re.DOTALL)
RE_DECLARACION = re.compile(r"Protected\s+WithEvents\s+(?P<id>\w+)\s+As\s", re.IGNORECASE)
# Prefijos de control usados en el proyecto; la heurística solo mira estos.
RE_USO_CODEBEHIND = re.compile(
    r"\b(?P<id>(?:hdn|txt|btn|lbl|ddl|grd|chk|rdb|pnl|lnk|img|rpt)\w+)\s*\.")


def _leer(ruta: Path) -> str:
    return ruta.read_text(encoding="utf-8", errors="replace")


def _hallazgo(severidad: str, detalle: str, resultado: str = "fallo") -> dict:
    return {"id": CHECK_ID, "resultado": resultado,
            "severidad": severidad, "detalle": detalle}


def _base_de(ruta: Path) -> Path:
    """De cualquiera de los tres archivos, la ruta base sin sufijos."""
    nombre = ruta.name
    for sufijo in (".aspx.designer.vb", ".aspx.vb", ".aspx"):
        if nombre.lower().endswith(sufijo):
            return ruta.with_name(nombre[: -len(sufijo)])
    return ruta


def _declarados(base: Path) -> set[str] | None:
    designer = base.with_name(base.name + ".aspx.designer.vb")
    if not designer.is_file():
        return None
    return {m.group("id") for m in RE_DECLARACION.finditer(_leer(designer))}


def run(project_root: Path, archivos_modificados: list[Path], ctx: dict | None) -> list[dict]:
    hallazgos: list[dict] = []
    bases: set[Path] = set()
    for archivo in archivos_modificados:
        nombre = archivo.name.lower()
        if nombre.endswith((".aspx", ".aspx.vb", ".aspx.designer.vb")):
            bases.add(_base_de(archivo))

    for base in sorted(bases):
        try:
            declarados = _declarados(base)
            if declarados is None:
                hallazgos.append(_hallazgo(
                    "error", f"{base.name}: no se encontró el .aspx.designer.vb, no se "
                             f"pudo verificar la declaración de controles",
                    resultado="error_check"))
                continue

            aspx = base.with_name(base.name + ".aspx")
            if aspx.is_file():
                texto = _leer(aspx)
                ids = {m.group("id") for m in RE_CONTROL_ASPX.finditer(texto)}
                ids |= {m.group("id") for m in RE_RUNAT.finditer(texto)}
                for control in sorted(ids - declarados):
                    hallazgos.append(_hallazgo(
                        "error",
                        f"{aspx.name}: el control '{control}' está en el markup pero no "
                        f"declarado en {base.name}.aspx.designer.vb — no compila en VS2008"))

            codebehind = base.with_name(base.name + ".aspx.vb")
            if codebehind.is_file():
                usados = {m.group("id") for m in RE_USO_CODEBEHIND.finditer(_leer(codebehind))}
                for control in sorted(usados - declarados):
                    hallazgos.append(_hallazgo(
                        "warning",
                        f"{codebehind.name}: '{control}' parece un control (por su prefijo) "
                        f"y no está declarado en el designer. Si es una variable local, "
                        f"ignora este aviso"))
        except Exception:
            hallazgos.append(_hallazgo("error", traceback.format_exc(),
                                       resultado="error_check"))
    return hallazgos
```

- [ ] **Step 4: Correr para verificar que pasa**

Run: `python -m unittest tests.test_designer_sync -v`
Expected: PASS, 7 pruebas.

- [ ] **Step 5: Validar contra el código real**

Run: `python "$HOME/.claude/hooks/cli.py" run-checks --project "<ruta de ReviewSystemGFS>"` con un cambio real en curso.
Expected: cero falsos positivos sobre los controles preexistentes. Si aparecen, ajustar los regex — **no** relajar la prueba ni bajar la severidad del primer caso, que sí es un error de compilación real.

- [ ] **Step 6: Commit**

```bash
git add profiles/reviewsystemgfs/checks/designer_sync.py tests/test_designer_sync.py
git commit -m "feat(checks): designer_sync como sustituto parcial del compilador ausente"
```

---

### Task 18: `sp_params.py` — el fallo más caro del stack

Este es el check con mayor retorno del plan: detecta el caso en que el VB envía un `Vn` que el SP nunca parsea. No falla en ningún lado — el dato simplemente desaparece — y hoy solo se detecta haciendo los pasos en la web.

**Files:**
- Create: `profiles/reviewsystemgfs/checks/sp_params.py`
- Test: `tests/test_sp_params.py`

**Interfaces:**
- Consumes: la interfaz de plugin de Task 10.
- Produces: hallazgos con `id: "sp_params"`. `Vn` enviado y no parseado → `error`. `@Validar` sin rama en el SP → `error`. SP no encontrado en `Sps/` → `warning` (puede vivir solo en la base).

- [ ] **Step 1: Escribir las pruebas que fallan**

Crear `tests/test_sp_params.py`:

```python
import importlib.util
import tempfile
import unittest
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
MODULO = RAIZ / "profiles" / "reviewsystemgfs" / "checks" / "sp_params.py"


def cargar():
    especificacion = importlib.util.spec_from_file_location("sp_params", MODULO)
    modulo = importlib.util.module_from_spec(especificacion)
    especificacion.loader.exec_module(modulo)
    return modulo


VB = """Partial Class frmReviewReport
    Private Sub Guardar()
        Dim parametros As String = "|V9=" + hdnReviewHeaderID.Value + "|V21=" + txtNuevo.Value + "|"
        Dim objRet = lConsulta.EjecutarSp("ReviewInsUpd", 7, parametros, ds, "")
    End Sub
End Class
"""

SP_COMPLETO = """CREATE Proc [dbo].[ReviewInsUpd]
(
  @Parametros Varchar(8000),
  @Resul Varchar(8000) Output,
  @DataSet XML = '',
  @Validar Int = 0
)
As
Begin
  Exec SepararCadena 'V9', @Parametros, '|', @Valor9 OutPut
  Exec SepararCadena 'V21', @Parametros, '|', @Valor21 OutPut

  if @Validar = 7
  begin
     Update ReviewHeader set NewField = @Valor21 where ReviewHeaderID = @Valor9
  end
End
"""


class TestSpParams(unittest.TestCase):
    def setUp(self):
        self.modulo = cargar()
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        (self.root / "Sps").mkdir()
        self.vb = self.root / "frmReviewReport.aspx.vb"
        self.vb.write_text(VB, encoding="utf-8")
        self.sp = self.root / "Sps" / "dbo.ReviewInsUpd.StoredProcedure.sql"
        self.sp.write_text(SP_COMPLETO, encoding="utf-8")

    def correr(self):
        return self.modulo.run(self.root, [self.vb], None)

    def test_todo_coherente_no_produce_hallazgos(self):
        self.assertEqual(self.correr(), [])

    def test_un_vn_que_el_sp_no_parsea_es_error(self):
        self.sp.write_text(SP_COMPLETO.replace(
            "  Exec SepararCadena 'V21', @Parametros, '|', @Valor21 OutPut\n", ""),
            encoding="utf-8")
        hallazgos = self.correr()
        self.assertTrue(any("V21" in h["detalle"] and h["severidad"] == "error"
                            for h in hallazgos))

    def test_el_mensaje_explica_que_el_dato_se_pierde_en_silencio(self):
        self.sp.write_text(SP_COMPLETO.replace(
            "  Exec SepararCadena 'V21', @Parametros, '|', @Valor21 OutPut\n", ""),
            encoding="utf-8")
        detalle = next(h["detalle"] for h in self.correr() if "V21" in h["detalle"])
        self.assertIn("silencio", detalle.lower())

    def test_un_validar_sin_rama_en_el_sp_es_error(self):
        self.sp.write_text(SP_COMPLETO.replace("if @Validar = 7", "if @Validar = 8"),
                           encoding="utf-8")
        hallazgos = self.correr()
        self.assertTrue(any("@Validar" in h["detalle"] and "7" in h["detalle"]
                            and h["severidad"] == "error" for h in hallazgos))

    def test_un_sp_que_no_esta_en_sps_es_solo_warning(self):
        self.sp.unlink()
        hallazgos = self.correr()
        self.assertTrue(hallazgos)
        self.assertTrue(all(h["severidad"] == "warning" for h in hallazgos))

    def test_ignora_archivos_que_no_son_vb(self):
        otro = self.root / "frm.js"
        otro.write_text("var p = '|V99=' + x;\n", encoding="utf-8")
        self.assertEqual(self.modulo.run(self.root, [otro], None), [])

    def test_soporta_varias_llamadas_a_sps_distintos(self):
        self.vb.write_text(VB + """
    Private Sub Buscar()
        Dim p As String = "|V0=3|V1=" + hdnLanguageID.Value + "|"
        Dim r = lConsulta.EjecutarSp("ReviewGetFilters", 4, p)
    End Sub
""", encoding="utf-8")
        (self.root / "Sps" / "dbo.ReviewGetFilters.StoredProcedure.sql").write_text(
            "CREATE Proc [dbo].[ReviewGetFilters]\nAs\nBegin\n"
            "  Exec SepararCadena 'V0', @Parametros, '|', @Valor0 OutPut\n"
            "  if @Validar = 4 begin Select 1 end\n"
            "End\n", encoding="utf-8")
        hallazgos = self.correr()
        self.assertTrue(any("V1" in h["detalle"] for h in hallazgos))


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Correr para verificar que falla**

Run: `python -m unittest tests.test_sp_params -v`
Expected: FAIL con `FileNotFoundError` sobre `sp_params.py`.

- [ ] **Step 3: Implementar el check**

Crear `profiles/reviewsystemgfs/checks/sp_params.py`:

```python
"""Check estructural: los |Vn= que el VB envía vs. los que el SP parsea.

El fallo más caro del stack: se envía V21, el SP nunca lo parsea, no falla en
ningún lado y el dato desaparece. Sin este check solo se detecta haciendo los
pasos en la aplicación.

Limitación conocida: un archivo que construye la cadena de parámetros en
fragmentos separados de la llamada a EjecutarSp puede producir atribuciones
imprecisas. Por eso el alcance es por bloque de método: se asocian los Vn de
un método con los SPs llamados en ese mismo método.
"""
from __future__ import annotations

import re
import traceback
from pathlib import Path

CHECK_ID = "sp_params"

RE_METODO = re.compile(
    r"(?:Private|Public|Protected|Friend)?\s*(?:Shared\s+)?(?:Sub|Function)\s+\w+.*?"
    r"End\s+(?:Sub|Function)", re.IGNORECASE | re.DOTALL)
RE_VN_ENVIADO = re.compile(r"\|(?P<vn>V\d{1,2})\s*=")
RE_LLAMADA_SP = re.compile(
    r"EjecutarSp\s*\(\s*[\"'](?P<sp>\w+)[\"']\s*,\s*(?P<validar>\d+)", re.IGNORECASE)
RE_VN_PARSEADO = re.compile(r"SepararCadena\s+'(?P<vn>V\d{1,2})'", re.IGNORECASE)
RE_RAMA_VALIDAR = re.compile(r"@Validar\s*=\s*(?P<n>\d+)", re.IGNORECASE)


def _leer(ruta: Path) -> str:
    return ruta.read_text(encoding="utf-8", errors="replace")


def _hallazgo(severidad: str, detalle: str, resultado: str = "fallo") -> dict:
    return {"id": CHECK_ID, "resultado": resultado,
            "severidad": severidad, "detalle": detalle}


def _ruta_sp(project_root: Path, nombre: str) -> Path | None:
    carpeta = Path(project_root) / "Sps"
    if not carpeta.is_dir():
        return None
    for ruta in carpeta.glob("*.sql"):
        if nombre.lower() in ruta.name.lower():
            return ruta
    return None


def run(project_root: Path, archivos_modificados: list[Path], ctx: dict | None) -> list[dict]:
    hallazgos: list[dict] = []
    for archivo in archivos_modificados:
        if not archivo.name.lower().endswith(".vb"):
            continue
        if archivo.name.lower().endswith(".designer.vb"):
            continue
        try:
            hallazgos += _revisar_vb(project_root, archivo)
        except Exception:
            hallazgos.append(_hallazgo("error", traceback.format_exc(),
                                       resultado="error_check"))
    return hallazgos


def _revisar_vb(project_root: Path, archivo: Path) -> list[dict]:
    hallazgos: list[dict] = []
    texto = _leer(archivo)
    for bloque in RE_METODO.findall(texto):
        llamadas = list(RE_LLAMADA_SP.finditer(bloque))
        if not llamadas:
            continue
        enviados = {m.group("vn").upper() for m in RE_VN_ENVIADO.finditer(bloque)}

        for llamada in llamadas:
            nombre_sp = llamada.group("sp")
            validar = llamada.group("validar")
            ruta_sp = _ruta_sp(project_root, nombre_sp)
            if ruta_sp is None:
                hallazgos.append(_hallazgo(
                    "warning",
                    f"{archivo.name}: se llama al SP '{nombre_sp}' pero no hay un .sql "
                    f"correspondiente en Sps/ — no se pudo verificar sus parámetros"))
                continue

            texto_sp = _leer(ruta_sp)
            parseados = {m.group("vn").upper() for m in RE_VN_PARSEADO.finditer(texto_sp)}
            ramas = {m.group("n") for m in RE_RAMA_VALIDAR.finditer(texto_sp)}

            for vn in sorted(enviados - parseados):
                hallazgos.append(_hallazgo(
                    "error",
                    f"{archivo.name}: se envía {vn} a '{nombre_sp}' pero el SP no lo "
                    f"parsea con SepararCadena — el valor se perdería en silencio, sin "
                    f"error en ninguna capa ({ruta_sp.name})"))

            if ramas and validar not in ramas:
                hallazgos.append(_hallazgo(
                    "error",
                    f"{archivo.name}: se llama a '{nombre_sp}' con @Validar = {validar} "
                    f"pero el SP no tiene esa rama (tiene: "
                    f"{', '.join(sorted(ramas, key=int))}) — el SP no haría nada"))
    return hallazgos
```

- [ ] **Step 4: Correr para verificar que pasa**

Run: `python -m unittest tests.test_sp_params -v`
Expected: PASS, 7 pruebas.

- [ ] **Step 5: Validar contra un caso real conocido**

Buscar en el repo de ReviewSystemGFS una llamada donde el check acierte y otra donde se equivoque, y anotar ambas en `docs/hallazgos-primer-ticket.md`. Si produce ruido en archivos con muchas llamadas, la salida correcta es afinar el alcance por método — no bajar la severidad, porque el hallazgo que atrapa es real y caro.

- [ ] **Step 6: Commit**

```bash
git add profiles/reviewsystemgfs/checks/sp_params.py tests/test_sp_params.py
git commit -m "feat(checks): sp_params detecta Vn no parseados y @Validar sin rama"
```

---

### Task 19: `xhtml_selfclose.py`

**Files:**
- Create: `profiles/reviewsystemgfs/checks/xhtml_selfclose.py`
- Test: `tests/test_xhtml_selfclose.py`

**Interfaces:**
- Consumes: la interfaz de plugin de Task 10; `gitdiff.added_lines` para limitarse a lo agregado.
- Produces: hallazgos con `id: "xhtml_selfclose"`, severidad `warning` (XHTML Transitional es tolerante en la práctica, y el markup viejo del repo está lleno de estos casos).

- [ ] **Step 1: Escribir las pruebas que fallan**

Crear `tests/test_xhtml_selfclose.py`:

```python
import importlib.util
import subprocess
import tempfile
import unittest
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
MODULO = RAIZ / "profiles" / "reviewsystemgfs" / "checks" / "xhtml_selfclose.py"


def cargar():
    especificacion = importlib.util.spec_from_file_location("xhtml_selfclose", MODULO)
    modulo = importlib.util.module_from_spec(especificacion)
    especificacion.loader.exec_module(modulo)
    return modulo


def _git(root: Path, *args: str) -> None:
    subprocess.run(["git", *args], cwd=root, check=True, capture_output=True, text=True)


class TestXhtmlSelfClose(unittest.TestCase):
    def setUp(self):
        self.modulo = cargar()
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        _git(self.root, "init")
        _git(self.root, "config", "user.email", "t@t.t")
        _git(self.root, "config", "user.name", "t")
        self.aspx = self.root / "frm.aspx"
        self.aspx.write_text("<div>viejo sin cerrar <br> aqui</div>\n", encoding="utf-8")
        _git(self.root, "add", ".")
        _git(self.root, "commit", "-m", "base")

    def correr(self):
        return self.modulo.run(self.root, [self.aspx], None)

    def test_un_br_agregado_sin_cerrar_es_warning(self):
        self.aspx.write_text("<div>viejo sin cerrar <br> aqui</div>\n<p>nuevo<br></p>\n",
                             encoding="utf-8")
        hallazgos = self.correr()
        self.assertEqual(len(hallazgos), 1)
        self.assertEqual(hallazgos[0]["severidad"], "warning")
        self.assertIn("br", hallazgos[0]["detalle"])

    def test_no_marca_el_markup_viejo_que_no_se_toco(self):
        self.aspx.write_text("<div>viejo sin cerrar <br> aqui</div>\n<p>nuevo</p>\n",
                             encoding="utf-8")
        self.assertEqual(self.correr(), [])

    def test_un_tag_correctamente_autocerrado_no_produce_hallazgos(self):
        self.aspx.write_text("<div>viejo sin cerrar <br> aqui</div>\n"
                             "<img src='x.png' alt='x' />\n", encoding="utf-8")
        self.assertEqual(self.correr(), [])

    def test_detecta_img_e_input_sin_cerrar(self):
        self.aspx.write_text("<div>viejo sin cerrar <br> aqui</div>\n"
                             "<img src='x.png'>\n<input type='text'>\n", encoding="utf-8")
        detalles = " ".join(h["detalle"] for h in self.correr())
        self.assertIn("img", detalles)
        self.assertIn("input", detalles)

    def test_ignora_archivos_que_no_son_aspx(self):
        otro = self.root / "frm.js"
        otro.write_text("var html = '<br>';\n", encoding="utf-8")
        self.assertEqual(self.modulo.run(self.root, [otro], None), [])


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Correr para verificar que falla**

Run: `python -m unittest tests.test_xhtml_selfclose -v`
Expected: FAIL con `FileNotFoundError`.

- [ ] **Step 3: Implementar el check**

Crear `profiles/reviewsystemgfs/checks/xhtml_selfclose.py`:

```python
"""Check estructural: tags vacíos sin autocerrar en markup XHTML 1.0 Transitional.

Solo mira las líneas agregadas: el markup existente del repo está lleno de
estos casos y marcarlos sería ruido, no información.
"""
from __future__ import annotations

import importlib.util
import re
import sys
import traceback
from pathlib import Path

CHECK_ID = "xhtml_selfclose"
VACIOS = ("br", "img", "input", "hr", "meta", "link", "area", "base", "col")
RE_TAG_ABIERTO = re.compile(
    r"<(?P<tag>" + "|".join(VACIOS) + r")\b(?P<cuerpo>[^>]*?)>", re.IGNORECASE)


def _cargar_gitdiff():
    """Importa lib.gitdiff del harness genérico, esté instalado o en el repo fuente."""
    for candidato in (Path(sys.argv[0]).resolve().parent / "lib" / "gitdiff.py",
                      Path.home() / ".claude" / "hooks" / "lib" / "gitdiff.py"):
        if candidato.is_file():
            especificacion = importlib.util.spec_from_file_location(
                "harness_gitdiff", candidato)
            modulo = importlib.util.module_from_spec(especificacion)
            especificacion.loader.exec_module(modulo)
            return modulo
    raise ImportError("no se encontró lib/gitdiff.py del harness")


def run(project_root: Path, archivos_modificados: list[Path], ctx: dict | None) -> list[dict]:
    hallazgos: list[dict] = []
    try:
        gitdiff = _cargar_gitdiff()
    except ImportError as error:
        return [{"id": CHECK_ID, "resultado": "error_check", "severidad": "warning",
                 "detalle": str(error)}]

    for archivo in archivos_modificados:
        if not archivo.name.lower().endswith(".aspx"):
            continue
        try:
            agregadas = gitdiff.added_lines(project_root, archivo) or []
            for numero, texto in agregadas:
                for encontrado in RE_TAG_ABIERTO.finditer(texto):
                    if encontrado.group("cuerpo").rstrip().endswith("/"):
                        continue
                    hallazgos.append({
                        "id": CHECK_ID, "resultado": "fallo", "severidad": "warning",
                        "detalle": f"{archivo.name}:{numero} <"
                                   f"{encontrado.group('tag')}> sin autocerrar; "
                                   f"XHTML 1.0 Transitional exige <"
                                   f"{encontrado.group('tag')} ... />"})
        except Exception:
            hallazgos.append({"id": CHECK_ID, "resultado": "error_check",
                              "severidad": "warning", "detalle": traceback.format_exc()})
    return hallazgos
```

- [ ] **Step 4: Correr para verificar que pasa**

Run: `python -m unittest tests.test_xhtml_selfclose -v`
Expected: PASS, 5 pruebas.

- [ ] **Step 5: Commit**

```bash
git add profiles/reviewsystemgfs/checks/xhtml_selfclose.py tests/test_xhtml_selfclose.py
git commit -m "feat(checks): xhtml_selfclose sobre las líneas agregadas"
```

---

### Task 20: `report.py` — observabilidad y ciclo de mejora

**Files:**
- Create: `harness/hooks/report.py`
- Modify: `harness/hooks/cli.py`
- Test: `tests/test_report.py`

**Interfaces:**
- Consumes: `harness`, la estructura de `.harness/tickets/`.
- Produces:
  - `report.agregar(project_root) -> dict` con claves `tickets`, `fases`, `intentos_por_fase`, `origen_de_fallos`, `reglas_mas_violadas`, `fases_escaladas`, `fallos_recurrentes_del_esceptico`.
  - `report.render(datos: dict) -> str` — texto para la terminal.
  - CLI: `python cli.py report --project <ruta>` y `--json` para la salida cruda.

- [ ] **Step 1: Escribir las pruebas que fallan**

Crear `tests/test_report.py`:

```python
import sys
import tempfile
import unittest
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ / "harness" / "hooks"))
import report  # noqa: E402
from lib import harness  # noqa: E402


class TestReport(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.sembrar("ISR-1", "fase_1", "aprobada", 2, [
            {"intento": 1, "origen": "check", "razon": "designer_sync: control sin declarar",
             "correccion_aplicada": "se declaró"}])
        self.sembrar("ISR-2", "fase_1", "escalado", 3, [
            {"intento": 1, "origen": "esceptico", "razon": "no valida el email", "correccion_aplicada": ""},
            {"intento": 2, "origen": "esceptico", "razon": "no valida el email", "correccion_aplicada": ""},
            {"intento": 3, "origen": "humano", "razon": "prueba manual: falló en el paso 2 — nada",
             "correccion_aplicada": ""}])

    def sembrar(self, ticket, fase, estado, intento, historial):
        harness.write_json(
            harness.fase_dir(self.root, ticket, fase) / "fase_state.json",
            {"fase_id": fase, "estado": estado, "intento_actual": intento,
             "max_reintentos": 3, "historial_fallos": historial})
        harness.write_json(
            harness.intento_dir(self.root, ticket, fase, 1) / "checks.json",
            {"fase_id": fase, "intento": 1, "resultado": "fallo",
             "checks": [{"id": "designer_sync", "resultado": "fallo",
                         "severidad": "error", "detalle": "x"}]})

    def test_cuenta_tickets_y_fases(self):
        datos = report.agregar(self.root)
        self.assertEqual(datos["tickets"], 2)
        self.assertEqual(datos["fases"], 2)

    def test_reporta_las_fases_escaladas(self):
        self.assertEqual(report.agregar(self.root)["fases_escaladas"], ["ISR-2/fase_1"])

    def test_distribuye_el_origen_de_los_fallos(self):
        origen = report.agregar(self.root)["origen_de_fallos"]
        self.assertEqual(origen["esceptico"], 2)
        self.assertEqual(origen["check"], 1)
        self.assertEqual(origen["humano"], 1)

    def test_detecta_el_fallo_recurrente_del_esceptico(self):
        recurrentes = report.agregar(self.root)["fallos_recurrentes_del_esceptico"]
        self.assertTrue(any("email" in r["razon"] and r["veces"] == 2 for r in recurrentes))

    def test_cuenta_las_reglas_mas_violadas(self):
        self.assertEqual(report.agregar(self.root)["reglas_mas_violadas"]["designer_sync"], 2)

    def test_el_render_sugiere_convertir_juicio_en_check(self):
        texto = report.render(report.agregar(self.root))
        self.assertIn("check determinista", texto)
        self.assertIn("email", texto)

    def test_un_proyecto_sin_tickets_no_revienta(self):
        with tempfile.TemporaryDirectory() as vacio:
            datos = report.agregar(Path(vacio))
            self.assertEqual(datos["tickets"], 0)
            self.assertIsInstance(report.render(datos), str)


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Correr para verificar que falla**

Run: `python -m unittest tests.test_report -v`
Expected: FAIL con `ModuleNotFoundError: No module named 'report'`.

- [ ] **Step 3: Implementar el reporte**

Crear `harness/hooks/report.py`:

```python
#!/usr/bin/env python3
"""Observabilidad del harness.

La pregunta que este reporte existe para responder: ¿qué fallos detecta hoy un
modelo caro que podría detectar mañana un script gratis? Esa lista es el
trabajo pendiente de mejora del harness.
"""
from __future__ import annotations

import json
from collections import Counter
from pathlib import Path

from lib import harness

UMBRAL_RECURRENCIA = 2


def agregar(project_root: Path) -> dict:
    carpeta = harness.tickets_dir(project_root)
    datos = {
        "tickets": 0, "fases": 0, "intentos_por_fase": {}, "fases_escaladas": [],
        "origen_de_fallos": Counter(), "reglas_mas_violadas": Counter(),
        "fallos_recurrentes_del_esceptico": [],
    }
    if not carpeta.is_dir():
        datos["origen_de_fallos"] = dict(datos["origen_de_fallos"])
        datos["reglas_mas_violadas"] = dict(datos["reglas_mas_violadas"])
        return datos

    razones_esceptico: Counter = Counter()
    for ticket in sorted(p for p in carpeta.iterdir() if p.is_dir()):
        datos["tickets"] += 1
        for fase in sorted(p for p in ticket.iterdir() if p.is_dir()):
            estado_path = fase / "fase_state.json"
            if not estado_path.is_file():
                continue
            estado = harness.read_json(estado_path)
            clave = f"{ticket.name}/{fase.name}"
            datos["fases"] += 1
            datos["intentos_por_fase"][clave] = {
                "intentos": estado["intento_actual"],
                "max": estado["max_reintentos"],
                "estado": estado["estado"],
            }
            if estado["estado"] == "escalado":
                datos["fases_escaladas"].append(clave)
            for fallo in estado.get("historial_fallos") or []:
                datos["origen_de_fallos"][fallo["origen"]] += 1
                if fallo["origen"] == "esceptico":
                    razones_esceptico[fallo["razon"].strip()] += 1
            for intento in sorted(p for p in fase.iterdir() if p.is_dir()):
                checks_path = intento / "checks.json"
                if not checks_path.is_file():
                    continue
                for check in harness.read_json(checks_path).get("checks") or []:
                    if check.get("resultado") == "fallo":
                        datos["reglas_mas_violadas"][check["id"]] += 1

    datos["fallos_recurrentes_del_esceptico"] = [
        {"razon": razon, "veces": veces}
        for razon, veces in razones_esceptico.most_common()
        if veces >= UMBRAL_RECURRENCIA]
    datos["origen_de_fallos"] = dict(datos["origen_de_fallos"])
    datos["reglas_mas_violadas"] = dict(datos["reglas_mas_violadas"])
    return datos


def render(datos: dict) -> str:
    lineas = ["HARNESS · reporte", "=" * 50,
              f"Tickets: {datos['tickets']}   Fases: {datos['fases']}", ""]

    if datos["intentos_por_fase"]:
        lineas.append("Intentos por fase")
        for clave, info in datos["intentos_por_fase"].items():
            lineas.append(f"  {clave}: {info['intentos']}/{info['max']} "
                          f"({info['estado']})")
        lineas.append("")

    if datos["fases_escaladas"]:
        lineas.append("Fases escaladas (requieren intervención humana)")
        lineas += [f"  {clave}" for clave in datos["fases_escaladas"]]
        lineas.append("")

    if datos["origen_de_fallos"]:
        lineas.append("Origen de los fallos")
        for origen, veces in sorted(datos["origen_de_fallos"].items(),
                                    key=lambda par: -par[1]):
            lineas.append(f"  {origen}: {veces}")
        lineas.append("")

    if datos["reglas_mas_violadas"]:
        lineas.append("Reglas más violadas")
        for regla, veces in sorted(datos["reglas_mas_violadas"].items(),
                                    key=lambda par: -par[1]):
            lineas.append(f"  {regla}: {veces}")
        lineas.append("")

    if datos["fallos_recurrentes_del_esceptico"]:
        lineas.append("Mejoras pendientes del harness")
        lineas.append("  Estos fallos los detecta hoy el escéptico (caro y opinable) más")
        lineas.append("  de una vez. Cada uno es un check determinista que falta escribir:")
        for entrada in datos["fallos_recurrentes_del_esceptico"]:
            lineas.append(f"    - {entrada['veces']}x: {entrada['razon']}")
        lineas.append("")
    else:
        lineas.append("Sin fallos recurrentes del escéptico: no hay check determinista "
                      "evidente por escribir todavía.")

    return "\n".join(lineas)


def main(project_root: Path, como_json: bool = False) -> int:
    datos = agregar(project_root)
    print(json.dumps(datos, ensure_ascii=False, indent=2) if como_json else render(datos))
    return 0
```

- [ ] **Step 4: Añadir el subcomando a `cli.py`**

Añadir `import report` después del bloque de imports de `lib`, y antes de `construir_parser`:

```python
def cmd_report(args) -> int:
    return report.main(resolver_proyecto(args.project), como_json=args.json)
```

Registrar:

```python
    p = sub.add_parser("report", help="Observabilidad: intentos, orígenes de fallo, mejoras")
    p.add_argument("--project")
    p.add_argument("--json", action="store_true")
    p.set_defaults(func=cmd_report)
```

- [ ] **Step 5: Correr para verificar que pasa**

Run: `python -m unittest tests.test_report -v`
Expected: PASS, 7 pruebas.

- [ ] **Step 6: Correr la suite completa**

Run: `python -m unittest discover -s tests -v`
Expected: PASS, 155 pruebas, cero fallos.

- [ ] **Step 7: Redesplegar y verificar contra el proyecto real**

Run: `.\deploy.ps1 -Proyecto "<ruta de ReviewSystemGFS>" -Perfil reviewsystemgfs`
Run: `python "$HOME/.claude/hooks/cli.py" report --project "<ruta de ReviewSystemGFS>"`
Expected: el reporte del ticket real completado en la Task 15, con sus intentos y orígenes de fallo.

- [ ] **Step 8: Commit**

```bash
git add harness/hooks/report.py harness/hooks/cli.py tests/test_report.py
git commit -m "feat(observabilidad): reporte de intentos, orígenes de fallo y mejoras pendientes"
```

---

## Autorepaso del plan

**1. Cobertura del spec.** Cada sección tiene tarea asignada:

| Sección del spec | Tarea(s) |
|---|---|
| §5 Arquitectura, tres planos | 1, 2, 2b, 15 (deploy) |
| §5.1 Estructura del repo fuente | 1, 15 |
| §5.2 Estado por ticket | 2, 8 |
| §6.1 `ticket_context.json` | 3, 8 |
| §6.2 `plan.json` | 3, 16 |
| §6.3 `checks.json` | 3, 10 |
| §6.4 `veredicto.json` | 3, 11, 12 |
| §6.5 `fase_state.json` | 3, 7 |
| §7 Ciclo de fase | 7, 10, 11, 12, 14 |
| §8.1 Reglas declarativas | 5, 6 |
| §8.2 Checks estructurales | 17, 18, 19 |
| §8.3 Verificación humana | 12 |
| §8.4 MCP opcional | Ninguna — es aditivo y fuera de alcance por §14 del spec. Documentado como tal |
| §9 Guardrails | 7 (contador), 9 (`PostToolUse`), 13 (`Stop`), 8 (contratos), 5+6 (`no_new_deps`) |
| §10 Observabilidad | 20 |
| §11 Migración de los tres archivos | 11 (escéptico), 14 (`agent-rsgfs`), 16 (planner) |
| §12 Manejo de errores | 6 y 10 (`error_check`), 8 (contratos), 9 y 13 (inertes sin perfil), 12 (nada por omisión) |
| §13 Estrategia de pruebas | Tareas 2-20 (fixtures y `unittest`), 15 (ciclo completo real) |
| §14 Alcance y orden | El orden de las tareas 1→20, con el checkpoint en la 15 |
| §15 Criterios de aceptación | Los 10 quedan cubiertos por las pruebas de las tareas 8-14 y verificados a mano en la 15 |

Un guardrail del spec queda parcial y está declarado como tal: `herramientas_permitidas` se valida en el contrato y se pasa al ejecutor (tareas 3, 14), pero su cumplimiento duro depende de los `permissions` de `settings.json` del proyecto, que se registran a mano en la Task 15. El spec ya lo marcaba "parcial"; el plan no lo mejora ni lo disimula.

**2. Placeholders.** Ninguna tarea contiene "TBD", "implementar después", "manejar errores apropiadamente" ni "similar a la tarea N". Todo paso que cambia código muestra el código. Las dos tareas sin código —15 (checkpoint) y los pasos de validación contra el repo real— son verificación humana declarada, no trabajo sin especificar.

**3. Consistencia de tipos.** Verificado a lo largo del plan: `find_project_root` devuelve `Path | None` y todos sus llamadores comprueban `None`; `added_lines` devuelve `list[tuple[int, str]] | None` y el `None` se trata como `error_check` en `run_file_checks`; los cinco `validate_*` devuelven `list[str]`; los checks estructurales cumplen la firma `run(project_root, archivos_modificados, ctx) -> list[Finding]` en las tres implementaciones (17, 18, 19); `state.registrar_fallo` recibe `origen` validado contra `contracts.ORIGENES`; y `_fase_activa` devuelve la misma tupla de cuatro elementos en los cuatro subcomandos que la usan.

Una corrección aplicada durante el repaso: `run-checks` (Task 10) filtra los checks declarativos excluyendo los `checks_estructurales`, para no pasarle a `run_file_checks` un id que solo un plugin sabe resolver. Sin ese filtro, un plan que pidiera `designer_sync` no habría corrido ninguna regla declarativa sobre los archivos.
