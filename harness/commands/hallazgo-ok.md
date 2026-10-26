---
description: Aprueba un hallazgo del reflector para que entre a la biblioteca
argument-hint: <id | TICKET/fase_N/hN>
---

El usuario aprueba un hallazgo propuesto por el reflector. Sus argumentos: `$ARGUMENTS`

Extrae el hallazgo tal como lo dio el usuario —el id (`h1`) o la referencia completa
(`ISR-123/fase_1/h1`, como la imprimen `hallazgos.md` y `hallazgos-pendientes`)— y
córrelo pasándolo tal cual:

```bash
python "$HOME/.claude/hooks/cli.py" resolver-hallazgo --decision ok --id <id o referencia>
```

Si falta, pídeselo antes de correr nada. Un id suelto solo vale para la fase activa
de `current.json`; para un hallazgo de otra fase u otro ticket hace falta la
referencia completa. No completes la referencia por tu cuenta.

Reporta la salida del comando tal cual, sin agregar interpretación. Si falla,
muestra el error tal cual. No edites `hallazgos.json` ni la biblioteca a mano: el
CLI es el único que escribe estado. Después de aprobar, sugiere versionar
`.claude/biblioteca/` con el proyecto.
