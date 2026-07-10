# Worker

Estructura futura para el proceso continuo: loop de monitoreo, leases,
ventanas calientes, cola rapida, backoff, recovery y politicas de resultado.

Desde el paso 9.1 contiene fachadas publicas de compatibilidad:

- `worker.control`
- `worker.queue`
- `worker.windows`

Estas rutas reexportan implementacion existente desde `services/continuous_*`,
`services/worker_*` y `services/order_execution.py`. No reemplazan todavia a los
imports actuales ni cambian `appointment-bot-worker`.
