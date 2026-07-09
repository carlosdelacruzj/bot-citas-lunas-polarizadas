# Admin API

Backend administrativo separado para CRUD de ordenes, pagos, contactos,
historial y estado publico del worker.

Ejecutar localmente:

```powershell
appointment-bot-admin-api
```

Por defecto escucha en `127.0.0.1:8766` para coexistir con la API embebida del
worker en `127.0.0.1:8765`.

Configuracion:

- `APPOINTMENT_BOT_ADMIN_API_HOST`: host de escucha, por defecto `127.0.0.1`.
- `APPOINTMENT_BOT_ADMIN_API_PORT`: puerto de escucha, por defecto `8766`.
- `APPOINTMENT_BOT_API_TOKEN`: bearer token administrativo existente.

Este proceso reutiliza los handlers y servicios PostgreSQL actuales. No aloja
un `ContinuousWorker` en memoria; por eso `worker/pause`, `worker/resume` y
`worker/restart` encolan comandos en `worker_commands` para que el worker activo
los consuma en su propio ciclo.
