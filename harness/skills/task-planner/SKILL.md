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

> **Qué cambia respecto a la v1:** la v1 producía planes bien estructurados pero "en el aire" — no obligaba a
> mirar el código. Un plan que dice "ajustar el backend" sin saber qué archivo, qué función o qué ya existe
> genera subtareas inventadas. La v2 **exige una fase de anclaje en el código antes de planificar** y que cada
> afirmación del plan quede etiquetada como **verificada** o **supuesto**.

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

### 1. `plan.md` — para el humano

El mismo documento de 12 secciones de la v2, sin cambios. Es lo que el usuario lee.
Se genera como `<nombre-de-la-tarea>-plan.md` (o `implementation-plan.md` si no hay nombre claro) con esta
estructura exacta:

```markdown
# Plan de Implementación: [Nombre de la tarea]

> Skill: task-planner-v3. Agentes: [lista provista | tabla por defecto].
> Leyenda de evidencia: ✅ Verificado en código · ⚠️ Por confirmar.

## 1. Resumen
[1-2 frases: qué se construye y qué valor aporta]

## 2. Objetivo
[Una frase]

## 3. Hallazgos del código (anclaje)
[Rol de los archivos clave con archivo:línea y ✅/⚠️. Patrones análogos a reutilizar.
Insights que cambian el alcance. Esta sección es la que hace confiable al resto del plan.]

## 4. Impacto
### Base de datos
### Backend
### Frontend
### Integraciones
### Otros (infra, seguridad, observabilidad, testing, documentación)
[Cada punto cita archivos/símbolos reales cuando aplique]

## 5. Dudas
### Críticas
[Vacío si no hay. Si hay alguna, el plan se detiene acá — ver Fase 3]
### Importantes
[Abiertas sin bloquear la ejecución]

## 6. Diseño de alto nivel
[Componentes, flujo, interacción]

## 7. Subtareas

| ID | Tarea | Descripción | Depende de | Agente sugerido | Justificación |
|----|-------|-------------|------------|-----------------|---------------|

## 8. Orden recomendado de ejecución
[Agrupar lo paralelizable, ej: "T2, T4 y T7 en paralelo, luego T3"]

## 9. Riesgos
[Qué podría salir mal o generar retrabajo — incluir riesgos técnicos vistos en el código]

## 10. Archivos afectados (estimado)

| Proyecto | Archivo | Acción |
|----------|---------|--------|

## 11. Checklist de aceptación
[Un ítem verificable por cada criterio de aceptación del ticket]

## 12. Observaciones
[Todo lo relevante que no entre arriba: convenciones del repo, comandos de build, etc.]
```

Si la Fase 3 detectó dudas críticas, generar solo las secciones 1, 2, 3 (lo hallado) y 5-Críticas, y detenerse
explícitamente indicando que el resto queda pendiente de esas respuestas.

### 2. `plan.json` — para el harness

El mismo plan en forma consumible por código. Va en
`.harness/tickets/<ticket_id>/plan.json`. El `.md` y el `.json` describen el mismo
plan: si difieren, el `.json` es el que ejecuta el harness, así que revísalo con el
mismo cuidado.

```json
{
  "ticket_id": "TK-1042",
  "perfil": "mi-proyecto",
  "generado_por": "task-planner-v3",
  "fases": [
    {
      "id": "fase_1",
      "titulo": "Agregar campo de comentario en el formulario de orden",
      "pasos": [
        "Declarar el control nuevo en la vista del formulario",
        "Guardar el valor mediante el procedimiento existente",
        "Releer el valor al cargar el formulario"
      ],
      "anclajes": [
        { "ref": "src/ordenes/EditarOrden.cs:412", "confianza": "verificado" },
        { "ref": "db/procedimientos/guardar_orden.sql:88", "confianza": "por_confirmar" }
      ],
      "criterio_exito": "El comentario se guarda al presionar Guardar y se relee al reabrir la orden",
      "checks_deterministas": ["audit_comments", "no_new_deps"],
      "prueba_manual": { "requerida": true, "url": "ordenes/editar", "datos": "orden 4471, idioma ES" },
      "herramientas_permitidas": ["read", "edit"],
      "max_reintentos": 3,
      "depende_de": [],
      "agente_ejecutor": "backend-agent"
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
- **`agente_ejecutor`**: opcional. Es obligatorio en todas las fases cuando el perfil
  tiene más de un agente en `.claude/agents/`. Su valor es el nombre del agente (el
  nombre del archivo sin extensión), nunca una ruta. Una fase no mezcla stacks: si toca
  dos, divídela en dos fases enlazadas con `depende_de`.

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
- [ ] Se emitió `plan.json` además de `plan.md`, y ambos describen el mismo plan.
- [ ] Se leyó el `rules.json` del perfil y todos los `checks_deterministas` existen ahí.
- [ ] `plan.json` pasa la validación:
      `python "$HOME/.claude/hooks/cli.py" validate --contrato plan --archivo <ruta>`
- [ ] Cada `criterio_exito` es comprobable por alguien que no leyó el código.
