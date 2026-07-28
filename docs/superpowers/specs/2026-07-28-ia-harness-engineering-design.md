# Diseño: IA Harness Engineering — Ecosistema de desarrollo con IA

> Fecha: 2026-07-28 · Autor: Omar Rodriguez · Estado: aprobado para planificación
> Repo fuente: `C:\AZZULE\IA harness` · Primer proyecto objetivo: ReviewSystemGFS
> Antecedente: `conversacion.txt` (conceptos y esquemas iniciales)

## 1. Resumen

Un harness de producción — la capa de ingeniería que convierte el razonamiento del
modelo en acción verificable — implementado **nativamente sobre Claude Code**, con
tres piezas ya existentes (planner, escéptico, agente de proyecto) integradas bajo
contratos explícitos, verificación determinista por scripts, y un gate humano
estructurado como única fuente de verdad funcional.

Cubre las cinco capas de harness engineering: orquestación de herramientas,
bucles de verificación, contexto y memoria, guardrails, y observabilidad.

## 2. Objetivo

Que un ticket ISR se ejecute fase por fase con reintentos acotados y memoria de
fallos, sin que el desarrollador tenga que pedir manualmente la documentación,
recordar el contador de intentos, ni confiar en que el modelo respetó las reglas
del proyecto.

## 3. Restricciones del contexto real

Estas restricciones determinan el diseño y no son negociables:

| Restricción | Origen | Implicación de diseño |
|---|---|---|
| ReviewSystemGFS solo compila con **VS2008**, fuertemente enlazado | Constatado por el usuario | **No existe verificación funcional automatizable.** La prueba real es hacer los pasos en la web |
| Stack legacy: VB.NET, ASP.NET Web Forms, .NET FW 3.5, jQuery 1.7.2, IE11 parcial | `agente-rsfgfs.md` §2, §12 | Las reglas prohibidas son estáticas y verificables por regex |
| Regla de negocio: comentarios de auditoría `[B]`/`[E]` obligatorios | `agente-rsfgfs.md` §4 | Verificable al 100% por script; `error` desde el día uno |
| Los tickets llegan pegados a mano (no hay integración de origen) | Decisión del usuario | `nroticket` se pregunta una vez y se persiste |
| Runtimes disponibles: Python 3.12, Node 16, Git 2.54, Windows PowerShell 5.1 | Verificado en el entorno | Hooks y checks en **Python 3.12**; deploy en PowerShell |
| MCPs de Postman y DB no garantizados en sesión | Solo Plane conectado al diseñar | El diseño no depende de ellos; son opcionales y aditivos |

## 4. Decisiones de arquitectura

| # | Decisión | Alternativas descartadas | Razón |
|---|---|---|---|
| D1 | **Runtime: Claude Code nativo** | Orquestador externo Python/Node; híbrido | Ya instalado; los tres `.md` migran casi tal cual; portable a cualquier repo sin construir infra |
| D2 | **Autonomía: automática dentro de la fase, gate humano al cerrarla** | Todo manual; automático entre fases | El ojo humano queda donde más vale (el límite de fase) sin quemar tokens en un plan mal anclado |
| D3 | **Skill orquestadora + hooks** (no una sola de las dos) | Solo skill; solo hooks | La skill conduce el flujo (juicio); los hooks hacen cumplir lo insaltable (hechos). Cada capa hace lo que sabe hacer |
| D4 | **El agente escribe los JSON; un script los valida y rechaza** | Wrapper de código que los genera (propuesto en `conversacion.txt`) | En Claude Code nativo no hay proceso wrapper. Se conserva el determinismo moviéndolo de la generación a la validación |
| D5 | **Los contadores los escribe solo el script**, nunca el modelo | Que el agente lleve la cuenta | `intento_actual` y `max_reintentos` son aritmética, no juicio |
| D6 | **El gate humano se estructura, no se elimina** | Automatizar con Playwright; verificar solo por MCPs de capa | Sin build ni tests, la prueba en navegador es la única verdad funcional. Playwright contra Web Forms con Windows Auth es frágil y caro |
| D7 | **Escalamiento de costo: checks → escéptico → humano** | Invocar al escéptico primero | Cada nivel filtra al siguiente. Los checks cuestan milisegundos; el humano es el recurso más caro |
| D8 | **El escéptico corre como subagente con contexto aislado** | Escéptico en el hilo principal | Un escéptico que leyó el razonamiento del executor ya está contaminado por él |
| D9 | **Los checks nuevos entran como `warning` y se promueven a `error`** | Todo `error` desde el inicio | Un repo legacy de 15 años dispara falsos positivos; un harness que grita por todo se aprende a ignorar |

