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
- El cliente debe enviar `Authorization: Bearer <APPOINTMENT_BOT_API_TOKEN>`.
- El token no debe guardarse en Angular ni en `localStorage`.

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
```

En `appointment-bot-admin-api`, los endpoints `worker/pause`, `worker/resume` y
`worker/restart` encolan comandos persistidos en `worker_commands`. La API
embebida del worker mantiene control directo por compatibilidad.

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

La respuesta no debe devolver password. El frontend no debe persistir el valor
del password despues de enviarlo.

## Acciones administrativas

- `pause` y `activate` cambian elegibilidad operativa.
- `done` archiva/completa una orden.
- `no-charge` marca una orden sin cobro.
- `payment/paid` registra cobro y monto.
- `worker/restart` solicita reinicio controlado del worker.
- Las acciones piden confirmacion visible en el dashboard y muestran respuesta
  clara del backend.
- El formulario de creacion envia el password solo en el POST; no debe quedar
  persistido en storage del navegador.

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
