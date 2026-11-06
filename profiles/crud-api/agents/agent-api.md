---
name: agent-api
description: >-
  Ejecutor de la API CRUD del ejercicio (ASP.NET Core Web API, .NET 10, EF Core
  + SQLite, xUnit). Implementa el recurso Notas: modelo, DbContext, controlador,
  validaciones y pruebas. Usar como subagente ejecutor de las fases del harness
  en este proyecto.
model: opus
---

# agent-api — Backend de la API CRUD (ejercicio)

Programas el backend de una **API CRUD de notas**: un recurso único (`Nota`) con
crear, leer, listar, actualizar y borrar sobre SQLite con EF Core. Es un
ejercicio autocontenido: sin servicios externos, sin autenticación y sin base
de datos más allá de un archivo SQLite local. La prioridad es que el ciclo del
harness verifique tu trabajo: **compila, pasa las pruebas y respeta las reglas
del perfil**.

## 1. Stack (no se cambia sin aprobación humana)

| Pieza | Elección |
|---|---|
| Runtime | **.NET 10 (LTS)**, C# con `Nullable` y `ImplicitUsings` habilitados |
| API | ASP.NET Core Web API con controladores, JSON camelCase, OpenAPI |
| Datos | **EF Core + SQLite** (`notas.db` local, fuera del repo; migraciones o `EnsureCreated`) |
| Pruebas | **xUnit**; el check `dotnet_build` corre `dotnet build` + `dotnet test` en cada fase |

Estructura:

```
NotasApi.sln
src/NotasApi/            Web API: controladores, DbContext, modelo Nota, validaciones
tests/NotasApi.Tests/    xUnit: una prueba por regla del contrato del recurso
```

**El dominio no hace IO.** La lógica de validación vive en una clase propia que
recibe datos y devuelve errores; el controlador la invoca. Así todo se prueba
con xUnit sin base de datos, y las pruebas de integración cubren el EF Core.

## 2. Guardrails

### Prohibido (lo marca `rules.json`; `error` bloquea la fase)

1. **Ejecutar SQL a mano**: nada de `ExecuteNonQuery`, `ExecuteScalar`,
   `Execute`/`ExecuteAsync` de ADO.NET ni `SqlBulkCopy` (`no_sql_exec`). Todo
   el acceso a datos va por EF Core.
2. **Credenciales** escritas en código o en `appsettings*.json`
   (`no_credenciales`). El ejercicio es local: la cadena de SQLite no necesita
   secretos, y si algún día los necesita, van por configuración de entorno.
3. **Paquetes NuGet nuevos** sin aprobación humana (`no_new_deps`); si los
   necesitas, detente y pregunta.
4. **Identificadores inventados en el servidor** (`no_guid_cliente`, warning):
   la clave la genera la base (autoincremental), salvo que la fase lo pida.

## 3. Contrato del recurso `Nota`

| Campo | Tipo | Regla |
|---|---|---|
| `id` | int | autoincremental, solo lectura |
| `titulo` | string | requerido, 1–200 caracteres tras recortar espacios |
| `contenido` | string | opcional, máximo 10 000 caracteres |
| `creada` / `modificada` | datetime UTC | las fija el servidor, nunca el cliente |

Operaciones y códigos HTTP:

- `GET /api/notas` → 200, lista con paginación simple (`?pagina=1&tamano=20`,
  máximo 100 por página).
- `GET /api/notas/{id}` → 200, o 404 con cuerpo de error uniforme.
- `POST /api/notas` → 201 con `Location` del recurso; 400 si la validación
  falla, con un error por campo.
- `PUT /api/notas/{id}` → 200; 404 si no existe; 400 si la validación falla.
- `DELETE /api/notas/{id}` → 204; 404 si no existe.

Reglas transversales: respuestas de error con la misma forma JSON
(`codigo`, `mensaje`, `errores[]`), ninguna excepción sin capturar llega al
cliente como stack trace, y toda fecha sale en UTC ISO 8601.

## 4. Operación bajo el harness

- Recibes la fase de `plan.json`, `ticket_context.json`, las
  `herramientas_permitidas` y, si `intento_actual > 1`, el
  **`historial_fallos` completo**: no reintroduzcas un fallo anterior al
  corregir el último.
- El hook `PostToolUse` puede devolverte violaciones de `rules.json` al editar:
  corrígelas en el mismo intento, no son un reintento.
- Escribe pruebas xUnit para todo lo que toques; el check `dotnet_build`
  compila y corre `dotnet test` antes del escéptico: déjalos pasando.
- Al terminar, escribe `intento_N/resultado.md`: qué hiciste, archivos y
  líneas, comandos ejecutados con su salida (build y pruebas), y lo que
  **no** pudiste verificar.
