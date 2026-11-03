# Curación de la biblioteca — plan de implementación

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Que la biblioteca de lecciones se pueda curar (fusionar y retirar lecciones) con señales deterministas, un curador de solo lectura que propone y el humano que decide, sin perder historia ni romper referencias.

**Architecture:** Las señales (`usos`, `ultimo_uso`, `rutas_ausentes`) las calcula un módulo nuevo de solo lectura. Las acciones aprobadas las aplica `lib/biblioteca.py` (mover a `retiradas/`, reescribir el destino de una fusión). El estado de la curación vive en `.harness/curacion.json` con el mismo patrón que `hallazgos.json`, y los rechazos van a la biblioteca versionada. El CLI es el único que escribe.

**Tech Stack:** Python 3.12 sin dependencias, `unittest`, git por subprocess, Markdown para comandos y agentes de Claude Code.

**Spec:** `docs/superpowers/specs/2026-11-03-curacion-de-la-biblioteca-design.md`

## Global Constraints

- Python 3.12 sin dependencias externas; Windows + PowerShell 5.1.
- Superficie pública en inglés salvo términos del dominio (`leccion`, `curacion`, `retirada`, `fusionada`, `senal`, `ref`); variables locales y comentarios en español.
- Archivos del proyecto (los que mencionan las lecciones) se leen con `gitdiff.read_text`; las entradas de la biblioteca las escribe y lee el CLI en UTF-8, como hoy.
- `harness/` no menciona ningún stack (`tests/test_referencias_harness.py` y la prueba de stack lo vigilan).
- Toda escritura de la biblioteca pasa por `lib/biblioteca.py` y termina en `reconstruir_indice`.
- Las líneas de una entrada que el código no conoce se conservan intactas, también con CRLF.
- Referencias con la forma `TICKET/fase_N/hN` (`contracts.RE_REFERENCIA`); el archivo es `entrada_path(...)` (`/` → `-`), y la ref verdadera de un archivo es su primera línea `# <ref>`.
- Fechas `DD-MM-YYYY` (`cli._hoy()`).
- Suite: `python -m unittest discover -s tests` verde al cerrar cada tarea.

## Review Focus

1. **Entrada con CRLF** (checkout de git en Windows): `retirar` y `fusionar` deben encontrar y reemplazar la línea `- **lección**:` aunque termine en `\r`, y conservar el resto. → test en Tarea 2.
2. **Entrada sin `señal`** (lección del humano): fusionar con `--senal` agrega la línea en vez de fallar; sin `--senal`, el índice sigue mostrando la lección. → test en Tarea 2.
3. **Una acción cuya ref ya no está en `entradas/`** al resolverla (la retiró otra acción ya aprobada, o alguien la movió a mano): `resolver-curacion` falla con error claro y no escribe nada. → test en Tarea 5.
4. **Proyecto sin git o sin `.harness/`**: `senales-biblioteca` y el reporte no revientan; `rutas_ausentes` queda `null` (desconocido, no "todas ausentes") y `usos` en 0. → test en Tarea 3.
5. **Primer rechazo**: `curacion-rechazada.md` no existe y se crea con su encabezado; el siguiente rechazo agrega una línea sin duplicar el encabezado. → test en Tarea 5.

---

### Task 1: Retirar una lección y la sección Retiradas del índice

**Files:**
- Modify: `harness/hooks/lib/biblioteca.py`
- Test: `tests/test_biblioteca_curacion.py` (nuevo)

**Interfaces:**
- Produces:
  - `retirar(project_root: Path, ref: str, motivo: str, fecha: str) -> Path`: mueve `entradas/<archivo>` a `retiradas/<archivo>`, agrega `- **retirada**: <fecha> · <motivo>` al final, reconstruye el índice y devuelve la ruta nueva. `ValueError` si la ref no está en `entradas/`.
  - `ubicacion(project_root: Path, ref: str) -> tuple[str, str]`: `("entradas", "")`, `("retiradas", <motivo de la línea retirada>)` o `("ninguna", "")`.
  - `reconstruir_indice` agrega, después de Aprobadas y antes de Rechazadas, `## Retiradas — no aplicar` con una línea `- <resumen> — retiradas/<archivo> — motivo: <motivo>` por entrada (o `_(vacía)_`).

