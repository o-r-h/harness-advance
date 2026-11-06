# Curación de la biblioteca de lecciones — diseño

Paso 5 del orden acordado con Omar el 02-11-2026 (ver `docs/tecnico.md`, "Pendientes
conocidos"). Omar delegó el diseño completo ("arranca como recomiendas", 03-11-2026):
**todas las decisiones de este documento son decisión de Claude** salvo las que dicen
lo contrario. Revísalas al leer.

## Por qué

La biblioteca (`<proyecto>/.claude/biblioteca/`) solo crece. Cada lección aprobada
entra a `INDEX.md`, que el planner lee en **cada** ticket y el reflector en **cada**
fase. Hoy no hay forma de sacar, fusionar ni corregir una lección: lo único que puede
hacer el humano es editar el `.md` a mano o borrarlo, y entonces se pierde la historia
(las líneas `falló`) y se rompen las referencias `TICKET/fase_N/hN` que la apuntan.

Lo que mostraba la biblioteca de un proyecto real (03-11-2026, solo lectura), 13 tickets después:

- **18 aprobadas, 0 implementadas, 0 con `falló`.** 3 rechazadas: dos como "duplicado
  de X, que quedó aprobada con el texto fusionado" y una porque "contradice
  el agente del perfil §4.1". La curación ya ocurre, pero solo en el momento de aprobar y solo
  contra lo que el humano recuerda.
- **Los duplicados se cuelan igual.** Cuatro aprobadas giran alrededor de "comentarios
  de 'por qué' (sin prefijo --)" con alcances que se pisan (`P12/fase_1/h1`,
  `P4/fase_2/h2`, `P5/fase_1/h1` y en parte `P3/fase_3/h1`). Se aprobaron en fases
  distintas y ninguna referencia a las otras.
- **La mayoría no se usa.** El plan más reciente (`ISR-113646`) ancló 6 de las 18 como
  `{"ref": ".claude/biblioteca/entradas/...", "confianza": "por_confirmar"}`. De las
  otras 12 no hay evidencia de uso desde que se aprobaron.
- **Muchas lecciones nombran rutas concretas** (`components/global/document-tooltip.vue`,
  `src/scss`, `global.api`, `el agente del perfil §4.1`). Si el código cambia, la lección puede
  quedar hablando de algo que ya no existe, y nadie se entera.

El costo de no curar no es el disco: es que el planner aplica como hipótesis lecciones
viejas, repetidas o contradictorias, y las que importan se diluyen entre las que no.

## Objetivos

1. **Señales deterministas** por lección, sin modelo: cuántas veces la anclaron los
   planes y cuándo fue la última; si menciona rutas que ya no existen en el proyecto;
   si falló o está implementada (eso ya existe). Salen en el reporte y alimentan al
   curador.
2. **Un curador** (agente de solo lectura, como el reflector) que lee la biblioteca
   completa con sus señales y **propone** acciones: fusionar lecciones que dicen lo
   mismo, retirar las que ya no valen o contradicen las reglas del perfil.
3. **El humano decide cada acción** con el mismo patrón que los hallazgos
   (ok / no / editar). El CLI aplica lo aprobado.
4. **Nada se pierde:** una lección retirada o fusionada se mueve, no se borra; conserva
   sus líneas `falló`, y su referencia sigue resolviendo a algo que dice adónde fue.

## No objetivos

- **Caducidad por fecha.** Una lección sobre un hecho de la plataforma no vence. La
  señal es el uso, no la edad; la decisión es humana.
- **Deduplicar o detectar contradicciones con código determinista.** Comparar texto
  libre en español con similitud de cadenas da falsos positivos y negativos; eso lo
  hace el curador, y el humano aprueba.
- **Curar en cada fase.** El curador se corre a pedido. Costaría en todas las fases y
  la biblioteca cambia despacio.
- **Biblioteca compartida entre proyectos** o importar lecciones de otro proyecto.
- **Tocar las rechazadas.** `rechazados/` sigue igual; el curador las lee para no
  proponer lo que ya se rechazó, nada más.

## Anti-objetivos (lo que lo haría un fracaso aunque funcione)

- Que el harness modifique, fusione o retire una lección **sin** aprobación humana.
- Que se pierda una línea `falló`: es la evidencia de que una lección no bastó.
- Que el harness genérico mencione un stack. El curador no conoce ninguno; lo que sabe
  del proyecto lo lee del perfil (`agents/*.md`, `rules.json`).
- Que una referencia vieja (`reincide`, un ancla en un plan cerrado) apunte a la nada.

## Diseño

### 1. Señales (determinista, `lib/biblioteca.py` + `report.py`)

Por cada entrada aprobada:

