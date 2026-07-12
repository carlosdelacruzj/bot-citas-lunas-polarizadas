# Contrato de ciclo de vida de ordenes

Este documento describe estados y transiciones que el admin API, CLI, worker y
dashboard deben respetar.

## Estados de `service_orders.status`

- `ready`: orden elegible para monitoreo/reserva.
- `paused`: orden pausada administrativamente o por rechazo de credenciales.
- `reserved_payment_pending`: reserva confirmada, pago pendiente.
- `paid`: cobro registrado.
- `archived`: orden cerrada o excluida de cola.

Solo `ready` puede entrar a una cola operativa. La cola normal del worker
procesa ordenes `ready` sin restricciones de reserva. Las ordenes `ready` con
restricciones no entran a la cola rapida normal y solo entran como seguimiento
cuando una reserva confirmada previa coincide con sus reglas.

El bloque de observadores usa hasta `OBSERVER_ACTIVE_ORDER_LIMIT` ordenes y
prioriza siempre las que no tienen restricciones. Si hay menos observadores
libres que ese limite, completa la rotacion con ordenes restringidas. Una orden
restringida puede detectar disponibilidad, pero antes de resolver CAPTCHA o
enviar la reserva debe cumplir estrictamente `minimum_hour`, `minimum_date` y
`allowed_weekdays`. Si el cupo no cumple, se registra como bloqueado por regla y
no se intenta reservar.

Las prioridades de `0` a `99` solo ordenan las ordenes dentro del comportamiento
normal. Una prioridad `100` o superior activa prioridad de enfoque: esas ordenes
ocupan primero los espacios disponibles del bloque de observadores, incluso si
tienen restricciones. Con dos ordenes enfocadas y limite `2`, solo se revisan
esas dos. Cuando una deja de estar `ready`, la enfocada restante conserva el
primer espacio y el segundo vuelve a completarse con otra orden elegible.
Las promociones automaticas por coincidencia de cupo nunca deben alcanzar `100`;
ese umbral queda reservado para enfoque asignado de forma intencional.

La prioridad de enfoque controla que ordenes ocupan el bloque de observadores,
pero no transfiere cupos entre sesiones. Si el segundo observador detecta un
cupo compatible con su propia regla, debe intentar reservarlo inmediatamente
con su propia cuenta. No debe cambiar a la orden enfocada, porque esa demora
puede hacer que ambos usuarios pierdan el cupo.

## Ordenamiento

La cola normal usa:

```text
priority DESC, created_at ASC
```

Las restricciones por orden se usan para decidir si la orden debe esperar un
cupo compatible y para validar el cupo antes de enviar reserva:

- `minimum_hour`
- `minimum_date`
- `allowed_weekdays`

Una cuenta puede tener varios tramites pendientes. En ese caso la orden
generica puede dividirse en subordenes con:

- `parent_order_id`
- `program_expediente`
- `program_plate`

Cada suborden comparte las credenciales del mismo titular, pero se procesa y se
cierra de forma independiente. Si una suborden tiene expediente o placa objetivo,
el worker debe seleccionar exactamente esa fila del listado de tramites; si no
la encuentra o no esta `PENDIENTE`, debe fallar claro antes de abrir el panel de
citas para evitar reservar el tramite equivocado.

Cuando una reserva queda confirmada (`registered`), el worker busca ordenes
restringidas `ready` que coincidan con la fecha/hora confirmada. Solo esas
ordenes se agregan como seguimiento a la cola rapida. Si ya no encuentran cupo,
permanecen `ready` para esperar otra coincidencia.

La espera entre ordenes dentro de la cola rapida se controla con:

- `QUEUE_DELAY_MIN_SECONDS`
- `QUEUE_DELAY_MAX_SECONDS`

Este delay no controla el monitoreo normal del observer. Solo se aplica entre
ordenes de la cola operativa cuando ya se esta procesando un bloque de usuarios
por disponibilidad, reserva confirmada o barrido rapido.

El observer normal usa sus propios intervalos:

- `OBSERVER_INTERVAL_MIN_SECONDS`
- `OBSERVER_INTERVAL_MAX_SECONDS`
- `CONTINUOUS_INTERVAL_MIN_SECONDS`
- `CONTINUOUS_INTERVAL_MAX_SECONDS`

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
- `service_orders.status` es operativo. La razon administrativa del cierre se
  guarda por separado en `closure_reason`, `closure_note` y `closed_at`.
- Razones de cierre soportadas:
  - `completed_by_us`: reservado por nosotros con cobro.
  - `family_no_charge`: reservado por nosotros sin cobro familiar.
  - `client_withdrew`: cliente retirado.
  - `external_slot`: cupo conseguido por un tercero.
  - `duplicate`: orden duplicada; la nota debe indicar la orden valida cuando
    aplique.
  - `not_serviceable`: caso no gestionable.
- Las razones sin cobro (`family_no_charge`, `client_withdrew`,
  `external_slot`, `duplicate`, `not_serviceable`) deben dejar
  `charge_required=false` y limpiar pagos pendientes.
- Una reserva confirmada debe persistirse junto con `runs`, `reservations`,
  `payments` y estado de orden segun corresponda.
- Las notificaciones de Telegram posteriores a una reserva confirmada son
  diferidas cuando vienen de la cola rapida, para no bloquear el inicio del
  siguiente intento. El mensaje copiable para el cliente debe mantenerse
  separado del mensaje operativo de contacto.
- Una reserva incierta debe quedar protegida por `reservation_attempts` y
  estado pendiente para evitar doble envio.
- Una orden bloqueada por regla propia puede quedar en espera o cooldown sin
  pausar ni archivar.

## Reglas para dashboard

- Borrar fisicamente no es una accion inicial; usar archivar/completar.
- No permitir editar directamente estados internos de DB.
- No marcar pagado sin monto.
- No cambiar reglas de una orden reclamada sin validacion backend.
- Mostrar claramente si una orden esta `ready` pero temporalmente bloqueada por
  `next_allowed_at`.
