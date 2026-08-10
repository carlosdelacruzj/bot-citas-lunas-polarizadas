# Contrato de control del worker

Este documento define como se controla el worker hoy y como debe migrarse a un
admin API separado.

## Estado actual

La topologia principal ejecuta `appointment-bot-worker` y
`appointment-bot-admin-api` como procesos independientes. La API embebida de
`8765` permanece como compatibilidad de rollback y, solo en ese modo, llama
metodos del objeto `ContinuousWorker` en memoria:

- `POST /api/v1/worker/pause`
- `POST /api/v1/worker/resume`
- `POST /api/v1/worker/restart`

La API embebida conserva este modelo por compatibilidad. El admin API separado
usa el canal persistido `worker_commands`.

## Estado publico del worker

Campos utiles para dashboard:

- `phase`
- `paused`
- `current_order_id`
- `masked_account`
- `session_started_at`
- `last_check_at`
- `next_check_at`
- `confirmed_reservations`
- `consecutive_errors`
- `last_error`
- `updated_at`
- `worker_running`
- `continuous_worker_enabled`

Campos internos que no deben salir al frontend:

- `owner_token`
- `lease_expires_at`
- cualquier dato no enmascarado de credenciales.

Estado implementado: `GET /api/v1/worker` usa una lista permitida de campos
publicos y filtra los campos internos aunque el worker los tenga en memoria.

## Fases operativas importantes

- `starting`: arranque.
- `paused`: pausa administrativa.
- `outside_hot_window`: vivo pero esperando ventana.
- `monitoring_observer`: observador activo.
- `monitoring_order`: orden activa.
- `rapid_queue`: cola rapida.
- `backoff` o `recovery_backoff`: espera por error o defensa.
- `daily_cutoff`: fin operativo diario.
- `lease_unavailable`: otro host tiene el lease.

El dashboard debe distinguir API viva de worker realmente procesando.
Cuando `phase` empieza por `monitoring_observer` y `current_order_id` esta vacio,
el dashboard debe mostrar `Observador general activo`: la cuenta esta buscando
cupos, pero no representa una orden de cliente.

Las alertas de disponibilidad sin orden o cliente asociado deben identificarse
en Telegram como `CUPO DETECTADO - OBSERVADOR GENERAL` y recordar que el cupo
todavia debe validarse contra las restricciones de las ordenes activas.

## Comandos actuales

- `pause`: pausa el loop sin matar el proceso.
- `resume`: reanuda el loop.
- `restart`: prepara reinicio controlado y devuelve codigo 75 al bootstrap.

Todos estos comandos requieren `Authorization: Bearer
<APPOINTMENT_BOT_API_TOKEN>`. Si el token no esta configurado, la API responde
`configuration_error` para evitar controles administrativos abiertos.

Un cliente administrativo autenticado puede enviar `X-Appointment-Actor` con
un identificador saneado de hasta 64 caracteres formado por letras, numeros,
`:`, `_` o `-`. El valor se persiste como `requested_by`; cualquier valor
ausente o invalido se normaliza a `admin_api`. Telegram usa un hash corto del
`chat_id` y nunca guarda el identificador completo en `worker_commands`.

## Canal persistido

El canal persistido permite que `appointment-bot-admin-api` solicite acciones
sin tener un objeto `ContinuousWorker` en memoria:

```text
worker_commands
```

Campos principales:

- `command_id`
- `command`
- `status`
- `requested_at`
- `claimed_at`
- `processed_at`
- `requested_by`
- `worker_owner_token`
- `error_message`

Comandos iniciales:

- `pause`
- `resume`
- `restart`

El admin API separado escribe comandos con estado `pending`. El worker activo
los reclama con su `owner_token`, los ejecuta en su propio ciclo y los marca
como `applied` o `failed`.

## Compatibilidad

Mientras la migracion conserva compatibilidad:

- mantener API embebida para control directo;
- mantener el canal persistido para el admin API separado;
- mantener `appointment-bot-worker`;
- mantener `scripts/start-worker.ps1`;
- no cambiar codigos de salida 0, 75 y 76.
