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
POST /api/v1/service-orders
POST /api/v1/service-orders/{order_id}/contact
POST /api/v1/service-orders/{order_id}/payment/paid
POST /api/v1/service-orders/{order_id}/pause
POST /api/v1/service-orders/{order_id}/activate
POST /api/v1/service-orders/{order_id}/done
POST /api/v1/service-orders/{order_id}/no-charge
GET  /api/v1/runs
GET  /api/v1/runs/{run_id}
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

## Endpoints agregados para completar migracion

Estos endpoints completan la superficie administrativa previa al refactor
interno:

```text
GET  /api/v1/worker/commands
POST /api/v1/service-orders/{order_id}/split-programs
```

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

No debe exponer password, usuario real sin mascara, datos de cifrado ni leases.

## Crear orden

`POST /api/v1/service-orders` acepta:

- `document_number`
- `password`
- `priority`
- `contact_whatsapp`
- `contact_name`
- `contact_source`
- `applicant_name`
- `charge_required`
- `minimum_reservation_hour`
- `minimum_reservation_date`
- `allowed_weekdays`
- `parent_order_id`
- `program_expediente`
- `program_plate`

La respuesta no debe devolver password. El frontend no debe persistir el valor
del password despues de enviarlo.

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
- `worker/restart` solicita reinicio controlado del worker.
- `manual-session/open` abre una sesion Playwright visible y local para una
  orden seleccionada cuando `MANUAL_SESSION_ENABLED=true`.
- Las acciones piden confirmacion visible en el dashboard y muestran respuesta
  clara del backend.
- El formulario de creacion envia el password solo en el POST; no debe quedar
  persistido en storage del navegador.

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
