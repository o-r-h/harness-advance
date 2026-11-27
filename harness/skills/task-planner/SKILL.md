---
name: task-planner
description: Analiza un requerimiento funcional o técnico (documento Markdown, historia de usuario, ticket) y genera un plan de implementación estructurado Y ANCLADO EN EL CÓDIGO REAL — objetivo, impacto con referencias archivo:línea, evidencia verificada vs. supuestos, dudas críticas, subtareas atómicas, dependencias, riesgos y agente sugerido por tarea. Usa esta skill siempre que el usuario pida "planificar" una tarea de desarrollo, comparta un .md con un requerimiento, mencione dividir un trabajo grande en subtareas, o necesite asignar trabajo a agentes especializados (backend, frontend, database, testing, etc.), incluso si no lo pide con la palabra "plan". No uses esta skill para escribir código, corregir bugs, refactorizar o revisar Pull Requests — su output termina en un plan, nunca en una implementación. Emite el plan en dos formatos: un .md legible y un plan.json consumible por el harness.
---

# Task Planner v3

## Objetivo

Transformar un requerimiento en un plan de implementación **claro, completo, ejecutable por otros agentes
y anclado en el código real del proyecto**.

La responsabilidad de esta skill termina cuando el plan existe. **Nunca escribe código ni modifica archivos
del proyecto** — solo produce el documento de plan.

La historia de versiones está en `references/notas-de-version.md`; no hace falta para planificar.

## Cuándo usar esta skill

Usarla cuando: llega una historia de usuario/ticket/requerimiento; hay que dividir un problema grande en
tareas; hay que repartir trabajo entre agentes/roles; se recibe un documento describiendo algo a construir.

No usarla para: escribir código, corregir bugs, refactorizar o revisar PRs. Si el usuario pide eso, indicarlo
y ofrecer ayudar directamente en lugar de generar un plan.

## Entradas

1. **`task_document`** (obligatorio): el requerimiento. Archivo `.md`, ticket pegado o descripción libre.
   Si está vacío, es solo un título o es ilegible → pedir el documento antes de continuar; no inventar.
2. **`available_agents`** (opcional): roles disponibles para asignar. Si el usuario los da, **usar solo esos**.
   Si no, usar la tabla por defecto (abajo) y **aclararlo en el plan**.
3. **`codebase`** (implícito): el repositorio de trabajo. Si existe, **es obligatorio anclarse en él** (Fase 0).
4. **`.claude/biblioteca/INDEX.md`** (opcional): el índice de la biblioteca de lecciones del proyecto, que
   dejan las fases de tickets anteriores. Cada línea de `## Aprobadas` trae la clasificación, la señal (o la
   lección, si no tiene señal) y el archivo `entradas/<archivo>.md`; **el índice no trae la lección
   completa**. Cuando la señal coincide con lo que pide el ticket, abre
   `.claude/biblioteca/entradas/<archivo>.md` y léela entera. Las de `## Rechazadas — no volver a proponer`
   y las de `## Retiradas — no aplicar` **no se aplican**. Una lección es hipótesis: se verificó en otro ticket y puede no valer en este (DA8).
   Una lección con `(falló N×)` en su línea ya volvió a ocurrir pese a estar escrita: pesa más al planear,
   léela primero y haz que la fase la cumpla de forma comprobable.
   Si el plan la usa, la ancla en la fase como
   `{"ref": ".claude/biblioteca/entradas/<archivo>.md", "confianza": "por_confirmar"}` y la Fase 0 la
   re-verifica en el código como cualquier otro supuesto.

---

## Flujo de trabajo

### Fase 0 — Anclaje en el código (grounding) ★ NUEVO

Antes de analizar impacto, **entender cómo está construido hoy** lo que el ticket va a tocar. Sin esto el resto
del plan es especulación.

1. **Localizar el punto de entrada real** de la funcionalidad afectada (página, módulo, endpoint, archivo).
   - Si el proyecto tiene un **grafo graphify** (`graphify-out/graph.json`): empezar con
     `graphify query "<tema del ticket>"`, `graphify path "<A>" "<B>"` para relaciones y
     `graphify explain "<concepto>"`. Devuelven un subgrafo acotado (más barato que grep masivo).
   - Si no hay grafo: usar búsqueda de contenido (grep/glob) sobre símbolos y textos del ticket.
