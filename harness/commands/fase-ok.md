---
description: Registra que la prueba manual de la fase activa pasó
argument-hint: [--aceptar-cambio "<motivo>"]
---

Corre este comando y reporta su salida al usuario, sin agregar interpretación:

```bash
python "$HOME/.claude/hooks/cli.py" record-manual --resultado ok
```

Si el comando falla, muestra el error tal cual. No intentes aprobar la fase por
otro medio ni editar el estado a mano: el CLI es el único que escribe estado.

Si el error dice que **el código cambió después de la verificación**, muéstrale al
humano los archivos que nombra y detente. **No agregues `--aceptar-cambio` por tu
cuenta**: solo si el humano lo escribe él mismo en `$ARGUMENTS`, con su motivo, lo
pasas tal cual: `record-manual --resultado ok --aceptar-cambio "<motivo>"`.

Si la fase quedó aprobada, sigue de inmediato con "Al cerrar una fase" de la skill
`ticket-loop` (`references/cerrar-fase.md`), antes de abrir la fase siguiente con
`CLI open-fase`: invoca al reflector, registra su propuesta y muestra los
hallazgos. Si la fase no quedó aprobada, termina ahí.