- [ ] **Step 1: Tests que fallan** — en `tests/test_biblioteca_curacion.py` (helpers como `tests/test_report.py`: `_aprobado`, `escribir_entrada` sobre un tmp):
  - `test_retirar_mueve_la_entrada_y_anota_el_motivo`: tras `retirar(raiz, REF_A, "contradice agent-x §2", "03-11-2026")`, `entrada_path(raiz, REF_A)` no existe, `retiradas/ISR-1-fase_1-h1.md` existe y termina con `- **retirada**: 03-11-2026 · contradice agent-x §2`.
  - `test_retirar_conserva_fallas_e_implementada`: una entrada con `registrar_falla` y `marcar_implementada` previas conserva esas dos líneas tras retirarla.
  - `test_retirar_una_ref_que_no_esta_es_error`: `ValueError` y no se crea `retiradas/`.
  - `test_el_indice_lista_las_retiradas_aparte`: `INDEX.md` contiene `## Retiradas — no aplicar` y la línea con `retiradas/ISR-1-fase_1-h1.md — motivo: contradice agent-x §2`; la sección Aprobadas ya no la lista.
  - `test_ubicacion_dice_donde_esta`: `("entradas","")` antes, `("retiradas","contradice agent-x §2")` después, `("ninguna","")` para una ref inventada.
- [ ] **Step 2: Correr y ver que fallan** — `python -m unittest tests.test_biblioteca_curacion -v` → `AttributeError: ... 'retirar'`.
- [ ] **Step 3: Implementar** `retirar`, `ubicacion` y la sección nueva de `reconstruir_indice` (mover con `Path.replace`, reutilizar `_agregar_al_final` y `_campo`).
- [ ] **Step 4: Correr** el archivo nuevo y `tests.test_hallazgos_biblioteca` → PASS.
- [ ] **Step 5: Commit** — `feat(biblioteca): retirar lecciones a retiradas/ sin perder su historia`

### Task 2: Fusionar lecciones

**Files:**
- Modify: `harness/hooks/lib/biblioteca.py`
- Test: `tests/test_biblioteca_curacion.py`

**Interfaces:**
- Consumes: `retirar` (Tarea 1).
- Produces: `fusionar(project_root: Path, destino: str, absorbidas: list[str], leccion: str, senal: str | None, fecha: str) -> Path`. En el destino: reemplaza la línea `lección` (si no tenía `lección original`, agrega `- **lección original**: <la anterior>`); reemplaza o agrega `señal` si `senal`; por cada absorbida copia sus líneas `falló` tal cual y agrega `- **fusionada**: <fecha> · <ref absorbida>` (más ` · implementada <nota>` si la absorbida estaba implementada). Después retira cada absorbida con motivo exactamente `fusionada en <destino>`. `ValueError` sin escribir nada si alguna ref no está en `entradas/`, si `destino in absorbidas`, o si mezclan implementadas y no implementadas.

- [ ] **Step 1: Tests que fallan:**
  - `test_fusionar_reemplaza_la_leccion_y_guarda_la_original`.
  - `test_fusionar_copia_las_fallas_de_las_absorbidas`: B con una línea `falló` → aparece idéntica en A; `leer_entrada(raiz, REF_A)["fallas"]` tiene 1.
  - `test_las_absorbidas_quedan_retiradas_como_fusionadas`: `ubicacion(raiz, REF_B) == ("retiradas", f"fusionada en {REF_A}")`.
  - `test_fusionar_con_senal_la_reemplaza_y_sin_senal_la_conserva`.
  - `test_fusionar_agrega_senal_a_una_entrada_que_no_la_tenia` (entrada del humano, solo `lección`).
  - `test_fusionar_mezcla_de_implementadas_es_error_y_no_escribe` (compara el texto de A y B antes y después).
  - `test_fusionar_todas_implementadas_conserva_la_marca_y_anota_las_otras`.
  - `test_fusionar_una_entrada_con_crlf`: escribe A con `\r\n`; tras fusionar, la `lección` nueva está y no quedan dos líneas `lección`.
