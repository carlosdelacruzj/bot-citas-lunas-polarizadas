# Contrato admin API

Este documento describe el contrato administrativo actual y las reglas para el
dashboard. El contrato vive tanto en la API local embebida por el worker como en
el proceso separado `appointment-bot-admin-api` mientras se completa la
migracion.

## Procesos

- API embebida del worker: `127.0.0.1:8765` por defecto.
- Admin API separado: `127.0.0.1:8766` por defecto.

El admin API separado reutiliza servicios PostgreSQL actuales y no tiene una
referencia en memoria a `ContinuousWorker`.

## Autenticacion

- `/health` puede ser publico.
- Todo endpoint bajo `/api/v1/` debe tratarse como administrativo.
- Las llamadas administrativas deben enviar
  `Authorization: Bearer <APPOINTMENT_BOT_API_TOKEN>`.
- En desarrollo local, `dashboard/proxy.conf.cjs` agrega ese header desde
  `.env` o desde la variable de entorno. El token no debe existir en Angular,
  campos visibles, bundle, `localStorage` ni `sessionStorage`.

## Endpoints actuales

La lista siguiente documenta las rutas nucleares, no un inventario exhaustivo.
Para comprobar el contrato desplegado se debe contrastar el router en
`src/appointment_bot/api/` y la respuesta del proceso activo; toda ruta nueva
debe incorporarse aqui cuando cambie una capacidad publica del dashboard.

```text
GET  /api/v1/worker
GET  /api/v1/service-orders
GET  /api/v1/operator-inbox
GET  /api/v1/service-orders/{order_id}
GET  /api/v1/monthly-summary?month=YYYY-MM
GET  /api/v2/monthly-summary?month=YYYY-MM
GET  /api/v1/post-appointment-followups
POST /api/v1/service-orders
POST /api/v1/service-orders/{order_id}/validate
POST /api/v1/service-orders/{order_id}/contact
POST /api/v1/service-orders/{order_id}/credentials
POST /api/v1/service-orders/{order_id}/priority
POST /api/v1/service-orders/{order_id}/restrictions
POST /api/v1/service-orders/{order_id}/payment/paid
POST /api/v1/service-orders/{order_id}/payment/partial
POST /api/v1/service-orders/{order_id}/whatsapp/prepare
POST /api/v1/whatsapp-messages/test/prepare
GET  /api/v1/whatsapp-messages/{message_id}/attachment
GET  /api/v1/whatsapp-messages/{message_id}/payment-attachment
POST /api/v1/whatsapp-messages/{message_id}/web/prepare
POST /api/v1/whatsapp-messages/{message_id}/sent
POST /api/v1/service-orders/{order_id}/whatsapp-followup/prepare
POST /api/v1/whatsapp-followup-messages/test/prepare
GET  /api/v1/whatsapp-followup-messages/{message_id}/attachments/{step}/{attachment}
POST /api/v1/whatsapp-followup-messages/{message_id}/web/prepare
POST /api/v1/whatsapp-followup-messages/{message_id}/sent
POST /api/v1/service-orders/{order_id}/pause
POST /api/v1/service-orders/{order_id}/activate
POST /api/v1/service-orders/{order_id}/done
POST /api/v1/service-orders/{order_id}/no-charge
POST /api/v1/service-orders/{order_id}/close
POST /api/v1/service-orders/{order_id}/split-programs
POST /api/v1/service-orders/{order_id}/post-appointment/review
GET  /api/v1/runs
GET  /api/v1/runs/{run_id}
GET  /api/v1/worker/commands
POST /api/v1/worker/pause
POST /api/v1/worker/resume
POST /api/v1/worker/restart
GET  /api/v1/runtime-controls/opportunity
POST /api/v1/runtime-controls/opportunity
GET  /api/v1/runtime-controls/captcha-authority
POST /api/v1/runtime-controls/captcha-authority
GET  /api/v1/opportunity-bursts?limit=20&status=closed
GET  /api/v1/opportunity-bursts/{burst_id}
GET  /api/v1/manual-sessions
POST /api/v1/manual-session/open
POST /api/v1/manual-session/close
```

