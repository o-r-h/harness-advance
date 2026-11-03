# Reporte del harness y seguimiento de lecciones — plan de implementación

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Que `cli.py report` conteste "¿el harness está aprendiendo?": lecciones que fallaron, deuda de lecciones, salud de los hallazgos y métricas de fases. La documentación queda separada en uso y técnica.

**Architecture:** La reincidencia nace en el reflector (campo `reincide`), se valida en el contrato, la confirma el humano con los comandos de siempre y se guarda como línea `falló` en la entrada original de la biblioteca. `/hallazgo-hecho` escribe la línea `implementada`. `report.py` es de solo lectura: lee `.harness/tickets/` y `.claude/biblioteca/` y agrega todo en un dict que se imprime como texto o como JSON.

**Tech Stack:** Python 3.12 estándar, `unittest`, sin dependencias.

**Spec:** `docs/superpowers/specs/2026-11-02-reporte-y-aprendizaje-design.md`

## Global Constraints

- Superficie pública en inglés (`project_root`, `read_json`); variables locales, comentarios y términos del dominio (`fase`, `intento`, `hallazgo`, `leccion`, `reincide`) en español.
- Nunca forzar UTF-8 al leer archivos del código del proyecto. Los JSON y `.md` que escribe el propio harness sí son UTF-8.
- Fechas `dd-mm-aaaa` (`contracts.RE_FECHA`).
- El harness genérico (`harness/`) no menciona ningún stack: lo vigila `TestSeparacionDePlanos`.
- El CLI es el único que escribe estado. El reporte no escribe nada.
- El reporte nunca revienta por un archivo ilegible o mal formado: lo nombra en "Archivos que no se pudieron leer" y sigue.
- La suite completa (`python -m unittest discover -s tests`, hoy 284 pruebas) queda en verde al final de cada tarea.

## Review Focus

1. Una entrada de la biblioteca con líneas que el código no conoce (agregadas a mano, o con CRLF tras un checkout de git) conserva esas líneas intactas después de `registrar_falla` y `marcar_implementada`. Test en la Tarea 2.
2. `--reincide` hacia una lección rechazada o inexistente se rechaza con error claro y no escribe nada: ni `hallazgos.json` ni la biblioteca. Test en la Tarea 3.
3. `--nueva` junto con `--reincide`, o cualquiera de los dos con `--decision no`, es un error. Test en la Tarea 3.
4. `report` en un proyecto sin `.harness/` ni `.claude/biblioteca/` sale con código 0 y cada sección dice que no hay datos. Test en las Tareas 5 y 6.
5. Datos viejos o rotos (JSON inválido, bytes cp1252, `fase_state.json` sin claves, `hallazgos.json` fuera de contrato) terminan en `ilegibles` y no detienen el reporte. Test en la Tarea 5.

---

## Mapa de archivos

| Archivo | Responsabilidad |
|---|---|
| `harness/hooks/lib/contracts.py` | `RE_REFERENCIA` y el campo opcional `reincide` |
| `harness/hooks/lib/biblioteca.py` | Leer una entrada, `aprobada`, `falló`, `implementada` y las marcas del índice |
| `harness/hooks/lib/hallazgos.py` | `reincide en <ref>` en el encabezado de `hallazgos.md` |
| `harness/hooks/cli.py` | `record-hallazgos` y `resolver-hallazgo` con reincidencia; subcomandos `hallazgo-hecho` y `report` |
| `harness/hooks/report.py` (nuevo) | `agregar` y `render`, de solo lectura |
| `harness/commands/hallazgo-hecho.md` (nuevo), `hallazgo-ok.md`, `hallazgo-editar.md` | Comandos del humano |
| `harness/agents/reflector.md`, `harness/skills/task-planner/SKILL.md` | Marcar `reincide`; peso de una lección que falló |
| `README.md`, `docs/tecnico.md` (nuevo) | Guía de uso y referencia técnica |

---

### Tarea 1: Contrato — `reincide`

