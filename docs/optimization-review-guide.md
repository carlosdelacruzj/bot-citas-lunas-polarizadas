# Guia de revision de optimizaciones

Este documento es el punto de entrada antes de proponer cambios de ventanas
calientes, frecuencia de requests, CAPTCHA, concurrencia o limpieza de evidencia.
La meta es revisar primero la data compacta y abrir archivos pesados solo cuando
un evento lo justifique.

## Orden de lectura

1. `docs/evidence-index.csv`: indice compacto por evento util.
2. `docs/evidence-summary.md`: resumen digerido para revisar patrones recientes.
3. `docs/reservation-optimization-log.md`: casos de reserva, CAPTCHA y casi-exito.
4. `docs/partial-availability-log.md`: disponibilidad parcial, reglas y `fetch_probe`.
5. Screenshots, HTML sanitizado y CAPTCHAs solo cuando el indice apunte a un caso.

## Como usarlo

- Para revisar si un cambio nuevo respeta el plan inicial, primero filtra
  `docs/evidence-index.csv` por `status`, `detection_origin`, `submission_outcome`
  y `defense_signal`.
- Si el patron necesita contexto humano, abre `docs/evidence-summary.md`.
- Si el caso involucra envio de reserva, CAPTCHA o confirmacion, abre la entrada
  correspondiente en `docs/reservation-optimization-log.md`.
- Si el caso es fecha/hora parcial o una senal `fetch_probe`, abre
  `docs/partial-availability-log.md`.
- Abre HTML, screenshots o CAPTCHAs solo desde las rutas de `evidence_paths`.

## Criterio para optimizar

- No reducir evidencia mientras se esten calibrando ventanas calientes, frecuencia
  o concurrencia.
- Separar deteccion de cupos, envio de reserva, confirmacion y senales de defensa.
- Tratar `fetch_probe` como evidencia diagnostica, no como autorizacion directa
  para reservar.
- Comparar cualquier ajuste agresivo contra `defense_signal`: `http_429`,
  `http_403`, `access_denied`, `unexpected_captcha`, `session_closed` o `network`.
- Si el portal muestra mensaje de exito, se permite avanzar como `registered`;
  la confirmacion posterior de `Programado` queda como auditoria.

## Siguientes pasos de pulcritud tecnica

1. Reducir `src/appointment_bot/db/orders.py` por subdominio:
   pagos/contactos, estado de orden, credenciales y promocion de ordenes.
2. Reducir `src/appointment_bot/worker/queue_runtime.py`:
   separar recorrido de cola rapida, ejecucion de una orden y decisiones de
   resultado compartidas con el worker.
3. Separar tests de flujo restantes:
   mantener `test_appointments.py` para lectura/seleccion y crear una suite
   dedicada para `programs.py`.

## Pulcritud tecnica completada

- `src/appointment_bot/flows/reservation_captcha.py` fue eliminado.
- La captura de imagen vive en `reservation_captcha_capture.py`.
- El refresh/reload vive en `reservation_captcha_refresh.py`.
- El llenado de CAPTCHA y click en `Reservar` vive en `reservation_submit.py`.
- La lectura/cierre de respuesta del portal vive en `reservation_portal.py`.
- Los tests de CAPTCHA de reserva viven en `tests/test_reservation_captcha.py`.
- `src/appointment_bot/services/postgres_database.py` fue eliminado.
- La conexion, migracion y helpers comunes viven en `db/common.py`,
  `db/connection.py`, `db/pool.py` y `db/migrations.py`.
- Ordenes, credenciales, pagos, leases de orden y estado de orden viven en
  `db/orders.py`.
- Reservas e intentos de reserva viven en `db/reservations.py`.
- Corridas, screenshots, checks y metricas de ventanas viven en
  `db/runs.py`.
- Reservas e intentos de reserva viven en `db/reservations.py`.
- Estado y lease del worker viven en `db/worker_state.py`.
- Comandos persistidos del worker viven en `db/worker_commands.py`.
- Limpieza historica de PostgreSQL vive en `db/cleanup.py`.
- Ventanas calientes, extension de ventana, cutoff diario y etiquetas de
  ventana viven en `worker/windows_runtime.py`.
- Lease del proceso continuo, token de propietario y renovacion periodica viven
  en `worker/lease.py`.
- Clasificacion de defensas del portal, errores de red y esperas de recovery
  viven en `worker/recovery.py`.
- Configuracion derivada para ejecutar observer, confirmacion y ordenes vive en
  `worker/execution.py`.
- Clasificacion y persistencia de resultados de ordenes monitoreadas vive en
  `worker/order_results.py`.
- Resultado del observer puro, confirmacion secundaria y deduplicacion de firma
  viven en `worker/observer_results.py`.
- Callbacks de estado, alertas inmediatas y racha de `unavailable` viven en
  `worker/state_callbacks.py`.
- Retencion/borrado de evidencias diferidas vive en `worker/deferred_reports.py`.
- Backoff y politica de errores de orden, observer, cola rapida y fallos
  inesperados vive en `worker/error_policy.py`.
- Cola rapida, leases de orden y ejecucion transicional de ordenes viven en
  `worker/queue_runtime.py`.
- El ciclo principal de `worker/continuous_worker.py` quedo dividido en arranque,
  iteracion, seleccion de trabajo disponible y cierre controlado.
- `_monitor_order` quedo reducido a ejecutar la orden, registrar el reporte y
  aplicar la decision devuelta por `worker_order_results.py`.
- `worker/continuous_worker.py` conserva la orquestacion del proceso continuo, leases,
  seleccion de trabajo, pausas, ventanas calientes, salud y metricas de ventana.
- `reservation_engine/runner.py` quedo como orquestador de corrida, navegador,
  video, reporte final y errores.
- Login, seleccion de tramite y bifurcacion entre etapa ya terminada o panel de
  cita viven en `reservation_engine/session_flow.py`.
- Monitoreo de disponibilidad, reload probe, diagnosticos por intento y envio de
  reserva viven en `reservation_engine/monitor.py`.
- Limpieza de evidencias no confirmadas y contexto de cliente viven en
  `reservation_engine/results.py`.
- Notificacion/persistencia de multiples tramites vive en
  `reservation_engine/program_notifications.py`.
- `reservation_engine/appointments.py` conserva apertura de panel, sede,
  constantes y helpers compartidos de formulario.
- Lectura de disponibilidad, snapshots estables y clasificacion de disponibilidad
  viven en `reservation_engine/appointment_reader.py`.
- Seleccion de fecha/hora y validacion pre-envio viven en
  `reservation_engine/appointment_selection.py`.
- La consulta directa `fetch_probe` vive en
  `reservation_engine/appointment_fetch_probe.py`.
- CAPTCHA, refresh, submit y lectura de respuesta del portal viven en
  `reservation_engine/reservation_captcha_*`,
  `reservation_engine/reservation_submit.py`,
  `reservation_engine/reservation_portal.py` y
  `reservation_engine/reservation_flow.py`.
- Finalizacion de corridas, persistencia historica y conversion a `RunReport`
  viven en `reports/run_reporting.py`.
- Resumen compacto de evidencia vive en `reports/evidence.py`.
- Bitacoras de optimizacion y disponibilidad parcial viven en
  `reports/optimization.py`.
- Fichas de estado y reporte diario viven en `reports/status.py`.

## Regenerar resumen manual

```powershell
appointment-bot-client evidence-summary --days 7 --output-dir reports/evidence
```

El comando genera CSV y Markdown desde PostgreSQL para revisar un rango sin
releer bitacoras largas.