2. **Identificar patrones análogos ya existentes** que se puedan reutilizar o replicar (¡casi siempre los hay!).
   Ej.: si el ticket pide un campo nuevo, buscar otro formulario del repo que ya tenga uno equivalente.
3. **Detectar insights que cambien el alcance** (código muerto, valores hardcodeados, un catálogo ya existente,
   una función ya presente). Estos suelen reducir el trabajo real a la mitad — hay que buscarlos activamente.
4. **Registrar cada hallazgo con su ancla `archivo:línea`** y marcarlo como **✅ Verificado** (leído en el
   código) o **⚠️ Por confirmar** (inferido, no comprobado).

> Regla de oro: **ninguna afirmación técnica del plan sin etiqueta de confianza.** "✅ Verificado" solo si se
> leyó en el código; todo lo demás es "⚠️ Por confirmar" y, si bloquea, sube a Dudas Críticas (Fase 3).

### Fase 1 — Comprensión

Leer el documento completo. Identificar objetivo, funcionalidades, actores, reglas de negocio, restricciones,
criterios de aceptación y tecnologías afectadas. Escribir un resumen de 1-2 frases que confirme el entendimiento.

### Fase 2 — Análisis de impacto (anclado)

Determinar qué áreas se tocan: BD, backend, frontend, APIs, integraciones, auth, configuración, infra, logging,
testing, documentación. **Para cada área afectada, citar los archivos/símbolos reales** hallados en la Fase 0
(con `archivo:línea` y su etiqueta ✅/⚠️). No asumir *cómo* se implementa cada cosa — solo qué se toca y por qué.

### Fase 3 — Dudas y bloqueantes

Buscar activamente información insuficiente: reglas ambiguas, comportamiento no definido, casos límite,
dependencias desconocidas, datos faltantes, conflictos con lo existente. Clasificar:

- **Críticas**: impiden planificar (el plan sería inventado sin la respuesta). Distinguir bien:
  una ambigüedad de **negocio** suele ser crítica; un detalle **interno de implementación**
  (nombre exacto de una función, columna, id) normalmente **no** bloquea — es trabajo del agente ejecutor y
  puede resolverse con una **subtarea de descubrimiento** (spike). No confundir "no lo sé aún" con "bloqueante".
- **Importantes**: no bloquean, conviene aclararlas antes de ejecutar.

**Si hay dudas críticas, detenerse acá.** Presentar solo Fase 1 (resumen), lo relevante de Fase 0, y las
preguntas críticas; esperar respuesta antes de las Fases 4-7. Un plan sobre supuestos es peor que no tener plan.

### Fase 4 — Diseño de alto nivel

Solución conceptual: componentes involucrados, flujo esperado, interacción entre módulos, apoyándose en los
patrones análogos hallados en Fase 0. Sin detalles de implementación (nombres de funciones, esquemas exactos).

### Fase 5 — Descomposición en subtareas

Subtareas **atómicas** (un objetivo), **independientes** (verificables por separado) y **verificables** (criterio
de "terminado"). Ni gigantes ("implementar el backend") ni triviales. Magnitud útil: una sesión enfocada de un
agente. Cuando la Fase 0 dejó incógnitas internas, **la primera subtarea suele ser un descubrimiento (spike)**
que las cierra y desbloquea el resto.

### Fase 6 — Dependencias

Para cada subtarea, indicar de qué depende. Distinguir qué corre en paralelo y qué es secuencial. Derivar el
orden recomendado a partir de las dependencias (no al revés).

### Fase 7 — Asignación de agentes

Sugerir el agente más adecuado por subtarea (de `available_agents` o la tabla por defecto) con una frase de
justificación. Es recomendación, no imposición. Si una subtarea necesita más de un perfil, listarlos por
prioridad en vez de forzar uno solo.

#### Agentes por defecto (si el usuario no da su propia lista)

| Tipo de tarea | Agente sugerido |
|---|---|
| Modelo de datos, migraciones | database-agent |
| Lógica de negocio, APIs | backend-agent |
| Componentes UI, formularios | frontend-agent |
| Integraciones externas | integration-agent |
| Automatización, CI/CD, infraestructura | devops-agent |
| Pruebas | testing-agent |
| Documentación | documentation-agent |

---