**Files:**
- Modify: `harness/hooks/lib/contracts.py` (constantes de hallazgos, `_validar_item_reflector`, `validate_hallazgos`)
- Test: `tests/test_contracts.py`

**Interfaces:**
- Produces: `contracts.RE_REFERENCIA = re.compile(r"^[^/\s]+/fase_\d+/h\d+$")`. `reincide` es opcional en cada hallazgo de la propuesta y de `hallazgos.json`, para ambos orígenes; si viene, es string que cumple `RE_REFERENCIA`.

- [ ] **Step 1: Escribir las pruebas que fallan** — clase `TestReincide` en `tests/test_contracts.py`:
  - `test_propuesta_sin_reincide_sigue_valida`: un item completo sin `reincide` → `validate_propuesta_hallazgos(...) == []`.
  - `test_propuesta_con_reincide_valido`: `"reincide": "ISR-109204-P5/fase_1/h2"` → `[]`.
  - `test_reincide_mal_formado`: para `"ISR-1/fase_1"`, `"ISR-1\\fase_1\\h1"`, `""` y `7` → la lista de errores contiene un mensaje que empieza con `hallazgos[0].reincide:`.
  - `test_hallazgos_guardado_acepta_reincide`: `validate_hallazgos` con un item `aprobado` de origen `reflector` que trae `reincide` válido → `[]`; con `"reincide": "x"` → un error `hallazgos[0].reincide:`.
- [ ] **Step 2: Correr** `python -m unittest tests.test_contracts -v`. Esperado: FAIL en las 4 nuevas.
- [ ] **Step 3: Implementar.** Una función `_validar_reincide(item, errores, prefijo)` que llaman `_validar_item_reflector` y la rama `humano` de `validate_hallazgos`. Mensaje: `f"{prefijo}reincide: formato esperado TICKET/fase_N/hN"`.
- [ ] **Step 4: Correr** la suite completa. Esperado: todo PASS.
- [ ] **Step 5: Commit** `feat(contracts): campo opcional reincide con forma de referencia`.

---

### Tarea 2: Biblioteca — leer una entrada, fallas, implementada e índice

**Files:**
- Modify: `harness/hooks/lib/biblioteca.py`
- Test: `tests/test_hallazgos_biblioteca.py`

**Interfaces:**
- Consumes: `contracts.RE_REFERENCIA` (Tarea 1).
- Produces:
  - `entrada_path(project_root: Path, ref: str, subdir: str = "entradas") -> Path`: `<biblioteca>/<subdir>/<ref con "/" cambiado por "-">.md`.
  - `leer_entrada(project_root: Path, ref: str) -> dict | None`: `None` si no existe en `entradas/`. Si existe: `{"ref", "senal", "leccion", "componente", "dimension", "origen", "aprobada", "implementada", "fallas"}`. Los campos ausentes valen `""`. `fallas` es una lista de `{"fecha", "ref", "tipo", "leccion"}`, con `tipo` `"implementada"` o `"sin pieza"`.
  - `escribir_entrada(project_root, ticket_id, fase_id, hallazgo, fecha: str | None = None) -> Path`: igual que hoy, pero si el estado es `aprobado` y viene `fecha`, agrega `- **aprobada**: <fecha>`.
  - `registrar_falla(project_root: Path, ref_original: str, ref_nueva: str, leccion: str, fecha: str) -> Path`: agrega `- **falló**: <fecha> · <ref_nueva> · <tipo> — <leccion en una línea>` al final de la entrada. El tipo es `implementada` si la entrada ya tiene `implementada`, y `sin pieza` si no. `ValueError` si la entrada no existe en `entradas/`. Reconstruye el índice.
  - `marcar_implementada(project_root: Path, ref: str, nota: str, fecha: str) -> str | None`: escribe o reemplaza `- **implementada**: <fecha> · <nota>` y devuelve el valor anterior, o `None`. Las líneas `falló` y cualquier otra línea quedan intactas. `ValueError` si la entrada no existe en `entradas/`. Reconstruye el índice.
  - `reconstruir_indice`: cada aprobada termina con `(implementada <fecha>)` si la tiene, y con `(falló N×)` si tiene N ≥ 1 fallas. Ese orden, separadas por un espacio.

