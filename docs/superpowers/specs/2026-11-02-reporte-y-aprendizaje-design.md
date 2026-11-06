# Reporte del harness y seguimiento de lecciones — diseño

Fecha: 02-11-2026 · Autor: Omar Rodriguez · Estado: borrador para aprobación

Amplía la Task 20 del plan original (ya ejecutada; el registro se retiró del repo)
y agrega la separación de la documentación. Es el paso 1 del orden acordado tras la
revisión externa del 02-11-2026 (registrada en `.superpowers/sdd/progress.md`).

## Intención

El reporte es **para Omar, no para el equipo**. Contesta una sola pregunta: **¿el
harness está aprendiendo?** Es decir, si un error deja una lección y esa lección
evita que el error vuelva.

El caso que muestra que funciona: el agente usó `curl` sin `.exe` en PowerShell; al
cerrar el ticket salió un hallazgo, se aprobó y se guardó en la biblioteca, y en el
ticket siguiente el agente usó `curl.exe`.

Hoy el harness no puede ver ni ese éxito ni su contrario. Los datos reales de
un proyecto real (13 tickets, 18 lecciones aprobadas y 3 rechazadas) muestran tres
cosas que el reporte tiene que hacer visibles:

1. **Nada registra si una lección falló.** Si el error vuelve, el reflector propone
   una lección nueva parecida y la biblioteca crece con duplicados. Las 3 rechazadas
   de ese proyecto son duplicados.
2. **Casi todas las lecciones son pedidos de arreglar el harness**, no consejos para
   el agente: 11 de las 18 tienen `componente: check`. Una incluso es un bug del propio
   harness (`ISR-109204-P5/fase_1/h2`: el runner compara contra HEAD). La biblioteca no
   sabe cuáles se hicieron, así que esa deuda es invisible.
3. **No hay métricas de fases** (intentos, origen de los fallos, escalados): la Task 20
   original las diseñó antes de que existieran los hallazgos.

## Metas

- **M1 · Lección que falló.** Cuando un error vuelve después de aprobada la lección
  que debía evitarlo, el reporte lo muestra con lo que el agente o la pieza debió
  hacer, separado en dos grupos (decisión de Omar):
  - **Falló estando implementada**: la pieza existía y no lo evitó. Es lo más grave.
  - **Volvió sin pieza**: la lección seguía siendo solo texto en la biblioteca. Es
    deuda que costó otra vez, y el número de veces dice qué pieza construir primero.
- **M2 · Deuda de lecciones.** Toda lección aprobada nombra la pieza del harness que
  la corrige (`regla`, `check`, `skill`, `hook`, `agente`). Mientras esa pieza no se
  construya, la lección solo vive como texto en la biblioteca. El reporte lista las
  que faltan, agrupadas por pieza.
- **M3 · Salud de los hallazgos.** Cuántos hay propuestos sin decidir, aprobados tal
  cual, aprobados con edición y rechazados, con sus motivos. Sirve para ver si el
  reflector propone de más o si hay fatiga de aprobación.
- **M4 · Métricas de fases.** Las de la Task 20 original: tickets, fases, intentos por
  fase, fases escaladas, origen de los fallos, reglas más violadas y fallos recurrentes
  del escéptico (candidatos a check determinista).
- **M5 · Documentación separada.** Un documento de uso y otro técnico, al día con todo
  lo de este diseño.

## Fuera de alcance

- Deduplicar, hacer caducar o detectar contradicciones entre lecciones. Es el paso 5
  del orden acordado y conviene diseñarlo con datos de este reporte. La reincidencia
  (M1) ya evita una fuente de duplicados.
- Medir que una lección **evitó** un error. Un error que no ocurre no deja rastro. Solo
  se ve cuando la lección falla.
- Un reporte de varios proyectos a la vez, en HTML o para el equipo.
- Registrar qué lecciones usó el planner en cada plan.

## Lo que haría fracasar esto aunque funcione

- Que el reporte **escriba** algo. Es de solo lectura: no toca `.harness/` ni la
  biblioteca.
- Que reviente con los datos reales. Hay tickets anteriores a los hallazgos (todo
  `EditorNotificaciones`), entradas de la biblioteca sin los campos nuevos y, en
  general, archivos de versiones anteriores del harness. Un archivo ilegible o mal
  formado se cuenta y se nombra al final del reporte, no detiene el resto.
