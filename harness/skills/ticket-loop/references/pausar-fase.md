## Pausar una fase

- Solo el humano pausa, con `/fase-pausa`. Nunca corras `pausar-fase` por iniciativa
  propia.
- Si a mitad de fase el humano pregunta otra cosa o pide parar, respóndele,
  recuérdale `/fase-pausa` y termina el turno sin retomar la fase.
- Se retoma con `/fase fase_N`: `open-fase` reanuda en el mismo intento.
- Si desde la pausa cambió el ticket activo (se abrió otro con `open-ticket`), `open-fase`
  solo actúa sobre el activo. Reabre el ticket pausado con `CLI open-ticket`, con el
  mismo id y los valores de su `ticket_context.json` (**sin invocar al task-planner ni
  reescribir `plan.json`**), y luego `/fase fase_N`.
- Al reanudar, sigue desde el paso que corresponde al estado impreso:
  `en_ejecucion` o `en_correccion` → paso 2; `en_verificacion` → paso 5 (si el
  código cambió durante la pausa, `record-veredicto` lo rechaza y manda al paso 4).
- Mientras la fase activa corre, `open-fase` de otra fase y `open-ticket` se
  rechazan.
