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

```text
GET  /api/v1/worker
GET  /api/v1/service-orders
GET  /api/v1/service-orders/{order_id}
GET  /api/v1/monthly-summary?month=YYYY-MM
POST /api/v1/service-orders
POST /api/v1/service-orders/{order_id}/contact
POST /api/v1/service-orders/{order_id}/priority
POST /api/v1/service-orders/{order_id}/restrictions
POST /api/v1/service-orders/{order_id}/payment/paid
POST /api/v1/service-orders/{order_id}/whatsapp/prepare
POST /api/v1/whatsapp-messages/test/prepare
GET  /api/v1/whatsapp-messages/{message_id}/attachment
GET  /api/v1/whatsapp-messages/{message_id}/payment-attachment
POST /api/v1/whatsapp-messages/{message_id}/web/prepare
POST /api/v1/whatsapp-messages/{message_id}/sent
POST /api/v1/service-orders/{order_id}/pause
POST /api/v1/service-orders/{order_id}/activate
POST /api/v1/service-orders/{order_id}/done
POST /api/v1/service-orders/{order_id}/no-charge
POST /api/v1/service-orders/{order_id}/close
POST /api/v1/service-orders/{order_id}/split-programs
GET  /api/v1/runs
GET  /api/v1/runs/{run_id}
GET  /api/v1/worker/commands
POST /api/v1/worker/pause
POST /api/v1/worker/resume
POST /api/v1/worker/restart
GET  /api/v1/manual-sessions
POST /api/v1/manual-session/open
POST /api/v1/manual-session/close
```

En `appointment-bot-admin-api`, los endpoints `worker/pause`, `worker/resume` y
`worker/restart` encolan comandos persistidos en `worker_commands`. La API
embebida del worker mantiene control directo por compatibilidad.

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
{"priority": 100}
```

Los valores `0` a `99` ordenan la cola normal; `100` o más activan enfoque.

`POST /api/v1/service-orders/{order_id}/restrictions` reemplaza el conjunto de
restricciones de reserva de una orden:

```json
{
  "minimum_reservation_hour": 11,
  "minimum_reservation_date": "2026-08-01",
  "maximum_reservation_date": "2026-08-31",
  "allowed_weekdays": [1, 3, 6]
}
```

Cada campo acepta `null` para quitar esa restricción. La fecha máxima es
inclusiva y no puede ser anterior a la mínima; los días usan numeración ISO de
`1=lunes` a `7=domingo`. Al guardar se limpia `next_allowed_at` para que una
restricción corregida no quede bloqueada por una espera calculada previamente.
La actualización se usa en la siguiente selección de la cola y no interrumpe
una sesión que ya está ejecutándose. Cada orden se actualiza por separado,
aunque varias compartan el mismo contacto.

Snapshots, filtros, tablas y copiado general deben trabajar exclusivamente con
el DTO enmascarado del listado.

La tarjeta operativa de la orden seleccionada puede mostrar el WhatsApp completo
obtenido mediante el endpoint de detalle. Debe conservarlo solo en memoria,
descartarlo al cambiar la orden o recargar la aplicación y evitar incluirlo en snapshots o
copias masivas.

## Crear orden

`POST /api/v1/service-orders` acepta:

- `document_number`: obligatorio; usuario o documento del cliente.
- `password`: obligatorio.
- `contact_name`: obligatorio; persona que contacto al negocio.
- `contact_source`: obligatorio; `tiktok`, `facebook` o `whatsapp`.
- `contact_whatsapp`: opcional.

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

El alta normal del dashboard solo presenta esos datos y las restricciones de
fecha opcionales. Los siguientes campos siguen disponibles en el contrato para
flujos administrativos avanzados, pero no se solicitan al crear un cliente:

- `priority`
- `applicant_name`
- `charge_required`
- `minimum_reservation_hour`
- `minimum_reservation_date`
- `maximum_reservation_date`
- `allowed_weekdays`
- `parent_order_id`
- `program_expediente`
- `program_plate`

La respuesta no debe devolver password. El frontend no debe persistir el valor
del password despues de enviarlo.

Si no se envian `minimum_reservation_date`, `maximum_reservation_date` ni
`allowed_weekdays`, la orden se
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
- `minimum_reservation_hour`: hora minima aceptable.
- `minimum_reservation_date`: fecha minima aceptable.
- `maximum_reservation_date`: fecha maxima aceptable, inclusive; no puede ser
  anterior a `minimum_reservation_date`.
- `allowed_weekdays`: dias ISO permitidos, `1=lunes` a `7=domingo`.

Cada suborden debe tratarse como trabajo independiente para pausa, activacion,
pago, reporte, sesion manual y cierre. Aunque comparta credenciales con la orden
padre, no debe mezclarse su estado de reserva ni su estado de pago.

Cuando el usuario cree una orden sin restricciones, Angular debe omitir estos
campos o enviarlos como `null`. No debe inventar restricciones por defecto.

## Acciones administrativas

- `pause` y `activate` cambian elegibilidad operativa.
- `done` archiva/completa una orden.
- `no-charge` marca una orden sin cobro.
- `close` archiva/cierra una orden con `closure_reason` y `closure_note`.
- `payment/paid` registra cobro y monto.
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
El listado de ordenes expone solo `whatsapp_message_status` y
`whatsapp_message_sent_at`; el telefono completo sigue limitado al detalle.

`POST /api/v1/whatsapp-messages/{message_id}/web/prepare` es exclusivamente local
y acepta `draft_kind` con `confirmation`, `payment` o `album`. Abre o reutiliza un perfil
Playwright persistente en `.runtime/whatsapp-web-profile/` y prepara dos mensajes
separados: constancia con saludo y detalle; despues QR con instrucciones y monto.
Cada imagen lleva su propio pie. Nunca pulsa Enviar ni cambia el paquete a `sent`.
La primera ejecucion puede devolver `login_required`; `draft_ready` solo significa
que el borrador solicitado esta visible y pendiente de revision humana.

El dashboard usa `album`: carga constancia y QR en una sola seleccion multiple,
elige cada miniatura y escribe su texto individual. `draft_ready` solo se devuelve
despues de volver a seleccionar ambas miniaturas y verificar sus descripciones. El
boton `Enviar por WhatsApp` encadena la creacion del paquete y esta preparacion sin
otro clic en el dashboard. Si la pagina o el contexto fueron cerrados, el backend
abre una ventana nueva y reintenta una vez. El operador revisa el album y pulsa un
unico `Enviar 2 seleccionados`.

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
Cada archivo debe ser PDF y se copia a `screenshots/whatsapp-followup-outgoing/`
al preparar el paquete. `POST /api/v1/whatsapp-followup-messages/{message_id}/web/prepare`
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

## Cambios requeridos antes de Angular con botones

- Filtrar `owner_token` de `GET /api/v1/worker`. Estado: completado.
- Hacer autorizacion estricta en `worker/pause` y `worker/resume`. Estado:
  completado.
- Crear DTOs publicos estables para worker, ordenes y runs. Estado:
  completado como allowlist de campos publicos.
- Definir errores consistentes: `bad_request`, `not_found`, `conflict`,
  `unauthorized`, `configuration_error`.
