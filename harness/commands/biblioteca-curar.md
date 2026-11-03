---
description: Corre el curador sobre la biblioteca de lecciones y registra lo que propone
---

El usuario pide curar la biblioteca de lecciones del proyecto. No hace falta un
ticket ni una fase abiertos. Sus argumentos, si los hay: `$ARGUMENTS`

1. Calcula las señales:

   ```bash
   python "$HOME/.claude/hooks/cli.py" senales-biblioteca --json
   ```

2. Invoca al subagente `curador`. Pásale: las entradas de
   `.claude/biblioteca/entradas/` completas, `INDEX.md`, las de `rechazados/`,
   `.claude/biblioteca/curacion-rechazada.md` si existe, el JSON de señales del paso
   1, y los `.claude/agents/*.md` y `.claude/rules.json` del proyecto. **No le pases
   esta conversación**: decide con lo que está en disco.

3. Guarda su JSON en `.harness/propuesta_curacion.json` y regístralo:

   ```bash
   python "$HOME/.claude/hooks/cli.py" record-curacion --archivo .harness/propuesta_curacion.json
   ```

   Si el CLI la rechaza, devuélvele el error al curador **una vez** para que la
   corrija y vuelve a registrarla. Si falla de nuevo, muestra el error y para.

4. Muestra `.harness/curacion.md` tal cual: cada acción con lo que hay que responder
   (`/curacion-ok`, `/curacion-editar`, `/curacion-no`).

5. **El turno termina ahí.** No resuelvas ninguna acción por tu cuenta: cada una la
   decide el usuario. Las acciones pendientes no bloquean nada.
