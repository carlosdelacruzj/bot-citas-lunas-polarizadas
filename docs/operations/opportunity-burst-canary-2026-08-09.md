# Ráfaga deslizante de oportunidades

Estado: ampliada y cargada mediante reinicio controlado el `2026-08-09`;
pendiente de la primera disponibilidad real posterior al despliegue.

## Objetivo

Aprovechar una liberación de varios cupos procesando la mayor cantidad posible
de órdenes compatibles sin mantener navegadores concurrentes durante la
observación normal. Solo una fecha y hora seleccionables confirmadas por una
sesión real pueden iniciar la ráfaga.

## Comportamiento vigente

1. La orden detectora conserva su sesión e intenta reservar sin esperar.
2. En paralelo se reclama el otro usuario del bloque activo si es compatible;
   si no lo es, se usa el siguiente compatible de la cola.
3. Cada auxiliar abre navegador, contexto y cookies propios, vuelve a leer el
   portal y realiza hasta cinco consultas ligeras durante 20 segundos.
4. El tercer intento hace un `reload_probe`; los demás usan el cambio
   `vacío -> LIMA-LA VICTORIA` y el intervalo vigente de `1-2` segundos.
5. Cada `registered` confirmado libera su posición y admite inmediatamente al
   siguiente usuario compatible, sin superar dos sesiones simultáneas.
6. Una sesión que termina sin reserva no se reemplaza por sí sola. La otra
   sesión puede continuar y cada reserva posterior vuelve a extender esa rama.
7. Cuando no quedan sesiones activas, candidatos compatibles o tiempo para
   admitir sesiones nuevas, el worker vuelve al observer normal.

`OPPORTUNITY_BURST_MAX_CLIENTS=0` elimina el límite fijo de clientes: se toma
una fotografía de toda la cola compatible al detectar el cupo. La admisión de
sesiones nuevas vence a los 300 segundos. Una reserva ya iniciada siempre
termina su confirmación o reconciliación aunque ese plazo se cumpla.

## Motivos de cierre

- `sessions_finished`: detector y auxiliares terminaron sin una nueva reserva
  confirmada que pudiera mantener la ráfaga.
- `candidate_queue_exhausted`: una reserva confirmó el cupo, pero ya no queda
  otro usuario compatible en la fotografía inicial de la cola.
- `burst_window_expired`: se agotaron los cinco minutos de admisión.
- `client_limit`: solo puede aparecer si el operador configura un límite
  positivo en `OPPORTUNITY_BURST_MAX_CLIENTS`.
- `portal_defense:*`, error técnico, pérdida de coordinación o
  `reservation_unconfirmed`: se detienen reemplazos por seguridad.

## Aislamiento y guardas

- Solo `available` real inicia la ráfaga; `fetch_probe`, evidencia histórica,
  estados parciales y cupos bloqueados por reglas no la activan.
- Cada orden usa navegador, contexto, credenciales, owner token de claim,
  heartbeat, `run_id` e intento de reserva independientes.
- Dos órdenes con las mismas credenciales nunca participan simultáneamente.
- Los auxiliares fuerzan una sola muestra CAPTCHA y 2Captcha conserva la
  autoridad.
- `reservation_unconfirmed`, error técnico, `403`, `429`, defensa o pérdida de
  coordinación detienen reemplazos nuevos. Las sesiones ya enviadas terminan
  su reconciliación y no se repite un submit ambiguo.
- Un claim tomado por otra ejecución se omite y se intenta el siguiente
  candidato sin duplicar cuenta.
- Pausa, reinicio y corte del worker reutilizan el evento de cancelación
  existente; los claims auxiliares se liberan en `finally`.

## Configuración activa

```env
OPPORTUNITY_BURST_ENABLED=true
OPPORTUNITY_BURST_MAX_SESSIONS=2
OPPORTUNITY_BURST_MAX_CLIENTS=0
OPPORTUNITY_BURST_MAX_SECONDS=300
OPPORTUNITY_BURST_SESSION_SECONDS=20
OPPORTUNITY_BURST_ATTEMPTS=5
OPPORTUNITY_BURST_RELOAD_PROBE_AFTER_ATTEMPT=3
```

El `.env` local quedó actualizado con estos valores. `0` significa sin límite
fijo de clientes, no sin límites operativos: siguen vigentes dos sesiones, la
ventana de cinco minutos, la cola compatible disponible y todas las guardas de
error. Los intervalos reutilizan
`OBSERVER_SITE_TOGGLE_INTERVAL_MIN_SECONDS` y
`OBSERVER_SITE_TOGGLE_INTERVAL_MAX_SECONDS`.

## Validación sin portal

- Una simulación procesó detector más seis auxiliares confirmados, consumió
  toda la cola compatible, mantuvo máximo dos sesiones y cerró con
  `candidate_queue_exhausted`.
- Otra simulación terminó detector y auxiliar en `unavailable`, no admitió a
  los candidatos restantes y cerró con `sessions_finished`.
- Una ventana reducida de prueba impidió el reemplazo posterior y cerró con
  `burst_window_expired`.
- La bandera desactivada no consultó candidatos ni creó tareas concurrentes.
- Las tareas instantáneas de la simulación revelaron y permitieron corregir dos
  carreras del arranque: nunca se abre un segundo auxiliar inicial sin
  `registered` y `maybe_start()` conserva el inicio aunque ese auxiliar termine
  antes de retornar.
- `compileall`, Ruff, `59 passed`, build Angular y `git diff --check` quedaron
  correctos.
- El worker se reinició sin orden activa. El comando persistido terminó
  `applied` y el proceso volvió saludable a `outside_hot_window` con
  `current_order_id=null`.

Estas simulaciones no sustituyen una prueba real: no abrieron el portal, no
llamaron a 2Captcha y no crearon reservas. La primera ejecución real debe
registrar `burst_id`, candidatos compatibles, clientes iniciados, duración,
máximo concurrente, resultados, defensas y reservas confirmadas.

## Rollback operativo

Rollback preferido, sin revertir código:

1. No reiniciar durante un submit. Esperar que el dashboard deje de mostrar
   `opportunity_burst` y revisar que no exista una reserva pendiente.
2. Establecer `OPPORTUNITY_BURST_ENABLED=false` en `.env`.
3. Reiniciar únicamente el worker desde Admin API o Telegram.
4. Confirmar que el siguiente cupo usa `opportunity_queue` secuencial y que no
   aparece un nuevo `burst_id`.

La bandera desactivada restaura la cadena previa de hasta diez clientes y 300
segundos. No hay migración PostgreSQL ni datos que revertir.

Rollback parcial si la ráfaga continua genera demasiada carga:

```env
OPPORTUNITY_BURST_MAX_CLIENTS=3
OPPORTUNITY_BURST_MAX_SECONDS=60
```

Ese ajuste recupera los límites iniciales sin retirar la concurrencia de dos
sesiones. También requiere reiniciar únicamente el worker cuando no existan
submissions pendientes.

Si se necesita retirar el código, revertir el commit que introdujo o amplió la
ráfaga, validar Ruff, `compileall`, pytest y dashboard, y reiniciar únicamente
el worker cuando no haya submissions pendientes. Nunca reintentar una reserva
`reservation_unconfirmed` como parte del rollback.
