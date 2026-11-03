# IA Harness — documentación técnica

Referencia para quien mantiene el harness o lo adapta: arquitectura, CLI, contratos,
perfiles y desarrollo. Para **usarlo** (instalar, abrir tickets, aprobar hallazgos, leer
el reporte), ve al [README](../README.md).

## Índice

- [Arquitectura: tres planos](#arquitectura-tres-planos)
- [Dónde va cada corrección](#dónde-va-cada-corrección)
- [Referencia del CLI](#referencia-del-cli)
- [Estado en disco y contratos](#estado-en-disco-y-contratos)
- [Crear el perfil de un proyecto nuevo](#crear-el-perfil-de-un-proyecto-nuevo)
- [Usarlo con otro modelo que no sea Claude](#usarlo-con-otro-modelo-que-no-sea-claude)
- [Desarrollo del propio harness](#desarrollo-del-propio-harness)
- [Estructura del repositorio](#estructura-del-repositorio)
- [Pendientes conocidos](#pendientes-conocidos)

---

## Arquitectura: tres planos

Separados por frecuencia de cambio:

```
harness/                    → se despliega a ~/.claude/            (genérico, cambia raro)
profiles/<proyecto>/        → se despliega a <proyecto>/.claude/   (todo lo del stack)
<proyecto>/.harness/        → estado de ejecución por ticket       (crece con cada ticket)
<proyecto>/.claude/biblioteca/ → lecciones aprobadas               (crece, se versiona)
```

- **El harness genérico no conoce ningún stack.** Un test (`TestSeparacionDePlanos`)
  falla si `harness/` menciona términos como VB.NET, Web Forms o jQuery. Todo eso va
  al perfil.
- **Los hooks se registran una sola vez, globalmente**, pero no hacen nada si el
  proyecto no tiene `.claude/rules.json`. Adoptar un proyecto nuevo es crearle un perfil.


## Dónde va cada corrección

Cada hallazgo (ver [Hallazgos y biblioteca de lecciones](../README.md#hallazgos-y-biblioteca-de-lecciones))
nombra la pieza del harness que corrige el fallo. De la más barata a la más cara, se
elige la primera que lo corrige:

| Lo que muestra la evidencia | `componente` |
|---|---|
| Un fallo mecánico que un patrón detecta en las líneas agregadas | `regla` (entrada de `rules.json`) |
| Un fallo mecánico que exige cruzar archivos o correr una herramienta | `check` (check estructural del perfil) |
| Un procedimiento de varios pasos con un disparador claro | `skill` |
| Evidencia **repetida** de que una instrucción escrita se ignora | `hook` |
| Orden normal del trabajo, o un dato corto que vale para toda fase | `agente` (texto siempre cargado; si se agrega algo, se recorta otro) |

## Referencia del CLI

`python ~/.claude/hooks/cli.py <subcomando>`. Todos aceptan `--project <ruta>`; si no
se indica, se usa el proyecto del directorio actual.

| Subcomando | Qué hace |
|---|---|
| `open-ticket --ticket-id --nroticket --desarrollador --fecha DD-MM-YYYY --perfil` | Crea el ticket y fija `ticket_context.json`. Se rechaza si la fase activa está corriendo, incluso con el mismo id |
| `open-fase --fase fase_N` | Abre una fase, o reanuda una `pausada` sin gastar intento. Rechaza la apertura si una fase de `depende_de` no está aprobada, o si otra fase está corriendo (hay que pausarla o cerrarla) |
| `pausar-fase [--motivo]` | Pausa la fase activa (solo desde `en_ejecucion`, `en_correccion` o `en_verificacion`) y guarda el motivo en `pausas`. No toca el intento ni el historial de fallos. En `pausada`, `record-veredicto` y `generar-prueba` se rechazan |
| `validate --contrato <nombre> --archivo <ruta>` | Valida un JSON contra su contrato (`plan`, `checks`, `veredicto`, `fase_state`, `ticket_context`, `hallazgos`) |
| `run-checks` | Corre los checks de la fase y escribe `checks.json`. Con errores bloqueantes registra el fallo (origen `check`), suma el intento o escala, y sale con 1; si no, deja la fase en `en_verificacion` |
| `record-veredicto --archivo` | Registra el veredicto del escéptico; si rechaza, incrementa el intento |
| `generar-prueba --pasos-json` | Escribe `prueba_manual.md` |
| `record-manual --resultado ok\|fallo [--paso --observacion]` | Registra la prueba manual |
| `record-hallazgos --archivo [--ticket --fase]` | Registra la propuesta del reflector. Solo sobre una fase `aprobada` o `escalado`; con `--ticket --fase`, sobre una fase ya cerrada |
| `resolver-hallazgo --id <hN\|TICKET/fase_N/hN> --decision ok\|no\|editar [--texto] [--motivo] [--nueva \| --reincide <ref>]` | Resuelve un hallazgo y lo escribe en la biblioteca. `--nueva` ignora el `reincide` del reflector; `--reincide` fija la lección a la que reincide. Solo valen con `ok` o `editar`, y no juntos. Una reincidencia aprobada no crea entrada: agrega una línea `falló` a la original |
| `hallazgo --texto [--dimension] [--componente]` | Hallazgo humano, en la fase activa |
| `hallazgo-hecho --id <TICKET/fase_N/hN> --nota` | Marca una lección aprobada como implementada (`- **implementada**: <fecha> · <nota>`). Solo acepta la referencia completa; si ya estaba marcada, reemplaza la marca e imprime la anterior |
| `hallazgos-pendientes` | Lista los hallazgos sin resolver de todos los tickets; siempre sale con 0 |
| `reconstruir-biblioteca` | Regenera `INDEX.md` desde las entradas |
| `senales-biblioteca [--json]` | Solo lectura. Por lección: `usos` (planes de este clon que la anclan; un ancla a una lección fusionada cuenta para su destino), `ultimo_uso`, `rutas_ausentes` (rutas de la señal y la lección que no coinciden por sufijo con nada de `git ls-files`; `null` sin git), `fallas`, `implementada`; y `ultima_curacion` |
| `record-curacion --archivo <propuesta>` | Valida la propuesta del curador y la guarda en `.harness/curacion.json` (+ `curacion.md`). Rechaza refs fuera de `entradas/` (diciendo adónde fueron si se retiraron), una ref en dos acciones y fusiones que mezclan implementadas con no implementadas. Reemplaza las acciones `propuesto` anteriores, conserva las resueltas; los ids `cN` nunca se reutilizan. No exige ticket |
| `resolver-curacion --id <cN> --decision ok\|no\|editar [--texto] [--senal] [--quitar <ref>]... [--motivo]` | Aplica, corrige y aplica, o rechaza una acción. `no` exige `--motivo` y lo agrega a `biblioteca/curacion-rechazada.md`. `editar`: en una fusión `--texto`, `--senal` y `--quitar` (no el destino, y deben quedar 2 refs); en una retirada, `--motivo`. Falla sin escribir si una ref ya no está en `entradas/` o la ancla el plan del ticket de `current.json` mientras alguna de sus fases no esté aprobada |
| `report [--json]` | Reporte de solo lectura del proyecto: lecciones, hallazgos y fases. Sin `.harness/` ni biblioteca sale con 0 y cada sección dice que no hay datos. Cómo leerlo: [Cómo leer el reporte](../README.md#cómo-leer-el-reporte) |

## Estado en disco y contratos

```
<proyecto>/.harness/
├── current.json                       ticket y fase activos
└── tickets/ISR-110722/
    ├── ticket.md                      el requerimiento
    ├── ticket_context.json            nroticket, desarrollador, fecha, perfil
    ├── plan.md / plan.json            el plan (humano / máquina)
    └── fase_1/
        ├── fase_state.json            estado, intento_actual, max_reintentos, historial_fallos, pausas
        ├── hallazgos.json / .md       propuestas del reflector y decisiones
        └── intento_1/
            ├── resultado.md           lo que hizo el ejecutor, con evidencia
            ├── checks.json            hechos de los scripts
            ├── prueba_manual.md       guion de clics
            └── veredicto.json         escéptico + prueba manual
```

La biblioteca (`<proyecto>/.claude/biblioteca/`) es estado de proyecto, no de ticket:
`entradas/` (aprobadas), `rechazados/`, `retiradas/` (salieron por una curación),
`curacion-rechazada.md` (curaciones rechazadas, una línea cada una) e `INDEX.md`,
derivado de las entradas. El estado de una curación en curso vive en
`.harness/curacion.json`, que no se versiona.

### Contrato de curación

La propuesta del curador (`contracts.validate_propuesta_curacion`) es
`{"acciones": [...]}`, lista que puede ir vacía. Cada acción es
`{"tipo": "retirar", "ref", "motivo"}` o
`{"tipo": "fusionar", "refs" (2 o más, sin repetir), "destino" (una de refs), "leccion", "senal"?, "motivo"}`.
En `.harness/curacion.json` (`contracts.validate_curacion`) cada acción suma `id`
(`cN`), `estado` (`propuesto`, `aprobado`, `rechazado`), `fecha_propuesta`,
`fecha_resuelta` al resolverse y `motivo_rechazo` si se rechazó.

Aplicar una **retirada** mueve la entrada a `retiradas/` y le agrega la línea
`retirada`. Aplicar una **fusión** reemplaza la `lección` (y la `señal`, si viene) del
destino, guarda la anterior como `lección original` si no tenía una, copia las líneas
`falló` de las absorbidas y les agrega una línea `fusionada` a cada una; después las
absorbidas se retiran con motivo `fusionada en <destino>`.

### Contrato de hallazgos y `reincide`

`hallazgos.json` y la propuesta del reflector comparten contrato
(`contracts.validate_hallazgos`). Además de `senal`, `leccion`, `evidencia`,
`confianza`, `dimension` y `componente`, un hallazgo puede traer el campo opcional
**`reincide`**: la referencia `TICKET/fase_N/hN` de una lección aprobada que ya debía
evitar este error. La parte del ticket es `[A-Za-z0-9][A-Za-z0-9_-]*`
(`contracts.RE_REFERENCIA`).

- `record-hallazgos` rechaza la propuesta si `reincide` no tiene forma de referencia o
  si no existe una entrada **aprobada** con esa referencia en `entradas/`. No escribe
  nada.
- `resolver-hallazgo` con `ok` o `editar` y un `reincide` (el del hallazgo o el de
  `--reincide`) no crea entrada nueva: agrega a la original una línea `falló`. Con
  `--nueva` se ignora el `reincide` y se crea entrada, como un hallazgo normal. Con
  `no` se rechaza como siempre.
- Una referencia a una lección rechazada o inexistente se rechaza con error claro y no
  escribe ni `hallazgos.json` ni la biblioteca.

### Líneas de una entrada de la biblioteca

Además de los campos del hallazgo (`señal`, `lección`, `evidencia`, `confianza`,
`dimension`, `componente`, `origen`, `lección original`), una entrada aprobada
lleva líneas que escribe solo el CLI (`harness/hooks/lib/biblioteca.py`):

| Línea | Quién la escribe | Significado |
|---|---|---|
| `- **aprobada**: <fecha>` | `resolver-hallazgo` y `hallazgo`, al crear la entrada | Cuándo se aprobó. Las entradas anteriores a esta versión no la tienen y siguen siendo válidas |
| `- **implementada**: <fecha> · <nota>` | `hallazgo-hecho` | La pieza que pedía la lección ya existe. Una sola línea: marcar de nuevo la reemplaza |
| `- **falló**: <fecha> · <ref nueva> · implementada\|sin pieza — <lección>` | `resolver-hallazgo` al aprobar una reincidencia | La lección volvió a fallar. Guarda su estado **en ese momento**, así "falló estando implementada" no depende de fechas ni del estado de hoy. Puede haber varias |
| `- **fusionada**: <fecha> · <ref absorbida>[ · implementada <fecha> · <nota>]` | `resolver-curacion`, en el destino de una fusión | Esa lección se fusionó en esta. Una por absorbida; las señales siguen esta línea para contar los usos |
| `- **retirada**: <fecha> · <motivo>` | `resolver-curacion`, al retirar o al absorber | La lección salió de `entradas/`. Va en el archivo de `retiradas/` |

Las líneas que el código no conoce (agregadas a mano, o con CRLF tras un checkout de
git) se conservan intactas. `INDEX.md` marca cada lección con `(implementada <fecha>)` y
`(falló N×)`, solo con las marcas que tenga; el planner y el reflector lo leen.

### Estados de una fase

Una fase pasa por: `pendiente` → `en_ejecucion` → `en_verificacion` →
`esperando_humano` → `aprobada`, con `en_correccion` entre intentos y `escalado` al
agotar los reintentos. Desde cualquier estado en ciclo (`en_ejecucion`,
`en_correccion`, `en_verificacion`) se puede pasar a `pausada` y volver al estado
de antes; `pausada` no bloquea el hook `Stop`. Los contratos están en `harness/hooks/lib/contracts.py` y
documentados en la spec, §6.

`fase_state.pausas` es una lista que nunca se borra, con un elemento por pausa:
`{"desde": <estado en ciclo>, "fecha": "dd-mm-aaaa", "motivo": str}`. Reanudar vuelve
al `desde` de la última. El interruptor `HARNESS_STOP=off` (solo ese valor, sin
distinguir mayúsculas ni espacios) apaga el hook `Stop`.

## Crear el perfil de un proyecto nuevo

```
profiles/<perfil>/
├── rules.json          reglas declarativas (obligatorio: es lo que activa el harness)
├── agents/<nombre>.md  el agente ejecutor del proyecto (uno o varios)
└── checks/<id>.py      checks estructurales opcionales
```

**`rules.json`**: reglas que se verifican sobre las líneas agregadas, sin escribir código.

```json
{
  "perfil": "mi-proyecto",
  "audit_comments": { "requerido": false, "severidad": "warning" },
  "prohibido": [
    { "id": "no_fetch", "archivos": [".js"], "severidad": "error",
      "patron": "\\bfetch\\s*\\(", "mensaje": "Usar el cliente HTTP del proyecto",
      "excluir": ["tests/"] }
  ],
  "no_new_deps": { "vigilar": ["package.json"], "severidad": "error",
                   "mensaje": "Ninguna dependencia nueva sin aprobación" },
  "checks_estructurales": ["mi_build"],
  "grupos": { "sintaxis_web": ["no_fetch"] }
}
```

Severidad: `error` bloquea; `warning` se reporta en `checks.json` y el escéptico
decide si importa. Un check nuevo conviene que entre como `warning` y se promueva a
`error` cuando se confirme que no da falsos positivos.

**Check estructural**: un `.py` en `checks/` que expone
`run(project_root, archivos_modificados, ctx) -> list[dict]`. Cada resultado es
`{"id", "resultado": "ok"|"fallo", "severidad": "error"|"warning", "detalle"}`. Si el
check revienta, se registra como `error_check` y no bloquea la fase: un bug del
harness no debe parecer un bug del código. Un check que `rules.json` declara pero cuyo
`.py` no existe también es `error_check`: pasar en silencio haría creer que se verificó.

Al escribir uno:

- Se ejecuta dentro de `cli.py`, así que puede hacer `from lib import gitdiff, harness`.
  Lee los archivos con `gitdiff.read_text` (respeta el BOM, UTF-8 → cp1252) y limita
  lo que reporta a `gitdiff.added_lines`, igual que los checks declarativos.
- El módulo se carga sin registrarse en `sys.modules`: `@dataclass` falla ahí; usa una
  clase normal.
- Su configuración va en `rules.json` bajo una clave propia, no en el código. Por
  ejemplo, `sp_params` de `reviewsystemgfs` lee `sp_params.carpetas_sp`: dónde están
  los SPs, en orden de prioridad, con rutas relativas a la raíz del proyecto, absolutas
  o con `%VARIABLES%` de entorno.

Ejemplos: `profiles/editornotificaciones/checks/` (build y contraste) y
`profiles/reviewsystemgfs/checks/` (estructurales, sin compilador).

**Agente ejecutor**: un `.md` con frontmatter `name` y `description` que conoce los
patrones del stack. Si el perfil tiene varios, cada fase del plan dice cuál la
ejecuta (`agente_ejecutor`).

## Usarlo con otro modelo que no sea Claude

El harness tiene dos capas, y solo una depende de Claude Code:

| Capa | Archivos | ¿Depende de Claude Code? |
|---|---|---|
| **Núcleo determinista** | `harness/hooks/cli.py`, `harness/hooks/lib/`, `rules.json`, `checks/`, contratos JSON | **No.** Es Python 3.12 sin dependencias; lo puede invocar cualquier agente o una persona |
| **Prompts** | `harness/agents/*.md`, `harness/skills/*/SKILL.md`, `harness/commands/*.md`, agentes del perfil | **No en su contenido.** Son instrucciones en Markdown que sirven como *system prompt* de cualquier modelo. El frontmatter (`model: opus`, `tools:`) sí es de Claude Code |
| **Cableado** | Registro de hooks en `settings.json`, subagentes con contexto aislado, comandos `/…`, carga de skills | **Sí.** Es lo que hay que reemplazar |

Hay tres caminos, de menos a más trabajo.

### Opción A — Claude Code con otro modelo, vía un gateway

Claude Code puede apuntar a un *LLM gateway* que hable la API de Anthropic y
traduzca a otros proveedores, por ejemplo [LiteLLM](https://docs.litellm.ai/docs/tutorials/claude_non_anthropic_models).
Así el harness funciona sin cambios: hooks, subagentes, skills y comandos incluidos.

```powershell
$env:ANTHROPIC_BASE_URL   = "http://localhost:4000"   # tu proxy LiteLLM
$env:ANTHROPIC_AUTH_TOKEN = "<clave del proxy>"
$env:ANTHROPIC_MODEL      = "<modelo definido en el proxy>"
claude
```

- Los agentes del harness piden `model: opus` en su frontmatter. Mapea ese alias
  al modelo que quieras en la configuración del gateway, o con las variables de
  alias de modelo de tu versión de Claude Code (por ejemplo
  `ANTHROPIC_DEFAULT_OPUS_MODEL`). Verifica el nombre exacto en la documentación de
  tu versión.
- Anthropic documenta el mecanismo de gateway
  ([LLM gateway](https://docs.claude.com/en/docs/claude-code/llm-gateway)), pero
  **no da soporte oficial a modelos que no sean Claude**. El uso de herramientas y
  el seguimiento de instrucciones largas varían según el modelo.
- El harness compensa una parte de esa variación: el estado lo escribe el CLI, los
  JSON se validan y los hooks bloquean. Aun así, prueba primero con un ticket chico.

### Opción B — Otro agente de programación (adaptador)

Para usarlo desde otra herramienta de agentes, reproduce cuatro piezas de cableado:

**1. Validación en vivo (equivale a `PostToolUse`).** Después de cada archivo que
el agente escriba, corre:

```bash
echo '{"tool_input": {"file_path": "C:/ruta/absoluta/al/archivo"}, "cwd": "C:/ruta/del/proyecto"}' \
  | python ~/.claude/hooks/check_rules.py
```

- Exit 0: todo bien.
- Exit 2: hubo violaciones. El **stderr** trae el mensaje; devuélveselo al modelo
  para que corrija antes de seguir.

Si tu herramienta no tiene eventos de post-escritura, pídele al agente en su prompt
que lo corra él mismo, o confía en `run-checks` (punto 3), que revisa todo el diff de
la fase.

**2. Puerta de cierre (equivale a `Stop`).** Antes de dar el turno por terminado:

```bash
echo '{"cwd": "C:/ruta/del/proyecto", "stop_hook_active": false}' \
  | python ~/.claude/hooks/gate_phase.py
```

Exit 2 significa que la fase está a medio ciclo: el stderr dice cuál es el siguiente
paso y el agente no debe cerrar el turno. Los payloads completos de los dos hooks
están en `docs/hook-payloads.md`.

**3. Orquestación.** Usa `harness/skills/ticket-loop/SKILL.md` como instrucciones del
agente principal, y el CLI tal cual. Las rutas `$HOME/.claude/hooks/cli.py` de los
documentos apuntan al lugar donde despliegues `harness/hooks/`; ajústalas si usas otro.

**4. Subagentes con contexto aislado.** El escéptico y el reflector deben correr como
**conversaciones nuevas**, con `harness/agents/skeptic.md` o
`harness/agents/reflector.md` como *system prompt* y solo las entradas que piden.
Nunca les pases la conversación del ejecutor. Si la herramienta no tiene subagentes,
haz una llamada aparte al modelo, en una conversación nueva.

- Para el reflector, da acceso **solo de lectura**: no debe poder correr el CLI ni
  escribir en la biblioteca.
- Su salida es JSON. Guárdala en archivo y regístrala con `record-veredicto` o
  `record-hallazgos`: el CLI la rechaza si no cumple el contrato.

Los comandos `/fase-ok`, `/hallazgo-ok`, etc. son atajos de un CLI: el humano puede
correr directamente `cli.py record-manual --resultado ok` o
`cli.py resolver-hallazgo --decision ok --id <ref>`.

### Opción C — Sin herramienta de agentes (modo manual)

Con cualquier chat (incluso un modelo local), el desarrollador hace de orquestador:

1. `cli.py open-ticket …`, pega el requerimiento y el prompt de `task-planner` en el
   chat, guarda el `plan.json` que devuelva y corre `cli.py validate --contrato plan`.
2. `cli.py open-fase --fase fase_1`, pega en el chat el agente del perfil más la fase
   del plan, y aplica los cambios.
3. `cli.py run-checks`.
4. En un chat **nuevo**, pega `skeptic.md`, el diff y `checks.json`; guarda el JSON y
   corre `cli.py record-veredicto`.
5. Haz la prueba manual y corre `cli.py record-manual`.
6. En otro chat nuevo, pega `reflector.md` con la evidencia de la fase y registra con
   `cli.py record-hallazgos`.

Es más lento, pero conserva lo esencial: el estado, los límites de reintento, los
contratos y la biblioteca no dependen del modelo.

## Desarrollo del propio harness

```bash
python -m unittest discover -s tests -q
```

- Solo stdlib y `unittest`.
- Cada cambio entra con su test, escrito primero.
- El harness no se valida a sí mismo: los hooks detectan el repo fuente y salen en silencio.

Tests que protegen el diseño:

- `TestSeparacionDePlanos`: `harness/` no menciona ningún stack.
- `TestReferenciasDelHarness`: toda skill, subagente, subcomando y comando nombrado en
  `harness/**/*.md` existe.
- `test_ningun_perfil_trae_biblioteca`: `deploy.ps1` nunca puede pisar la biblioteca
  de un proyecto.
- `test_documentacion`: el README menciona cada comando de `harness/commands/`, este
  documento cada subcomando de `cli.py`, y ningún encabezado `## ` se repite entre los dos.
- `test_registrar_hooks`: nada ajeno de `settings.json` cambia (hooks de otros, otras
  claves, orden, acentos) y un JSON roto no se escribe.
- `test_report`: el reporte, con datos sembrados por sección; no escribe nada en el
  proyecto y no revienta con archivos ilegibles.
- `test_punta_a_punta`: dos tickets completos con un modelo falso (respuestas fijas del
  planner, ejecutor, escéptico y reflector) sobre el CLI, los hooks, git y el reporte
  reales. El primero falla checks, escéptico y prueba manual, escala y deja una lección
  que se aprueba y se implementa; en el segundo el error vuelve y el reporte lo muestra
  como "falló estando implementada". Atrapa lo que se rompe entre piezas.

Documentos de diseño:

| Documento | Contenido |
|---|---|
| `docs/superpowers/specs/2026-07-28-ia-harness-engineering-design.md` | La spec: decisiones D1–D13, contratos, ciclo, verificación |
| `docs/superpowers/plans/2026-07-28-ia-harness.md` | Plan original (tareas 1–20) |
| `docs/superpowers/plans/harness-advance.md` | Plan de esta versión: origen en Harness² y decisiones DA1–DA9 |
| `docs/hook-payloads.md` | Payloads reales de los hooks, capturados con una sonda |
| `docs/superpowers/specs/2026-11-02-reporte-y-aprendizaje-design.md` | Reincidencia, lección implementada y reporte: qué se decidió y por qué |
| `docs/superpowers/plans/2026-11-02-reporte-y-aprendizaje.md` | Plan de esa versión (8 tareas) |

## Estructura del repositorio

```
├── harness/                  harness genérico → ~/.claude/
│   ├── agents/               skeptic.md, reflector.md, curador.md
│   ├── commands/             /ticket-abrir, /fase, /fase-pausa, /fase-ok, /fase-fallo, /hallazgo*, /hallazgo-hecho,
│   │                         /biblioteca-curar, /curacion-ok, /curacion-no, /curacion-editar
│   ├── hooks/                check_rules.py (PostToolUse), gate_phase.py (Stop), cli.py, report.py, lib/
│   └── skills/               ticket-loop, task-planner
├── profiles/                 un perfil por proyecto → <proyecto>/.claude/
│   ├── reviewsystemgfs/
│   └── editornotificaciones/
├── tests/                    suite unittest del harness
├── docs/                     spec, planes y payloads de hooks
├── historico/                archivos de partida, ya migrados
├── task-plannerv2.md         fuente del planner v3
├── registrar_hooks.py        fusiona los hooks en settings.json; lo llama deploy.ps1, no se despliega
└── deploy.ps1                despliegue a ~/.claude y al proyecto
```

## Pendientes conocidos

Menores abiertos:

- `resumen.volvieron_sin_pieza` del reporte es histórico: cuenta las lecciones con al
  menos una falla `sin pieza` aunque después se hayan implementado, así que puede ser
  mayor que lo que lista la Deuda.
- La sección Fases del reporte es larga con datos reales: lista todas las fases, las
  razones del escéptico van sin recortar y "reglas más violadas" mezcla warnings con
  errores.

Límites conocidos de los checks y del diff (revisión del paso 4, 03-11-2026):

- `sp_params` no ve las llamadas que llevan el SP en la cadena (`|VN=Sp|V0=n|...`),
  que se despachan con `LlenaCombos`/`LlenaGrid` → `EjecutarSp(Sp, Validar, ...)`: son
  cerca de la mitad de las llamadas reales (unas 23 en `Scripts/*.js` y 2 en VB). Un
  `|V27=` que el SP no parsea ahí pasa sin aviso.
- `sp_params` da `error` para `IF @Validar = 1 ... ELSE ...` llamado con otro valor; en
  el corpus actual solo aparece en SPs sin `@Parametros`.

Orden acordado de lo que sigue (hechos: el paso 1, el reporte y las reincidencias; el
paso 2, el test de punta a punta, que destapó que `run-checks` no registraba sus fallos;
el paso 3, el registro de hooks por `deploy.ps1` y `HARNESS_STOP=off`; el paso 4, los
checks estructurales de `reviewsystemgfs`, ajustados contra el repo real: el plan
original ponía en `error` un caso que compila y buscaba los SPs en una carpeta
congelada desde 2016; y el paso 5, la curación de la biblioteca con señales, curador y
aprobación humana. Sin caducidad por fecha, a propósito: la señal es el uso, y la
decisión, humana):

6. **Backlog**: escéptico con otro modelo (vía gateway) y tickets en paralelo (hoy hay
   un solo `current.json` por proyecto).