| Señal | Cómo se calcula |
|---|---|
| `usos` | Número de `plan.json` en `.harness/tickets/*/` cuyos `anclajes` traen `ref` igual a la ruta de la entrada (`.claude/biblioteca/entradas/<archivo>.md`). |
| `ultimo_uso` | El ticket más reciente que la ancló (por fecha de `ticket_context.json`; sin fecha, por nombre). |
| `rutas_ausentes` | Rutas que mencionan la `señal` y la `lección` (no la `evidencia`, que cita artefactos de `.harness/` como `intento_1/veredicto.json`) y que no coinciden con ningún archivo ni carpeta rastreados por git (`git ls-files`). Coincidir es **por sufijo de segmentos completos**: `components/global/document-tooltip.vue` coincide con `proyecto/Assets/components/global/document-tooltip.vue`, porque las lecciones escriben rutas relativas a un subproyecto. Un token cuenta como ruta si tiene al menos un `/` y no tiene espacios (`src/scss` cuenta; `global.api` y `§4.1` no). |
| `fallas`, `implementada` | Ya existen. |

`report.py` agrega una sección **Curación** con: lecciones sin uso desde que se
aprobaron, lecciones con rutas ausentes, y cuándo se curó por última vez. Es
información, no acción. *Decisión de Claude:* no hay umbral que dispare nada; el
reporte sugiere `/biblioteca-curar` cuando hay al menos una señal.

**Límites aceptados**, que el reporte y el curador conocen:

- Los planes anteriores a la v3 del planner no anclan: para ellos `usos` es 0 aunque la
  lección se haya leído.
- `.harness/` no se versiona, así que `usos` cuenta los planes **de este clon**. Otro
  desarrollador ve otros números. Por eso **"sin uso" nunca basta para retirar**: es
  una pista para el curador, no un motivo.
- Un archivo que existe en disco pero git no rastrea (por ejemplo un `.min.css`
  generado) cuenta como ausente. *Decisión de Claude:* se prefiere eso a recorrer el
  disco, que incluye `node_modules` y artefactos.

### 2. El curador (`harness/agents/curador.md`)

Agente de solo lectura (`Read, Grep, Glob`), como el reflector. Recibe:

- `INDEX.md` y **todas** las entradas aprobadas completas.
- Las rechazadas con su motivo, y `curacion-rechazada.md`.
- Las señales del punto 1 (las calcula el CLI y se las pasa la skill o el comando).
- Los `agents/*.md` y el `rules.json` del perfil, para detectar contradicciones con
  las reglas del proyecto.

Propone, en JSON, acciones de dos tipos:

- **`fusionar`**: `{"tipo": "fusionar", "refs": [A, B, ...], "destino": A, "leccion": "<texto fusionado>", "senal": "<señal fusionada>", "motivo": "..."}`.
  El destino es una de las refs (la que más se usa, o la más antigua). Las demás se
  retiran como "fusionada en <destino>".
- **`retirar`**: `{"tipo": "retirar", "ref": A, "motivo": "..."}`. Motivos esperables:
  contradice una regla del perfil (cita cuál), habla de código que ya no existe (cita
  la ruta ausente), quedó cubierta por una pieza implementada que ya la hace cumplir.

Reglas del curador (en su `.md`): solo lo que la evidencia sostiene; no reescribir por
estilo; una lección con `falló` no se retira sin decir por qué el error ya no puede
ocurrir; una propuesta vacía es válida; no proponer lo que ya se rechazó en una
curación anterior salvo con evidencia nueva.

### 3. El ciclo de aprobación (CLI + comandos)

Igual que los hallazgos, para no enseñar un segundo patrón:

- `cli.py senales-biblioteca [--json]`: imprime las señales (lo usa la skill para
  armar la entrada del curador, y sirve sola).
- `cli.py record-curacion --archivo <propuesta.json>`: valida contra un contrato nuevo
  (`contracts.validate_curacion`) y guarda las acciones en `.harness/curacion.json`,
  con estado `propuesto`. Rechaza:
  - refs que no existen en `entradas/`;
  - un `destino` fuera de `refs`;
  - una ref en dos acciones de la misma propuesta;
  - una fusión que mezcla lecciones implementadas con no implementadas (ver punto 4).

  *Decisión de Claude:* hay **una sola curación viva**. Los ids son globales y
  crecientes (`c1`, `c2`...; nunca se reutilizan). Una propuesta nueva reemplaza las
  acciones todavía `propuesto` de la anterior, igual que `record-hallazgos` con las del
  reflector, y conserva las ya resueltas como historia.