En `appointment-bot-admin-api`, los endpoints `worker/pause`, `worker/resume` y
`worker/restart` encolan comandos persistidos en `worker_commands`. La API
embebida del worker mantiene control directo por compatibilidad.

## Control de autoridad CAPTCHA

`GET /api/v1/runtime-controls/captcha-authority` devuelve el modo efectivo,
límite y contadores de la cohorte, decisiones restantes, umbrales, timeout,
estado/causa del circuito y actor de la última mutación. No devuelve respuestas
CAPTCHA ni credenciales.

`POST /api/v1/runtime-controls/captcha-authority` acepta el estado completo o
los valores vigentes omitidos, salvo `mode`, que es obligatorio:

```json
{
  "mode": "canary",
  "canary_limit": 20,
  "min_char_confidence": 0.60,
  "sequence_confidence_product": 0.60,
  "timeout_ms": 500,
  "reset_circuit": false,
  "reset_counters": false
}
```

`mode=2captcha` es el rollback inmediato. `reset_circuit=true` exige una
revisión operativa previa de la causa. `reset_counters=true` inicia una cohorte
nueva sin borrar `captcha_authority_decisions`; no debe usarse para ocultar un
rechazo. Los cambios aplican desde el siguiente CAPTCHA y no requieren editar
`.env` ni reiniciar el worker.

## Control de OBS-006 y OBS-007

`GET /api/v1/runtime-controls/opportunity` devuelve la revision, fuente del
estado, modo deseado y efectivo de OBS-006/OBS-007, admision, breaker y rafaga
activa. `inherit` significa que la bandera de entorno vigente sigue siendo la
fuente efectiva; `enabled`, `disabled` y `draining` hacen que PostgreSQL sea la
autoridad.

`POST /api/v1/runtime-controls/opportunity` exige actor autenticado, motivo y
proteccion contra acciones obsoletas:

```json
{
  "action": "drain",
  "target": "obs006",
  "reason": "rollback del canario",
  "expected_revision": 3
}
```

Las acciones son `activate`, `deactivate`, `drain` y `reset_breaker`. El
drenaje solo aplica a OBS-006 y solo cuando existe una rafaga activa. Una
revision desactualizada, activar con breaker abierto, desactivar una rafaga sin
drenarla o resetear un breaker ya cerrado devuelve `409 Conflict`. Activar o
reiniciar procesos nunca resetea el breaker implicitamente.

`GET /api/v1/opportunity-bursts` acepta `limit=1..100` y el filtro opcional
`status=running|draining|closed|aborted`. El detalle incluye candidatos,
ejecuciones y eventos OBS-007 sanitizados. No expone credenciales, contactos,
cookies, owner tokens ni `RunReport.details` crudo.

## Seguimiento post-cita

`GET /api/v1/post-appointment-followups` devuelve todas las órdenes con una
reserva confirmada, su cita, el último resultado post-cita y una instantánea de
etapas. Documento y contactos permanecen enmascarados. Cada elemento incluye
`parent_order_id`, `program_expediente` y `program_plate` para distinguir los
trámites de una misma cuenta. El payload incluye totales de casos que requieren
atención, accesos perdidos y trámites con avance o cierre.

`POST /api/v1/service-orders/{order_id}/post-appointment/review` realiza una
consulta sin cuerpo y de solo lectura. Exige una reserva confirmada, rechaza una
segunda revisión concurrente de la misma orden y abre un contexto Playwright
aislado. No pulsa reservar, no selecciona sede, no resuelve CAPTCHA y no envía
mensajes.

La API persiste y devuelve `message_text` exactamente como fue leído de la
columna `Mensaje`, además de `message_present` y `message_class` (`none`, `ok`,
`observation` o `unknown`). Este endpoint es interno y requiere autenticación
administrativa. Un rechazo de credenciales se informa como
`access_lost`; un fallo técnico se mantiene separado como `portal_unavailable`.

## Resumen mensual

`GET /api/v1/monthly-summary?month=YYYY-MM` calcula el resumen en
`America/Lima`:

- ingresos cobrados y cantidad de pagos por `payments.paid_at`;
- reservas confirmadas por `reservations.reserved_at`;
- órdenes creadas y conversión de su cohorte por `service_orders.created_at`;
- ticket promedio, comparación de ingresos con el mes anterior e ingresos por
  día;
- actividad por fuente de contacto;
- estado actual separado: órdenes activas, reservas pendientes de cobro,
  importe pendiente, contactos faltantes y órdenes activas con más de siete
  días.

El ingreso cobrado nunca incluye pagos pendientes ni proyecciones. La respuesta
no expone documentos, WhatsApp, credenciales ni evidencia cruda.

`GET /api/v2/monthly-summary?month=YYYY-MM` es el contrato comercial vigente
para decisiones. Mantiene el endpoint v1 como rollback y separa:

- `period_metrics`: eventos ocurridos dentro del periodo, con cobertura, corte
  y `daily_revenue` para la evolución gráfica de cobros;
- `cohort_metrics`: órdenes creadas en el mes y su conversión posterior, con
  numerador y denominador;
- `current_attention_snapshot`: pendientes actuales con `as_of`, sin
  convertirlos en historia del mes seleccionado;
- MTD contra los mismos días del mes anterior y, por separado, mes cerrado
  contra mes cerrado.

Un contacto operativo es válido si tiene teléfono o nombre de usuario de
WhatsApp. La fuente de captación se conserva en `service_orders`; los valores
copiados durante la migración histórica se identifican como backfill y no se
presentan como prueba del origen original.

## Detalles de endpoints administrativos

`GET /api/v1/worker/commands` debe devolver una lista resumida y segura de
comandos recientes:

- `command_id`
- `command`
- `status`
- `requested_at`
- `claimed_at`
- `processed_at`
- `error_message`

No devuelve `worker_owner_token`.

`POST /api/v1/service-orders/{order_id}/split-programs` reutiliza la misma
logica que el CLI `order-split-programs`. La respuesta indica las subordenes
creadas y si la orden padre quedo archivada. Angular pide confirmacion visible
porque cambia la cola operativa.

## Datos de orden

La lista de ordenes debe exponer solo datos publicos o enmascarados:

- `order_id`
- `applicant_id`
- `applicant_name`
- `document_number_masked`
- `contact_name`
- `contact_source`
- `contact_whatsapp_masked`
- prioridad, cobro, estado, reserva y pago
- `whatsapp_message_status`, `whatsapp_message_sent_at`
- `whatsapp_message_action_state`
- `whatsapp_followup_status`, `whatsapp_followup_sent_at`
- `whatsapp_followup_action_state`
- `parent_order_id`, `program_expediente`, `program_plate`
- reglas de reserva
- timestamps

No debe exponer password, documento/WhatsApp completos, datos de cifrado ni
leases.

`GET /api/v1/service-orders/{order_id}` es el detalle administrativo explicito.
Requiere bearer token estricto y usa una allowlist separada. Puede agregar
`document_number` y `contact_whatsapp` completos para editar la orden elegida,
pero nunca password, datos de cifrado, cookies ni leases. El dashboard solo
consulta este endpoint al abrir la edicion y descarta el detalle al cerrarla.

`POST /api/v1/service-orders/{order_id}/priority` acepta un entero no negativo:

```json
{ "priority": 100 }
```

Los valores `0` a `99` ordenan la cola normal; `100` o más activan enfoque.

`POST /api/v1/service-orders/{order_id}/credentials` reemplaza el acceso de una
orden activa o pausada:

```json
{
  "document_number": "74037811",
  "document_type": "dni",
  "password": "nueva-clave"
}
```

La respuesta nunca devuelve la contraseña. La operación conserva el
`order_id`, contacto, pagos e historial; rechaza documentos asociados a otra
cuenta y no se ejecuta mientras alguna orden de la cuenta tenga un lease vivo.
Todas las órdenes activas que compartan la cuenta quedan pausadas, sin el error
operativo anterior y con `preflight_status=pending`. El API programa una nueva
validación para cada una y solo `mark_order_preflight_validated` las devuelve a
`ready`. El frontend mantiene la nueva contraseña únicamente en memoria hasta
enviarla y pide confirmación sin incluirla en mensajes o logs.

