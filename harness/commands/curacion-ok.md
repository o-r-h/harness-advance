---
description: Aprueba una acción de curación de la biblioteca y la aplica
argument-hint: <cN>
---

El usuario aprueba una acción que propuso el curador. Sus argumentos: `$ARGUMENTS`

Extrae el id de la acción (`c1`, como lo imprime `.harness/curacion.md`) y córrelo:

```bash
python "$HOME/.claude/hooks/cli.py" resolver-curacion --decision ok --id <cN>
```

Si falta el id, pídeselo antes de correr nada. Reporta la salida del comando tal
cual, sin agregar interpretación; si falla, muestra el error tal cual. No edites la
biblioteca ni `curacion.json` a mano: el CLI es el único que escribe estado. Después
de aplicar, sugiere versionar `.claude/biblioteca/` con el proyecto.
