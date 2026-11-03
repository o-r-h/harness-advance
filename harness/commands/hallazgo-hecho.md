---
description: Marca como implementada la pieza que pedía una lección de la biblioteca
argument-hint: <TICKET/fase_N/hN> "<nota>"
---

El usuario avisa que ya hizo la pieza del harness que pedía una lección aprobada. Sus
argumentos: `$ARGUMENTS`

Extrae la referencia completa de la lección (`ISR-123/fase_1/h1`, como la imprime
`hallazgos.md` o `INDEX.md`) y la nota que dice qué se hizo (un commit, un archivo),
y córrelos pasándolos tal cual:

```bash
python "$HOME/.claude/hooks/cli.py" hallazgo-hecho --id <referencia> --nota "<nota>"
```

Si falta la referencia o la nota, pídesela antes de correr nada. Solo vale la
referencia completa: no aceptes un id suelto (`h1`) ni la completes por tu cuenta.

Reporta la salida del comando tal cual, sin agregar interpretación; si reemplazó una
marca anterior, la segunda línea la dice. Si falla, muestra el error tal cual. No
edites la biblioteca a mano: el CLI es el único que escribe estado. Después de marcar,
sugiere versionar `.claude/biblioteca/` con el proyecto.
