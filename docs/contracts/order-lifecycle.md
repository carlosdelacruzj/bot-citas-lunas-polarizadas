# Contrato de ciclo de vida de ordenes

Estado: vigente. Ultima verificacion: `2026-08-31`.

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

`service_package` separa el paquete comercial de las reglas de busqueda. El
paquete `integral` fija `S/160`, registra un primer abono de `S/80` y conserva
`S/71.40` como tasa oficial pagada por cuenta del cliente. Su alta supone que el
operador ya recibio el abono, pago la tasa y creo la cuenta y solicitud antes de
entregar las credenciales al preflight.

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

Un traspaso secuencial solo nace cuando la orden observada queda
`blocked_by_order_rule`. Una reserva confirmada no transfiere su oportunidad:
continua por la cola general si corresponde. Entre candidatos compatibles con
una oportunidad bloqueada o una rafaga, se atiende primero a quien acepta menos
de las oportunidades observadas y posee reglas mas restrictivas; prioridad y
antiguedad desempatan despues, salvo prioridad exclusiva.

Si el traspaso recorrio al menos un candidato compatible, la orden restringida
que lo origino se revisa una vez mas al final de esa misma ventana. Si entretanto
aparece una fecha valida puede reservarla; si sigue siendo incompatible conserva
`ready` y no recibe backoff.

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

Los cobros se conservan adicionalmente como movimientos inmutables en
`payment_receipts`; `payments.amount_paid` sigue siendo el total acumulado. En
el paquete integral, la reserva solicita el saldo de `S/80`, no los `S/160`
completos.

El pago completo exige la orden pendiente de cobro. Si el monto es menor al
acordado requiere autorizacion y motivo. La transaccion marca pago/orden y
encola postpago durable; no implica entrega WhatsApp.

## Subordenes

Los estados historicos no determinan multiplicidad: solo las filas
`PENDIENTE` son reservables. Una fila pendiente junto con filas canceladas o
atendidas conserva el flujo normal. Cero pendientes bloquea; mas de una exige
una decision interna antes de seleccionar, CAPTCHA o submit.

La decision se aplica contra la revision exacta del listado observado. Resolver
uno exige expediente exacto o una placa que identifique una sola fila pendiente.
Resolver todos crea atomicamente una suborden por expediente mediante
`parent_order_id` y archiva el padre. Cada suborden mantiene objetivo, reglas,
reserva, evidencia y estado propios.

Precio y condiciones no se multiplican implicitamente. El operador debe
confirmar las mismas condiciones para todos o definir servicio, reglas, precio y
`charge_required` por hijo. Una orden integral o con historia financiera falla
cerrado al dividir hasta que exista una regla explicita de asignacion contable.
Repetir la misma decision es idempotente; una revision obsoleta produce
conflicto y obliga a actualizar.

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
