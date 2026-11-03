# Pausa de fase y registro automático de hooks — plan de implementación

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** que el humano pueda pausar y reanudar una fase sin gastar intentos, que una variable de entorno apague el hook `Stop`, y que `deploy.ps1` registre los hooks del harness en `~/.claude/settings.json` sin tocar nada ajeno.

**Architecture:**
- El estado `pausada` vive en la máquina de estados (`lib/state.py`) y en el contrato (`lib/contracts.py`).
- El CLI expone `pausar-fase` y `open-fase` reanuda; el hook `Stop` ya no bloquea en `pausada`.
- El registro de hooks es un script de Python en la raíz (`registrar_hooks.py`), con una función pura de fusión y un `main` que lee, respalda y escribe. `deploy.ps1` lo llama.

**Tech Stack:** Python 3.12 stdlib, `unittest`, PowerShell 5.1 (`deploy.ps1`).

**Spec:** `docs/superpowers/specs/2026-11-02-pausa-y-registro-de-hooks-design.md`

## Global Constraints

- Solo stdlib y `unittest`. Tests con `python -m unittest discover -s tests`; pytest no está instalado.
- Nombres:
  - Superficie pública en inglés solo donde ya existe así (`validate_*`, `read_json`); lo nuevo sigue el estilo del archivo.
  - En `state.py`, `cli.py` y `report.py` las funciones y locales van en español.
  - Mensajes al usuario en español.
- Fechas `dd-mm-aaaa` (las da `cli._hoy()`). El respaldo usa `dd-mm-aaaa-HHMMSS`.
- Errores del CLI con `_error(...)` (prefijo `HARNESS · `, exit 1). La máquina de estados lanza `state.TransicionInvalida`, que `main` convierte en error.
- `harness/` no puede mencionar ningún stack (`TestSeparacionDePlanos`).
- `test_documentacion` exige que `README.md` nombre cada comando de `harness/commands/` y `docs/tecnico.md` cada subcomando de `cli.py`. Todo comando o subcomando nuevo entra con su línea de documentación en la misma tarea.
- `test_referencias_harness` exige que todo `/comando`, subcomando o skill nombrado en `harness/**/*.md` exista.
- Pausar nunca toca `intento_actual` ni `historial_fallos`. `pausas` nunca se borra.
- El registro de hooks nunca borra entradas ni toca hooks ajenos, otras claves, su orden o sus acentos. Un `settings.json` roto no se escribe.
- Cada tarea: test primero, verlo fallar, implementar, suite completa en verde, commit con `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`.

## Review Focus

1. **La fase pausada y `current.json`:** después de `pausar-fase`, `current.json` sigue apuntando a la fase pausada. `open-fase` de otra fase independiente se permite y la pausada queda pausada. Test en Task 2.
2. **`open-ticket` con el mismo id del ticket activo y una fase corriendo:** también se rechaza, porque `open-ticket` pone `fase_id` en `None` y la dejaría huérfana. Test en Task 2.
3. **`settings.json` con BOM o sin la clave `hooks`:** se lee igual (`utf-8-sig`), se escribe sin BOM y se crea `hooks`. Test en Task 5.
4. **Segunda pausa tras reanudar:** `pausas` acumula dos elementos y reanudar vuelve al `desde` de la última. Test en Task 1.
5. **`HARNESS_STOP` con otros valores (`OFF`, ` off `, `0`, vacío):** solo `off` sin distinguir mayúsculas y sin espacios alrededor apaga el hook. `0` y vacío no. Test en Task 3.

---

### Task 1: Estado `pausada` en el contrato y en la máquina de estados

**Files:**
- Modify: `harness/hooks/lib/contracts.py` (`ESTADOS_FASE`, constante nueva, `validate_fase_state`)
- Modify: `harness/hooks/lib/state.py`
- Test: `tests/test_contracts.py`, `tests/test_state.py`

**Interfaces:**
- Produces:
  - `contracts.ESTADOS_EN_CICLO = frozenset({"en_ejecucion", "en_correccion", "en_verificacion"})`.
  - `"pausada"` en `contracts.ESTADOS_FASE`.
  - `state.pausar_fase(project_root: Path, ticket_id: str, fase_id: str, motivo: str, fecha: str) -> dict`.
  - `state.reanudar_fase(project_root: Path, ticket_id: str, fase_id: str) -> dict`.
  - Ambas devuelven el estado guardado.

