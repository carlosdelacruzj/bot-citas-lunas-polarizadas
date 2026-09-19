# Resumen digerido de evidencia

Este archivo es la lectura rapida antes de abrir HTML, screenshots o logs largos.

## Corte y cobertura
- Generado: `2026-09-19 16:42:28 America/Lima`.
- Ventana solicitada: mes activo 2026-09 (America/Lima).
- Rango real de eventos indexados: `2026-09-01 09:04:52` a `2026-09-19 16:39:48` (America/Lima).
- Cobertura temporal verificable: 2936/2936 eventos con hora de cierre.
- Fuente: filas sanitizadas del indice compacto de evidencia.

## Limites
- Es un snapshot generado; no representa el runtime ni PostgreSQL en vivo.
- Incluye solo eventos utiles definidos por la politica de evidencia, no todos los runs.
- Una ruta indexada no prueba que el artefacto siga retenido; verificarla antes de citarla.
- La ausencia de un evento no demuestra que el portal no haya sido consultado.

## Totales
- Eventos indexados: 2936
- Reservas registradas: 139
- Reservas no confirmadas: 2
- Disponibilidades completas: 369
- Disponibilidades parciales: 2372
- Senales de defensa: 14

## Origen de deteccion
- fetch_probe: 2444
- normal: 480
- reload_probe: 4
- slot_lost_reobservation: 8

## Ultimos eventos utiles
- 2026-09-19 16:39:48 | order-*** | partial | fetch_probe | 06/11/2026 08:00 | blocked_by_order_rule
- 2026-09-19 16:39:31 | order-*** | partial | fetch_probe | 06/11/2026 08:00 | blocked_by_order_rule
- 2026-09-19 16:39:13 | order-*** | partial | fetch_probe | 06/11/2026 08:00 | blocked_by_order_rule
- 2026-09-19 16:38:57 | order-*** | partial | fetch_probe | 06/11/2026 08:00 | blocked_by_order_rule
- 2026-09-19 16:38:43 | order-*** | partial | fetch_probe | 06/11/2026 08:00 | blocked_by_order_rule
- 2026-09-19 16:38:27 | order-*** | partial | fetch_probe | 06/11/2026 08:00 | blocked_by_order_rule
- 2026-09-19 16:38:10 | order-*** | partial | fetch_probe | 06/11/2026 08:00 | blocked_by_order_rule
- 2026-09-19 16:37:55 | order-*** | partial | fetch_probe | 06/11/2026 08:00 | blocked_by_order_rule
- 2026-09-19 16:37:40 | order-*** | partial | fetch_probe | 06/11/2026 08:00 | blocked_by_order_rule
- 2026-09-19 16:37:26 | order-*** | partial | fetch_probe | 06/11/2026 08:00 | blocked_by_order_rule

## Senales de defensa
- 2026-09-19 15:14:50 | order-*** | network | Locator.wait_for: Timeout 5000ms exceeded.
Call log:
  - waiting for locator("#MainContent_idUcitas_btgSiguiente") to be visible
    14 × locator resolved to hidden <input type="submit" value="Reservar Cita" id="MainContent_idUcitas_btgSiguiente" onclick="if(this.disabled){return false;};" name="ctl00$MainContent$idUcitas$btgSiguiente" class="btn btn-primary btn-lg px-5 rounded-pill shadow"/>
- 2026-09-19 15:08:33 | order-*** | network | Locator.wait_for: Timeout 5000ms exceeded.
Call log:
  - waiting for locator("#MainContent_idUcitas_btgSiguiente") to be visible
    14 × locator resolved to hidden <input type="submit" value="Reservar Cita" id="MainContent_idUcitas_btgSiguiente" onclick="if(this.disabled){return false;};" name="ctl00$MainContent$idUcitas$btgSiguiente" class="btn btn-primary btn-lg px-5 rounded-pill shadow"/>
- 2026-09-19 15:04:11 | order-*** | network | Locator.wait_for: Timeout 5000ms exceeded.
Call log:
  - waiting for locator("#MainContent_idUcitas_btgSiguiente") to be visible
    14 × locator resolved to hidden <input type="submit" value="Reservar Cita" id="MainContent_idUcitas_btgSiguiente" onclick="if(this.disabled){return false;};" name="ctl00$MainContent$idUcitas$btgSiguiente" class="btn btn-primary btn-lg px-5 rounded-pill shadow"/>
- 2026-09-18 11:18:30 | order-*** | network | Locator.wait_for: Timeout 30000ms exceeded.
Call log:
  - waiting for locator("#MainContent_idUcitas_cbosede") to be visible
- 2026-09-17 09:30:36 | order-*** | http_403 | La reserva fue confirmada por mensaje de exito del portal.
- 2026-09-12 10:18:49 | order-*** | network | Locator.wait_for: Timeout 30000ms exceeded.
Call log:
  - waiting for locator("#MainContent_idUcitas_cbosede") to be visible
- 2026-09-09 13:29:11 | order-*** | http_403 | La reserva fue confirmada por mensaje de exito del portal.
- 2026-09-09 11:36:26 | order-*** | http_403 | La reserva fue confirmada por mensaje de exito del portal.
- 2026-09-09 11:00:08 | order-*** | http_403 | La reserva fue confirmada por mensaje de exito del portal.
- 2026-09-09 10:45:51 | order-*** | http_403 | La reserva fue confirmada por mensaje de exito del portal.

## Lectura recomendada
- Usar `docs/evidence-index.csv` para filtrar el caso exacto.
- Abrir las rutas de evidencia solo cuando este resumen apunte a un evento.
- Comparar cambios contra `docs/contracts/optimization.md`.
