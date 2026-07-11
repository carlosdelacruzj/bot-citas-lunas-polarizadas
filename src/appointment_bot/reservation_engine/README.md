# Reservation Engine

Estructura futura para el motor de reservas: Playwright, login, lectura de
cupos, seleccion de fecha/hora, CAPTCHA, envio y confirmacion.

Desde el paso 9.5 contiene la implementacion del motor Playwright del portal:

- `reservation_engine.flow`
- `reservation_engine.portal`
- `reservation_engine.submit`
- `reservation_engine.runner`
- `reservation_engine.session_flow`
- `reservation_engine.monitor`
- `reservation_engine.observer`
- `reservation_engine.appointments`
- `reservation_engine.appointment_reader`
- `reservation_engine.appointment_selection`
- `reservation_engine.appointment_fetch_probe`
- `reservation_engine.login`
- `reservation_engine.programs`
- `reservation_engine.stages`
- `reservation_engine.reservation_captcha_capture`
- `reservation_engine.reservation_captcha_refresh`
- `reservation_engine.reservation_controls`
- `reservation_engine.reservation_submit`
- `reservation_engine.reservation_portal`
- `reservation_engine.reservation_flow`
- `reservation_engine.timings`
- `reservation_engine.results`
- `reservation_engine.program_notifications`

Desde el paso 9.7 se retiraron las rutas antiguas `flows/*`,
`services/session_*`, `services/reservation_flow.py`,
`services/reservation_timings.py` y `services/observer.py`. Los consumidores
internos deben importar directamente desde `appointment_bot.reservation_engine.*`.

No cambiar aqui contratos de PostgreSQL, API, notificaciones o reportes.