- [ ] **Step 1: Tests del contrato** en `tests/test_contracts.py`, sobre un `fase_state` válido de base:
  - `test_fase_state_acepta_pausada_con_pausas`: `estado="pausada"`, `pausas=[{"desde": "en_correccion", "fecha": "02-11-2026", "motivo": "sin motivo"}]` → `[]`.
  - `test_fase_state_pausada_exige_pausas`: `estado="pausada"` sin `pausas`, o con `pausas=[]` → error que menciona `pausas`.
  - `test_fase_state_pausas_es_opcional_fuera_de_pausada`: `en_ejecucion` sin `pausas` → `[]`. Con dos pausas históricas → `[]`.
  - `test_fase_state_rechaza_pausas_mal_formadas`, con un `subTest` por caso:
    - `pausas` no es lista;
    - un elemento no es objeto;
    - falta `motivo`;
    - `fecha="2026-11-02"`;
    - `desde="aprobada"` (todo `desde` debe estar en `ESTADOS_EN_CICLO`).

- [ ] **Step 2: Tests de estado** en `tests/test_state.py`:
  - `test_pausar_guarda_el_estado_previo_sin_tocar_intento_ni_historial`: fase en `en_correccion`, intento 2, con un fallo. Se pausa con `motivo="almuerzo"` y `fecha="02-11-2026"`. Resultado:
    - `estado == "pausada"`;
    - `intento_actual == 2`;
    - el historial queda igual;
    - `pausas == [{"desde": "en_correccion", "fecha": "02-11-2026", "motivo": "almuerzo"}]`.
  - `test_pausar_se_rechaza_fuera_del_ciclo`: para `esperando_humano`, `aprobada`, `escalado` y `pausada`, lanza `TransicionInvalida` y el mensaje contiene el estado. Para `esperando_humano` el mensaje contiene además `ya no bloquea`.
  - `test_reanudar_vuelve_al_estado_previo`: pausar desde `en_verificacion` y reanudar da `en_verificacion` con el mismo intento. `pausas` conserva su elemento.
  - `test_segunda_pausa_acumula_y_reanuda_a_la_ultima`: pausar desde `en_ejecucion`, reanudar, `registrar_fallo` (pasa a `en_correccion`), pausar y reanudar. `len(pausas) == 2` y el estado final es `en_correccion`.
  - `test_reanudar_exige_pausada`: sobre `en_ejecucion` lanza `TransicionInvalida`.
  - `test_fallo_y_aprobacion_se_rechazan_en_pausada`: con la fase pausada, `registrar_fallo` y `aprobar_fase` lanzan `TransicionInvalida`.

- [ ] **Step 3: Correr y ver fallar**

Run: `python -m unittest tests.test_contracts tests.test_state`
Expected: FAIL (no existen `pausada`, `pausar_fase` ni `reanudar_fase`).

- [ ] **Step 4: Implementar**
  - En `contracts.py`:
    - suma `pausada` a `ESTADOS_FASE`;
    - define `ESTADOS_EN_CICLO`;
    - valida `pausas` en `validate_fase_state`, reutilizando `_texto` y `RE_FECHA` como el resto del archivo.
  - En `state.py`:
    - `pausar_fase` agrega `{"desde", "fecha", "motivo"}` a `pausas` (la crea si falta) y pone `estado="pausada"`;
    - `reanudar_fase` restaura `pausas[-1]["desde"]`;
    - `registrar_fallo` y `aprobar_fase` rechazan `pausada` con su propio mensaje, antes del chequeo que ya tienen.
  - Todo pasa por `_guardar`.

- [ ] **Step 5: Suite completa**

Run: `python -m unittest discover -s tests`
Expected: OK.

- [ ] **Step 6: Commit** — `feat(state): estado pausada con historial de pausas`

---

### Task 2: CLI — `pausar-fase`, reanudar con `open-fase`, sin fases huérfanas

**Files:**
- Modify: `harness/hooks/cli.py`
- Create: `harness/commands/fase-pausa.md`
- Modify: `README.md` (mención de `/fase-pausa`), `docs/tecnico.md` (fila de `pausar-fase`)
- Test: `tests/test_cli_pausa.py` (nuevo)