## 5. Arquitectura — tres planos

Separados por frecuencia de cambio:

1. **Harness genérico** (cambia raro, sirve en todo proyecto) → se despliega a `~/.claude/`.
   No contiene ningún conocimiento de VB.NET ni de ReviewSystemGFS.
2. **Perfil de proyecto** (uno por repo) → se despliega a `<proyecto>/.claude/`.
   Todo lo específico del stack: agente, reglas, checks.
3. **Estado de ejecución** (crece por ticket) → vive en `<proyecto>/.harness/tickets/`.
   Es la capa de observabilidad.

Los hooks se registran **una sola vez, globalmente**, pero son inertes sin perfil:
lo primero que hace `check_rules.py` es buscar `./.claude/rules.json`; si no existe,
sale con código 0 en silencio. Adoptar un proyecto nuevo = crear su perfil.

### 5.1. Estructura del repo fuente

```
C:\AZZULE\IA harness\
├── harness/                        → deploy a ~/.claude/
│   ├── skills/
│   │   ├── ticket-loop/SKILL.md    orquestadora: abre ticket, corre fases, escala
│   │   └── task-planner/SKILL.md   task-planner v3 (evolución de v2)
│   ├── agents/
│   │   └── skeptic.md              escéptico genérico, sin reglas de proyecto
│   └── hooks/
│       ├── check_rules.py          PostToolUse: valida el archivo recién tocado
│       ├── gate_phase.py           Stop: bloquea cierre sin veredicto aprobado
│       ├── validate_contracts.py   valida plan.json / veredicto.json contra esquema
│       ├── report.py               `harness report`: observabilidad
│       └── lib/harness.py          estado, perfil activo, resolución de rutas, diff
├── profiles/
│   └── reviewsystemgfs/            → deploy a <ReviewSystemGFS>/.claude/
│       ├── agents/agent-rsgfs.md   el agente actual, cirugía mínima
│       ├── rules.json              reglas declarativas del stack
│       └── checks/
│           ├── designer_sync.py    .aspx ↔ .designer.vb ↔ .aspx.vb
│           ├── sp_params.py        |Vn= del VB ↔ SepararCadena 'Vn' del SP
│           └── xhtml_selfclose.py  tags sin cerrar en .aspx
├── deploy.ps1                      copia (o junction) a ~/.claude y al proyecto
└── docs/superpowers/specs/         este documento
```

`deploy.ps1` recibe la ruta del proyecto como parámetro; el diseño no hardcodea
rutas locales, y el perfil se resuelve en tiempo de ejecución por el directorio de
trabajo. Así el mismo perfil funciona en la copia de cualquier miembro del equipo.

### 5.2. Estado por ticket

```
<proyecto>/.harness/tickets/ISR-110722/
├── ticket.md                el requerimiento pegado
├── ticket_context.json      nroticket, desarrollador, fecha, perfil
├── plan.md                  legible para el humano (formato actual del planner)
├── plan.json                el mismo plan, consumible por código
├── ticket_state.json        fase actual, progreso global
└── fase_1/
    ├── fase_state.json      intento_actual, max_reintentos, historial_fallos
    └── intento_1/
        ├── resultado.md     documentación de lo hecho (hoy se pide a mano)
        ├── checks.json      veredicto de los scripts (hechos)
        ├── prueba_manual.md guion de clics para el humano
        └── veredicto.json   juicio del escéptico + resultado de la prueba manual
```

