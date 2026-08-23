# Contrato de ciclo de vida de ordenes

Este documento describe estados y transiciones que el admin API, CLI, worker y
dashboard deben respetar.

## Estados de `service_orders.status`

- `ready`: orden elegible para monitoreo/reserva.
- `paused`: orden pausada administrativamente o por rechazo de credenciales.
- `reserved_payment_pending`: reserva confirmada, pago pendiente.
- `paid`: cobro registrado.
- `archived`: orden cerrada o excluida de cola.

Cada orden conserva `reservation_price` desde su alta. Las órdenes existentes
al migrar a PostgreSQL v42 permanecen en `S/40`; las nuevas nacen en `S/50`.
La reserva confirmada copia ese valor al pago pendiente, por lo que cambiar el
precio general no modifica retroactivamente clientes ya registrados.

Un abono conserva `payments.status=pending` y
`service_orders.status=reserved_payment_pending`; su `amount_paid` es el total
acumulado y debe ser menor que `amount_agreed`. Solo un cierre explicito cambia
ambos estados a `paid` y encola `post_payment_followup`. Un cierre por menos de
lo acordado requiere una diferencia explicita y motivada; nunca se infiere a
partir de un abono.

Solo `ready` puede entrar a una cola operativa. La cola normal del worker
procesa órdenes sin restricciones positivas y también órdenes que únicamente
tienen `excluded_date_ranges`: una exclusión protege fechas concretas, pero no
convierte a la orden en espera de una coincidencia. Las órdenes con fecha
mínima/máxima o días permitidos sí se consideran restringidas y
su propia sesión solo intenta reservar cuando el cupo cumple esas reglas.

El bloque de observadores usa hasta `OBSERVER_ACTIVE_ORDER_LIMIT` órdenes. La
selección respeta prioridad, segundos trámites, menor penalización por
restricciones y antigüedad;
dentro del bloque se ejecuta primero quien lleva más tiempo sin revisión.
Antes de resolver CAPTCHA o enviar la reserva, cualquier orden debe cumplir
`minimum_date`, `maximum_date`, `allowed_weekdays` y
`excluded_date_ranges`. Los límites de cada exclusión son inclusivos. Si el
cupo incumple cualquier regla o cae dentro de un rango excluido, se registra
como bloqueado por regla y no se intenta reservar.
El horario no participa en compatibilidad: para la fecha permitida más próxima
se usa el horario visible más temprano.

Las prioridades de `0` a `99` solo ordenan las ordenes dentro del comportamiento
normal. Las prioridades de `100` a `199` activan prioridad de enfoque: esas
ordenes ocupan primero los espacios disponibles del bloque, incluso si tienen
restricciones. Con dos ordenes enfocadas y limite `2`, se rotan esas dos. Cuando
una deja de estar `ready`, la enfocada restante conserva el primer espacio y el
segundo vuelve a completarse con otra orden elegible.
La prioridad solo cambia por una accion explicita del operador desde dashboard,
API o Telegram. El worker no aumenta automaticamente la prioridad despues de
una reserva ni por coincidencia de fecha u hora.

Una prioridad `200` o superior activa el enfoque exclusivo. Mientras esa orden
este `ready` y sea elegible, `list_observer_orders()` devuelve solo esa orden,
sin importar `OBSERVER_ACTIVE_ORDER_LIMIT`. Al asignar el modo exclusivo, otro
exclusivo previo vuelve a prioridad `100` y se limpia la espera pendiente de la
nueva orden. Si una fecha se descarta por sus reglas, la orden permanece
elegible sin un cooldown temporal, sea normal, enfocada o exclusiva. Esto no
crea navegadores ni
workers paralelos: el worker existente repite sus sesiones de forma secuencial
sobre la misma orden.

