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
- `worker.queue_traversal`
- `worker.queue_policy`
- `worker.order_execution`
- `worker.windows_runtime`
- `worker.lease`
- `worker.recovery`
- `worker.error_policy`
- `worker.deferred_reports`
- `worker.execution`
- `worker.state_callbacks`
- `worker.order_results`
- `worker.observer_results`
- `worker.opportunity_burst`

Desde el paso 9.7 se retiraron las rutas antiguas `services/continuous_*`,
`services/order_execution.py` y `services/worker_*.py`. `appointment-bot-worker`
apunta a `worker.host:main` y `scripts/start-worker.ps1` ejecuta
`appointment_bot.worker.host`.

Desde el P2 de backend, `worker.queue_runtime` es una fachada de compatibilidad.
`queue_traversal` recorre la cola, `order_execution` ejecuta una orden y
`queue_policy` concentra limites, diferimiento de estado y pausas entre ordenes.
La ejecucion individual invoca el motor de sesion en `reservation_engine/`.
`opportunity_burst` coordina el canario detector + auxiliar y deja la cadena
secuencial intacta como rollback por configuracion.