`POST /api/v1/service-orders/{order_id}/restrictions` reemplaza el conjunto de
restricciones de reserva de una orden:

```json
{
  "minimum_reservation_date": "2026-08-01",
  "maximum_reservation_date": "2026-08-31",
  "allowed_weekdays": [1, 3, 6],
  "excluded_date_ranges": [
    { "start_date": "2026-08-10", "end_date": "2026-08-20" }
  ]
}
```

Cada campo acepta `null` para quitar esa restricción. La fecha máxima es
inclusiva y no puede ser anterior a la mínima; los días usan numeración ISO de
`1=lunes` a `7=domingo`. Al guardar se limpia `next_allowed_at` para que una
restricción corregida no quede bloqueada por una espera calculada previamente.
`excluded_date_ranges` acepta una lista de rangos inclusivos; cada elemento
requiere `start_date` y `end_date`. Una fecha dentro de cualquiera de esos
periodos se rechaza aunque cumpla los demás límites. Los rangos superpuestos se
ordenan y consolidan antes de persistirlos; una lista vacía quita las exclusiones.
Una orden que solo tenga `excluded_date_ranges` conserva el tratamiento de cola
normal. Solo `minimum_reservation_date`, `maximum_reservation_date` o
`allowed_weekdays` la clasifican como restringida
para esperar una coincidencia. La exclusión se valida siempre antes del CAPTCHA
y del envío de reserva.
`minimum_reservation_hour` permanece únicamente como campo histórico de salida;
en creación o edición cualquier valor no vacío devuelve HTTP `400`. El horario
visible nunca bloquea una fecha autorizada.
La actualización se usa en la siguiente selección de la cola y no interrumpe
una sesión que ya está ejecutándose. Cada orden se actualiza por separado,
aunque varias compartan el mismo contacto.

Snapshots, filtros, tablas y copiado general deben trabajar exclusivamente con
el DTO enmascarado del listado.

La tarjeta operativa de la orden seleccionada puede mostrar el WhatsApp completo
obtenido mediante el endpoint de detalle. Debe conservarlo solo en memoria,
descartarlo al cambiar la orden o recargar la aplicación y evitar incluirlo en snapshots o
copias masivas.

La sesión manual debe construir su configuración con `username`, `password` y
`document_type` de la orden. No puede depender del tipo global ni del valor por
defecto `dni`; una orden con `foreign_resident_card` debe seleccionar Carné de
Extranjería antes de enviar el formulario del portal.

## Crear orden

`POST /api/v1/service-orders` acepta:

- `document_number`: obligatorio; usuario o documento del cliente.
- `document_type`: obligatorio; `dni` o `foreign_resident_card`. El portal usa
  respectivamente las opciones DNI y Carné de Extranjería.
- `password`: obligatorio.
- `contact_name`: obligatorio; persona que contacto al negocio.
- `contact_source`: obligatorio; `tiktok`, `facebook` o `whatsapp`.
- `contact_whatsapp`: opcional.

El alta no habilita inmediatamente la orden. Se guarda con `status=paused` y
`preflight_status=pending`, y el API inicia una validacion en segundo plano con
una sesion Playwright exclusiva. La validacion:

1. comprueba tipo de documento, usuario y contrasena en el portal;
2. sustituye `applicant_name` por el nombre real mostrado por el portal;
3. obtiene y conserva el listado de tramites;
4. exige al menos un tramite con estado `PENDIENTE`;
5. cambia la orden a `ready` solo si todo lo anterior termina correctamente.

Si falla, la orden permanece pausada con `preflight_status=failed`,
`preflight_message` y evidencia visual en `screenshots/preflight/`. El operador
puede corregir el acceso mediante
`POST /api/v1/service-orders/{order_id}/credentials`; esa operación inicia la
nueva validación automáticamente. Mientras el estado sea
`pending`, `running` o `failed`, el endpoint de activacion rechaza la orden.

`GET /api/v1/service-orders` y el detalle incluyen `preflight_status`,
`preflight_message`, `preflight_started_at`, `preflight_validated_at` y
`preflight_details`. Las ordenes creadas antes de este contrato conservan
`preflight_status=not_required` para no alterar la cola historica.

