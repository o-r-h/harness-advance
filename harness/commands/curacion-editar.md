---
description: Corrige una acción de curación de la biblioteca y la aplica
argument-hint: <cN> [--texto "<lección>"] [--senal "<señal>"] [--quitar <ref>] [--motivo "<motivo>"]
---

El usuario corrige una acción que propuso el curador y la aprueba. Sus argumentos:
`$ARGUMENTS`

Extrae el id de la acción (`c1`) y lo que el usuario quiere corregir, y córrelo
pasándolo tal cual:

```bash
python "$HOME/.claude/hooks/cli.py" resolver-curacion --decision editar --id <cN> [opciones]
```

Opciones, según el tipo de la acción (`.harness/curacion.md` lo dice):

- **Fusión**, al menos una:
  - `--texto "<lección>"`: la lección fusionada, corregida.
  - `--senal "<señal>"`: la señal corregida. Es lo que muestra `INDEX.md` y lo que el
    planner compara con el ticket.
  - `--quitar <TICKET/fase_N/hN>`: saca esa lección de la fusión; se repite para
    sacar varias. No vale para el destino ni para dejar una sola lección.
- **Retirada**: `--motivo "<motivo>"`, el motivo corregido.

Si no queda claro qué corregir, pregúntaselo antes de correr nada; no completes el
texto por tu cuenta. Reporta la salida del comando tal cual; si falla, muestra el
error tal cual. No edites la biblioteca ni `curacion.json` a mano. Después de
aplicar, sugiere versionar `.claude/biblioteca/` con el proyecto.
