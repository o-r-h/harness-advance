---
description: Registra que la prueba manual de la fase activa pasó
---

Corre este comando y reporta su salida al usuario, sin agregar interpretación:

```bash
python "$HOME/.claude/hooks/cli.py" record-manual --resultado ok
```

Si el comando falla, muestra el error tal cual. No intentes aprobar la fase por
otro medio ni editar el estado a mano: el CLI es el único que escribe estado.

Si la fase quedó aprobada, sigue con la sección "Al cerrar una fase" de la skill
`ticket-loop`: invoca al reflector, registra su propuesta y muestra los hallazgos.