`.harness/` arranca en `.gitignore`. Al versionarlo (cuando el harness se proponga
al equipo) el formato no cambia: solo se quita esa línea.

## 6. Contratos

### 6.1. `ticket_context.json`

Se crea una vez al abrir el ticket, preguntando lo que falte. Elimina un fallo
silencioso concreto: comentarios `[B]/[E]` con ticket, nombre o fecha inventados.
El hook verifica coincidencia exacta contra este archivo, no solo "forma de fecha".

```json
{
  "ticket_id": "ISR-110722",
  "nroticket": "110722",
  "desarrollador": "OMAR RODRIGUEZ",
  "fecha": "28-07-2026",
  "perfil": "reviewsystemgfs"
}
```

### 6.2. `plan.json` — emitido por el planner v3

`plan.md` no cambia; gana un hermano estructurado. Los campos nuevos respecto a la
v2 son los que habilitan las capas de guardrails y de reintentos.

```json
{
  "ticket_id": "ISR-110722",
  "perfil": "reviewsystemgfs",
  "generado_por": "task-planner-v3",
  "fases": [
    {
      "id": "fase_1",
      "titulo": "Agregar campo de comentario en Other Q",
      "pasos": ["..."],
      "anclajes": [
        { "ref": "frmReviewReport.aspx.vb:412", "confianza": "verificado" },
        { "ref": "Sps/dbo.ReviewInsUpd.StoredProcedure.sql:88", "confianza": "por_confirmar" }
      ],
      "criterio_exito": "El comentario se guarda y se relee al reabrir la review",
      "checks_deterministas": ["audit_comments", "no_new_deps", "fw35_syntax",
                               "designer_sync", "sp_params"],
      "prueba_manual": { "requerida": true, "url": "frmReviewReport.aspx",
                         "datos": "review 4471, idioma EN" },
      "herramientas_permitidas": ["read", "edit", "db_mcp:read_only"],
      "max_reintentos": 3,
      "depende_de": []
    }
  ]
}
```

Los `anclajes` conectan las etiquetas ✅/⚠️ que el planner v2 ya produce con el
escéptico: una fase no se aprueba si un `por_confirmar` que la bloqueaba sigue sin
resolverse.

### 6.3. `checks.json` — emitido por los scripts

```json
{
  "fase_id": "fase_1",
  "intento": 2,
  "resultado": "fallo",
  "checks": [
    { "id": "audit_comments", "resultado": "ok" },
    { "id": "designer_sync", "resultado": "fallo", "severidad": "error",
      "detalle": "hdnNuevoCampo usado en frmReviewReport.aspx.vb:418 pero no declarado en frmReviewReport.aspx.designer.vb" },
    { "id": "no_es6", "resultado": "fallo", "severidad": "warning",
      "detalle": "frmReviewReport.js:203 usa arrow function" }
  ]
}
```

Regla de agregación: `resultado: "fallo"` si existe algún check con
`severidad: "error"` fallando. Los `warning` no bloquean; pasan al escéptico, que
decide si importan en ese contexto.

### 6.4. `veredicto.json` — emitido por el escéptico y completado por el humano

```json
{
  "fase_id": "fase_1",
  "intento": 2,
  "aprobado": false,
  "juicio_esceptico": {
    "aprobado": true,
    "razones_rechazo": [],
    "claims_sin_evidencia": [],
    "anclajes_sin_resolver": []
  },
  "prueba_manual": {
    "requerida": true,
    "ejecutada": true,
    "resultado": "fallo",
    "fallo_en_paso": 3,
    "observacion": "el campo volvió vacío al reabrir"
  }
}
```

Condición de cierre de fase — las tres deben cumplirse:

1. `checks.json.resultado == "ok"`
2. `juicio_esceptico.aprobado == true`
3. `prueba_manual.resultado == "ok"` (o `requerida == false`)

### 6.5. `fase_state.json` — escrito solo por scripts