- [ ] **Step 1: Escribir las pruebas que fallan** — clase `TestMarcasDeLaEntrada`, con una entrada aprobada `ISR-1/fase_1/h1` escrita por `escribir_entrada(..., fecha="02-11-2026")`:
  - `test_la_aprobada_lleva_fecha`: `leer_entrada(root, "ISR-1/fase_1/h1")["aprobada"] == "02-11-2026"`.
  - `test_sin_fecha_no_escribe_aprobada`: con `fecha=None` → `"aprobada"` vale `""`.
  - `test_leer_entrada_inexistente`: `leer_entrada(root, "ISR-9/fase_1/h1") is None`.
  - `test_falla_sin_pieza`: `registrar_falla(root, "ISR-1/fase_1/h1", "ISR-2/fase_3/h1", "Usar curl.exe", "03-11-2026")` → `fallas == [{"fecha": "03-11-2026", "ref": "ISR-2/fase_3/h1", "tipo": "sin pieza", "leccion": "Usar curl.exe"}]`.
  - `test_falla_estando_implementada`: `marcar_implementada(..., "check curl", "04-11-2026")` y luego `registrar_falla(...)` → `tipo == "implementada"`.
  - `test_varias_fallas_se_acumulan`: dos `registrar_falla` → `len(fallas) == 2`, en orden.
  - `test_marcar_implementada_devuelve_la_anterior`: primera marca → `None`. La segunda devuelve `"04-11-2026 · check curl"` y `leer_entrada(...)["implementada"]` es la nueva.
  - `test_falla_o_marca_sobre_rechazada_o_inexistente`: con una entrada en `rechazados/` y con una ref que no existe → `ValueError` en las dos funciones.
  - `test_conserva_lineas_ajenas` (Review Focus 1): escribir a mano en la entrada `"\r\n- **nota**: puesta a mano\r\n"`. Tras `registrar_falla` y `marcar_implementada`, el texto contiene `- **nota**: puesta a mano` y las líneas `falló` siguen ahí.
  - `test_indice_muestra_las_marcas`: con implementada y 2 fallas, la línea de la aprobada en `INDEX.md` termina en `(implementada 04-11-2026) (falló 2×)`.
- [ ] **Step 2: Correr** `python -m unittest tests.test_hallazgos_biblioteca -v`. Esperado: FAIL.
- [ ] **Step 3: Implementar** las funciones de arriba. El parseo de `falló` usa `re.findall` sobre `^- \*\*falló\*\*: (\S+) · (\S+) · (implementada|sin pieza) — (.*)$`. Las escrituras editan la lista de líneas existente; nunca regeneran la entrada desde un dict.
- [ ] **Step 4: Correr** la suite completa. Esperado: todo PASS.
- [ ] **Step 5: Commit** `feat(biblioteca): fecha de aprobación, fallas, implementada y marcas en el índice`.

---

### Tarea 3: CLI — reincidencia al registrar y al resolver

**Files:**
- Modify: `harness/hooks/cli.py` (`cmd_record_hallazgos`, `cmd_resolver_hallazgo`, `cmd_hallazgo`, parser de `resolver-hallazgo`)
- Modify: `harness/hooks/lib/hallazgos.py` (`_encabezado`)
- Modify: `harness/commands/hallazgo-ok.md`, `harness/commands/hallazgo-editar.md`
- Test: `tests/test_cli_hallazgos.py`, `tests/test_documentos_del_harness.py`

