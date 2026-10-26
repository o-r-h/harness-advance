---
description: Rechaza un hallazgo del reflector, con el motivo
argument-hint: <id> "<motivo>" [fase_N]
---

El usuario rechaza un hallazgo propuesto por el reflector. Sus argumentos: `$ARGUMENTS`

Extrae el id del hallazgo, el motivo y, si lo dio, la fase (`fase_N`), y córrelo:

```bash
python "$HOME/.claude/hooks/cli.py" resolver-hallazgo --decision no --id <id> --motivo "<motivo>" [--fase <fase>]
```

Si falta el id o el motivo, pídeselos antes de correr nada: el motivo se guarda y
evita que el reflector vuelva a proponer lo mismo. Pasa `--fase` solo si el
usuario la dio; sin ella el CLI usa la fase activa de `current.json`.

Reporta la salida del comando tal cual, sin agregar interpretación. Si falla,
muestra el error tal cual. No edites `hallazgos.json` ni la biblioteca a mano: el
CLI es el único que escribe estado.