**Interfaces:**
- Consumes: Task 1 (`state.pausar_fase`, `state.reanudar_fase`, `contracts.ESTADOS_EN_CICLO`).
- Produces:
  - Subcomando `pausar-fase [--project] [--motivo TEXTO]`.
  - Comando `/fase-pausa`.
  - `cli.EN_CICLO` pasa a ser `contracts.ESTADOS_EN_CICLO`; se borra la definición local.

- [ ] **Step 1: Tests** en `tests/test_cli_pausa.py`.

  Arma el proyecto como `tests/test_cli_veredicto.py`: un plan con `fase_1`, una `fase_2` independiente (`depende_de: []`) y una `fase_3` que depende de `fase_1`. Corre `open-ticket` y `open-fase --fase fase_1`. Luego:
  - `test_pausar_deja_la_fase_pausada_con_motivo`: `pausar-fase --motivo "almuerzo"` → exit 0, stdout contiene `/fase fase_1`. El estado queda `pausada` y `pausas[-1]["motivo"] == "almuerzo"`.
  - `test_pausar_sin_motivo_guarda_sin_motivo`: `pausas[-1]["motivo"] == "sin motivo"`.
  - `test_pausar_sin_fase_activa_falla`: proyecto con ticket abierto y sin fase → exit 1.
  - `test_pausar_esperando_humano_explica_que_no_bloquea`: con la fase en `esperando_humano` → exit 1 y stderr contiene `ya no bloquea`.
  - `test_open_fase_reanuda_una_fase_pausada`: pausar y luego `open-fase --fase fase_1` → exit 0, stdout contiene `reanudada`, el estado vuelve a `en_ejecucion` y el intento sigue en 1.
  - `test_open_fase_sobre_fase_no_pausada_sigue_idempotente`: dos `open-fase --fase fase_1` seguidos → exit 0 y el estado no cambia.
  - `test_veredicto_y_prueba_se_rechazan_en_pausada`:
    - con la fase pausada, `record-veredicto` (con un veredicto válido) y `generar-prueba` (con pasos válidos) salen con 1;
    - stderr contiene `/fase fase_1`;
    - no se escribe `veredicto.json` ni `prueba_manual.md`.
  - `test_no_se_abre_otra_fase_con_la_activa_corriendo`: con `fase_1` en `en_ejecucion`, `open-fase --fase fase_2` → exit 1. Stderr contiene `fase_1` y `/fase-pausa`, y `current.json` sigue en `fase_1`.
  - `test_con_la_activa_pausada_se_abre_otra_y_la_pausada_sigue_pausada`: pausar `fase_1` y luego `open-fase --fase fase_2` → exit 0, `fase_1` sigue `pausada` y `current.json` apunta a `fase_2`.
  - `test_open_ticket_se_rechaza_con_la_fase_corriendo`: con `fase_1` en `en_ejecucion`, `open-ticket` de otro ticket y `open-ticket` del mismo id → exit 1 y stderr contiene `/fase-pausa`. Tras pausar, `open-ticket` del otro ticket → exit 0.
  - `test_fase_dependiente_de_una_pausada_no_se_abre`: pausar `fase_1` y `open-fase --fase fase_3` → exit 1 y stderr contiene `pausada`, por el error de dependencia que ya existe.

- [ ] **Step 2: Correr y ver fallar**

Run: `python -m unittest tests.test_cli_pausa`
Expected: FAIL (no existe `pausar-fase`).

- [ ] **Step 3: Implementar en `cli.py`**
  - `cmd_pausar_fase`: usa `_fase_activa`, llama a `state.pausar_fase(..., motivo=args.motivo or "sin motivo", fecha=_hoy())` e imprime la fase, el intento y `Para retomarla: /fase <fase_id>`. Registra el subparser `pausar-fase` con `--project` y `--motivo`.
  - Helper `_fase_corriendo(raiz) -> tuple[str, str, str] | None`: devuelve `(ticket_id, fase_id, estado)` de `current.json` si esa fase está en `ESTADOS_EN_CICLO`, y `None` si no.
  - `cmd_open_ticket` rechaza si `_fase_corriendo` devuelve algo.
  - `cmd_open_fase`:
    - rechaza si la fase corriendo es otra (`fase_id != args.fase`);
    - si el estado existente de la fase pedida es `pausada`, llama a `state.reanudar_fase` e imprime `Fase <id> reanudada en estado '<estado>', intento i/m`;
    - si no, sigue con `abrir_fase` como hoy;
    - los dos mensajes de rechazo nombran la fase corriendo y `/fase-pausa`.
  - `cmd_record_veredicto` y `cmd_generar_prueba`: si `estado["estado"] == "pausada"`, `_error` con `reanúdala con /fase <fase_id>` antes de escribir nada.
  - `EN_CICLO = contracts.ESTADOS_EN_CICLO`.

