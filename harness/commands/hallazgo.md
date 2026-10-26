---
description: Propone una lección propia; entra a la biblioteca ya aprobada
argument-hint: "<lección>"
---

El usuario propone una lección que vio y ningún agente vio. Sus argumentos: `$ARGUMENTS`

```bash
python "$HOME/.claude/hooks/cli.py" hallazgo --texto "<lección>"
```

Si falta la lección, pídesela antes de correr nada. Si el usuario indica la
dimensión (`proceso` o `dominio`) o el componente (`regla`, `check`, `skill`,
`hook` o `agente`), agrégalos como `--dimension` y `--componente`.

Reporta la salida del comando tal cual, sin agregar interpretación. Si falla,
muestra el error tal cual. No edites `hallazgos.json` ni la biblioteca a mano: el
CLI es el único que escribe estado. Después, sugiere versionar
`.claude/biblioteca/` con el proyecto.