```json
{
  "fase_id": "fase_1",
  "estado": "en_correccion",
  "intento_actual": 2,
  "max_reintentos": 3,
  "historial_fallos": [
    {
      "intento": 1,
      "origen": "check",
      "razon": "designer_sync: hdnNuevoCampo no declarado en el designer",
      "correccion_aplicada": "Se agregó la declaración Protected WithEvents en el .designer.vb"
    }
  ]
}
```

Valores de `estado`: `pendiente` · `en_ejecucion` · `en_verificacion` ·
`esperando_humano` · `en_correccion` · `aprobada` · `escalado`.

El campo **`origen`** (`check` | `esceptico` | `humano`) es la pieza que habilita
el ciclo de mejora del harness: un mismo tipo de fallo repetido con
`origen: "esceptico"` es un check determinista esperando a ser escrito.

## 7. El ciclo de fase

```
1. Abrir fase          fase_state.json → intento 1, estado en_ejecucion
2. Ejecutar            subagente del perfil (agent-rsgfs), recibe:
                       la fase de plan.json + ticket_context + historial_fallos
                       + herramientas_permitidas
   └─ en vivo          hook PostToolUse valida cada archivo tocado y devuelve el
                       fallo al agente al instante.
                       NO cuenta como intento: es autocorrección, no reintento
3. Checks completos    checks.json                       [gratis, milisegundos]
   └─ fallo →          intento+1, volver a 2. No se invoca al escéptico
4. Escéptico           subagente, contexto aislado       [caro]
   └─ rechaza →        intento+1, volver a 2
5. Guion de prueba     prueba_manual.md; el ciclo SE DETIENE (esperando_humano)
6. Veredicto humano    /fase-ok  |  /fase-fallo <paso> "<observación>"
   └─ fallo →          cuenta como intento; la observación entra al historial
7. Fase aprobada       estado aprobada; el control vuelve al humano para la
                       siguiente fase (D2: el gate está entre fases)

En cualquier punto, agotados los max_reintentos → estado: escalado.
El hook Stop impide avanzar a la fase siguiente hasta que el humano intervenga.
```

El aislamiento de contexto del escéptico (D8) es deliberado: recibe el diff, el
`criterio_exito`, `checks.json` y el `historial_fallos` — **no** la conversación
donde el executor se convenció de que su trabajo estaba bien.

## 8. Verificación

### 8.1. Reglas declarativas — `rules.json` del perfil

Lo que hoy son viñetas de "PROHIBIDO" en `agente-rsfgfs.md` §3.1 pasa a ser datos.
Añadir una regla no requiere tocar código.

```json
{
  "perfil": "reviewsystemgfs",
  "audit_comments": {
    "requerido": true,
    "formatos": {
      ".vb":   "'--[B] ISR {ticket} {dev} {fecha}",
      ".js":   "//--[B] ISR {ticket} {dev} {fecha}",
      ".sql":  "--[B] ISR {ticket} {dev} {fecha}",
      ".aspx": "<%--[B] ISR {ticket} {dev} {fecha}--%>"
    },
    "fecha_formato": "DD-MM-YYYY",
    "valores_desde": "ticket_context.json",
    "severidad": "error"
  },
  "prohibido": [
    { "id": "no_async",   "archivos": [".vb"], "severidad": "error",
      "patron": "\\b(Async|Await)\\b",
      "mensaje": "FW 3.5 no soporta async/await" },
    { "id": "no_fetch",   "archivos": [".js"], "severidad": "error",
      "patron": "\\bfetch\\s*\\(",
      "mensaje": "IE11: usar Azzule.ConsultarDatos()" },
    { "id": "no_raw_sql", "archivos": [".vb"], "severidad": "error",
      "patron": "SqlCommand\\(\\s*\"(SELECT|INSERT|UPDATE|DELETE)",
      "mensaje": "El acceso a datos va por Global_asax.InstanciarConsulta() + EjecutarSp()" },
    { "id": "no_orm",     "archivos": [".vb"], "severidad": "error",
      "patron": "(DbContext|EntityFramework|LinqToSql)",
      "mensaje": "Prohibido ORM: acceso directo con SqlConnection/SqlCommand" },
    { "id": "no_es6",     "archivos": [".js"], "severidad": "warning",
      "patron": "(=>|\\b(let|const)\\s|\\bPromise\\b)",
      "mensaje": "jQuery 1.7.2 / IE11: preferir var y function" },
    { "id": "no_fw_moderno", "archivos": [".vb"], "severidad": "warning",
      "patron": "IsNullOrWhiteSpace",
      "mensaje": "No disponible en FW 3.5" }
  ],
  "no_new_deps": {
    "vigilar": ["ReviewSystem.vbproj", "Web.config", "packages.config"],
    "severidad": "error",
    "mensaje": "Ninguna Reference/DLL/paquete nuevo sin aprobación humana explícita"
  },
  "checks_estructurales": ["designer_sync", "sp_params", "xhtml_selfclose"],
  "grupos": {
    "fw35_syntax": ["no_async", "no_orm", "no_fw_moderno"],
    "ie11_syntax": ["no_fetch", "no_es6"]
  }
}
```

