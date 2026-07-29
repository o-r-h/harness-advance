---
description: Registra que la prueba manual de la fase activa pasó
---

Corre este comando y reporta su salida al usuario, sin agregar interpretación:

```bash
python "$HOME/.claude/hooks/cli.py" record-manual --resultado ok
```

Si el comando falla, muestra el error tal cual. No intentes aprobar la fase por
otro medio ni editar el estado a mano: el CLI es el único que escribe estado.