- Que necesite un modelo. El reporte es un script determinista.
- Que la reincidencia agregue una entrada nueva a la biblioteca. Si lo hace, el
  duplicado que se quería evitar vuelve por otro camino.

## Restricciones

- Las del plan original y las convenciones de Omar: superficie pública en inglés,
  locales y términos del dominio en español; nunca forzar UTF-8 al leer archivos del
  proyecto; fechas `dd-mm-aaaa`; el harness no menciona ningún stack (lo vigila un
  test).
- El CLI es el único que escribe estado; el modelo solo produce JSON validado.
- Python estándar, sin dependencias; pruebas con `unittest`. La suite de 284 pruebas
  sigue en verde.
- Windows y PowerShell 5.1 son el entorno de uso.

## Cómo se construye: lo decidido

### 1. Reincidencia (M1)

**El reflector la detecta.** Ya recibe `INDEX.md` con las lecciones aprobadas. Cuando
un hallazgo nuevo es el mismo error que una lección aprobada ya debía evitar, agrega
el campo opcional `reincide` con la referencia de esa lección
(`TICKET/fase_N/hN`). Marca toda reincidencia, esté o no implementada la lección. En
ese caso, `leccion` describe **lo que debió hacer el agente o la pieza** en esta fase
según la lección original, y `evidencia` dice dónde se vio.

**El contrato lo valida.** `reincide` es opcional en la propuesta y en
`hallazgos.json`. Si viene, tiene forma de referencia y `record-hallazgos` comprueba
que exista una entrada **aprobada** con esa referencia en `.claude/biblioteca/entradas/`.
Si no existe, la propuesta se rechaza con el error, como cualquier otra propuesta
inválida.

**El humano lo confirma** con los mismos comandos de hoy:

- `/hallazgo-ok` y `/hallazgo-editar`: el hallazgo queda `aprobado` en
  `hallazgos.json`, pero **no** crea entrada nueva. El CLI agrega a la entrada original
  una línea `- **falló**: <fecha> · <ref nueva> — <lección del hallazgo>`. Una lección
  puede acumular varias.
- `/hallazgo-no`: se rechaza como hoy, a `rechazados/` con su motivo.

`hallazgos.md` muestra en el encabezado del hallazgo `reincide en <ref>`, para que
el humano sepa qué está aprobando.

**Cuando el reflector se equivoca** *(decisión de Claude)*, `resolver-hallazgo` con
`ok` o `editar` acepta dos opciones, que los comandos `/hallazgo-ok` y
`/hallazgo-editar` pasan tal cual:

- `--nueva`: no es reincidencia; se ignora `reincide` y se crea una entrada nueva,
  como hoy.
- `--reincide <ref>`: es reincidencia de esa lección, la marque o no el reflector, o
  aunque marque otra. Se valida igual que el campo.

**La línea `falló` guarda el estado de la lección en ese momento** *(decisión de
Claude)*:
`- **falló**: <fecha> · <ref nueva> · implementada|sin pieza — <lección del hallazgo>`.
Así, "falló estando implementada" no depende del estado actual ni de ordenar fechas
del mismo día.

**Fecha de aprobación** *(decisión de Claude)*: las entradas nuevas llevan
`- **aprobada**: <fecha>`. Las 18 entradas de ese proyecto no la tienen y siguen siendo
válidas. No se bloquea automáticamente una reincidencia contra una lección aprobada
después de la fase: el reflector y el humano lo juzgan, como hoy con todo hallazgo.

### 2. Lección implementada (M2)

**Comando nuevo `/hallazgo-hecho <ref> "<nota>"`**, que corre
`cli.py hallazgo-hecho --id <ref> --nota "<nota>"`. La nota es obligatoria: un commit,
un archivo o una descripción corta de qué se construyó. El comando escribe en la
entrada de la biblioteca `- **implementada**: <fecha> · <nota>`.

- La referencia tiene que ser una entrada aprobada; si no, error.
- Si ya estaba marcada, se reemplaza la marca y el comando imprime la anterior.
- Las líneas `falló` se conservan siempre.

