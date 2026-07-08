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

1. Reducir `src/appointment_bot/services/continuous_worker.py`:
   separar ventanas calientes, lease, ciclo principal, backoff/recovery y
   ejecucion de cola/observer.
2. Partir `src/appointment_bot/services/session_runner.py`:
   separar preparacion de sesion/video, login y tramite, monitoreo de
   disponibilidad, y finalizacion/reporte.
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
- La conexion, migracion y helpers comunes viven en `postgres_common.py`.
- Ordenes, credenciales, pagos, leases de orden y estado de orden viven en
  `postgres_orders.py`.
- Reservas e intentos de reserva viven en `postgres_reservations.py`.
- Corridas, screenshots, checks y metricas de ventanas viven en
  `postgres_runs.py`.
- Estado y lease del worker viven en `postgres_worker.py`.
- Limpieza historica de PostgreSQL vive en `postgres_cleanup.py`.

## Regenerar resumen manual

```powershell
appointment-bot-client evidence-summary --days 7 --output-dir reports/evidence
```

El comando genera CSV y Markdown desde PostgreSQL para revisar un rango sin
releer bitacoras largas.
