# Canario de ráfaga de oportunidades

Estado: implementado el `2026-08-09`; pendiente de la primera disponibilidad
real posterior al despliegue.

## Objetivo

Reducir el tiempo perdido entre clientes cuando el portal libera varios cupos.
La operación normal continúa con el observer secuencial. Solo una fecha y hora
seleccionables confirmadas por una sesión real pueden iniciar la ráfaga.

## Comportamiento vigente

1. La orden detectora conserva su sesión y empieza su reserva sin esperar.
2. En paralelo se reclama el otro usuario del bloque activo si es compatible;
   si no lo es, se usa el siguiente compatible de la cola.
3. El auxiliar abre navegador, contexto y cookies propios, vuelve a leer el
   portal y realiza hasta cinco consultas ligeras durante 20 segundos.
4. El tercer intento hace un `reload_probe`; los demás usan el cambio
   `vacío -> LIMA-LA VICTORIA` y el intervalo vigente de `1-2` segundos.
5. Si detector o auxiliar confirma `registered`, la posición liberada se ocupa
   con el siguiente usuario compatible, sin superar dos sesiones simultáneas.
6. Sin reserva confirmada no existe reemplazo. Cuando terminan las sesiones
   activas, el worker vuelve al observer normal.

El canario admite como máximo tres clientes contando al detector: detector,
primer auxiliar y un reemplazo. La admisión de sesiones nuevas vence a los 60
segundos. Una reserva ya iniciada siempre termina su confirmación o
reconciliación aunque ese plazo se cumpla.

## Aislamiento y guardas

- Solo `available` real inicia el canario; `fetch_probe`, evidencia histórica,
  estados parciales y cupos bloqueados por reglas no lo activan.
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

## Configuración

```env
OPPORTUNITY_BURST_ENABLED=true
OPPORTUNITY_BURST_MAX_SESSIONS=2
OPPORTUNITY_BURST_MAX_CLIENTS=3
OPPORTUNITY_BURST_MAX_SECONDS=60
OPPORTUNITY_BURST_SESSION_SECONDS=20
OPPORTUNITY_BURST_ATTEMPTS=5
OPPORTUNITY_BURST_RELOAD_PROBE_AFTER_ATTEMPT=3
```

Los intervalos entre consultas reutilizan
`OBSERVER_SITE_TOGGLE_INTERVAL_MIN_SECONDS` y
`OBSERVER_SITE_TOGGLE_INTERVAL_MAX_SECONDS`. El `.env` local no se modificó;
los valores anteriores son los defaults del código y se cargarán en el próximo
arranque del worker. La validación de configuración impide superar durante el
canario dos sesiones, tres clientes, 60 segundos, 20 segundos por auxiliar y
cinco intentos; ampliar esos techos requiere otro cambio revisado de código.

## Evidencia de validación

- Compilación y lint verifican el nuevo coordinador y la configuración.
- La suite existente permanece en `59 passed`.
- Una simulación aislada confirmó detector + auxiliar, máximo de dos sesiones,
  reemplazo por el siguiente usuario después de `registered` y cierre al agotar
  tres clientes.
- Otra simulación confirmó que `OPPORTUNITY_BURST_ENABLED=false` no consulta
  candidatos ni crea tareas concurrentes.
- No se abrió el portal, no se llamó a 2Captcha y no se creó una reserva durante
  estas simulaciones.

La validación real debe registrar `burst_id`, duración, auxiliares ejecutados,
máximo concurrente, resultados, defensas y reservas confirmadas. No se ampliará
a tres sesiones hasta reunir al menos diez ráfagas y treinta auxiliares sin
incidentes.

## Rollback operativo

Rollback preferido, sin revertir código:

1. No reiniciar durante un submit. Esperar que el dashboard deje de mostrar
   `opportunity_burst` y revisar que no exista una reserva pendiente.
2. Establecer `OPPORTUNITY_BURST_ENABLED=false` en `.env`.
3. Reiniciar únicamente el worker desde Admin API o Telegram.
4. Confirmar que el siguiente cupo usa `opportunity_queue` secuencial y que no
   aparece un nuevo `burst_id`.

La bandera desactivada conserva exactamente la cadena previa de hasta diez
clientes y 300 segundos. No hay migración PostgreSQL ni datos que revertir.

Si también se necesita retirar el código, revertir el commit que introdujo el
canario, validar Ruff, `compileall`, pytest y dashboard, y reiniciar únicamente
el worker cuando no haya submissions pendientes. Nunca reintentar una reserva
`reservation_unconfirmed` como parte del rollback.
