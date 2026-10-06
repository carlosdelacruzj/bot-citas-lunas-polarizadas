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

Admin API no encola ni aplica `restart` mientras exista una sesion manual en
`opening`, `active`, `closing` o `close_timeout`. La barrera responde `409`; un
timeout de cierre sigue contando como navegador vivo hasta su baja real.

El reinicio con `release_safe_backoffs=true` tambien libera una espera antigua
del observador solo si coincide exactamente con su bloqueo persistido y el
ultimo run rotativo acredita `InvalidPortalCredentials`, sin submit. Conserva
la exclusion de esa cuenta y audita la liberacion; no libera defensas del portal.

No ampliar la allowlist sin implementar semantica idempotente, autorizacion,
auditoria y tratamiento seguro de trabajo activo.

## Autenticacion y actor

Los controles requieren autenticacion estricta mediante bearer o sesion local
confiable. Sin configuracion segura fallan cerrado.

El actor se deriva de la cookie local o del bearer autenticado. Un
`X-Appointment-Actor` solo se acepta con su firma HMAC valida, hasta 64
caracteres en `[A-Za-z0-9:_-]`; sin firma se usa la huella SHA-256 corta del
bearer. Telegram firma y persiste un hash corto, nunca el chat o usuario
completo.

## Salida coordinada

- `0`: cierre normal;
- `75`: reinicio coordinado;
- `76`: host sin lease, lease perdido o detencion coordinada que no debe
  reiniciarse en bucle.

Los supervisores respetan estos codigos y mantienen limite de reinicios.

## Lease global

El lease de `worker_state` posee un heartbeat dedicado desde que el worker lo
adquiere hasta que termina su liberacion. No depende del loop de chequeos, de
callbacks del observer ni del heartbeat separado del claim de una orden.

Una excepcion transitoria de PostgreSQL activa reintentos breves mientras el
ultimo vencimiento confirmado siga vigente. Si PostgreSQL confirma que el owner
ya no puede renovar o se supera el vencimiento local sin recuperacion, la
perdida es irreversible para ese host: se activa cancelacion, se detiene la
admision nueva y el proceso sale con `76`.

El claim de orden sigue renovandose de manera independiente. Antes del submit,
la reserva comprueba tanto cancelacion global como propiedad de la orden. Si la
perdida ocurre despues de persistir `intent`, no pulsa `Reservar` y conserva el
intento como resultado no reintentable hasta conciliacion.

## Control de oportunidades

`opportunity_runtime_control` gobierna admision de rafagas y reobservaciones;
no reemplaza `worker_commands`.

- `enabled`: admite si el breaker está cerrado;
- `disabled`: bloquea trabajo nuevo;
- `draining`: solo para rafagas; deja terminar sesiones ya iniciadas;
- `circuit_state=open`: bloquea siempre hasta reset explicito auditado.

Al adquirir un lease nuevo, el worker reconcilia rafagas abandonadas como
`aborted`. No reintenta submits ni elimina evidencia.

Runbook: [`../operations/opportunity-bursts.md`](../operations/opportunity-bursts.md).

## Seguridad

La disponibilidad verificada genera un unico aviso de texto mediante la outbox
asincrona, con deduplicacion diaria por sede, fecha y hora. La captura obligatoria
queda local; ni el observador ni las evidencias diferidas repiten el aviso con foto.
Confirmaciones, resultados inciertos y errores de reserva mantienen sus avisos.

La seleccion normal de un expediente unico o del objetivo guardado es silenciosa
en Telegram. No reemplaza el listado validado del preflight con filas sin revisar.
Los bloqueos de identidad, multiplicidad o estado conservan su aviso deduplicado;
un cambio del formato interno no convierte una seleccion normal en una alerta.

- no matar una sesion durante submit;
- no liberar backoff como efecto lateral de un comando;
- no marcar un comando aplicado antes del punto seguro;
- una variacion marcada del contrato de seguridad del portal aplica pausa
  persistente, conserva el error y alerta antes de admitir mas trabajo;
- una deteccion `available` con `AUTO_RESERVE=false` aplica pausa persistente y
  avisa que la orden ya puede abrirse con medicion para continuar manualmente;
- no ejecutar controles por SQL, Telegram o PowerShell fuera de Admin API;
- no asumir salud funcional por PID o HTTP aislado.

## Observador rotativo