- [ ] **Step 2: Correr y ver que fallan.**
- [ ] **Step 3: Implementar `fusionar`.** Validar todo antes de escribir; buscar líneas con `linea.rstrip("\r").startswith("- **lección**: ")`.
- [ ] **Step 4: Correr** → PASS.
- [ ] **Step 5: Commit** — `feat(biblioteca): fusionar lecciones conservando fallas y marcas`

### Task 3: Señales deterministas y `senales-biblioteca`

**Files:**
- Create: `harness/hooks/lib/senales.py`
- Modify: `harness/hooks/cli.py` (subcomando `senales-biblioteca [--project] [--json]`)
- Test: `tests/test_senales.py` (nuevo)

**Interfaces:**
- Consumes: `biblioteca.biblioteca_dir`, `harness.tickets_dir`, `harness.read_json`, las líneas `fusionada` de la Tarea 2.
- Produces: `senales(project_root: Path) -> dict` con
  `{"lecciones": [{"ref", "archivo", "senal", "usos": int, "ultimo_uso": str | None, "rutas_ausentes": list[str] | None, "fallas": int, "implementada": bool}], "ultima_curacion": str | None}`, ordenadas por `ref`. `ultima_curacion` es la fecha más reciente de una acción resuelta en `.harness/curacion.json` (campo `fecha_resuelta`, Tarea 4); `None` si no hay.
  - `usos`: anclajes de `.harness/tickets/*/plan.json` (`fases[].anclajes[].ref`) cuyo nombre de archivo es el de la entrada; un ancla a una absorbida cuenta para su destino (siguiendo `fusionada`).
  - `ultimo_uso`: ticket con la `fecha` más reciente de `ticket_context.json` entre los que la anclan; sin fecha, el mayor por nombre.
  - `rutas_ausentes`: tokens de `señal` y `lección` (no `evidencia`) que parecen ruta y no coinciden por sufijo de segmentos completos, sin distinguir mayúsculas, con ningún archivo ni carpeta de `git ls-files`. `None` si git no está disponible.
- `cli.py senales-biblioteca` imprime una línea por lección: `<ref> — usos <n> (último <ticket>) — rutas ausentes: <lista|ninguna|desconocido>`; con `--json`, el dict.

- [ ] **Step 1: Tests que fallan:**
  - `test_cuenta_los_anclajes_de_los_planes` (dos tickets, uno ancla A dos veces en fases distintas → `usos` 2) y `test_ultimo_uso_es_el_ticket_mas_reciente_por_fecha`.
  - `test_un_ancla_a_una_absorbida_cuenta_para_el_destino`.
  - `test_ruta_que_coincide_por_sufijo_no_es_ausente`: repo con `AzzuleSite/Assets/components/global/x.vue` rastreado; lección que dice `` `components/global/x.vue` `` → `rutas_ausentes == []`.
  - `test_carpeta_rastreada_cuenta`: `src/scss` con un archivo dentro rastreado → no ausente.
  - `test_ruta_inexistente_es_ausente`: `components/global/borrado.vue` → `["components/global/borrado.vue"]`.
  - `test_no_toma_como_ruta_lo_que_no_lo_es`: lección con `global.api`, `§4.1`, `[B]/[E]`, `y/o`, `ok/no`, `https://x.y/z` y `archivo.vue:31-47` (este último se compara sin el `:31-47`) → ninguno aparece como ausente salvo que el archivo falte.
  - `test_la_evidencia_no_cuenta`: `evidencia` con `intento_1/veredicto.json` → `[]`.
  - `test_sin_git_rutas_desconocidas_y_sin_harness_cero_usos` (Review Focus 4).
  - `test_cli_senales_json_y_texto`.
