# Contrato de seguridad de reserva

Este documento define las garantias que no deben romperse al separar admin API,
worker y dashboard.

## Principios

- Una orden debe ejecutarse con una sesion Playwright nueva.
- No reutilizar login, cookies ni contexto entre clientes.
- No enviar dos reservas para la misma orden.
- No repetir automaticamente si la confirmacion queda incierta.
- No considerar una reserva segura sin evidencia suficiente del portal.

## Claim de orden

Antes de ejecutar una orden, el worker debe reclamarla con
`service_orders.lease_owner` y `lease_expires_at`. La ejecucion solo debe
continuar si el lease sigue vigente.

Durante la ejecucion, un heartbeat renueva el lease. Si el lease se pierde, el
resultado debe tratarse como incierto o error controlado, no como exito normal.

## Intentos de reserva

`reservation_attempts` protege el envio:

- `intent`: se va a intentar reservar.
- `pending`: el envio empezo.
- `confirmed`: reserva resuelta como confirmada.
- `rejected`: el portal rechazo o el cupo se perdio.
- `unknown`: no se pudo clasificar con seguridad.

Debe existir como maximo un intento activo por orden en estados `intent`,
`pending` o `unknown`.

## Confirmacion

La confirmacion mas fuerte es la etapa `Programado`. El texto de exito del
portal puede ser evidencia positiva, pero futuras fases deben mantener una
frontera clara entre:

- cupo detectado;
- envio de reserva;
- texto de exito;
- etapa `Programado`;
- conciliacion posterior.

## Evidencia

Guardar evidencia cuando hay:

- disponibilidad completa;
- intento de CAPTCHA;
- envio de reserva;
- respuesta del portal;
- error importante;
- reserva incierta.

La evidencia no debe incluir credenciales ni datos sensibles sin sanitizar.

## Sesion manual

Una sesion manual debe:

- abrir Playwright visible en una sesion nueva;
- no reutilizar cookies del worker;
- no devolver password al frontend;
- no cambiar estado de reserva por si sola;
- registrar auditoria minima en logs;
- estar deshabilitada por defecto;
- aceptar solo clientes loopback.

## Acciones administrativas concurrentes

El backend debe proteger acciones peligrosas si una orden esta reclamada:

- pausar;
- archivar;
- marcar pagado;
- cambiar prioridad o reglas;
- abrir sesion manual.

El frontend solo puede sugerir/deshabilitar botones; la regla real debe vivir
en backend.
