# Reservation Engine

Estructura futura para el motor de reservas: Playwright, login, lectura de
cupos, seleccion de fecha/hora, CAPTCHA, envio y confirmacion.

Desde el paso 9.1 contiene fachadas publicas de compatibilidad:

- `reservation_engine.flow`
- `reservation_engine.portal`
- `reservation_engine.submit`

Estas rutas reexportan implementacion existente desde `flows/` y `services/`.
No reemplazan todavia a los imports actuales ni cambian el comportamiento de
Playwright, CAPTCHA o reserva.