**Interfaces:**
- Consumes: `biblioteca.leer_entrada`, `biblioteca.registrar_falla`, `escribir_entrada(..., fecha=)` (Tarea 2).
- Produces:
  - `cli._hoy() -> str`: la fecha de hoy en `dd-mm-aaaa`.
  - `record-hallazgos` copia `reincide` cuando viene. Si apunta a una ref sin entrada aprobada, falla con `la propuesta dice que hallazgos[i] reincide en '<ref>', que no es una lección aprobada de la biblioteca` y no escribe nada.
  - `resolver-hallazgo` acepta `--nueva` (flag) y `--reincide <ref>`, solo con `--decision ok|editar`.
    - La ref de reincidencia efectiva es `--reincide` si viene; si no, el `reincide` del hallazgo, salvo que venga `--nueva`.
    - Con ref efectiva: el hallazgo queda `aprobado`, con `reincide` igual a esa ref. Se llama a `registrar_falla(root, ref_efectiva, ref_del_hallazgo, hallazgo["leccion"], _hoy())` **en lugar de** `escribir_entrada`. Imprime `Hallazgo <ref> aprobado como reincidencia de <ref_efectiva>: <ruta de la entrada original>`.
    - Con `--nueva`: se borra `reincide` del hallazgo y se escribe la entrada nueva como hoy.
  - Toda aprobación (`resolver-hallazgo` y `hallazgo`) pasa `fecha=_hoy()` a `escribir_entrada`.
  - En `hallazgos.md`, el encabezado de un hallazgo con `reincide` agrega `reincide en <ref>` antes del estado.

- [ ] **Step 1: Escribir las pruebas que fallan** — clase `TestReincidencia(Base)` en `tests/test_cli_hallazgos.py`. Arranca con una lección aprobada `ISR-110722/fase_1/h1` en la biblioteca: se propone, se aprueba y se cierra la fase 2 para la propuesta nueva.
  - `test_registra_el_campo_reincide`: propuesta en fase_2 con `reincide: "ISR-110722/fase_1/h1"` → código 0; `hallazgos.json` lo conserva; `hallazgos.md` contiene `reincide en ISR-110722/fase_1/h1`.
  - `test_reincide_hacia_rechazada_o_inexistente` (Review Focus 2): para una ref en `rechazados/` y para `ISR-9/fase_1/h1` → código 1, stderr contiene `no es una lección aprobada` y `hallazgos.json` de fase_2 no existe.
  - `test_aprobar_reincidencia_no_crea_entrada`: `resolver-hallazgo --decision ok --id ISR-110722/fase_2/h1` → la cantidad de archivos en `entradas/` no cambia; `leer_entrada(root, "ISR-110722/fase_1/h1")["fallas"][0]["ref"] == "ISR-110722/fase_2/h1"`; stdout contiene `aprobado como reincidencia de ISR-110722/fase_1/h1`.
  - `test_editar_reincidencia_guarda_la_leccion_corregida`: `--decision editar --texto "Usar curl.exe"` → la falla trae `leccion == "Usar curl.exe"`.
  - `test_nueva_ignora_reincide`: `--decision ok --nueva` → existe `entradas/ISR-110722-fase_2-h1.md`; el hallazgo guardado no tiene `reincide`; la original no tiene fallas.
  - `test_reincide_manual_sin_marca_del_reflector`: propuesta sin `reincide`, aprobada con `--reincide ISR-110722/fase_1/h1` → hay falla en la original y no hay entrada nueva.
  - `test_opciones_incompatibles` (Review Focus 3): `--nueva --reincide X`, `--decision no --motivo m --nueva` y `--decision no --motivo m --reincide X` → código 1 cada una, y el hallazgo sigue `propuesto`.
  - `test_toda_aprobacion_lleva_fecha`: tras `--decision ok` sin reincidencia, y tras `hallazgo --texto t` → `leer_entrada(...)["aprobada"]` cumple `contracts.RE_FECHA`.
  - En `tests/test_documentos_del_harness.py`, `TestComandosDeHallazgos.test_ok_y_editar_documentan_nueva_y_reincide`: `hallazgo-ok.md` y `hallazgo-editar.md` contienen `--nueva` y `--reincide`.