Los `checks_deterministas` de cada fase en `plan.json` pueden nombrar tanto un check
individual (`designer_sync`) como un grupo declarado aquí (`fw35_syntax`). Los grupos
existen para que el plan no tenga que enumerar cada regex; resolverlos es trabajo de
`check_rules.py`, y un nombre que no exista ni como check ni como grupo es un error
de validación de contrato, no un check que se ignora en silencio.

### 8.2. Checks estructurales — el compilador ausente

Sin VS2008 en el loop, estos tres compensan parte de lo que atraparía el build:

**`designer_sync`** — el error de compilación #1 en Web Forms. Cruza los IDs de
control usados en el `.aspx.vb` contra las declaraciones del `.aspx.designer.vb` y
los controles `runat="server"` del `.aspx`. Un control agregado al markup sin
declarar en el designer no compila, y sin build no se detectaría hasta abrir VS2008.

**`sp_params`** — específico de la arquitectura del proyecto. Extrae los `|Vn=` que
el VB envía y los compara contra los `SepararCadena 'Vn'` que el SP declara;
verifica además que el `@Validar` usado exista como rama `if @Validar = N` en el SP.
Atrapa el fallo más costoso del stack: se envía `V21`, el SP nunca lo parsea, no
falla en ningún lado y el dato simplemente desaparece. Hoy eso solo se detecta
haciendo los pasos en la web.

**`xhtml_selfclose`** — tags sin cerrar en `.aspx`, que XHTML 1.0 Transitional exige.

### 8.3. Verificación humana — `prueba_manual.md`

El harness deriva el guion del `criterio_exito` y los `anclajes` de la fase:

```markdown
# Prueba manual — fase_1 / intento_2
URL: frmReviewReport.aspx  ·  Datos: review 4471, idioma EN

| # | Paso | Qué deberías ver |
|---|------|------------------|
| 1 | Abrir la review 4471 y entrar a Other Q | El campo Comentario aparece vacío |
| 2 | Escribir "prueba harness" y guardar      | Mensaje de guardado exitoso |
| 3 | Salir y reabrir la review                | El campo conserva "prueba harness" |

Responder: /fase-ok   ·   /fase-fallo 3 "el campo volvió vacío"
```

`/fase-fallo` registra la observación en `historial_fallos` con `origen: "humano"`,
de modo que el intento siguiente arranca sabiendo qué falló y en qué paso — el dato
que hoy se pierde entre corrección y corrección.

### 8.4. Verificación opcional por MCP

Si los MCPs de DB y Postman están disponibles en la sesión, el escéptico puede
comprobar que el SP existe, que las columnas referenciadas son reales, o que un
endpoint responde. Es aditivo: **ninguna parte del diseño depende de ello**, y no
sustituye la prueba funcional en navegador.

## 9. Guardrails

