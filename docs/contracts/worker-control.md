# Contrato de control del worker

Estado: vigente. Ultima verificacion: `2026-08-29`.

Codigo propietario: `worker/continuous_worker.py`, `worker/host.py`,
`services/api/worker_routes.py` y `db/worker_commands.py`.

## Autoridad

El worker decide cuando una operacion Playwright puede ejecutarse o detenerse.
Admin API solicita acciones; no altera el loop ni sus recursos directamente.

Existen dos transportes con la misma semantica:

- la API embebida del worker aplica el control sobre su `ContinuousWorker`;
- Admin API encola un comando durable en `worker_commands`.

La topologia normal usa el canal durable. La API embebida permanece como
compatibilidad local y no debe convertirse en un segundo plano de control.

## Estado publico

La respuesta administrativa usa una allowlist:

- `phase`, `paused`, `current_order_id`, `masked_account`;
- `session_started_at`, `last_check_at`, `next_check_at`, `updated_at`;
- `confirmed_reservations`, `consecutive_errors`, `last_error`;
- `worker_running`, `worker_starting`, `continuous_worker_enabled`.

No expone `owner_token`, lease, credenciales ni datos sin enmascarar.

Una API viva no prueba worker funcional. En Admin API, `worker_running` depende
del lease/estado persistido; salud puede responder `api_only` sin worker activo.
`phase` es informativa y extensible: el frontend no debe congelar un enum ni
interpretar una fase desconocida como fallo.

## Comandos

Comandos permitidos:

- `pause`: impide admitir trabajo nuevo y espera una frontera segura;
- `resume`: reanuda admision;
- `restart`: prepara salida coordinada para que el supervisor reinicie.

Admin API crea el comando como `pending`. El worker reclama FIFO, registra su
owner y lo termina como `applied` o `failed`. Aceptar el HTTP no equivale a que
el comando ya fue aplicado.

No ampliar la allowlist sin implementar semantica idempotente, autorizacion,
auditoria y tratamiento seguro de trabajo activo.

## Autenticacion y actor

Los controles requieren autenticacion estricta mediante bearer o sesion local
confiable. Sin configuracion segura fallan cerrado.

`X-Appointment-Actor` admite hasta 64 caracteres en `[A-Za-z0-9:_-]`; un valor
ausente o invalido se normaliza a `admin_api`. Telegram persiste un hash corto,
nunca el chat o usuario completo.

## Salida coordinada

- `0`: cierre normal;
- `75`: reinicio coordinado;
- `76`: host sin lease o detencion coordinada que no debe reiniciarse en bucle.

Los supervisores respetan estos codigos y mantienen limite de reinicios.

## Oportunidades OBS-006/007

`opportunity_runtime_control` gobierna admision de rafagas y reobservaciones;
no reemplaza `worker_commands`.

- `inherit`: usa configuracion activa;
- `enabled`: admite si el breaker está cerrado;
- `disabled`: bloquea trabajo nuevo;
- `draining`: solo para rafagas; deja terminar sesiones ya iniciadas;
- `circuit_state=open`: bloquea siempre hasta reset explicito auditado.

Al adquirir un lease nuevo, el worker reconcilia rafagas abandonadas como
`aborted`. No reintenta submits ni elimina evidencia.

Runbook: [`../operations/opportunity-bursts.md`](../operations/opportunity-bursts.md).

## Seguridad

- no matar una sesion durante submit;
- no liberar backoff como efecto lateral de un comando;
- no marcar un comando aplicado antes del punto seguro;
- no ejecutar controles por SQL, Telegram o PowerShell fuera de Admin API;
- no asumir salud funcional por PID o HTTP aislado.