Con dos o mas clientes `ready`, se revisan directamente sus cuentas por uso
menos reciente, sin cuentas auxiliares ni exigir deteccion previa. Varias ordenes
de una cuenta cuentan como un cliente y comparten su antiguedad de rotacion.
Con uno, alterna una revision del cliente y una cuenta auxiliar diferente; sin
clientes, solo rota auxiliares. Un cliente en backoff sigue contando como activo:
si todos estan bloqueados se espera sin sustituirlos por cuentas historicas.
Cada turno conserva la sesion configurada: hasta 15 consultas en 120 segundos,
cambios de sede cada 1-2 segundos y recarga prevista en el intento 8 mientras
no se hayan consultado fechas/horarios. Conserva las rafagas y traspasos. Al reiniciar, el turno unico empieza
por el cliente. Si no hay auxiliar elegible, espera y vuelve al cliente.
El observador auxiliar elige la cuenta validada menos recientemente usada
entre cuentas sin ninguna orden `ready`.
Exige validacion posterior al cambio de credenciales y ausencia de fallos de acceso,
leases, intentos activos/inciertos, preflight, revision activa y descansos pendientes.
La admision se vuelve a comprobar bajo el bloqueo de cuenta. Cada turno abre una
sesion aislada, verifica la sede exigida y cierra el navegador antes de liberar el
lease; perderlo cancela la observacion.

Cada actualizacion auxiliar consulta como maximo dos fechas y dos horarios, sin submit ni
muestreo repetido de CAPTCHA. Las fechas listadas permiten seleccionar clientes
compatibles sin presentar esos listados como cupos verificados. Cada cliente usa
sus credenciales y el presupuesto de reserva; se conserva el limite de candidatos
y tiempo de la cola. Las alertas requieren disponibilidad materializada y captura.

La cadencia global conserva el intervalo configurado, con piso de 30 segundos;
cada cuenta descansa al menos 180 segundos. Ambos tiempos quedan en PostgreSQL
antes de abrir y despues de cerrar la sesion. No se reinician al cambiar cuenta
ni al reiniciar el proceso. Si no hay cuenta elegible se espera, sin usar una fija.
Una defensa detiene globalmente la rotacion: 900 segundos por demasiadas solicitudes,
180 por indisponibilidad temporal; otras defensas/fallos esperan al menos 180 o el
maximo de recuperacion configurado. El rechazo explicito de credenciales registra perdida de acceso por cuenta y,
si tiene reserva, reutiliza `access_lost` del seguimiento. Pausa solo sus ordenes
`ready`, conserva pagos y cierres, y continua la rotacion con la cadencia normal
sin descanso ni contador de errores global. La cuenta queda excluida hasta
corregir y revalidar el acceso. Otros fallos excluyen la cuenta hasta nueva
validacion, salvo fallos de red. Cambios de contrato siguen pausando el worker.
No se rota para continuar solicitudes durante el bloqueo del portal.

### Recorrido adicional de evidencia

Solo con cero ordenes `ready` (ninguna pendiente o todas pausadas), despues de
la deteccion normal del observador, se completa un recorrido separado de fotos.
La deteccion conserva su presupuesto de dos fechas/dos horarios por actualizacion y su callback;
el recorrido admite hasta dos consultas adicionales tras la deteccion principal, sin CAPTCHA final ni submit. Cada cupo adicional
solo alerta despues de validar la seleccion visible exacta, cupos positivos,
boton habilitado y captura canonica archivada; reutiliza la deduplicacion diaria
por sede, fecha y hora de la deteccion normal.
Reutiliza la captura canonica y descarta pares ya fotografiados. El avance por
sede y dia de Lima se conserva en `runs.details_json.observer_evidence_collection`;
las siguientes cuentas revisan primero fechas pendientes menos visitadas.
Una fecha se completa cuando todos sus horarios listados tienen foto verificada;
una fecha sin horario verificado sigue pendiente, nunca cuenta como fotografiada.
El resultado principal conserva la revision inicial; `initial_status` y
`session_captures` distinguen los hallazgos adicionales verificados, con cupos,
fecha de verificacion y ruta de evidencia, sin convertirlos en intentos de reserva.
La deteccion normal sigue revisando la fecha mas cercana en cada sesion.

Antes de cada consulta adicional se relee la cola: un cliente `ready`, incluso
en backoff, detiene el recorrido. La pausa global, cancelacion, perdida del lease
y defensas mantienen prioridad; no se habilita observacion durante una pausa
global ni se evita la pausa por `AUTO_RESERVE=false`. Los descansos y exclusiones
de cuentas siguen siendo los de la rotacion existente. Un fallo conserva las
fotos ya archivadas y el avance parcial del run, sin acreditar la consulta fallida.
