# Admin API

Entrypoint del proceso administrativo. Compone el servidor HTTP, sirve el
dashboard y posee los servicios de larga vida que no pertenecen al worker:

- dispatcher/perfil persistente de WhatsApp;
- scheduler de recordatorios;
- scheduler de revision post-cita;
- recuperacion de preflights pendientes.

La definicion de rutas vive en `services/local_api.py` y `services/api/`.
Admin API persiste comandos; no ejecuta reservas Playwright.

Contrato: [`../../../docs/contracts/admin-api.md`](../../../docs/contracts/admin-api.md).