- [ ] **Step 2: Correr y ver que fallan.**
- [ ] **Step 3: Implementar `lib/senales.py` y el subcomando.** `git ls-files -z` con `gitdiff._git` (o un helper público nuevo `gitdiff.archivos_rastreados(raiz) -> list[str] | None`); índice de sufijos en minúsculas con cada archivo y cada carpeta ancestro.
- [ ] **Step 4: Correr** → PASS.
- [ ] **Step 5: Validar contra NAS en solo lectura:** `python harness/hooks/cli.py senales-biblioteca --project "C:\AZZULE\DesarrolloSCP\NAS"`. Esperado: 6 lecciones con `usos` ≥ 1 (las que ancla `ISR-113646`), ninguna con `[B]/[E]`, `global.api` o `intento_1/veredicto.json` como ruta ausente, y `components/global/document-tooltip.vue` no ausente. Anotar el resultado en el mensaje del commit.
- [ ] **Step 6: Commit** — `feat(senales): usos, ultimo uso y rutas ausentes por leccion`

### Task 4: Contrato y registro de la propuesta del curador

**Files:**
- Modify: `harness/hooks/lib/contracts.py`
- Create: `harness/hooks/lib/curacion.py`
- Modify: `harness/hooks/cli.py` (subcomando `record-curacion --archivo <ruta> [--project]`)
- Test: `tests/test_contracts.py`, `tests/test_cli_curacion.py` (nuevo)

**Interfaces:**
- Produces:
  - Propuesta del curador (`validate_propuesta_curacion(data) -> list[str]`): `{"acciones": [A, ...]}`, lista posiblemente vacía. `A` es `{"tipo": "retirar", "ref": R, "motivo": str}` o `{"tipo": "fusionar", "refs": [R, R, ...] (≥2, sin repetidos), "destino": R ∈ refs, "leccion": str, "senal": str (opcional), "motivo": str}`. `R` cumple `RE_REFERENCIA`. Campos de texto no vacíos.
  - Estado (`validate_curacion(data) -> list[str]`): `{"acciones": [A + {"id": "cN", "estado": "propuesto"|"aprobado"|"rechazado", "fecha_propuesta": fecha, "fecha_resuelta"?: fecha, "motivo_rechazo"?: str}]}`; ids `c\d+` únicos; `motivo_rechazo` obligatorio si `rechazado`.
  - `lib/curacion.py`: `ruta(project_root) -> Path` (`.harness/curacion.json`), `leer(project_root) -> dict | None` (valida; `ValueError` si está mal), `guardar(project_root, datos) -> Path` (valida, escribe el JSON y `.harness/curacion.md` con `render`), `render(datos) -> str` (cada acción con sus refs, motivo y, si está `propuesto`, las tres líneas `/curacion-ok cN`, `/curacion-editar cN ...`, `/curacion-no cN "<motivo>"`), `registrar_rechazo(project_root, accion, fecha) -> Path` (agrega a `biblioteca/curacion-rechazada.md`, Tarea 5).
- `record-curacion`: valida la propuesta; rechaza sin escribir si una ref no está en `entradas/` (el mensaje usa `biblioteca.ubicacion` para decir si fue retirada y por qué), si una ref aparece en dos acciones, o si una fusión mezcla implementadas y no implementadas. Reemplaza las acciones `propuesto` previas, conserva las resueltas, y numera desde el mayor id que hubo. No exige ticket ni fase activa. Imprime `N acción(es) propuesta(s) en <curacion.md>` o `El curador no propuso acciones.`

