# Runtime actual

Este documento congela el comportamiento actual antes de separar worker, admin
API y dashboard. Debe usarse como referencia de compatibilidad durante la
migracion.

## Entrypoints

- `appointment-bot-worker` apunta a `appointment_bot.services.continuous_host:main`.
- `appointment-bot-client` apunta a `appointment_bot.services.client_cli:run`.
- `appointment-bot-admin-api` apunta a `appointment_bot.admin_api.server:main`.
- `scripts/start-worker.ps1` levanta Docker/PostgreSQL y ejecuta el host continuo.
- `scripts/start-worker-hidden.vbs` inicia el bootstrap de Windows sin ventana.

## Proceso actual

El host continuo (`services/continuous_host.py`) hace dos cosas en el mismo
proceso:

1. crea `ContinuousWorker`;
2. crea la API local con `create_local_api_server(worker_controller=worker)`.

La API local puede controlar el worker porque tiene una referencia en memoria al
objeto `ContinuousWorker`. Esta relacion es el acoplamiento principal que debe
romperse con cuidado cuando exista un admin API separado.

Tambien existe un proceso separado `appointment-bot-admin-api` para la fase 5
de migracion. Ese proceso reutiliza los handlers y servicios PostgreSQL
actuales, escucha por defecto en `127.0.0.1:8766` y no aloja un
`ContinuousWorker` en memoria.

## API local actual

El host sirve por defecto en `127.0.0.1:8765`.

Endpoints existentes:

```text
GET  /health
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

`/health` es liveness publico. Los endpoints administrativos usan bearer token
cuando `APPOINTMENT_BOT_API_TOKEN` esta configurado. Para la migracion del
dashboard, las rutas administrativas deben tratarse como protegidas aunque el
servicio siga escuchando solo en loopback.

## Leases

Hay dos niveles de exclusividad:

- `worker_state.owner_token`: evita dos workers continuos activos sobre la misma
  base.
- `service_orders.lease_owner` y `service_orders.lease_expires_at`: evitan que
  dos ejecuciones reclamen la misma orden.

Durante una reserva, el lease de la orden se renueva por heartbeat. Si se pierde
el lease durante una ejecucion, el resultado no debe repetirse automaticamente
como si nada hubiera pasado.

## Cola y subordenes por tramite

La cola operativa procesa filas `service_orders.status = 'ready'` como trabajos
independientes. La prioridad sigue siendo `priority DESC, created_at ASC`.

Cuando una misma cuenta tiene varios tramites pendientes, la orden generica
puede dividirse en subordenes con `parent_order_id`, `program_expediente` y
`program_plate`. Cada suborden comparte credenciales con el titular, pero el
worker abre una sesion Playwright nueva por suborden y selecciona explicitamente
el expediente/placa objetivo antes de leer cupos o reservar.

Si una suborden no encuentra su tramite objetivo o el tramite ya no esta
`PENDIENTE`, el flujo falla de forma clara antes de abrir el panel de citas para
evitar reservar el tramite equivocado. El `reload_probe` debe conservar el mismo
expediente/placa objetivo.

## Codigos de salida del host

- `0`: salida normal por corte diario.
- `75`: reinicio controlado o health failure.
- `76`: otro host tiene el lease del worker.

`scripts/start-worker.ps1` depende de esos codigos para decidir cuanto esperar
antes de relanzar.

## Admin API separado

El admin API separado usa:

- `APPOINTMENT_BOT_ADMIN_API_HOST`, por defecto `127.0.0.1`;
- `APPOINTMENT_BOT_ADMIN_API_PORT`, por defecto `8766`;
- `APPOINTMENT_BOT_API_TOKEN` como bearer token administrativo.

En este proceso, `GET /api/v1/worker` lee estado persistido del worker, pero
`POST /api/v1/worker/pause`, `POST /api/v1/worker/resume` y
`POST /api/v1/worker/restart` encolan comandos persistidos en
`worker_commands`. La API embebida por el worker conserva control directo por
compatibilidad.

## Comandos persistidos

`worker_commands` registra comandos administrativos solicitados por procesos
sin `ContinuousWorker` en memoria. El worker activo reclama el siguiente comando
`pending` con su `owner_token`, lo aplica en su propio ciclo y lo marca como
`applied` o `failed`.

## Corte diario

El worker no inicia nuevas consultas despues de las 18:00 Lima. Si ya habia una
ejecucion en curso, la deja terminar. Luego genera reporte diario y el bootstrap
puede esperar hasta la hora de resume configurada antes de relanzar.

## Compatibilidad obligatoria

Hasta que exista un reemplazo probado:

- no cambiar el contrato de `appointment-bot-worker`;
- no cambiar los codigos de salida;
- no cambiar el bootstrap de Windows;
- no quitar la API local embebida;
- no mover `pause`, `resume` ni `restart` fuera del proceso actual sin un canal
  persistido de comandos.