- `cli.py resolver-curacion --id <cN> --decision ok|no|editar [--texto] [--motivo]`:
  - `ok`: aplica la acción.
  - `editar`: aplica con lo corregido por el humano. En `fusionar`: `--texto`
    reemplaza la `lección`, `--senal` la `señal` (es lo que muestra `INDEX.md` y lo que
    el planner compara con el ticket), y `--quitar <ref>` (repetible) saca refs de la
    fusión sin tocar el destino; si queda una sola ref, no hay fusión y se rechaza con
    error claro. En `retirar`: `--motivo` reemplaza el motivo.
  - `no`: la rechaza con su motivo. *Decisión de Claude:* el rechazo se escribe en la
    biblioteca versionada, `biblioteca/curacion-rechazada.md` (una línea por acción:
    tipo, refs, motivo, fecha), para que viaje con el repo como `rechazados/` y el
    curador de otro clon tampoco la vuelva a proponer.
  - Si la acción toca una lección **anclada por el plan del ticket abierto**
    (`current.json`), `resolver-curacion` la rechaza con un mensaje que dice qué
    ticket la ancla: retirarla a mitad de fase haría que el escéptico vea un ancla sin
    resolver y tumbe el intento. Se resuelve después de cerrar el ticket. *Decisión de
    Claude.*
- Comandos: `/biblioteca-curar` (corre el curador y `record-curacion`, y termina el
  turno mostrando las acciones), `/curacion-ok <cN>`, `/curacion-no <cN> "<motivo>"`,
  `/curacion-editar <cN> "<texto>"`.

*Decisión de Claude:* la curación es estado de proyecto y no de ticket, y no exige
fase activa ni ticket abierto. Las propuestas pendientes no bloquean nada.

### 4. Qué hace "aplicar" (`lib/biblioteca.py`)

- **Retirar A:** mueve `entradas/A.md` a `retiradas/A.md` y le agrega
  `- **retirada**: <fecha> · <motivo>`. Sus líneas `falló` y `implementada` quedan
  intactas.
- **Fusionar A, B en A:** reemplaza la `lección` (y la `señal`, si viene) de A por el
  texto aprobado, conserva la original como `- **lección original**: ...` si A no la
  tenía, agrega `- **fusionada**: <fecha> · <B>` por cada absorbida, y **copia a A las
  líneas `falló` de B** (con su ref y su estado de entonces). B se retira con motivo
  `fusionada en <A>`.
- `INDEX.md` gana una sección **Retiradas — no aplicar** con una línea por entrada y su
  motivo. El planner no las aplica; el reflector no las vuelve a proponer.
- **Implementadas:** solo se fusionan lecciones con el mismo estado (todas implementadas
  o ninguna). Fusionar una implementada con una que no lo es haría que sus `falló`
  copiadas desaparezcan de las dos secciones del reporte, que las clasifica por ese
  estado. Si son todas implementadas, el destino conserva su línea `implementada` y
  recibe las notas de las otras en su línea `fusionada`. *Decisión de Claude.*
- **Referencias viejas:** `record-hallazgos` con `reincide` a una lección retirada
  sigue rechazando, pero el error dice adónde fue ("fusionada en X: usa esa ref"). Un
  ancla en un plan cerrado a `entradas/B.md` deja de resolver; las señales cuentan sus
  usos para el destino de la fusión, siguiendo la línea `fusionada`.

Todo cambio pasa por el CLI y `reconstruir_indice`, como hoy.

### 5. Documentación y planner

- `README.md`: sección corta "Curar la biblioteca": cuándo correrla, cómo decidir.
- `docs/tecnico.md`: contrato de curación, líneas nuevas de una entrada (`retirada`,
  `fusionada`), carpeta `retiradas/`.
- `task-planner` y `reflector.md`: una línea cada uno sobre la sección Retiradas.

## Restricciones

- Python 3.12 sin dependencias, Windows + PowerShell 5.1, igual que el resto.
- Convenciones del repo: superficie pública en inglés salvo términos del dominio
  (`leccion`, `curacion`, `retirada`), comentarios en español; encoding de archivos del
  proyecto con `gitdiff.read_text`; las entradas de la biblioteca las escribe el CLI en
  UTF-8.
- `harness/` no menciona ningún stack (lo vigila `test_referencias_harness`).
- TDD y un test de punta a punta del ciclo: proponer → aprobar una fusión y una retirada
  → INDEX y referencias correctas.

## Lo que queda al builder

- El formato exacto del JSON de propuesta y de `curacion.json` (seguir el de
  `hallazgos.json`).
- La heurística exacta de "parece ruta" para `rutas_ausentes`, validada contra la
  biblioteca de un proyecto real en solo lectura: no debe marcar `global.api` ni `§4.1`.
- Cómo se muestran las acciones al terminar `/biblioteca-curar` (como `hallazgos.md`).
