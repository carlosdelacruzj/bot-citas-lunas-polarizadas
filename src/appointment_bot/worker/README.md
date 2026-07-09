# Worker

Estructura futura para el proceso continuo: loop de monitoreo, leases,
ventanas calientes, cola rapida, backoff, recovery y politicas de resultado.

Por ahora no contiene logica funcional y no reemplaza a `services/continuous_*`,
`services/worker_*` ni `services/order_execution.py`. La migracion real se hara
por fases documentadas antes de mover codigo.