La prioridad de enfoque controla que ordenes ocupan el bloque de observacion,
pero no transfiere cupos entre sesiones. Si el segundo observador detecta un
cupo compatible con su propia regla, debe intentar reservarlo inmediatamente
con su propia cuenta. No debe cambiar a la orden enfocada, porque esa demora
puede hacer que ambos usuarios pierdan el cupo. Esto tambien aplica si durante
la sesion aparece una orden con prioridad `200`: el enfoque exclusivo modifica
la siguiente seleccion de observadores, pero no cancela ni difiere una reserva
compatible que ya fue detectada por otra sesion.

## Ordenamiento

La cola normal usa:

```text
priority DESC, created_at ASC
```

Las restricciones positivas que deciden si una orden debe esperar un cupo
compatible son:

- `minimum_date`
- `maximum_date`
- `allowed_weekdays`

`excluded_date_ranges` es una protección negativa: no saca por sí sola a la
orden de la cola normal, pero siempre se valida antes del CAPTCHA y del envío.

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

Cada selección conserva en `selection_observation` las combinaciones fecha/hora
realmente leídas. Si la sesión actual encuentra una opción compatible, reserva
de inmediato y no recorre fechas adicionales solo para completar el inventario.
Si queda bloqueada por reglas, conserva todas las combinaciones encontradas en
el recorrido ya necesario.

Desde el canario del `2026-08-11`, `selection_observation` conserva además el
modo de estabilización (`event_atomic`, `legacy_fallback` o `legacy`), espera de
señal, causa/duración de fallback y cantidad de snapshots atómicos. Estos campos
son telemetría: no cambian las reglas de compatibilidad ni autorizan un submit.

Después de una detección, la cadena de oportunidades evalúa tanto órdenes
abiertas como restringidas. Solo excluye a quien no sea compatible con ninguna
fecha observada. El orden es:

1. prioridad manual exclusiva (`>=200`);
2. segundos trámites (`parent_order_id` presente);
3. mayor cantidad de combinaciones compatibles;
4. menor complejidad de restricciones;
5. prioridad manual restante y antigüedad.

La cadena es secuencial y conserva contexto, cookies y lease independientes por
orden. Intenta como máximo `OPPORTUNITY_HANDOFF_MAX_CANDIDATES` clientes durante
`OPPORTUNITY_HANDOFF_MAX_SECONDS`; los valores por defecto son `10` y `300`.
Continúa después de cada reserva confirmada y termina si un cliente confirma que
los cupos desaparecieron, vence la ventana, se agotan candidatos o surge un
resultado ambiguo. Cada nueva sesión vuelve a leer el portal: las oportunidades
son evidencia temporal, no inventario garantizado ni transferencia directa.

Con `OPPORTUNITY_BURST_ENABLED=true`, una selección completa del detector abre
una ráfaga antes de esa cadena: el detector continúa y se inicia un auxiliar
compatible, priorizando la otra orden del bloque activo. Hay como máximo dos
sesiones simultáneas. Cada `registered` confirmado libera una posición para el
siguiente compatible; con `OPPORTUNITY_BURST_MAX_CLIENTS=0` se puede recorrer
toda la fotografía inicial de la cola durante un máximo de 300 segundos. Un
resultado sin cupos cierra esa sesión; una defensa, error técnico o
`reservation_unconfirmed` detiene reemplazos nuevos sin repetir submits
ambiguos. Cuando la ráfaga termina, no repite los mismos cupos en la cadena
secuencial y vuelve al observer normal. Con la bandera en `false`, este bloque
no reclama candidatos y se conserva el comportamiento secuencial anterior.

El muestreo CAPTCHA adicional solo corresponde a la sesión detectora. Toda
sesión posterior de la cadena fuerza una sola muestra antes de 2Captcha para no
multiplicar la demora de entrenamiento en el camino crítico.

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
- Al agotarse normalmente la cola rapida, el worker revisa en sesiones nuevas las
  ordenes confirmadas en ese ciclo y actualiza su evidencia con la vista de nombres
  y `Separa Cita Peritaje: Programado`. Esa captura reemplaza la imagen de la
  notificacion diferida de Telegram; si la revision falla, se conserva la captura
  original como respaldo. Es posprocesamiento: nunca se ejecuta entre intentos ni
  cuando la cola se detuvo por pausa, limite, incertidumbre o error.