**Deuda** = toda entrada aprobada sin `implementada`. Corrige lo que se dijo en la
conversación: no hay lecciones que sean "solo consejo", porque toda lección del
reflector trae `componente`. Las del humano (`/hallazgo`) pueden no traerlo: van a la
deuda en un grupo "sin pieza" *(decisión de Claude; no se cambia el comando
existente)*.

### 3. INDEX.md

Cada lección aprobada muestra sus marcas al final de la línea, por ejemplo
`(implementada 02-11-2026)` o `(falló 2×)`. El planner y el reflector leen el índice:
así saben qué lecciones ya tienen una pieza que las respalda y cuáles fallaron
estando en la biblioteca. *(Decisión de Claude:)* el reflector cambia su
instrucción para marcar `reincide`; el planner solo ve las marcas, y su instrucción
gana una línea: una lección con `falló` pesa más al planear.

### 4. El reporte

`python cli.py report [--project <ruta>] [--json]`, sobre un solo proyecto. Sale en
texto para la terminal y, con `--json`, crudo. Lee `.harness/tickets/` y
`.claude/biblioteca/`.

Las secciones van en este orden, de lo que más dice sobre si el harness aprende a lo
que menos:

1. **Resumen**: tickets, fases, fases escaladas, lecciones aprobadas, implementadas,
   que fallaron estando implementadas y que volvieron sin pieza.
2. **Fallaron estando implementadas**: las fallas cuya línea `falló` dice
   `implementada`. Por lección, su señal y su pieza; por cada falla, fecha, ticket y
   lo que debió hacer. Es la sección más grave: la pieza no funciona.
3. **Deuda**: lecciones aprobadas sin implementar, agrupadas por pieza. Las que
   **volvieron sin pieza** (fallas con `sin pieza`) van primero dentro de su grupo,
   con "costó otra vez N×" y, por cada vez, fecha, ticket y lo que debió hacer.
4. **Hallazgos**: propuestos sin decidir (con su referencia), aprobados tal cual,
   aprobados con edición (los que traen `leccion_original`) y rechazados, con sus
   motivos.
5. **Fases**: lo de la Task 20 original, con un cambio *(decisión de Claude)*. La
   Task 20 agrupaba los fallos del escéptico por texto exacto de `razon`, y en ese proyecto
   las 11 razones son distintas, así que la sección saldría siempre vacía. Se agrupa
   por fase: una fase que el escéptico rechazó en dos o más intentos es candidata a
   check determinista, y se muestran sus razones.
6. **Archivos que no se pudieron leer**, si hubo.

Si un dato no existe en el proyecto, su sección dice que no hay datos; no desaparece
en silencio.

### 5. Documentación (M5)

- **`README.md` pasa a ser la guía de uso**: qué es, instalación y despliegue, el ciclo
  de un ticket, uso diario, los comandos uno por uno (incluidos `/hallazgo-hecho` y el
  reporte), cómo leer el reporte y errores frecuentes. Al principio enlaza al documento
  técnico.
- **`docs/tecnico.md`** reúne arquitectura (tres planos), "dónde va cada corrección",
  referencia del CLI, estado en disco y contratos (incluidos `reincide`, `implementada`
  y `falló`), cómo crear el perfil de un proyecto, uso con otros modelos, desarrollo
  del propio harness, estructura del repositorio y pendientes conocidos.
- Ninguna sección se duplica: si un tema se toca en los dos, uno enlaza al otro.

## Lo que queda al constructor

- El texto exacto del reporte y el esquema de `--json`, dentro del orden de secciones
  de arriba.
- La regla precisa que da el reflector para decidir "es el mismo error".
- Cómo se reparte el código entre `report.py`, `lib/biblioteca.py` y `cli.py`.
- La redacción de los dos documentos.

## Cómo se sabe que quedó bien

- Pruebas nuevas con datos sembrados para cada sección del reporte y para cada camino
  de la reincidencia y de `hallazgo-hecho`, incluidos los errores.
- Una prueba que confirma que el reporte no escribe nada en el proyecto.
- Una prueba que recorre datos viejos o mal formados sin reventar.
- Prueba de aceptación manual, solo lectura: correr el reporte sobre
  un proyecto real con datos (debe contar sus lecciones aprobadas, implementadas
  y rechazadas) y sobre otro proyecto sin datos (tickets sin hallazgos).
- Los tests de referencias y de documentos del harness siguen pasando con el comando
  nuevo y con la documentación separada.