Las fuentes permitidas viven en `core/contacts.py`: `tiktok`, `facebook` y
`whatsapp`. API, DB y CLI usan esa misma lista. La fuente se normaliza a
minusculas, el nombre colapsa espacios repetidos y WhatsApp conserva solo un
`+` inicial y digitos. No se agrega codigo de pais ni se inventan datos.

Los errores de entrada pueden incluir:

```json
{
  "status": "bad_request",
  "message": "...",
  "field_errors": {
    "contact_source": "..."
  }
}
```

El dashboard traduce esos nombres tecnicos a las etiquetas visibles del
formulario.

El menú principal no muestra totales de listados ni resultados filtrados. Los
conteos pertenecen al contenido de cada sección, evitando que una búsqueda o un
filtro cambie el significado de la navegación. La tabla de órdenes pagina los
resultados localmente con 20 filas por defecto y permite 10, 20 o 50. Conserva
filtro rápido, orden, dirección, tamaño y página en el navegador; la búsqueda
libre usa almacenamiento de sesión para no persistir nombres o documentos.

Los valores de estado del API permanecen estables y técnicos. El dashboard los
traduce con un catálogo central de etiqueta y tono; no debe imprimir estados
crudos como `ready`, `archived` o `reservation_unconfirmed`. Los cambios
correctos se notifican con un toast breve, sin dejar un segundo mensaje fijo en
la pantalla. Los errores globales visibles se cierran automáticamente tras ocho
segundos y una confirmación crítica puede seguir usando un diálogo explícito.

Todas las fechas visibles usan `DD-MM-YYYY`. Las fechas con hora usan
`DD-MM-YYYY HH:mm:ss` en `America/Lima`. Este estándar es solo de presentación:
API, PostgreSQL y controles HTML de fecha conservan `YYYY-MM-DD` o ISO 8601 para
evitar ambigüedades. El formateador común debe normalizar tanto datos históricos
`DD/MM/YYYY` como fechas ISO antes de mostrarlos; ninguna tabla debe imprimir el
valor crudo recibido del API.

El alta normal del dashboard solo presenta esos datos y las restricciones de
fecha opcionales. Los siguientes campos siguen disponibles en el contrato para
flujos administrativos avanzados, pero no se solicitan al crear un cliente:

- `priority`
- `applicant_name`
- `charge_required`
- `minimum_reservation_date`
- `maximum_reservation_date`
- `allowed_weekdays`
- `excluded_date_ranges`
- `parent_order_id`
- `program_expediente`
- `program_plate`

La respuesta no debe devolver password. El frontend no debe persistir el valor
del password despues de enviarlo.

Si no se envian `minimum_reservation_date`, `maximum_reservation_date`,
`allowed_weekdays` ni `excluded_date_ranges`, la orden se
crea sin restriccion de fecha. El dashboard no debe inventar restricciones.

## Subordenes y restricciones en Angular

El dashboard debe mostrar y permitir crear/editar con cuidado los datos que ya
forman parte del contrato:

- `parent_order_id`: identifica la orden generica de la misma cuenta.
- `program_expediente`: expediente objetivo de una suborden.
- `program_plate`: placa objetivo de una suborden.
- `closure_reason`: razon administrativa del cierre.
- `closure_note`: nota corta de cierre, por ejemplo la orden valida de un
  duplicado.
- `closed_at`: timestamp en que la orden dejo de estar activa.
- `minimum_reservation_date`: fecha minima aceptable.
- `maximum_reservation_date`: fecha maxima aceptable, inclusive; no puede ser
  anterior a `minimum_reservation_date`.
- `allowed_weekdays`: dias ISO permitidos, `1=lunes` a `7=domingo`.
- `excluded_date_ranges`: periodos inclusivos que el bot debe ignorar aunque el
  resto de las reglas permita la fecha.

Cada suborden debe tratarse como trabajo independiente para pausa, activacion,
pago, reporte, sesion manual y cierre. Aunque comparta credenciales con la orden
padre, no debe mezclarse su estado de reserva ni su estado de pago.

