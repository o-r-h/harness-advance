---
description: Pausa la fase activa para conversar de otra cosa o cerrar el día; se retoma con /fase
argument-hint: "<motivo>"
---

Corre este comando y reporta su salida al usuario, sin agregar interpretación.

Si el usuario dio un motivo (`$ARGUMENTS` no está vacío):

```bash
python "$HOME/.claude/hooks/cli.py" pausar-fase --motivo "$ARGUMENTS"
```

Si no dio motivo:

```bash
python "$HOME/.claude/hooks/cli.py" pausar-fase
```

Si el comando falla, muestra el error tal cual. No edites el estado a mano: el CLI
es el único que escribe estado.

Termina el turno ahí. No retomes la fase ni sigas con el ciclo: la pausa existe
para que el usuario converse de otra cosa; se retoma solo con `/fase fase_N`.
