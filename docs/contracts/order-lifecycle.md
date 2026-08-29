# Contrato de ciclo de vida de ordenes

Estado: vigente. Ultima verificacion: `2026-08-29`.

Codigo propietario: `core/models.py`, `core/rules.py`, `db/order_*`,
`db/reservations.py` y `services/api/service_order_routes.py`.

## Estados de orden

`service_orders.status` admite:

- `ready`: elegible para la cola;
- `paused`: conservada pero no elegible;
- `reserved_payment_pending`: reserva confirmada y cobro abierto;
- `paid`: servicio cobrado/completado por nosotros;
- `archived`: cierre sin trabajo futuro de la cola.

Solo `ready` puede reclamarse. Backoff, preflight, intento y resultado no son
estados alternativos de esta columna.

## Creacion y preflight

Cada orden persiste contacto, credenciales cifradas, servicio, precio y reglas.
Si requiere preflight nace pausada; solo vuelve a `ready` tras validacion. Un
HTTP `201` prueba persistencia, no activacion.

## Servicio y precio

`service_type` admite `standard`, `selected_weekday` y `custom`.
`reservation_price` debe ser positivo y se conserva por orden. `S/50` es el
default cuando no se especifica; un cambio global no reescribe ordenes creadas.

La reserva copia el precio al pago acordado.

## Restricciones

Reglas positivas:

- `minimum_date` y `maximum_date`;
- `allowed_weekdays`.

Regla negativa: `excluded_date_ranges`.

Las positivas sacan la orden de la cola general y exigen coincidencia; una
exclusion por si sola no la saca, pero siempre se valida antes de CAPTCHA o
submit. Guardar reglas limpia esperas derivadas de restricciones anteriores.

Una fecha incompatible produce `partial / blocked_by_order_rule`, sin backoff
general y sin contar como intento compatible.

## Prioridad y admision

Los niveles especiales son focused `100` y exclusive `200`. Solo una orden puede
mantener prioridad exclusiva; asignar otra degrada la anterior.

El ranking de admision considera prioridad, suborden, compatibilidad de reglas y
antiguedad. El orden de ejecucion dentro del bloque también rota por suborden y
ultima corrida; no debe presentarse como el mismo ranking.

Cuando aparece una oportunidad, cada candidato conserva cuenta, contexto
Playwright, claim y lease independientes. Nunca se transfieren cookies entre
ordenes.

## Claims, intentos y backoff

Una orden reclamada no puede ejecutarse simultaneamente por otro worker. Un
intento `intent`, `pending` o `unknown` bloquea una admision nueva hasta
reconciliarse.

`next_allowed_at` excluye temporalmente una orden `ready`; no cambia su estado.
Resultados de regla no crean backoff global.

## Resultados

Resultados de ejecución:

`available`, `completed`, `error`, `partial`, `paused`, `registered`,
`reservation_unconfirmed`, `skipped`, `unavailable` y `unknown`.

Estados internos como `submission_intent`, `submission_pending` o `programmed`
pertenecen a la evidencia de intento, no al resultado público equivalente.

Una seleccion unica archiva screenshot antes de CAPTCHA o submit. Un submit
ambiguo permanece sin reintento automatico.

## Reserva y pago

Una reserva confirmada deja la orden en `reserved_payment_pending`, salvo flujo
sin cobro. El pago parcial debe ser positivo y menor al acordado; conserva pago
pendiente y no encola postpago.

El pago completo exige la orden pendiente de cobro. Si el monto es menor al
acordado requiere autorizacion y motivo. La transaccion marca pago/orden y
encola postpago durable; no implica entrega WhatsApp.

## Subordenes

Una cuenta con varios tramites se divide mediante `parent_order_id`, expediente
y placa objetivo. Precio, reglas y credenciales se heredan al dividir y el padre
se archiva. Cada suborden mantiene estado, reserva y pago propios.

## Cierre

`closure_reason`, `closure_note` y `closed_at` registran el motivo administrativo
sin reemplazar el estado operativo. Una orden cerrada no regresa a la cola por
editar contacto o por una comunicación pendiente.

## Integraciones posteriores

- WhatsApp: [`whatsapp.md`](whatsapp.md).
- Recordatorios y post-cita: [`../project-status.md`](../project-status.md).
- Seguridad de reserva: [`reservation-safety.md`](reservation-safety.md).

El éxito de una reserva o pago no depende del éxito de WhatsApp. `uncertain` es
terminal para reintento automático.
