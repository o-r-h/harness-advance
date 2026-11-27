## Plantilla de `plan.md`

El mismo documento de 12 secciones de la v2; lo único que cambia es la línea `Skill: task-planner-v3` del
encabezado. Es lo que el usuario lee.
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