| Guardrail | Implementación | Determinista |
|---|---|---|
| Reglas del stack en cada archivo tocado | hook `PostToolUse` → `check_rules.py` | Sí |
| No cerrar fase sin veredicto aprobado | hook `Stop` → `gate_phase.py` | Sí |
| Límite de reintentos por fase | `fase_state.json`, contador escrito por script | Sí |
| Escalamiento a humano al agotar reintentos | `estado: escalado` + bloqueo del hook `Stop` | Sí |
| Herramientas permitidas por fase | `herramientas_permitidas` + `permissions` en `settings.json` del proyecto | Parcial |
| Contratos JSON bien formados | `validate_contracts.py` | Sí |
| Sin dependencias nuevas | regla `no_new_deps` sobre `.vbproj` / `Web.config` | Sí |

`herramientas_permitidas` es "parcial" con honestidad: el ajuste fino por fase
(p. ej. solo `SELECT` en la DB durante la fase 1) depende de la granularidad que
ofrezca el MCP correspondiente. Lo que sí es duro es el conjunto de permisos a
nivel proyecto en `settings.json`.

## 10. Observabilidad

`harness report` (`report.py`) recorre `.harness/tickets/` y responde:

- Intentos consumidos por fase, y qué fases se escalaron.
- Distribución del origen de los fallos: `check` / `esceptico` / `humano`.
- Reglas más violadas.
- **Fallos del escéptico que se repiten** — la lista de trabajo para mejorar el
  harness. Cada patrón recurrente detectado hoy por un modelo Opus es un check
  determinista que debería costar milisegundos.

Este último punto es el ciclo de mejora completo: el principio de Hashimoto
convertido en una consulta sobre archivos propios en lugar de en una intuición.

## 11. Migración de los tres archivos existentes

| Archivo actual | Cambio | Magnitud |
|---|---|---|
| `task-plannerv2.md` | → **v3**: emite `plan.json` junto al `.md`; cada fase declara `checks_deterministas`, `prueba_manual`, `herramientas_permitidas`, `max_reintentos`, `anclajes` estructurados | Menor. La Fase 0 de anclaje es su mayor valor y no se toca |
| `agente-esceptico.md` | Se **parte en dos**: escéptico genérico (exige evidencia, emite `veredicto.json`) + reglas de proyecto que ahora vienen de `rules.json`. Se elimina todo lo heredado de otro proyecto: "Kilo Code", `.kilocode/**/*.md`, "actor system", prohibiciones de TypeScript | Reescritura. Es el archivo con más deuda: hoy juzga ReviewSystemGFS contra reglas que no son suyas |
| `agente-rsfgfs.md` | Cirugía mínima: leer `ticket_context.json` para los `[B]/[E]`, respetar `herramientas_permitidas`, consumir `historial_fallos`. Su checklist de §10 pasa a ejecutarse por hooks en vez de por memoria | Mínima. Es el archivo más sólido de los tres |

## 12. Manejo de errores

| Situación | Comportamiento |
|---|---|
| `plan.json` malformado o incompleto | `validate_contracts.py` lo rechaza con el campo faltante; el planner corrige. No se abre ninguna fase con un plan inválido |
| Falta `ticket_context.json` | La skill lo pide antes de ejecutar. Sin él, `check_rules.py` no puede validar `[B]/[E]` y reporta `error` |
| No existe perfil en el proyecto | Los hooks salen con código 0 en silencio. El harness no estorba en repos no adoptados |
| Un check crashea | Se registra como `resultado: "error_check"` con el traceback; **no** bloquea la fase (un bug del harness no debe parecer un bug del código) y queda visible en `harness report` |
| El escéptico devuelve JSON inválido | Se le reintenta una vez con el error; si falla de nuevo, se escala a humano |
| Reintentos agotados | `estado: escalado`; el hook `Stop` bloquea el avance hasta intervención humana |
| El humano no ejecuta la prueba manual | La fase queda en `esperando_humano` indefinidamente. No hay timeout: nada se aprueba por omisión |

## 13. Estrategia de pruebas del propio harness

El harness es código y también necesita verificarse:

