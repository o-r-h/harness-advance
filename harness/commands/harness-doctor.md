---
description: Revisa, sin cambiar nada, si el harness y el proyecto están bien instalados
---

Corre este comando y muestra su salida tal cual:

```bash
python "$HOME/.claude/hooks/cli.py" doctor
```

Si el humano tiene a mano la carpeta del harness (donde está `deploy.ps1`), agrega
`--fuente <esa carpeta>` para comparar lo instalado con ella.

`doctor` solo lee. Cada `falla` y cada `aviso` trae su remedio en la línea
siguiente: **no apliques ningún remedio por tu cuenta**; explícaselo al humano y
espera a que él decida.