Cuando el usuario cree una orden sin restricciones, Angular debe omitir estos
campos o enviarlos como `null`. No debe inventar restricciones por defecto.
En la edición, Angular permite agregar varios rangos como etiquetas removibles.
Si el operador completa un único rango y guarda sin pulsar `Agregar otro rango`,
el rango pendiente también forma parte de la actualización.

El editor reutilizable presenta los días ISO como botones de lunes a domingo y
ofrece presets visuales. Estos presets no crean reglas nuevas en el backend:
solo traducen la elección del operador a los mismos campos del contrato. En
particular, `Cualquier fecha` limpia las restricciones de fecha y `Solo sábados`
envía `allowed_weekdays=[6]`; ninguna selección se persiste antes de confirmar
el guardado del formulario.

## Acciones administrativas

### Política de lectura del dashboard

El dashboard consulta los mismos endpoints sin cambiar su contrato, pero usa
una cadencia acorde al tipo de información. Las lecturas son cancelables: una
navegación o filtro nuevo desuscribe la solicitud anterior y una cancelación no
se presenta como error. La pestaña oculta no realiza polling y, al volver, solo
consulta si la última actualización de esa vista ya venció.

La política mantiene un contexto preparado para incorporar en el futuro
`updated_since` o cursores. Los endpoints actuales siguen devolviendo snapshots
completos; no se anuncia todavía una actualización incremental que el backend
no soporte.

- `pause` y `activate` cambian elegibilidad operativa.
- `done` archiva/completa una orden.
- `no-charge` marca una orden sin cobro.
- `close` archiva/cierra una orden con `closure_reason` y `closure_note`.
- `payment/paid` cierra el cobro y encola el postpago en la misma transaccion.
  Exige `amount_paid >= amount_agreed`; una diferencia inferior solo se acepta
  con `allow_difference=true` y `difference_reason` no vacio.
- `payment/partial` registra el total acumulado abonado, que debe permanecer por
  debajo de `amount_agreed`; conserva pago y orden pendientes y nunca encola
  postpago.
- Ambos endpoints aceptan la fotografia opcional
  `expected_payment_status`, `expected_amount_agreed` y
  `expected_amount_paid`; si ya cambio, responden `409 Conflict`. La escritura
  financiera y su auditoria con `X-Appointment-Actor` comparten transaccion.
- `whatsapp/prepare` crea una copia inmutable del saludo, constancia principal y
  cobro para una reserva confirmada; no envia nada por si mismo.
- `worker/restart` solicita reinicio controlado del worker.
- `manual-session/open` abre una sesion Playwright visible y local para una
  orden seleccionada cuando `MANUAL_SESSION_ENABLED=true`.
- Las acciones piden confirmacion visible en el dashboard y muestran respuesta
  clara del backend.
- El formulario de creacion envia el password solo en el POST; no debe quedar
  persistido en storage del navegador.

## WhatsApp asistido sin API de Meta

`POST /api/v1/whatsapp-messages/test/prepare` recibe `recipient_phone` en formato
internacional con `+` y crea un paquete ficticio. No referencia ni modifica una
orden real. Devuelve confirmacion, cobro de prueba, enlace `wa.me` y las URL
autenticadas de la constancia y la imagen de pago.

`POST /api/v1/service-orders/{order_id}/whatsapp/prepare` solo acepta una orden
`reserved_payment_pending` con reserva `confirmed`, pago `pending`, monto acordado,
cobro habilitado, contacto internacional y una constancia PNG segura. Si ya existe
un envio confirmado, exige `{"allow_resend": true}` para preparar otra copia.

Los endpoints `attachment` y `payment-attachment` entregan solamente las copias
preparadas en `screenshots/whatsapp-outgoing/`, requieren autenticacion estricta y
usan `Cache-Control: no-store`. El endpoint `sent` registra la confirmacion manual;
abrir `wa.me`, copiar texto o descargar la imagen no cambia el estado ni el pago.
El listado de ordenes expone el estado del paquete y
`whatsapp_message_action_state`, que combina evidencia enviada, job durable y
necesidad manual sin exponer errores crudos. El telefono completo sigue
limitado al detalle.