- [ ] **Step 2: Correr** `python -m unittest tests.test_cli_hallazgos tests.test_documentos_del_harness -v`. Esperado: FAIL en las nuevas.
- [ ] **Step 3: Implementar** en `cli.py` y `lib/hallazgos.py`. Toda validación de opciones y de la ref ocurre antes de escribir cualquier archivo. En los dos `.md` de comandos: si el usuario agrega `--nueva` o `--reincide <ref>`, se pasan tal cual al CLI, con una línea sobre cuándo usar cada una: "no es reincidencia" y "es reincidencia de esta otra lección".
- [ ] **Step 4: Correr** la suite completa. Esperado: todo PASS.
- [ ] **Step 5: Commit** `feat(cli): reincidencias registradas como falla de la lección original`.

---

### Tarea 4: `/hallazgo-hecho`

**Files:**
- Modify: `harness/hooks/cli.py` (`cmd_hallazgo_hecho` y su parser)
- Create: `harness/commands/hallazgo-hecho.md`
- Test: `tests/test_cli_hallazgos.py`, `tests/test_documentos_del_harness.py`

**Interfaces:**
- Consumes: `biblioteca.marcar_implementada` (Tarea 2), `cli._hoy` (Tarea 3).
- Produces: `cli.py hallazgo-hecho [--project] --id <TICKET/fase_N/hN> --nota "<nota>"`. Solo acepta la referencia completa. Salida: `Lección <ref> implementada: <fecha> · <nota>`, y si había una marca anterior, una segunda línea `Reemplaza la marca anterior: <valor>`.

- [ ] **Step 1: Escribir las pruebas que fallan** — clase `TestHallazgoHecho(Base)`:
  - `test_marca_la_leccion`: código 0; `leer_entrada(...)["implementada"]` termina en `· commit abc123`; `INDEX.md` contiene `(implementada `.
  - `test_reemplaza_y_avisa`: segunda llamada → stdout contiene `Reemplaza la marca anterior:`.
  - `test_exige_nota_no_vacia`: `--nota "  "` → código 1.
  - `test_rechaza_ref_suelta_o_no_aprobada`: `--id h1` y una ref de `rechazados/` → código 1, y la entrada no cambia.
  - En `TestComandosDeHallazgos`, el comando nuevo pasa `test_cada_comando_tiene_descripcion_y_subcomando` y `test_los_que_resuelven_aceptan_la_referencia_completa`. Agrégalo a las listas de esas pruebas si las enumeran.
- [ ] **Step 2: Correr** `python -m unittest tests.test_cli_hallazgos tests.test_documentos_del_harness -v`. Esperado: FAIL.
- [ ] **Step 3: Implementar** el subcomando y `hallazgo-hecho.md`, con frontmatter `description: Marca como implementada la pieza que pedía una lección de la biblioteca` y `argument-hint: <TICKET/fase_N/hN> "<nota>"`, en el mismo estilo que `hallazgo-ok.md`: CLI único que escribe, salida tal cual y sugerir versionar `.claude/biblioteca/`.
- [ ] **Step 4: Correr** la suite completa (incluye `test_referencias_harness`). Esperado: todo PASS.
- [ ] **Step 5: Commit** `feat(cli): /hallazgo-hecho marca la lección como implementada`.

---

### Tarea 5: `report.agregar` — los datos

**Files:**
- Create: `harness/hooks/report.py`
- Test: `tests/test_report.py`

**Interfaces:**
- Consumes: `harness.tickets_dir`, `biblioteca.biblioteca_dir`, `biblioteca.leer_entrada` (Tarea 2), `contracts.validate_hallazgos`, `contracts.validate_fase_state`.
- Produces: `report.agregar(project_root: Path) -> dict`, serializable a JSON, con exactamente estas claves:

