---
description: Configura qué navegador automatizado y qué base usa el probador en este proyecto
---

Setup de la prueba asistida. Se corre una vez por proyecto y se repite cuando cambia
el navegador o la base. `CLI` = `python "$HOME/.claude/hooks/cli.py"`; si el
directorio actual no está dentro del proyecto, agrega `--project <ruta del proyecto>`.

1. `CLI setup-prueba` muestra la configuración actual o dice que no hay.
2. Revisa **tus propias herramientas** y agrúpalas por el servidor que las da.
   Candidatos a navegador: los que navegan, hacen clic y toman capturas. Candidatos
   a base: los que corren consultas.
3. Pregúntale al humano, en un solo mensaje y con esos candidatos a la vista:
   - cuál es el navegador, o si no hay;
   - cuál es la base, o si no hay; y si la hay, en qué ambiente debe consultar
     el probador (o "el que esté activo");
   - qué herramientas de esa base quedan **prohibidas**. Propón tú las que cambian
     de ambiente, de servidor o de base, y las que escriben o ejecutan; el humano
     confirma o corrige. Anota los nombres completos, tal como los ves.
4. Si falta un navegador o una base, **no instales nada**: la instalación, su
   versión y sus credenciales son del humano. Explícale qué falta, guarda el setup
   con lo que hay y dile que lo repita cuando lo conecte.
5. **Nunca pidas ni teclees credenciales ni cadenas de conexión**: viven en la
   configuración de cada servidor, que maneja el humano.
6. Guarda la respuesta:
   `CLI setup-prueba --navegador <servidor> | --sin-navegador --base <servidor> | --sin-base [--ambiente <ambiente>] [--prohibida <herramienta> ...]`
   y muéstrale el resumen que imprime.

Las `prohibidas` son un bloqueo técnico: `setup-prueba` genera
`<proyecto>/.claude/agents/probador.md`, una copia del probador con esas herramientas
en `disallowedTools`, que el proyecto usa en lugar del global. Vale desde la próxima
sesión: díselo al humano. Por eso cada nombre va completo y exacto, sin comas ni
espacios. Si el proyecto ya tiene un probador propio, el setup no lo toca y avisa
qué agregarle a mano.
