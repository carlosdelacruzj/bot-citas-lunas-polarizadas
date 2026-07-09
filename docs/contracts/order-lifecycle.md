# Contrato de ciclo de vida de ordenes

Este documento describe estados y transiciones que el admin API, CLI, worker y
dashboard deben respetar.

## Estados de `service_orders.status`

- `ready`: orden elegible para monitoreo/reserva.
- `paused`: orden pausada administrativamente o por rechazo de credenciales.
- `reserved_payment_pending`: reserva confirmada, pago pendiente.
- `paid`: cobro registrado.
- `archived`: orden cerrada o excluida de cola.

Solo `ready` entra en la cola activa.

## Ordenamiento

La cola activa usa:

```text
priority DESC, created_at ASC
```

Las restricciones por orden se aplican antes de enviar reserva:

- `minimum_hour`
- `minimum_date`
- `allowed_weekdays`

## Estado operativo en `order_state`

`order_state` guarda informacion de ultimo resultado y cooldown:

- `last_status`
- `last_message`
- `consecutive_errors`
- `credential_failures`
- `next_allowed_at`
- `last_run_at`
- `last_success_at`
- flags de submission pendiente

`next_allowed_at` puede excluir temporalmente una orden sin cambiar
`service_orders.status`.

## Estados de resultado

Resultados principales:

- `available`
- `completed`
- `error`
- `partial`
- `paused`
- `registered`
- `reservation_unconfirmed`
- `skipped`
- `unavailable`
- `unknown`

Estados internos adicionales:

- `programmed`
- `submission_intent`
- `submission_pending`

## Reglas de cierre

- Una orden `paid`, `reserved_payment_pending` o `archived` no debe volver a la
  cola activa.
- Una reserva confirmada debe persistirse junto con `runs`, `reservations`,
  `payments` y estado de orden segun corresponda.
- Una reserva incierta debe quedar protegida por `reservation_attempts` y
  estado pendiente para evitar doble envio.
- Una orden bloqueada por regla propia puede quedar en cooldown sin pausar ni
  archivar.

## Reglas para dashboard

- Borrar fisicamente no es una accion inicial; usar archivar/completar.
- No permitir editar directamente estados internos de DB.
- No marcar pagado sin monto.
- No cambiar reglas de una orden reclamada sin validacion backend.
- Mostrar claramente si una orden esta `ready` pero temporalmente bloqueada por
  `next_allowed_at`.
