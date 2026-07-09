# Contrato de control del worker

Este documento define como se controla el worker hoy y como debe migrarse a un
admin API separado.

## Estado actual

Hoy `continuous_host.py` crea `ContinuousWorker` y la API local en el mismo
proceso. Por eso estos endpoints llaman metodos del objeto en memoria:

- `POST /api/v1/worker/pause`
- `POST /api/v1/worker/resume`
- `POST /api/v1/worker/restart`

Separar el admin API en otro proceso rompe este modelo si no se agrega un canal
persistido.

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

## Comandos actuales

- `pause`: pausa el loop sin matar el proceso.
- `resume`: reanuda el loop.
- `restart`: prepara reinicio controlado y devuelve codigo 75 al bootstrap.

## Contrato futuro

Antes de separar `pause`, `resume` y `restart`, crear un canal persistido:

```text
worker_commands
```

Campos minimos propuestos:

- `command_id`
- `command`
- `status`
- `requested_at`
- `started_at`
- `finished_at`
- `message`

Comandos iniciales:

- `pause`
- `resume`
- `restart`

El admin API escribira comandos. El worker los consumira y marcara resultado.
El admin API no debe depender de tener `ContinuousWorker` en memoria.

## Compatibilidad

Hasta completar el canal persistido:

- mantener API embebida para control directo;
- mantener `appointment-bot-worker`;
- mantener `scripts/start-worker.ps1`;
- no cambiar codigos de salida 0, 75 y 76.