- WhatsApp es un flujo automatico durable posterior a la reserva y no forma
  parte del camino critico de reserva. Solo una reserva `confirmed` con orden
  `reserved_payment_pending`, pago pendiente, monto, contacto internacional y
  constancia segura puede encolar confirmacion y cobro.
- `whatsapp_automation_jobs` gobierna `queued`, `blocked`, `running`, `sent`,
  `failed` y `uncertain`. Un `sent` exige evidencia segura; una entrega ambigua
  queda `uncertain` y nunca se reintenta automaticamente. Ese estado no marca
  el pago como cobrado. Los paquetes `test_mode=true` no cambian ordenes,
  reservas ni pagos.
- La bandeja operativa no considera pendiente a toda orden pagada. El estado
  accionable combina evidencia real `sent` y el trabajo durable de
  `whatsapp_automation_jobs`:
  - cualquier envio real confirmado prevalece sobre un fallo anterior;
  - `queued`, `blocked` y `running` siguen bajo responsabilidad automatica;
  - solo `failed` o `uncertain` sin evidencia posterior requieren revision;
  - una orden historica sin trabajo automatico queda `not_applicable` para la
    bandeja, sin borrar sus paquetes ni enviar mensajes retroactivos.
- Un resultado `uncertain` solo abre la orden para revision; nunca ofrece un
  reintento directo desde la bandeja.
- Los recordatorios de cita se derivan exclusivamente de la reserva
  `confirmed` mas reciente de cada orden y de `reservations.appointment_day`.
  El destinatario procede del contacto administrativo primario; nunca de
  credenciales, formularios del portal ni campos honeypot.
- Cada recordatorio usa la clave durable
  `appointment_reminder:{reservation_id}:{appointment_day}`. Una reconciliacion
  repetida no crea duplicados y el texto queda persistido antes del intento.
- El recordatorio se guarda `blocked` y no puede reclamarse hasta que exista el
  `daily_slot_summary` de la misma fecha operativa y ninguno de sus intentos
  permanezca `queued`, `blocked` o `running`. El resumen diario conserva
  prioridad `0`; los recordatorios usan prioridad `100`.
- La autoridad operativa reside en `appointment_reminder_control`: `disabled`
  no crea ni permite reclamar trabajos, `dry_run` solo calcula, `canary` limita
  la admision a 1 o 2 `order_id` elegibles y `live` admite todos dentro del
  limite diario. Cada cambio usa revision optimista y conserva la plantilla en
  `appointment_reminder_template_versions`.
- Solo se aceptan `{nombre}`, `{fecha}`, `{hora}` y `{sede}`; `{fecha}` es
  obligatoria y los datos ausentes se renderizan como `por confirmar`.
  `{nombre}` corresponde exclusivamente a `applicants.full_name`, es decir, la
  persona que asistira al peritaje; nunca usa el nombre administrativo del
  contacto de WhatsApp. Si el nombre del solicitante falta, se usa `cliente`.
  La API entrega tambien la etiqueta de fecha renderizada para que la vista
  previa coincida literalmente con el mensaje final.
- `GET /api/v1/appointment-reminders` expone tambien los candidatos vigentes
  para la vista interna de Seguimiento. El detalle limita cada fila a nombre,
  orden, fecha, hora, sede, destinatario enmascarado y estado; no publica el
  contacto completo ni credenciales.
- Despues del claim se revalidan fecha Lima, reserva vigente y contacto. Un
  trabajo obsoleto termina `skipped` antes de abrir el chat. Si el intento llega
  al envio, conserva la misma semantica estricta: `sent` exige evidencia de una
  burbuja saliente, mientras `uncertain` es terminal y no se reintenta.
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