- [ ] **Step 4: Comando y documentación**
  - `harness/commands/fase-pausa.md`:
    - frontmatter con `description: Pausa la fase activa para conversar de otra cosa o cerrar el día; se retoma con /fase` y `argument-hint: "<motivo>"`;
    - el cuerpo, al estilo de `fase-ok.md`, corre `python "$HOME/.claude/hooks/cli.py" pausar-fase --motivo "$ARGUMENTS"` (omitiendo `--motivo` si `$ARGUMENTS` está vacío), muestra la salida tal cual y **termina el turno sin retomar la fase**.
  - `README.md`: en la sección de comandos de fase, `/fase-pausa ["<motivo>"]` en una línea, y que se retoma con `/fase fase_N` sin gastar intento.
  - `docs/tecnico.md`:
    - fila `pausar-fase` en la tabla del CLI;
    - en la fila de `open-fase`, que reanuda una fase pausada y se rechaza con otra fase corriendo;
    - `open-ticket` igual.

- [ ] **Step 5: Suite completa**

Run: `python -m unittest discover -s tests`
Expected: OK.

Si un test existente se apoyaba en abrir otra fase u otro ticket con una fase corriendo, ajusta su preparación (aprobar o pausar la fase antes). No debilites la guarda.

- [ ] **Step 6: Commit** — `feat(cli): pausar-fase, open-fase reanuda y no se deja una fase corriendo sin dueño`

---

### Task 3: Hook `Stop`, skill `ticket-loop` y punta a punta

**Files:**
- Modify: `harness/hooks/gate_phase.py`
- Modify: `harness/skills/ticket-loop/SKILL.md`
- Modify: `README.md`, `docs/tecnico.md` (interruptor `HARNESS_STOP`)
- Test: `tests/test_hook_gate_phase.py`, `tests/test_punta_a_punta.py`

**Interfaces:**
- Consumes: Tasks 1 y 2.
- Produces: `gate_phase.BLOQUEANTES = contracts.ESTADOS_EN_CICLO`; variable de entorno `HARNESS_STOP`.

- [ ] **Step 1: Tests del hook** en `tests/test_hook_gate_phase.py`. `lanzar` acepta un `env` opcional que se fusiona sobre `os.environ`.
  - `test_NO_bloquea_una_fase_pausada`: con `con_estado("pausada")` → exit 0. El helper debe escribir un `pausas` válido cuando el estado es `pausada`, porque el contrato lo exige.
  - `test_HARNESS_STOP_off_apaga_el_hook`: `en_ejecucion` con `HARNESS_STOP` en `off`, `OFF` y ` off ` → exit 0.
  - `test_HARNESS_STOP_con_otro_valor_no_apaga`: `en_ejecucion` con `HARNESS_STOP` en `0`, `""` y `no` → exit 2.
  - `test_el_bloqueo_ofrece_la_pausa`: `en_ejecucion` → stderr contiene `/fase-pausa`.

- [ ] **Step 2: Paso de punta a punta** en `tests/test_punta_a_punta.py`, dentro de `ticket_que_escala`, justo después de `self.assertEqual(self.fase(t)["estado"], "en_verificacion")` del intento 2:
  - `self.cli("open-ticket", ...ISR-9..., codigo=1)`: no se abandona una fase corriendo.
  - `self.cli("pausar-fase", "--motivo", "almuerzo")`, y `self.hook_stop().returncode == 0`.
  - `self.cli("open-fase", "--fase", "fase_1")`: el estado es `("en_verificacion", 2)` y `self.hook_stop().returncode == 2`.

  Lo que sigue del test queda igual. El bloqueo de `Stop` que ya se verificaba ahí pasa a estar después de reanudar. El conteo de la pausa en el reporte lo verifica Task 4.

- [ ] **Step 3: Correr y ver fallar**

Run: `python -m unittest tests.test_hook_gate_phase tests.test_punta_a_punta`
Expected: FAIL en `HARNESS_STOP` y en `/fase-pausa` del mensaje.