```text
resumen: {tickets, fases, fases_escaladas, lecciones_aprobadas, implementadas,
          fallaron_implementadas, volvieron_sin_pieza}          # todos int; los dos
                                                                # últimos cuentan lecciones
fallaron_implementadas: [{ref, senal, componente, fallas: [{fecha, ref, leccion}]}]
deuda: {<componente o "sin pieza">: [{ref, senal, fallas: [{fecha, ref, leccion}]}]}
       # solo aprobadas sin implementada; dentro de cada grupo, primero las de más
       # fallas "sin pieza", luego por ref
hallazgos: {propuestos: [{ref, senal}], aprobados_tal_cual: int,
            aprobados_editados: int, reincidencias: int, del_humano: int,
            rechazados: [{ref, motivo}]}
       # aprobados_* y rechazados cuentan solo origen reflector; reincidencias =
       # aprobados con reincide; editados = con leccion_original y sin reincide
fases: {intentos_por_fase: {"T/fase_N": {intentos, max, estado}},
        escaladas: ["T/fase_N"], origen_de_fallos: {origen: int},
        reglas_mas_violadas: {check_id: int},
        rechazos_repetidos_del_esceptico: [{fase, veces, razones: [str]}]}
       # una fase entra si su historial tiene >= 2 fallos de origen esceptico
ilegibles: [ruta relativa a project_root, con "/"]
```

`senal` de una lección es su `senal`, o su `leccion` si no trae señal. Las fallas de `fallaron_implementadas` son solo las de tipo `implementada`, y las de `deuda`, solo las `sin pieza`.

- [ ] **Step 1: Escribir las pruebas que fallan.** `tests/test_report.py` siembra un proyecto con 2 tickets. ISR-1/fase_1 queda aprobada con 2 intentos y un fallo de check `designer_x`. ISR-2/fase_1 queda escalada, con 2 rechazos del escéptico de razones distintas y uno humano. Para la biblioteca usa `escribir_entrada`, `registrar_falla` y `marcar_implementada` (no texto a mano). Siembra 3 aprobadas: A (check, implementada, 1 falla implementada), B (check, sin implementar, 2 fallas sin pieza) y C (sin componente, del humano). También un `hallazgos.json` con un propuesto, un aprobado tal cual, uno editado, una reincidencia, un rechazado con motivo y uno del humano.
  - `test_resumen`: `{"tickets": 2, "fases": 2, "fases_escaladas": 1, "lecciones_aprobadas": 3, "implementadas": 1, "fallaron_implementadas": 1, "volvieron_sin_pieza": 1}`.
  - `test_fallaron_implementadas`: una sola lección, A, con 1 falla.
  - `test_deuda_agrupa_y_ordena`: `deuda["check"][0]["ref"]` es B, con 2 fallas; `"sin pieza"` contiene C; A no aparece en la deuda.
  - `test_salud_de_hallazgos`: `aprobados_tal_cual == 1`, `aprobados_editados == 1`, `reincidencias == 1`, `del_humano == 1`, `rechazados == [{"ref": ..., "motivo": ...}]`, `len(propuestos) == 1`.
  - `test_fases`: `escaladas == ["ISR-2/fase_1"]`; `origen_de_fallos == {"check": 1, "esceptico": 2, "humano": 1}`; `reglas_mas_violadas == {"designer_x": 1}`; `rechazos_repetidos_del_esceptico` tiene una entrada con `fase == "ISR-2/fase_1"`, `veces == 2` y las 2 razones.
  - `test_proyecto_vacio` (Review Focus 4): un directorio vacío → todos los conteos en 0, listas vacías e `ilegibles == []`.
  - `test_datos_rotos_no_detienen` (Review Focus 5): agregar al proyecto sembrado un `fase_state.json` con JSON inválido, otro con bytes `b"\xe9"`, otro que es `{}`, un `hallazgos.json` fuera de contrato y un `checks.json` que es una lista → no lanza; `ilegibles` nombra los 5; el resumen sigue contando lo legible.
  - `test_no_escribe_nada`: tomar `{ruta: (tamaño, mtime_ns)}` de todo el árbol antes y después de `agregar` → iguales.
