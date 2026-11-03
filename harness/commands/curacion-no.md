---
description: Rechaza una acción de curación de la biblioteca, con el motivo
argument-hint: <cN> "<motivo>"
---

El usuario rechaza una acción que propuso el curador. Sus argumentos: `$ARGUMENTS`

Extrae el id de la acción (`c1`) y el motivo, y córrelos pasándolos tal cual:

```bash
python "$HOME/.claude/hooks/cli.py" resolver-curacion --decision no --id <cN> --motivo "<motivo>"
```

Si falta el id o el motivo, pídeselo antes de correr nada: el motivo queda en
`.claude/biblioteca/curacion-rechazada.md` y el curador lo lee para no volver a
proponerla. Reporta la salida del comando tal cual; si falla, muestra el error tal
cual. No edites la biblioteca ni `curacion.json` a mano. Después de rechazar,
sugiere versionar `.claude/biblioteca/` con el proyecto.
