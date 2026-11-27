## Cuando una fase escala

Al agotarse los reintentos, la fase queda en `escalado`. No arranques otro intento
ni pases a la fase siguiente. Reporta al humano, en este orden:

1. Qué se intentó en cada intento y qué falló, tomado del `historial_fallos`.
2. Qué patrón se repite entre los fallos.
3. Si el patrón es un fallo del escéptico que ya apareció más de una vez,
   propón la corrección según la escalera *dónde va cada corrección*: la pieza más
   barata que lo habría atrapado. Ese es el ciclo de mejora del harness: convertir
   juicio caro en verificación barata.

Haya o no patrón, después del reporte ejecuta siempre "Al cerrar una fase"
(`references/cerrar-fase.md`): la fase escalada es la que más enseña. Esto vale
también cuando la fase escaló por un `/fase-fallo`.