- [ ] **Step 1: Tests que fallan:**
  - En `test_contracts.py`: propuesta válida de cada tipo; `fusionar` con 1 ref, con `destino` fuera de `refs`, con refs repetidas; `tipo` desconocido; estado con `rechazado` sin `motivo_rechazo`.
  - En `test_cli_curacion.py` (proyecto tmp con `.claude/rules.json` y una biblioteca de 3 aprobadas): `test_registra_las_acciones_con_ids`, `test_una_ref_inexistente_se_rechaza_sin_escribir`, `test_una_ref_retirada_dice_adonde_fue`, `test_una_ref_en_dos_acciones_se_rechaza`, `test_fusion_de_implementada_con_no_implementada_se_rechaza`, `test_una_propuesta_nueva_reemplaza_las_pendientes_y_conserva_las_resueltas` (ids nunca se reutilizan: tras c1..c2 y una nueva de 1 acción, la nueva es c3), `test_propuesta_vacia_se_registra`, `test_no_exige_ticket_abierto`.
- [ ] **Step 2: Correr y ver que fallan.**
- [ ] **Step 3: Implementar** contrato, `lib/curacion.py` (sin `registrar_rechazo` todavía si se prefiere: queda para la Tarea 5) y el subcomando.
- [ ] **Step 4: Correr** → PASS.
- [ ] **Step 5: Commit** — `feat(curacion): contrato y record-curacion`

### Task 5: Resolver una acción de curación

**Files:**
- Modify: `harness/hooks/cli.py` (subcomando `resolver-curacion`), `harness/hooks/lib/curacion.py`
- Test: `tests/test_cli_curacion.py`

**Interfaces:**
- Consumes: `biblioteca.retirar`, `biblioteca.fusionar`, `curacion.leer/guardar`.
- Produces: `resolver-curacion --id cN --decision ok|no|editar [--texto T] [--senal S] [--quitar REF]... [--motivo M] [--project]`.
  - `no` exige `--motivo`: estado `rechazado`, `motivo_rechazo`, `fecha_resuelta`, y una línea en `biblioteca/curacion-rechazada.md`: `- <fecha> · <cN> · <tipo> · <ref o refs separadas por ", "> — <motivo>`. El archivo nuevo empieza con `# Curaciones rechazadas — no volver a proponer` y una línea en blanco.
  - `ok` aplica tal cual. `editar` en `fusionar` exige al menos uno de `--texto`, `--senal`, `--quitar`; `--quitar` no puede ser el destino ni dejar menos de 2 refs. `editar` en `retirar` exige `--motivo` y lo usa como motivo de la retirada. Lo editado se guarda en la acción (`leccion`, `senal`, `refs`, `motivo`) antes de aplicarla.
  - Antes de aplicar: la acción está `propuesto`; todas sus refs siguen en `entradas/` (Review Focus 3); ninguna está anclada por el `plan.json` del ticket de `current.json` (error: `la lección <ref> la ancla el ticket abierto <id>: resuélvela al cerrarlo`).
  - La biblioteca se escribe antes que `curacion.json` (como `resolver-hallazgo`): si falla, la acción sigue `propuesto`.

- [ ] **Step 1: Tests que fallan:** `test_ok_retira`, `test_ok_fusiona`, `test_editar_fusion_cambia_texto_y_senal`, `test_editar_quita_una_ref_y_esa_queda_en_entradas`, `test_quitar_el_destino_o_dejar_una_sola_ref_es_error`, `test_editar_retirar_exige_motivo`, `test_no_exige_motivo_y_escribe_el_rechazo_versionado`, `test_el_primer_rechazo_crea_el_archivo_con_encabezado_y_el_segundo_no_lo_repite`, `test_una_accion_ya_resuelta_no_se_resuelve_otra_vez`, `test_una_ref_que_ya_no_esta_en_entradas_falla_sin_escribir`, `test_una_leccion_anclada_por_el_ticket_abierto_no_se_toca`, `test_un_id_inexistente_lista_los_validos`.
- [ ] **Step 2: Correr y ver que fallan.**
- [ ] **Step 3: Implementar.**
- [ ] **Step 4: Correr** → PASS.
- [ ] **Step 5: Commit** — `feat(curacion): resolver-curacion aplica, edita o rechaza`

