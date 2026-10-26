---
description: Registra que la prueba manual falló, con el paso y lo observado
argument-hint: <número de paso> "<qué pasó en realidad>"
---

El usuario reporta que la prueba manual falló. Sus argumentos: `$ARGUMENTS`

Extrae el número de paso y la observación, y córrelo:

```bash
python "$HOME/.claude/hooks/cli.py" record-manual --resultado fallo --paso <N> --observacion "<observación>"
```

Si falta el número de paso o la observación, pídeselos antes de correr nada: sin
esos dos datos el intento siguiente no sabe qué corregir.

Después de registrarlo, mira el estado que imprimió el CLI:

- Si la fase quedó en `escalado`, se agotaron los reintentos: **no arranques otro
  intento.** Sigue con "Cuando una fase escala" y después con "Al cerrar una fase"
  de la skill `ticket-loop`.
- Si no, lee el `historial_fallos` de la fase y arranca el intento siguiente
  teniendo presente **todos** los fallos anteriores, no solo el último.
