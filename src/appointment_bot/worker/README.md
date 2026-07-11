# Worker

Estructura futura para el proceso continuo: loop de monitoreo, leases,
ventanas calientes, cola rapida, backoff, recovery y politicas de resultado.

Desde el paso 9.4 contiene la implementacion del proceso continuo:

- `worker.control`
- `worker.queue`
- `worker.windows`
- `worker.host`
- `worker.continuous_worker`
- `worker.queue_runtime`
- `worker.windows_runtime`
- `worker.lease`
- `worker.recovery`
- `worker.error_policy`
- `worker.deferred_reports`
- `worker.execution`
- `worker.state_callbacks`
- `worker.order_results`
- `worker.observer_results`

Desde el paso 9.7 se retiraron las rutas antiguas `services/continuous_*`,
`services/order_execution.py` y `services/worker_*.py`. `appointment-bot-worker`
apunta a `worker.host:main` y `scripts/start-worker.ps1` ejecuta
`appointment_bot.worker.host`.

`worker.queue_runtime` invoca el motor de sesion en `reservation_engine/`.