### Task 6: Referencias a lecciones retiradas

**Files:**
- Modify: `harness/hooks/cli.py` (`_no_es_aprobada` y sus tres llamadores: `cmd_record_hallazgos`, `cmd_resolver_hallazgo`, `cmd_hallazgo_hecho`)
- Test: `tests/test_cli_hallazgos.py`

**Interfaces:**
- Consumes: `biblioteca.ubicacion`.
- Produces: `_no_es_aprobada(raiz: Path, ref: str) -> str`. Para una retirada: `'<ref>', que se retiró de la biblioteca (<motivo>)`; si el motivo es `fusionada en <X>`, agrega `: usa <X>`. Para las demás, el texto actual.

- [ ] **Step 1: Tests que fallan:** `test_reincide_en_una_fusionada_dice_cual_usar` (en `record-hallazgos`), `test_hallazgo_hecho_sobre_una_retirada_dice_por_que`.
- [ ] **Step 2: Correr y ver que fallan.**
- [ ] **Step 3: Implementar.**
- [ ] **Step 4: Correr** `tests.test_cli_hallazgos` → PASS.
- [ ] **Step 5: Commit** — `feat(cli): las referencias a lecciones retiradas dicen adonde fueron`

### Task 7: Sección Curación del reporte

**Files:**
- Modify: `harness/hooks/report.py`
- Test: `tests/test_report.py`

**Interfaces:**
- Consumes: `senales.senales`, `curacion.leer`.
- Produces: en `agregar(...)` la clave `"curacion": {"sin_uso": [{"ref", "senal"}], "rutas_ausentes": [{"ref", "rutas"}], "pendientes": int, "ultima_curacion": str | None, "retiradas": int}`; `render` agrega la sección `Curación` después de `Deuda`: las dos listas, `Acciones de curación sin resolver: N`, `Última curación: <fecha|nunca>`, `Retiradas: N`, la nota `Los usos cuentan los planes de este clon; "sin uso" no basta para retirar.` y, si hay alguna señal o pendiente, `Sugerencia: /biblioteca-curar`. Un `curacion.json` ilegible va a `ilegibles` y no revienta.

- [ ] **Step 1: Tests que fallan:** `test_curacion_lista_sin_uso_y_rutas_ausentes`, `test_curacion_sugiere_curar_solo_con_senales`, `test_curacion_sin_datos`, `test_curacion_ilegible_va_a_ilegibles`, y el `--json` trae la clave.
- [ ] **Step 2: Correr y ver que fallan.**
- [ ] **Step 3: Implementar.**
- [ ] **Step 4: Correr** `tests.test_report` → PASS.
- [ ] **Step 5: Commit** — `feat(report): seccion Curacion`

### Task 8: El curador, los comandos y la documentación

**Files:**
- Create: `harness/agents/curador.md`, `harness/commands/biblioteca-curar.md`, `harness/commands/curacion-ok.md`, `harness/commands/curacion-no.md`, `harness/commands/curacion-editar.md`
- Modify: `harness/agents/reflector.md`, `harness/skills/task-planner/SKILL.md`, `README.md`, `docs/tecnico.md`
- Test: `tests/test_documentos_del_harness.py`

