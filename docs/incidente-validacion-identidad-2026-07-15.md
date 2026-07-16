# Incidente de validacion de identidad del 15-07-2026

## Resultado del analisis

Las ordenes de Bryanha Rubinos y Ken Escobedo iniciaron sesiones Playwright separadas,
con navegadores y contextos nuevos. Los registros no muestran reutilizacion de cookies ni
credenciales entre clientes.

El rechazo ocurrio antes de resolver el CAPTCHA, cuando el control de seguridad comparo el
nombre de la orden con el nombre presentado por el portal. La comparacion anterior dependia
del orden textual de nombres y apellidos, por lo que una representacion equivalente en otro
orden podia producir un falso rechazo.

## Correccion

- La identidad se compara por componentes normalizados y acepta el mismo nombre aunque el
  portal cambie el orden de nombres y apellidos.
- Si el portal presenta un valor vacio, oculto o transitorio, se realizan hasta tres lecturas
  breves antes de tomar una decision.
- Una identidad ausente o realmente diferente sigue bloqueando el envio de la reserva.
- El log registra solamente la cantidad de componentes comparados; no expone nombres reales.

Esta correccion no elimina la barrera de seguridad ni permite continuar ante una identidad
diferente.