- [ ] **Step 4: Implementar `gate_phase.py`**
  - Lo primero en `main()`, antes de leer stdin: si `os.environ.get("HARNESS_STOP", "").strip().lower() == "off"`, `return 0`.
  - `BLOQUEANTES = contracts.ESTADOS_EN_CICLO`.
  - El mensaje de bloqueo suma la línea: `Si el humano pidió detenerse o cambió de tema, ofrécele /fase-pausa y termina el turno sin retomar la fase.`
  - Actualiza el docstring: `pausada` tampoco bloquea, y existe `HARNESS_STOP=off`.

- [ ] **Step 5: Skill y documentación**
  - En `ticket-loop/SKILL.md`, sección nueva `## Pausar una fase`, después de "El ciclo de una fase":
    - solo el humano pausa, con `/fase-pausa`, y nunca se corre `pausar-fase` por iniciativa propia;
    - si el humano pregunta otra cosa a mitad de fase o pide parar, se responde, se le recuerda `/fase-pausa` y se termina el turno sin retomar la fase;
    - se retoma con `/fase fase_N`, porque `open-fase` reanuda en el mismo intento;
    - `open-fase` de otra fase y `open-ticket` se rechazan mientras la fase activa corre.
  - En el paso 1 del ciclo ("Abrir"), una frase: si la fase estaba `pausada`, `open-fase` la reanuda.
  - `README.md`: el interruptor `HARNESS_STOP=off` (`$env:HARNESS_STOP="off"; claude`), solo para emergencias y solo al abrir la sesión.
  - `docs/tecnico.md`: `pausada` en "Estados de una fase" (no bloquea `Stop`; vuelve al estado de antes) y `pausas` en el contrato de `fase_state`.

- [ ] **Step 6: Suite completa**

Run: `python -m unittest discover -s tests`
Expected: OK.

- [ ] **Step 7: Commit** — `feat(hooks): Stop no bloquea en pausada, HARNESS_STOP=off y ticket-loop sabe pausar`

---

### Task 4: Pausas en el reporte

**Files:**
- Modify: `harness/hooks/report.py`
- Test: `tests/test_report.py`, `tests/test_punta_a_punta.py`

**Interfaces:**
- Produces: `agregar(...)["fases"]["pausas_por_fase"]: dict[str, int]`, solo con las fases que tienen al menos una pausa.

- [ ] **Step 1: Tests**
  - En `tests/test_report.py`, con el estilo de siembra del archivo:
    - `test_pausas_por_fase`: una fase con 2 pausas y otra sin `pausas` → `{"T/fase_1": 2}`. `render` contiene `Pausas:` y `T/fase_1 2 veces`, con el mismo `_veces` del archivo.
    - `test_sin_pausas_no_hay_linea`: `pausas_por_fase == {}` y `render` no contiene `Pausas:`.
  - En `tests/test_punta_a_punta.py`, segundo test: `datos["fases"]["pausas_por_fase"] == {"ISR-1/fase_1": 1}`.

- [ ] **Step 2: Correr y ver fallar**

Run: `python -m unittest tests.test_report tests.test_punta_a_punta`
Expected: FAIL (`KeyError: 'pausas_por_fase'`).

- [ ] **Step 3: Implementar**
  - En `agregar`, donde ya se lee `fase_state.json`: `len(datos.get("pausas") or [])`.
  - En `_seccion_fases`, después de "Origen de los fallos": `  Pausas: <fase> <n veces>, ...`, ordenado por fase.

- [ ] **Step 4: Suite completa**

Run: `python -m unittest discover -s tests`
Expected: OK.

- [ ] **Step 5: Commit** — `feat(report): pausas por fase`

---

### Task 5: `registrar_hooks.py`

**Files:**
- Create: `registrar_hooks.py` (raíz del repo)
- Test: `tests/test_registrar_hooks.py` (nuevo; importa el módulo con `sys.path.insert(0, str(RAIZ))`)

**Interfaces:**
- Produces:
  - `registrar(settings: dict, hooks_dir: str) -> tuple[dict, list[str]]`: función pura. Devuelve una copia profunda con los hooks registrados y las líneas a imprimir. No muta la entrada.
  - `main(argv: list[str] | None = None) -> int`, con los argumentos `--settings RUTA --hooks-dir RUTA`.
  - Tabla de hooks del harness, sacada del spec:

| Evento | matcher | archivo | comando |
|---|---|---|---|
| `PostToolUse` | `Edit\|Write\|MultiEdit` | `check_rules.py` | `python "<str(Path(hooks_dir) / archivo)>"` |
| `Stop` | `""` | `gate_phase.py` | igual |

  - Formato de cada línea de estado: `<Evento> (<archivo>): registrado | ruta actualizada | ya estaba`.
  - Avisos adicionales:
    - una entrada mixta (`matcher sin tocar`);
    - duplicados (`<n> entradas del harness`).

**Algoritmo de `registrar`** (lo que la firma no determina):

```
para cada (evento, matcher, archivo) de la tabla:
  lista = settings.setdefault("hooks", {}).setdefault(evento, [])
  nuestras = entradas de la lista con algún hook cuyo "command" contiene archivo
  si no hay: append {"matcher": matcher, "hooks": [{"type": "command", "command": cmd}]} → "registrado"
  si hay: en cada una, poner cmd en los hooks que nombran archivo;
          si todos los hooks de la entrada son nuestros, poner matcher; si no, avisar "matcher sin tocar"
          → "ruta actualizada" si algo cambió en alguna, si no "ya estaba"
          si len(nuestras) > 1: avisar el duplicado
```

- [ ] **Step 1: Tests.** Fixture `REAL`: un dict como el `settings.json` actual de Omar.
  - Claves: `env` con un valor con acento (`"NOTA": "configuración"`), `model`, `enabledPlugins`.
  - `hooks` con entradas de codebase-memory: `PostToolUse` con matcher `Read`, `PreToolUse`, `SessionStart` con cuatro matchers y `SubagentStart`. Cada una con `command`, `args` y `timeout`.
  - Sin los hooks del harness.

  Tests:
  - `test_registra_desde_cero_y_conserva_lo_ajeno`:
    - `registrar(REAL, d)` agrega una entrada al final de `PostToolUse` y crea `Stop`;
    - todo lo demás queda igual a `REAL`: compara el resultado sin las entradas nuevas contra `REAL`, incluido el orden de las claves con `list(...)`;
    - las dos líneas dicen `registrado`.
  - `test_no_muta_la_entrada`: `REAL` queda igual tras llamar.
  - `test_segunda_vez_ya_estaba`: `registrar(registrar(REAL, d)[0], d)` devuelve datos iguales y dos líneas `ya estaba`.
  - `test_ruta_vieja_se_actualiza`: entrada con `python "C:/viejo/check_rules.py"` → queda el comando nuevo y la línea dice `ruta actualizada`.
  - `test_matcher_distinto_se_corrige`: la entrada propia con matcher `Write` pasa a `Edit|Write|MultiEdit`.
  - `test_entrada_mixta_no_toca_el_matcher`: entrada `{"matcher": "Write", "hooks": [ajeno, nuestro]}` → el comando nuestro se corrige, el matcher sigue en `Write`, el ajeno queda igual y hay una línea con `matcher sin tocar`.
  - `test_duplicados_se_corrigen_y_se_avisa`: dos entradas propias en `Stop` → las dos corregidas, ninguna borrada, y una línea con `2 entradas del harness`.
  - `test_sin_clave_hooks`: `{"model": "x"}` → crea `hooks`.
  - Tests de `main` sobre un directorio temporal:
    - `test_main_crea_el_archivo_si_no_existe`: exit 0, el archivo existe y no hay `*.bak-*`.
    - `test_main_segunda_corrida_no_escribe_ni_respalda`: tras la primera corrida, guarda `mtime_ns` y el contenido. La segunda sale con exit 0, no cambia nada, no crea un respaldo nuevo y stdout contiene `ya estaba`.
    - `test_main_respalda_solo_cuando_escribe`: con `REAL` en disco, exit 0. Hay exactamente un `settings.json.bak-*` que coincide con `^settings\.json\.bak-\d{2}-\d{2}-\d{4}-\d{6}$`, y su contenido es el original byte a byte.
    - `test_main_escribe_utf8_sin_bom_indent_2_y_lf`: el archivo escrito no empieza con BOM, no contiene `\r`, contiene `configuración` literal (sin `\u00f3`) y es `json.dumps(datos, indent=2, ensure_ascii=False) + "\n"`.
    - `test_main_lee_con_bom`: un archivo con BOM se procesa con exit 0 y queda escrito sin BOM.
    - `test_main_json_roto_no_toca_nada`: con `{"hooks": [` → exit 1, el archivo sigue igual byte a byte, no hay respaldo y la salida contiene `línea` y `columna`.
    - `test_main_json_que_no_es_objeto`: con `[]` → exit 1 y el archivo sigue igual.