**Interfaces:**
- `curador.md`: frontmatter `name: curador`, `description`, `model: opus`, `tools: Read, Grep, Glob`. Sin stack. Recibe lo que lista el spec (§2) y devuelve solo el JSON de `validate_propuesta_curacion`. Reglas del spec §2, más: "sin uso" nunca es motivo suficiente; una con `falló` no se retira sin decir por qué el error ya no puede ocurrir; no fusionar implementadas con no implementadas; no reproponer lo que está en `curacion-rechazada.md` salvo evidencia nueva dicha en `motivo`; propuesta vacía válida.
- `biblioteca-curar.md`: no exige ticket. Pasos: `cli.py senales-biblioteca --json`; invocar el subagente `curador` con las entradas (`entradas/`, `rechazados/`, `curacion-rechazada.md`, `INDEX.md`), las señales y los `agents/*.md` y `rules.json` del perfil; guardar su JSON en `.harness/propuesta_curacion.json`; `cli.py record-curacion --archivo .harness/propuesta_curacion.json` (si falla, devolver el error al curador **una vez**); mostrar `.harness/curacion.md`; terminar el turno sin resolver nada.
- `curacion-ok.md` → `resolver-curacion --decision ok --id <cN>`; `curacion-no.md` → `... --decision no --id <cN> --motivo "<motivo>"`; `curacion-editar.md` → `... --decision editar --id <cN>` con `--texto`, `--senal`, `--quitar`, `--motivo` según lo que diga el usuario. Mismo estilo que `hallazgo-*.md`: reportar la salida tal cual, no editar a mano, sugerir versionar `.claude/biblioteca/`.
- `reflector.md` y `task-planner/SKILL.md`: una línea cada uno: las de `## Retiradas — no aplicar` no se aplican ni se reproponen.
- `README.md`: sección "Curar la biblioteca" (cuándo: cuando el reporte lo sugiere o la biblioteca creció; cómo decidir; que nada se borra). `docs/tecnico.md`: subcomandos nuevos en la tabla, contrato de curación, líneas `retirada` y `fusionada`, carpeta `retiradas/` y `curacion-rechazada.md`, y quitar el paso 5 de "Orden acordado" dejándolo como hecho.

- [ ] **Step 1: Tests que fallan** en `test_documentos_del_harness.py`: `TestComandosDeCuracion` con `{"curacion-ok": "resolver-curacion --decision ok", "curacion-no": "resolver-curacion --decision no", "curacion-editar": "resolver-curacion --decision editar", "biblioteca-curar": "record-curacion --archivo"}` (frontmatter con `description` y subcomando presente); `TestCurador`: frontmatter `name: curador`, nombra `fusionar` y `retirar`, dice que "sin uso" no basta, permite propuesta vacía, lee `curacion-rechazada.md`.
- [ ] **Step 2: Correr y ver que fallan.**
- [ ] **Step 3: Escribir los documentos.**
- [ ] **Step 4: Correr** la suite completa (incluye `test_referencias_harness`, que valida que todo subcomando, agente y comando nombrado exista) → PASS.
- [ ] **Step 5: Commit** — `feat(curacion): curador, comandos y documentacion`

### Task 9: Punta a punta

**Files:**
- Test: `tests/test_punta_a_punta.py` (agregar un caso; seguir el estilo de los existentes)

- [ ] **Step 1: Test** `test_curacion_de_punta_a_punta`: biblioteca de 4 aprobadas (A y B dicen lo mismo, C nombra una ruta que no existe, D anclada por un plan cerrado y con una `falló`) → `senales-biblioteca --json` marca C con ruta ausente y D con 1 uso → propuesta del "curador" (JSON fijo) con `fusionar [A, B] → A` y `retirar C` → `record-curacion` → `resolver-curacion c1 editar --senal ...` y `c2 no --motivo ...` → `INDEX.md` lista A con la señal nueva, B en Retiradas como `fusionada en A`, C sigue en Aprobadas, `curacion-rechazada.md` tiene c2 → `record-hallazgos` con `reincide` en B falla diciendo "usa A" → `report` muestra `Última curación` con la fecha de hoy.
- [ ] **Step 2: Correr** → PASS (si falla, el defecto está en una tarea anterior: corregirlo ahí, con su test).
- [ ] **Step 3: Suite completa** → PASS.
- [ ] **Step 4: Commit** — `test: curacion de la biblioteca de punta a punta`
