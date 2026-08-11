# Reservation Engine

## Evidencia de cupos y CAPTCHA

La ejecución normal y el observador usan el mismo encuadre centrado del panel de
citas después de seleccionar fecha y hora y comprobar que el CAPTCHA cargó. Cada
detección conserva una sola captura del modal.

Después de registrar cada resultado, la primera captura de una combinación de
fecha y hora se copia en `screenshots/DD-MM-YYYY/cupos-unicos/`. El observador y
las órdenes normales comparten la carpeta y la regla: si el cupo ya existe para
esa fecha y hora, no se genera otra copia.

El observador conserva además cinco muestras consecutivas del CAPTCHA original
extraído del HTML. Esas muestras son evidencia independiente y no generan cinco
capturas del modal ni se sustituyen por recortes de pantalla.

Una reobservación posterior a `slot_lost` puede producir más de un cupo dentro
de la misma ejecución. Cada captura debe conservar su propia fecha y hora antes
de archivar; nunca se debe nombrar la imagen del primer intento con los datos
del intento recuperado. Todos los cupos distintos de esa secuencia participan
en el archivo compartido y mantienen la misma deduplicación por fecha y hora.

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
- `reservation_engine.appointment_modal_styles`
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