`POST /api/v1/whatsapp-messages/{message_id}/web/prepare` es exclusivamente local
y acepta `draft_kind` con `confirmation`, `payment` o `album`. Abre o reutiliza un perfil
Playwright persistente en `.runtime/whatsapp-web-profile/`. El modo `album` carga
juntas la constancia y la imagen de pago y escribe los textos combinados en la
descripcion visible. Por defecto no pulsa Enviar ni cambia el paquete a `sent`.
La primera ejecucion puede devolver `login_required`; `draft_ready` solo significa
que el borrador solicitado esta visible y pendiente de revision humana.

El mismo endpoint acepta `auto_send=true` cuando `draft_kind=album`, tanto para
simulacros como para paquetes de órdenes reales. En ese caso exige que las dos
miniaturas y el texto esten listos, pulsa Enviar una vez mediante el control
visible situado abajo a la derecha, espera que
desaparezcan las dos miniaturas y regrese el compositor normal,
registra `sent` y cierra el contexto Playwright. Un tipo de borrador distinto
recibe HTTP 400 si intenta usar `auto_send`. Si el resultado posterior al clic
no es concluyente, conserva el paquete como `prepared` y no realiza un segundo
intento automatico.

El dashboard usa `album`: carga constancia y QR en una sola seleccion multiple,
comprueba que aparezcan las dos miniaturas e intenta escribir la descripcion
combinada. Si WhatsApp no permite confirmar el texto, conserva las imagenes y
devuelve una advertencia para revision manual. El boton `Enviar por WhatsApp`
encadena la creacion del paquete y esta preparacion sin otro clic en el dashboard.
Si la pagina o el contexto fueron cerrados, el backend abre una ventana nueva y
reintenta una vez. El operador revisa el album y pulsa un unico
`Enviar 2 seleccionados`.

La imagen y los datos de cobro viven exclusivamente en
`.runtime/whatsapp-payment/`. `payment-details.json` define `phone`,
`account_name` e `image`; no se versiona. Al preparar el paquete se copia una
instantanea de la imagen a `screenshots/whatsapp-outgoing/` y se registra en
`payment_attachment_path`. El monto de produccion siempre procede del pago de la
orden, no del archivo privado.

`POST /api/v1/service-orders/{order_id}/whatsapp-followup/prepare` prepara el
seguimiento posterior al pago. Es un flujo separado del cobro: solo acepta una
orden `paid` con reserva `confirmed`, pago `paid` y WhatsApp internacional. El
paquete conserva cuatro secciones internas, adjunta los PDFs configurados y
consolida el texto post-pago.

Los PDFs post-pago se configuran localmente en
`.runtime/whatsapp-followup/followup-details.json` con una lista `documents`.
Cada archivo debe ser uno de los PDF originales conservados en `pdfs/`. El
paquete registra esas rutas directamente y no crea una copia por cliente.
`POST /api/v1/whatsapp-followup-messages/{message_id}/web/prepare`
abre WhatsApp Web localmente, envia primero los PDFs y luego envia el texto como
segundo mensaje. Si el envio automatico termina correctamente, el paquete queda
marcado como `sent`; `POST /api/v1/whatsapp-followup-messages/{message_id}/sent`
queda como confirmacion manual de respaldo.

## Compatibilidad de proxy

Durante la migracion hay dos targets validos para Angular:

- `http://127.0.0.1:8765`: API embebida del worker, compatible con el flujo
  actual.
- `http://127.0.0.1:8766`: admin API separado, target preferido para validar la
  arquitectura objetivo.

El dashboard no debe depender de memoria compartida con `ContinuousWorker`. Si
opera contra `8766`, los controles del worker deben pasar por
`worker_commands`.

## Sesion manual

`GET /api/v1/manual-sessions` devuelve las sesiones manuales activas en el
proceso admin API actual, con `session_id`, `order_id`, cuenta enmascarada,
estado y timestamps de apertura/actualizacion.

`POST /api/v1/manual-session/open` acepta:

- `order_id`

`POST /api/v1/manual-session/close` acepta:

- `session_id`

Restricciones:

- deshabilitado por defecto con `MANUAL_SESSION_ENABLED=false`;
- solo loopback;
- no devuelve password, cookies ni rutas internas;
- no reutiliza contexto Playwright del worker;
- prepara la ventana hasta login, tramite seleccionado, modal de cita abierto y
  sede requerida seleccionada, por defecto `LIMA-LA VICTORIA`;
- no cambia estado de reserva por si mismo;
- no selecciona fecha/hora, no resuelve CAPTCHA y no envia reserva;
- permite multiples sesiones manuales activas por proceso, cada una con
  navegador/contexto Playwright separado;
- cada sesion se limpia cuando se cierra su ventana, termina su hilo o el
  dashboard pide cerrar por `session_id`.
- después de una solicitud de cierre, el registro activo se retira como máximo
  en ocho segundos aunque el cierre interno de Playwright se demore.

## Runs

`GET /api/v1/runs` es para listado resumido. `GET /api/v1/runs/{run_id}` puede
devolver evidencia asociada, pero no incluye `details` crudos por defecto.

Para diagnostico manual, el cliente puede pedir:

```text
GET /api/v1/runs/{run_id}?include_details=1
```

El dashboard no debe mostrar/copiar JSON crudo por defecto.

## Editor de reglas de reserva

La creación y la edición de órdenes consumen el mismo componente visual para
`minimum_reservation_date`, `maximum_reservation_date`, `allowed_weekdays` y
`excluded_date_ranges`. Ningún formulario acepta restricciones horarias.
Esta reutilización no cambia los payloads del API: evita que ambos formularios
diverjan en etiquetas, validación de rangos o comportamiento responsive.

## Política de carga del dashboard

El dashboard consulta siempre el estado común (`/health`, worker y sesiones
manuales) y agrega solo los recursos requeridos por la vista activa:

| Vista      | Recursos específicos                                             |
| ---------- | ---------------------------------------------------------------- |
| Pendientes | órdenes y total de CAPTCHA sin etiqueta humana                   |
| Resumen    | órdenes, actividad y resumen mensual                             |
| Finanzas   | movimientos, resumen financiero y categorías en la primera carga |
| Órdenes    | órdenes                                                          |
| CAPTCHA    | resumen, página visible y cola de revisión CAPTCHA               |
| Actividad  | runs y comandos del worker                                       |

Al navegar se hace una primera carga inmediata de la nueva vista. Después, el
refresco automático actualiza únicamente esa vista y omite el ciclo si todavía
hay otra actualización en curso. Cambiar el mes consulta Resumen o Finanzas,
pero no ambos módulos simultáneamente.

Rutas del dashboard servido por el admin API:

| Ruta                      | Vista              |
| ------------------------- | ------------------ |
| `/pendientes`             | bandeja de trabajo |
| `/resumen?month=YYYY-MM`  | resumen mensual    |
| `/ordenes`                | listado de órdenes |
| `/ordenes/{order_id}`     | orden seleccionada |
| `/actividad`              | runs y comandos    |
| `/actividad/{run_id}`     | run seleccionado   |
| `/finanzas?month=YYYY-MM` | control financiero |
| `/captchas?mode=review\|history` | revisión o historial CAPTCHA |

La vista `review` solicita `review_status=pending`,
`review_scope=targeted` y `sort=review_priority`. La vista `history` conserva
`review_scope=all`, incluido el filtro explícito **Pendientes**, para que la
priorización nunca oculte ni elimine evidencia.

Cada vista se entrega como un chunk Angular diferido. El servidor debe mantener
el fallback de rutas desconocidas hacia `index.html`; el admin API incorporado
ya aplica este comportamiento.

## Cambios requeridos antes de Angular con botones

- Filtrar `owner_token` de `GET /api/v1/worker`. Estado: completado.
- Hacer autorizacion estricta en `worker/pause` y `worker/resume`. Estado:
  completado.
- Crear DTOs publicos estables para worker, ordenes y runs. Estado:
  completado como allowlist de campos publicos.
- Definir errores consistentes: `bad_request`, `not_found`, `conflict`,
  `unauthorized`, `configuration_error`.
