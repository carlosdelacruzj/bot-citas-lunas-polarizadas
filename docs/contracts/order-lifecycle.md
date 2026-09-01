# Contrato de ciclo de vida de ordenes

Estado: vigente. Ultima verificacion: `2026-09-01`.

Codigo propietario: `core/models.py`, `core/rules.py`, `db/order_*`,
`db/reservations.py`, `db/service_order_repository.py`, `db/unit_of_work.py`, `db/payment_repository.py`, `services/application/create_service_order.py`,
`services/application/register_payment.py` y
`services/api/service_order_routes.py`.

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

`core/service_packages.py` es la autoridad comercial de claves, etiquetas,
precio fijo, abono inicial, tasa oficial, saldo y compatibilidad. Admin API
expone esa misma definicion en `GET /api/v1/service-packages`; dashboard,
Telegram, previews y avisos no reconstruyen montos por su cuenta.

`service_type` admite `standard`, `selected_weekday` y `custom`.
`reservation_price` debe ser positivo y se conserva por orden. `S/50` es el
default cuando no se especifica; un cambio global no reescribe ordenes creadas.

La reserva copia el precio al pago acordado.

`service_package` separa el paquete comercial de las reglas de busqueda. El
paquete `integral` fija `S/160`, registra un primer abono de `S/80` y conserva
`S/71.40` como tasa oficial pagada por cuenta del cliente. Su alta supone que el
operador ya recibio el abono, pago la tasa y creo la cuenta y solicitud antes de
entregar las credenciales al preflight. Siempre exige `charge_required=true`;
dominio y PostgreSQL rechazan otra combinacion de precio, abono, tasa o tipo.

Repetir exactamente el alta integral es idempotente: reutiliza el pago y los
identificadores deterministas del recibo y costo. Cuando ya existe historia
financiera no se permiten correcciones silenciosas del paquete, precio, tipo o
cobro. Una devolucion o reclasificacion requiere movimientos y auditoria
explicitos antes de habilitar un flujo de correccion.

Combinaciones admitidas para nuevas ordenes:

| Paquete | Precio | `service_type` compatible |
| --- | --- | --- |
| `standard` | fijo `S/50` | `standard` |
| `restricted` | fijo `S/70` | `selected_weekday`, `custom` |
| `integral` | fijo `S/160` | `standard` |
| `custom` | definido por orden | cualquiera vigente |

El paquete describe el acuerdo comercial; las reglas de fecha siguen en
`minimum_date`, `maximum_date`, `allowed_weekdays` y
`excluded_date_ranges`. `selected_weekday` conserva su requisito historico de
un unico dia, mientras `custom` permite reglas mas generales.

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

Una incompatibilidad con seleccion sincronizada, captura canonica previa y cero
intento de reserva puede iniciar inmediatamente una rafaga para otros candidatos
compatibles. Si falta cualquiera de esas barreras, conserva el traspaso
secuencial como fallback.

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
completos. El pago completo debe conservar `amount_agreed=S/160` y acumular
`amount_paid=S/160`; no admite descuento ni cierre directo como completado.

Cada recibo conserva `payment_id` y `order_id`; una FK compuesta garantiza que
ambos pertenecen al mismo pago. PostgreSQL bloquea `UPDATE`, `DELETE` y el
borrado en cascada del pago. Una correccion se representa como una nueva fila
negativa `payment_correction`, referenciada al recibo original del mismo pago y
orden, con motivo y actor. No puede corregir otra correccion ni exceder el monto
original. No existe todavia una accion API para crearla.

El pago completo exige la orden pendiente de cobro. Si el monto es menor al
acordado requiere autorizacion y motivo. La transaccion marca pago/orden y
encola postpago durable; no implica entrega WhatsApp.

Una orden integral no puede convertirse en sin cobro ni archivarse mediante la
accion generica `done`. Un cierre `uncollectible` conserva el abono inicial, el
costo oficial y deja el pago como `written_off`; los cierres que implican
devolucion permanecen bloqueados hasta una correccion contable auditada.
En cualquier paquete, una orden con recibos tampoco puede pasar por un cierre
sin cobro que intente eliminar su pago.

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
