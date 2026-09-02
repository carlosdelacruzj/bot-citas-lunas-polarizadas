# Contrato de recordatorios y seguimiento post-cita

Estado: vigente. Ultima verificacion: `2026-08-30`.

Codigo propietario: `services/appointment_reminders.py`,
`db/appointment_reminders.py`, `services/post_appointment.py` y
`db/post_appointment.py`.

Este contrato separa agenda, recordatorios, revision del portal y comunicacion.
Preparar, encolar, enviar, entregar y leer son hechos distintos.

## Autoridad y propiedad

- PostgreSQL conserva lotes, jobs, revisiones, resultados y frescura.
- Admin API posee ambos schedulers y expone consulta/control autenticado.
- Admin API y su dispatcher son los unicos propietarios del perfil WhatsApp.
- El scheduler post-cita consulta el portal en modo de solo lectura; no reserva,
  no resuelve CAPTCHA y no envia mensajes.
- El texto de `appointment_reminder` pertenece a las plantillas versionadas del
  [`contrato WhatsApp`](whatsapp.md), no al control del scheduler.

## Recordatorios previos a la cita

El control persistido admite:

- `disabled`: registra estado, pero no crea jobs;
- `dry_run`: calcula y muestra candidatos sin encolar;
- `live`: puede crear jobs cuando pasan todas las barreras.

La anticipacion permitida es de `1..3` dias. Cada `service_date` congela su
`appointment_day` al crear el lote. Cambiar la anticipacion despues no mueve el
lote actual ni modifica trabajos existentes; la nueva configuracion aplica
desde el siguiente dia de servicio cuando corresponda.

Antes de encolar se exige:

1. reserva confirmada y fecha normalizada;
2. orden no cerrada por una causa excluyente;
3. destinatario WhatsApp valido;
4. plantilla vigente compatible con la anticipacion;
5. total dentro de `APPOINTMENT_REMINDERS_DAILY_LIMIT`;
6. clave de deduplicacion no creada previamente.

El limite de recordatorios es configurable y su valor predeterminado es `100`;
no es el limite fijo de post-cita. Los jobs pueden quedar bloqueados hasta que
termine el resumen diario de evidencias. Un resumen ausente o activo no autoriza
el envio.

Cada job nuevo congela `service_date`, `appointment_day`, reserva, orden,
destinatario, texto renderizado, clave de plantilla y revision. La identidad del
saludo usa `applicant_name`; `contact_name` no sustituye al asistente.

Los estados tecnicos de WhatsApp y su politica de `uncertain` se rigen por
[`whatsapp.md`](whatsapp.md). Ningun fallo ambiguo autoriza reintento automatico.

## Revision post-cita

El scheduler opera en `America/Lima` desde las `20:00`, revisa como maximo `20`
casos por dia y espera aleatoriamente entre `4` y `7` segundos entre casos.
Mantiene una sola revision activa por orden y usa un lock persistente para no
admitir dos reclamos automaticos equivalentes.

Son elegibles las reservas confirmadas cuya cita ocurrio entre ayer y los
ultimos `30` dias, salvo ordenes cerradas por causas excluyentes. No se revisa
dos veces la misma reserva en el mismo dia. `completed` y `access_lost` son
resultados terminales y salen de la cola automatica.

La sesion de portal usa:

- navegador headless aislado;
- `auto_reserve=false`;
- `MONITOR_WINDOW_SECONDS=0`;
- lectura del expediente y sus etapas;
- cero submit, CAPTCHA o comunicacion.

Resultados de negocio vigentes:

- `review_required`;
- `upcoming`;
- `awaiting_update`;
- `observation_no_progress`;
- `observation_with_progress`;
- `in_progress`;
- `completed`;
- `access_lost`;
- `portal_unavailable`.

La ejecucion automatica registra aparte `running`, `completed`, `failed` o
`skipped`. Tres fallos tecnicos consecutivos del dia abren el breaker y detienen
nuevos reclamos. Una ejecucion interrumpida se cierra como fallo y no se
reintenta automaticamente ese mismo dia.

## Acciones manuales y frescura

La consulta expone filtros, conteos globales, ultima revision, frescura y
siguiente revision automatica. Una revision es `current` solo si corresponde al
dia vigente en Lima; una revision anterior puede mostrarse como `stale` sin
perder su historial.

Las revisiones manuales usan la misma sesion conservadora y no pueden competir
con otra revision activa de la orden. Corregir credenciales, conciliar un envio
o cambiar una orden son acciones separadas y requieren su flujo autorizado.

## API y presentacion

Admin API expone configuracion de recordatorios y seguimiento post-cita. Los
detalles HTTP viven en [`admin-api.md`](admin-api.md). El dashboard puede
paginar, buscar y ordenar, pero no reconstruye autoridad, deduplicacion,
terminalidad ni frescura desde el cliente.

Una preparacion o una tarjeta visible nunca prueba envio, entrega o lectura.