## Salida — dos archivos hermanos

Los dos describen el mismo plan. **Antes de escribir cada uno, lee su archivo de
referencia entero** (están junto a esta skill): la estructura es exacta y el
harness valida el `.json`.

| Archivo | Para quién | Referencia |
|---|---|---|
| `<nombre-de-la-tarea>-plan.md` (o `implementation-plan.md`) | El humano | `references/plantilla-plan-md.md`: las 12 secciones |
| `.harness/tickets/<ticket_id>/plan.json` | El harness, que lo ejecuta fase por fase | `references/plan-json.md`: ejemplo y cómo llenar cada campo |

Si difieren, el `.json` es el que ejecuta el harness: revísalo con el mismo cuidado.

Si la Fase 3 detectó dudas críticas, genera solo las secciones 1, 2, 3 (lo hallado) y
5-Críticas del `.md`, y detente indicando que el resto queda pendiente de esas respuestas.

### El requerimiento va citado, no parafraseado

Cada fase de `plan.json` lleva en `citas` las frases de `ticket.md` que esa fase
cumple, **copiadas tal cual**: nombres de campos, textos de mensajes, valores,
ejemplos y criterios de aceptación. El ejecutor y el escéptico trabajan con esas
palabras y con la ruta de `ticket.md`, no con tu resumen: un mensaje "parecido" al
que pidió el humano es un fallo. El harness rechaza el plan si una cita no aparece
textual en `ticket.md`. Si una fase no cumple ninguna frase del ticket (un spike,
una preparación), va sin `citas`.

---

## Principios

- **Anclar antes de planificar**: leer el código real primero; nada de subtareas sobre un backend imaginario.
- **Etiquetar la confianza**: ✅ Verificado vs. ⚠️ Por confirmar en toda afirmación técnica.
- **Buscar el patrón que ya existe** para reutilizarlo, en vez de diseñar de cero.
- **Comprender antes de planificar; no asumir requisitos ausentes** — preguntar en vez de inventar.
- No implementar código ni tomar decisiones de diseño detallado.
- Preferir tareas pequeñas y desacopladas; un spike de descubrimiento es válido como primera subtarea.
- Distinguir ambigüedad de negocio (a menudo bloqueante) de hueco de implementación (rara vez bloqueante).
- Proponer agentes, nunca imponerlos.
- Mantener las subtareas dentro del alcance técnico del requerimiento.
- Respetar convenciones del repo (etiquetas de ticket, comandos de build, actualización de índices/grafos).

## Checklist antes de entregar el plan

- [ ] Se ejecutó la Fase 0: el plan cita archivos/símbolos reales, no genéricos.
- [ ] Cada afirmación técnica tiene etiqueta ✅/⚠️.
- [ ] Se buscó y (si existe) se citó un patrón análogo reutilizable.
- [ ] El objetivo está en una frase clara.
- [ ] No quedan dudas críticas sin reportar (o el plan se detuvo en Fase 3).
- [ ] Todas las áreas de impacto se revisaron contra el código, no se asumieron.
- [ ] Cada subtarea es independiente y verificable; las incógnitas internas tienen un spike.
- [ ] Dependencias explícitas y orden de ejecución derivado de ellas.
- [ ] Cada subtarea tiene un agente sugerido de `available_agents` (nunca inventado).
- [ ] Hay tabla de archivos afectados y checklist de aceptación mapeado a los CA del ticket.
- [ ] Otro agente podría tomar el plan y ejecutarlo sin volver a preguntar lo básico.
- [ ] Si existe `.claude/biblioteca/INDEX.md`, se leyó; cada lección de la biblioteca que usa el plan se
      abrió completa en `entradas/` y quedó anclada como `por_confirmar`, y ninguna rechazada se aplicó.
- [ ] Se emitió `plan.json` además de `plan.md`, y ambos describen el mismo plan.
- [ ] Se leyó el `rules.json` del perfil y todos los `checks_deterministas` existen ahí.
- [ ] Cada fase que cumple algo del ticket lleva sus `citas`, copiadas de `ticket.md` sin retocar.
- [ ] `plan.json` pasa la validación:
      `python "$HOME/.claude/hooks/cli.py" validate --contrato plan --archivo <ruta>`
- [ ] Cada `criterio_exito` es comprobable por alguien que no leyó el código.
