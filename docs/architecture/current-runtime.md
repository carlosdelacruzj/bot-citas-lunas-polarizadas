# Runtime actual

Este documento describe el comportamiento vigente despues de completar la
migracion interna hasta el paso 9.7. Debe usarse como referencia de
compatibilidad, no como lista de trabajo futuro.

## Entrypoints

- `appointment-bot-worker` apunta a `appointment_bot.worker.host:main`.
- `appointment-bot-client` apunta a `appointment_bot.services.client_cli:run`.
- `appointment-bot-admin-api` apunta a `appointment_bot.admin_api.server:main`.
- `scripts/start-worker.ps1` levanta Docker/PostgreSQL y ejecuta el host continuo.
- `scripts/start-admin-dashboard.ps1` construye Angular y levanta el admin API
  que sirve el dashboard.
- `scripts/start-runtime.ps1` inicia en segundo plano los bootstraps del worker,
  admin/dashboard, control de Telegram y servicio sombra de CAPTCHA; la tarea
  programada de Windows lo ejecuta directamente al iniciar sesion.
- Cada bootstrap queda en un proceso independiente y el lanzador termina
  despues de iniciarlos; cerrar una consola de instalacion no detiene el worker.
- `scripts/install-startup-task.ps1` instala o recupera esa tarea sin usar VBS
  ni omitir la politica de ejecucion de PowerShell.
- `scripts/start-captcha-shadow.ps1` supervisa el servicio de `test-captcha` en
  `127.0.0.1:8787`, lo inicia con la sesion y lo recupera si deja de responder.
- El build Angular de produccion conserva la hoja de estilos como recurso
  externo normal (`inlineCritical=false`) para cumplir la politica CSP del admin
  API sin depender de eventos inline bloqueados por el navegador.

## Proceso actual

El host continuo (`worker/host.py`) hace dos cosas en el mismo
proceso:

1. crea `ContinuousWorker`;
2. crea la API local con `create_local_api_server(worker_controller=worker)`.

La API local puede controlar el worker porque tiene una referencia en memoria al
objeto `ContinuousWorker`. El loop, ventanas, lease del worker, comandos
persistidos, recovery y cola rapida viven ahora bajo `appointment_bot.worker`.

El motor Playwright del portal vive ahora bajo `appointment_bot.reservation_engine`:
login, seleccion de tramite, lectura de citas, fetch/reload probes, CAPTCHA,
submit de reserva y confirmacion post-submit.

Los reportes y evidencia operativa viven ahora bajo `appointment_bot.reports`:
historial final de corridas, resumen compacto de evidencia, bitacoras de
optimizacion/disponibilidad parcial, fichas de estado y reporte diario.

Los wrappers historicos de `services/postgres_*`, `services/continuous_*`,
`services/order_execution.py`, `services/worker_*`, `flows/*`,
`services/session_*`, `services/reservation_*`, `services/observer.py` y
`services/*_reports` fueron retirados en el paso 9.7. Los consumidores internos
usan rutas nuevas directas.

También existe el proceso separado `appointment-bot-admin-api`. Reutiliza los
handlers y servicios PostgreSQL, escucha en `127.0.0.1:8766`, sirve el build
Angular con sesión local segura y no aloja un `ContinuousWorker` en memoria.
El proxy Angular queda solo para desarrollo o rollback.

## API local actual

El host sirve por defecto en `127.0.0.1:8765`.

Endpoints existentes:

```text
GET  /health
GET  /api/v1/worker
GET  /api/v1/service-orders
GET  /api/v1/service-orders/{order_id}
POST /api/v1/service-orders
POST /api/v1/service-orders/{order_id}/contact
POST /api/v1/service-orders/{order_id}/payment/paid
POST /api/v1/service-orders/{order_id}/pause
POST /api/v1/service-orders/{order_id}/activate
POST /api/v1/service-orders/{order_id}/done
POST /api/v1/service-orders/{order_id}/no-charge
POST /api/v1/service-orders/{order_id}/close
POST /api/v1/service-orders/{order_id}/split-programs
GET  /api/v1/runs
GET  /api/v1/runs/{run_id}
GET  /api/v1/worker/commands
GET  /api/v1/manual-sessions
GET  /api/v1/finance/categories
GET  /api/v1/finance/entries
GET  /api/v1/finance/summary
POST /api/v1/manual-session/open
POST /api/v1/manual-session/close
POST /api/v1/finance/entries
POST /api/v1/finance/entries/{entry_id}/edit
POST /api/v1/finance/entries/{entry_id}/void
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
- no retirar nuevas superficies de compatibilidad sin validar CLI, API, tests,
  scripts, n8n y consumidores de flujo Playwright contra la ruta reemplazante.