- [ ] **Step 2: Correr y ver fallar**

Run: `python -m unittest tests.test_registrar_hooks`
Expected: FAIL (no existe el módulo).

- [ ] **Step 3: Implementar `registrar_hooks.py`**
  - Docstring que diga que corre solo al desplegar y por qué va en Python (el `ConvertTo-Json` de PS 5.1 corta lo anidado y escapa los acentos).
  - Lectura con `encoding="utf-8-sig"`. Comparación por datos (`nuevo == original`).
  - Respaldo con `shutil.copy2` antes de escribir.
  - Escritura atómica: `tempfile.mkstemp` en el mismo directorio, `newline="\n"`, y `os.replace`.
  - Errores de JSON con `error.lineno` y `error.colno`.
  - Salida por stdout reconfigurada a UTF-8, como `cli.py`.
  - Guarda `if __name__ == "__main__": sys.exit(main())`.

- [ ] **Step 4: Suite completa**

Run: `python -m unittest discover -s tests`
Expected: OK.

- [ ] **Step 5: Commit** — `feat(deploy): registrar_hooks.py fusiona los hooks del harness en settings.json`

---

### Task 6: `deploy.ps1` y documentación de instalación

**Files:**
- Modify: `deploy.ps1`
- Modify: `README.md` (instalación), `docs/tecnico.md` (estructura del repo, pendientes)
- Test: `tests/test_deploy.py` (nuevo)

**Interfaces:**
- Consumes: Task 5 (`registrar_hooks.py --settings --hooks-dir`).

- [ ] **Step 1: Tests** en `tests/test_deploy.py`, leyendo `deploy.ps1` como texto:
  - `test_deploy_llama_a_registrar_hooks`: contiene `registrar_hooks.py`, `--settings`, `--hooks-dir` y `$LASTEXITCODE`.
  - `test_deploy_ya_no_pisa_un_respaldo_fijo`: no contiene `"$Settings.bak"`.
  - `test_deploy_tiene_el_switch_SinHooks`: contiene `[switch]$SinHooks`.
  - `test_registrar_hooks_no_se_despliega`: `registrar_hooks.py` existe en la raíz y no dentro de `harness/`.

- [ ] **Step 2: Correr y ver fallar**

Run: `python -m unittest tests.test_deploy`
Expected: FAIL.

- [ ] **Step 3: Implementar `deploy.ps1`**
  - `param` suma `[switch]$SinHooks`.
  - Se reemplaza el bloque "Respaldo de settings.json y recordatorio de los hooks":
    - con `-SinHooks`, se imprime el bloque para pegar como hoy, sin respaldo;
    - sin él, `& python (Join-Path $Fuente "registrar_hooks.py") --settings $Settings --hooks-dir (Join-Path $Global "hooks")`, y si `$LASTEXITCODE -ne 0`, `throw` con un mensaje que diga que `settings.json` no se tocó.
  - Actualiza el `.EXAMPLE` con `-SinHooks`.

- [ ] **Step 4: Documentación**
  - `README.md`, instalación:
    - el paso 2 manual ("Registrar los hooks") desaparece; `deploy.ps1` los registra y dice qué hizo;
    - se nombran el respaldo con fecha y hora y `-SinHooks` (que imprime el bloque para pegar a mano);
    - la mención a `settings.json.bak` se corrige.
  - `docs/tecnico.md`:
    - `registrar_hooks.py` en "Estructura del repositorio";
    - el punto 3 sale de "Pendientes conocidos", con la misma forma en que salieron los pasos 1 y 2, y la numeración de lo que sigue queda coherente.
    - Una línea en "Tests que protegen el diseño" para `test_registrar_hooks`: nada ajeno de `settings.json` cambia, y un JSON roto no se escribe.

- [ ] **Step 5: Suite completa**

Run: `python -m unittest discover -s tests`
Expected: OK.

- [ ] **Step 6: Commit** — `feat(deploy): deploy.ps1 registra los hooks y -SinHooks para hacerlo a mano`
