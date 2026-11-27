## `plan.json`: ejemplo y cómo llenar cada campo

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
      "citas": [
        "Agregar un campo Comentario (máximo 500 caracteres) en el formulario de orden",
        "Si se guarda vacío mostrar: \"El comentario es obligatorio\""
      ],
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
- **`citas`**: las frases de `ticket.md` que esta fase cumple, copiadas tal cual
  (se perdonan solo espacios y saltos de línea). Cita lo que no admite versión
  propia: nombres, textos de mensajes, valores, ejemplos, criterios de aceptación.
  No cites el ticket entero ni escribas aquí tu interpretación: eso va en `pasos`.
  El harness rechaza el plan si una cita no aparece textual en `ticket.md`.
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
