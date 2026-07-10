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

Las rutas antiguas `services/continuous_*`, `services/order_execution.py` y
`services/worker_*.py` son wrappers explicitos para conservar compatibilidad
durante la transicion. `appointment-bot-worker` apunta a `worker.host:main`.

`worker.queue_runtime` todavia invoca el motor de sesion existente. El traslado
fino de login, lectura de cupos, CAPTCHA, submit y confirmacion queda para
`reservation_engine/` en el Paso 9.5.
