# Contrato de seguridad de reserva

Estado: vigente.

Ultima verificacion: `2026-09-02`.

Responsable: dominios `reservation_engine/`, `worker/`, caso transaccional
`services/application/confirm_reservation.py` y persistencia en `db/`.

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

El lease global del host tiene un heartbeat propio y no sustituye este claim.
La perdida de cualquiera de los dos activa la cancelacion conservadora. La
ultima barrera se evalua despues de guardar `intent` y justo antes del clic: si
la propiedad cambio en ese intervalo, no se envia el submit y el intento no se
convierte en reintentable automaticamente.

## Intentos de reserva

`reservation_attempts` protege el envio:

- `intent`: se va a intentar reservar.
- `pending`: el envio empezo.
- `confirmed`: reserva resuelta como confirmada.
- `rejected`: el portal rechazo o el cupo se perdio.
- `unknown`: no se pudo clasificar con seguridad.

Debe existir como maximo un intento activo por orden en estados `intent`,
`pending` o `unknown`.

Cada cupo unico debe archivar su screenshot inmediatamente antes de CAPTCHA o
submit. La captura tecnica de un CAPTCHA para evidencia, sin resolverlo ni pulsar
`Reservar`, no constituye un intento de reserva. Los resultados
`blocked_by_order_rule` y `priority_deferred` deben conservar
`reservation_attempted=false` y no deben crear una fila en
`reservation_attempts`.

Esta captura canonica debe contener fecha y hora exactas del modal ya
estabilizado y conservarse antes de continuar en los tres caminos: seleccion
inicial, seleccion bloqueada por regla y reobservacion recuperada tras
`slot_lost`. Si no puede guardarse o archivarse, el flujo debe detenerse antes
de crear la intencion de reserva. La captura CAPTCHA es evidencia secundaria y
no puede sustituir a la captura canonica del cupo.

## Confirmacion

La confirmacion primaria es el texto explicito de exito devuelto por el portal
despues del submit. La etapa `Programado` es una confirmacion posterior y sirve
como conciliacion o fallback cuando el texto no pudo conservarse. Ambas deben
mantener una frontera clara entre:

- cupo detectado;
- envio de reserva;
- texto de exito;
- etapa `Programado`;
- conciliacion posterior.

La conciliacion posterior debe iniciar sesion con el `document_type` persistido
en la orden, igual que la ejecucion principal. No puede volver implicitamente a
`dni`, porque eso produciria un falso rechazo de credenciales para cuentas con
Carne de Extranjeria.

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

La admision se serializa por cuenta del portal mediante un bloqueo de fila y un
propietario persistido en el lease de la orden. Debe rechazar antes de abrir
Chromium si la cuenta tiene lease de worker, intento activo o incierto,
preflight pendiente/en curso, revision post-cita activa u otra sesion manual.
El propietario se renueva mientras el navegador vive y se libera solamente
despues de cerrar el contexto.

El inventario usa `opening`, `active`, `closing` y `close_timeout`. Agotar el
tiempo de cierre no elimina la sesion: permanece bloqueando nuevas aperturas y
reinicios hasta que el thread y Chromium terminen realmente.

## Acciones administrativas concurrentes

El backend debe proteger acciones peligrosas si una orden esta reclamada:

- pausar;
- archivar;
- marcar pagado;
- cambiar prioridad o reglas;
- abrir sesion manual.

El frontend solo puede sugerir/deshabilitar botones; la regla real debe vivir
en backend.