- [ ] **Step 2: Correr** `python -m unittest tests.test_report -v`. Esperado: FAIL con `ModuleNotFoundError: No module named 'report'`.
- [ ] **Step 3: Implementar** `report.agregar`. Recorre `tickets/*/fase_*/` (`fase_state.json`, `hallazgos.json`, `intento_*/checks.json`) y `biblioteca/entradas/*.md`, con un `try` por archivo que captura `OSError`, `ValueError` (incluye `JSONDecodeError` y `UnicodeDecodeError`), `KeyError`, `TypeError` y `AttributeError`, y anota la ruta en `ilegibles`. La ref de una entrada sale de su primera línea (`# <ref>`), no del nombre del archivo. No reutilices el código de la Task 20 original: la agrupación del escéptico cambió.
- [ ] **Step 4: Correr** la suite completa. Esperado: todo PASS.
- [ ] **Step 5: Commit** `feat(report): agregación de lecciones, hallazgos y fases, de solo lectura`.

---

### Tarea 6: `report.render` y `cli.py report`

**Files:**
- Modify: `harness/hooks/report.py`, `harness/hooks/cli.py`
- Test: `tests/test_report.py`

**Interfaces:**
- Consumes: `report.agregar` (Tarea 5).
- Produces: `report.render(datos: dict) -> str`; `cli.py report [--project <ruta>] [--json]`, que sale con código 0. `--json` imprime `json.dumps(datos, ensure_ascii=False, indent=2)`.

Encabezados exactos, en este orden: `HARNESS · reporte`, `Resumen`, `Fallaron estando implementadas`, `Deuda`, `Hallazgos`, `Fases`, `Archivos que no se pudieron leer`. Este último solo aparece si hay ilegibles. Una sección sin datos lleva la línea `  Sin datos todavía.`.

- [ ] **Step 1: Escribir las pruebas que fallan**, sobre el proyecto sembrado de la Tarea 5:
  - `test_secciones_en_orden`: los índices de los encabezados en el texto son crecientes.
  - `test_deuda_dice_cuanto_costo`: el texto contiene `costó otra vez 2×` en la línea de B.
  - `test_falla_muestra_lo_que_debio_hacer`: el texto contiene la lección de la falla sembrada en A.
  - `test_secciones_vacias` (Review Focus 4): en un proyecto vacío, `render` contiene `Sin datos todavía.` al menos 4 veces y no contiene `Archivos que no se pudieron leer`.
  - `test_cli_report_texto_y_json`: correr `cli.py report --project <root>` → código 0, stdout con `Resumen`. Con `--json` → `json.loads(stdout)["resumen"]["tickets"] == 2`.
- [ ] **Step 2: Correr** `python -m unittest tests.test_report -v`. Esperado: FAIL.
- [ ] **Step 3: Implementar** `render` y el subcomando (`import report` después de los imports de `lib`).
- [ ] **Step 4: Correr** la suite completa. Esperado: todo PASS.
- [ ] **Step 5: Aceptación de solo lectura.** Antes y después, `git -C C:\AZZULE\DesarrolloSCP\NAS status --short` y el mismo snapshot de tamaños y mtimes de `.harness` y `.claude\biblioteca` deben ser iguales.
  - `python harness/hooks/cli.py report --project C:\AZZULE\DesarrolloSCP\NAS --json`. Esperado: `lecciones_aprobadas == 18` e `implementadas == 0`. `rechazados` con 3 entradas y `propuestos` con 4, salvo que NAS haya cambiado desde el 02-11-2026; en ese caso, anota los números reales.
  - Lo mismo sin `--json`, y sobre `C:\AZZULE\EditorNotificaciones`. Esperado: código 0 y, en la biblioteca, `Sin datos todavía.`.
  - Si `ilegibles` no está vacío, revisa cada archivo antes de cerrar: o es un dato roto de verdad (anótalo), o el reporte lee mal un formato válido (corrígelo).
- [ ] **Step 6: Commit** `feat(cli): subcomando report, en texto y JSON`.

---

### Tarea 7: Reflector y planner

**Files:**
- Modify: `harness/agents/reflector.md`, `harness/skills/task-planner/SKILL.md`
- Test: `tests/test_documentos_del_harness.py`

**Interfaces:**
- Consumes: el contrato de la Tarea 1 y las marcas del índice de la Tarea 2.

