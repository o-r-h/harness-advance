---
description: Aprueba un hallazgo del reflector con la lección corregida por el humano
argument-hint: <id | TICKET/fase_N/hN> "<lección corregida>"
---

El usuario aprueba un hallazgo, pero con la lección corregida. Sus argumentos: `$ARGUMENTS`

Extrae el hallazgo tal como lo dio el usuario —el id (`h1`) o la referencia completa
(`ISR-123/fase_1/h1`, como la imprimen `hallazgos.md` y `hallazgos-pendientes`)— y la
lección corregida, y córrelo pasando el hallazgo tal cual:

```bash
python "$HOME/.claude/hooks/cli.py" resolver-hallazgo --decision editar --id <id o referencia> --texto "<texto>"
```

Si falta el hallazgo o el texto, pídeselos antes de correr nada. Un id suelto solo
vale para la fase activa de `current.json`; para un hallazgo de otra fase u otro
ticket hace falta la referencia completa. No completes la referencia por tu cuenta.
Si el usuario agrega `--nueva` (no es reincidencia: ignora la marca del reflector) o
`--reincide <ref>` (es reincidencia de esta otra lección), pásalos tal cual al CLI.
Ejemplo: `... --id <id o referencia> --reincide ISR-123/fase_1/h1`.

Reporta la salida del comando tal cual, sin agregar interpretación. Si falla,
muestra el error tal cual. No edites `hallazgos.json` ni la biblioteca a mano: el
CLI es el único que escribe estado. Después de aprobar, sugiere versionar
`.claude/biblioteca/` con el proyecto.