- **Checks y hooks**: fixtures con archivos `.vb`/`.js`/`.aspx`/`.sql` que violan cada
  regla y otros que la cumplen. Cada check debe atrapar el caso malo y no marcar el
  bueno — un check con falsos positivos es peor que no tenerlo (D9).
- **`sp_params` y `designer_sync`**: fixtures tomados del código real de
  ReviewSystemGFS, incluyendo un caso conocido de `Vn` no parseado.
- **Contratos**: validación de esquema con ejemplos válidos e inválidos de cada JSON.
- **Máquina de estados**: transiciones de `fase_state.json` — que el contador nunca
  se pase de `max_reintentos`, que un `warning` no bloquee, que un `error` sí.
- **Ciclo completo**: un ticket real de ReviewSystemGFS de punta a punta. Esta es la
  prueba que decide si el diseño sirve; el resto solo evita regresiones.

## 14. Alcance y orden de construcción

No construir las cuatro piezas antes de probar ninguna. El orden propuesto llega
primero al ciclo mínimo funcionando sobre un ticket real:

1. **Contratos + estado**: esquemas JSON, `lib/harness.py`, `validate_contracts.py`.
2. **Ciclo mínimo**: skill `ticket-loop` + escéptico limpio + `check_rules.py` con
   solo `audit_comments` y `no_new_deps`, y el gate humano con `/fase-ok` / `/fase-fallo`.
3. **Validar con un ticket ISR real** de ReviewSystemGFS. Aquí se decide si el
   diseño aguanta; ajustar antes de seguir.
4. **Planner v3**: emisión de `plan.json`.
5. **Checks estructurales**: `designer_sync`, `sp_params`, `xhtml_selfclose`.
6. **Observabilidad**: `harness report` y `deploy.ps1`.

Fuera de alcance en esta iteración, explícitamente: automatización con Playwright,
dependencia de los MCPs de DB/Postman, integración con Plane u otro origen de
tickets, y perfiles para proyectos distintos de ReviewSystemGFS.

## 15. Criterios de aceptación

- [ ] Un ticket ISR pegado a mano produce `plan.md` + `plan.json` válido contra esquema.
- [ ] Abrir una fase crea su estado; el contador de intentos lo escribe solo el script.
- [ ] Un archivo guardado sin par `[B]/[E]` completo y coincidente con
      `ticket_context.json` produce un fallo inmediato del hook durante la ejecución.
- [ ] Un `error` de check impide invocar al escéptico; un `warning` no.
- [ ] El escéptico emite `veredicto.json` válido sin haber visto la conversación del executor.
- [ ] Al aprobar el escéptico se genera `prueba_manual.md` con pasos derivados del
      `criterio_exito`, y el ciclo se detiene esperando al humano.
- [ ] `/fase-fallo 3 "..."` incrementa el intento y deja la observación en
      `historial_fallos` con `origen: "humano"`.
- [ ] Agotados los reintentos, el hook `Stop` impide avanzar de fase.
- [ ] En un repo sin perfil, los hooks no producen ninguna salida ni fricción.
- [ ] `harness report` muestra intentos por fase y origen de los fallos de al menos
      un ticket real completado.

## 16. Observaciones

- El remoto del proyecto objetivo es `http://10.10.50.37:3000/AzzuleNew/ReviewSystemGFS`.
  El diseño no depende de la ruta local: el perfil se resuelve por directorio de
  trabajo y `deploy.ps1` recibe la ruta como parámetro.
- En Windows, enlazar en lugar de copiar requiere junctions (`mklink /J`) o modo
  desarrollador. `deploy.ps1` soporta ambos modos; por defecto copia, para evitar
  depender de permisos elevados.
- El harness genérico no debe adquirir conocimiento del stack legacy. Cada vez que
  se sienta la tentación de poner algo de VB.NET en `harness/`, eso pertenece a
  `profiles/`.
- Contrapunto a tener presente: a medida que mejoren los modelos, parte de este
  andamiaje sobrará. Los checks deterministas envejecen bien (son hechos); las
  instrucciones que compensan limitaciones del modelo, no. Conviene revisar
  periódicamente qué se puede quitar.
