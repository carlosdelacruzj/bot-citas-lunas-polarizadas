# Worker

Orquesta la cola continua, leases, comandos, monitoreo y revision posterior a la
reserva. Decide cuando una operacion Playwright es segura y persiste heartbeat,
fase y resultado.

Admin API controla mediante comandos persistidos; no invoca metodos en memoria
en la topologia principal. El worker no posee el perfil persistente de WhatsApp:
solo prepara o encola trabajo durable.

Contrato: [`../../../docs/contracts/worker-control.md`](../../../docs/contracts/worker-control.md).