- [ ] **Step 1: Escribir las pruebas que fallan** en `TestAgenteReflector`:
  - `test_explica_reincide`: el texto contiene `reincide`, `TICKET/fase_N/hN` y `debió hacer`.
  - `test_reincide_aunque_este_implementada`: el texto contiene `implementada`.
  - `test_el_ejemplo_de_salida_cumple_el_contrato` (ya existe): el ejemplo agrega un segundo bloque JSON con `reincide`. Si la prueba toma solo el primer bloque, extiéndela para validar todos los bloques ```json del archivo.
  - Una prueba en una clase del planner: `task-planner/SKILL.md` contiene `falló`.
- [ ] **Step 2: Correr** `python -m unittest tests.test_documentos_del_harness -v`. Esperado: FAIL.
- [ ] **Step 3: Redactar.**
  - En `reflector.md`: cuándo una lección nueva es reincidencia de una aprobada (el mismo error que la `senal` de esa lección debía evitar, aunque esté implementada). Que en ese caso `leccion` describa lo que debió hacer el agente o la pieza en esta fase. Que se use la ref de la entrada (`entradas/<archivo>` en el índice, o la primera línea de la entrada). Que nunca se marque una rechazada.
  - En el planner: una línea que dice que una lección con `(falló N×)` pesa más al planear.
- [ ] **Step 4: Correr** la suite completa (incluye la separación de planos). Esperado: todo PASS.
- [ ] **Step 5: Commit** `docs(harness): el reflector marca reincidencias y el planner pesa las que fallaron`.

---

### Tarea 8: Documentación de uso y técnica

**Files:**
- Modify: `README.md` (pasa a ser la guía de uso)
- Create: `docs/tecnico.md`
- Create: `tests/test_documentacion.py`

**Interfaces:**
- Consumes: todos los comandos y subcomandos de las tareas anteriores.

Reparto, según el spec:
- **`README.md`**: qué es, instalación y despliegue, el ciclo de un ticket, uso diario, los comandos uno por uno (incluidos `/hallazgo-hecho`, `--nueva` y `--reincide`), cómo leer el reporte (sección por sección, con qué hacer ante "fallaron estando implementadas" y ante la deuda) y errores frecuentes. Arriba, un enlace a `docs/tecnico.md`.
- **`docs/tecnico.md`**: arquitectura de tres planos, dónde va cada corrección, referencia del CLI, estado en disco y contratos (con `reincide` y las líneas `aprobada`, `falló` e `implementada` de la entrada), crear el perfil de un proyecto, uso con otros modelos, desarrollo del harness, estructura del repositorio y pendientes conocidos. En pendientes: quitar lo que ya se resolvió y agregar los pasos 2 a 6 del orden acordado (ver `.superpowers/sdd/progress.md`).

- [ ] **Step 1: Escribir las pruebas que fallan** en `tests/test_documentacion.py`:
  - `test_readme_enlaza_al_tecnico`: `README.md` contiene `docs/tecnico.md`.
  - `test_readme_documenta_cada_comando`: cada `harness/commands/*.md` aparece en `README.md` como `` `/<nombre> ``.
  - `test_tecnico_documenta_cada_subcomando`: cada subcomando de `add_parser` de `cli.py` aparece en `docs/tecnico.md`.
  - `test_sin_secciones_duplicadas`: ningún encabezado `## ` aparece con el mismo texto en los dos archivos.
- [ ] **Step 2: Correr** `python -m unittest tests.test_documentacion -v`. Esperado: FAIL.
- [ ] **Step 3: Redactar** los dos documentos. Mueve el contenido del README actual (no lo reescribas desde cero) y agrega lo nuevo.
- [ ] **Step 4: Correr** la suite completa. Esperado: todo PASS. Anota el total de pruebas.
- [ ] **Step 5: Commit** `docs: README de uso y docs/tecnico.md, al día con el reporte y las reincidencias`.
- [ ] **Step 6: Ledger.** En `.superpowers/sdd/progress.md` (no versionado): Task 20 ampliada completa, con los commits y el resultado de la aceptación de la Tarea 6; SIGUIENTE: paso 2 del orden (test de punta a punta con modelo falso).
