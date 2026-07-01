# Version de primera reserva automatica - 30/06/2026

Este checkpoint documenta la version del bot que por primera vez llego a ejecutar
una reserva automatica real en produccion. Se considera una version semiexitosa:
el bot detecto cupo, selecciono fecha y hora, resolvio el CAPTCHA, pulso `Reservar`
y luego una pasada posterior confirmo que la etapa ya estaba en `Programado`.

## Version registrada

- Branch: `codex/observer-multiclient-flow`.
- Commit base: `8526612` (`Optimize reservation queue alerts`).
- Estado de trabajo al registrar este checkpoint: habia cambios locales sin commit en:
  - `src/appointment_bot/flows/appointments.py`
  - `src/appointment_bot/flows/login.py`
  - `src/appointment_bot/main.py`
  - `src/appointment_bot/services/run_reporting.py`
  - `src/appointment_bot/services/reservation_timings.py`

Es importante conservar este detalle porque la primera reserva automatica ocurrio con una
version local del arbol de trabajo, no solo con el ultimo commit limpio.

## Evidencia observada

- Fecha de operacion: 30/06/2026, hora de Lima.
- Orden: `order-42334486`.
- Solicitante: GERARDO ADAN TUNI JUAREZ.
- Sede: LIMA-LA VICTORIA.
- Fecha reservada: 15/07/2026.
- Hora reservada: 11:00.
- Log principal: `logs/run-20260630-073410.log`.
- Estado posterior en cola: `reserved_payment_pending`.
- Estado posterior de reserva: `confirmed`.

Archivos de evidencia generados:

- `screenshots/result-available-20260630-083738-eb808447-order-42334486-d20c73d69f2549348a88b4614e6a4c66.png`
- `screenshots/reservation-confirmation-20260630-083738-eb808447-order-42334486-dc4f3a341ec74204b3017959d023cdb0.png`
- `screenshots/process-stages-20260630-083738-eb808447-order-42334486-17645429f5d04ddab4e25bdf539d2742.png`
- `screenshots/process-stages-20260630-093108-a8710f24-order-42334486-ee3e01efef264b188970c3f96883bf09.png`
- `videos/reservations/20260630-143108-GERARDO-ADAN-TUNI-JUAREZ-Contacto-Gerardo.mp4`

## Secuencia confirmada

| Hora | Evento |
| --- | --- |
| 08:37:38 | Inicio de revision para `order-42334486`. |
| 08:38:11 | El portal mostro cupo en LIMA-LA VICTORIA para 15/07/2026 con horas 10:00 y 11:00. |
| 08:38:12 | El bot selecciono 15/07/2026 y 11:00. |
| 08:38:13 | El bot guardo la imagen del panel para resolver CAPTCHA. |
| 08:38:36 | 2captcha resolvio el CAPTCHA de reserva. |
| 08:38:37 | El bot lleno el CAPTCHA y pulso `Reservar`. |
| 08:38:38 | Se guardo screenshot de confirmacion de reserva. |
| 08:38:54 | El bot reporto `RESERVATION_UNCONFIRMED` porque no confirmo `Programado` dentro del timeout. |
| 09:31:15 | Una pasada posterior detecto que `Separa Cita Peritaje` ya estaba en estado `Programado`. |
| 09:31:18 | La corrida termino como `completed`. |

## Resultado

La reserva fue efectiva para el portal, pero la continuidad inmediata del flujo fallo:
despues de pulsar `Reservar`, el bot no logro confirmar la etapa `Programado` dentro del
tiempo de espera de esa misma corrida. Por eso notifico `RESERVATION_UNCONFIRMED`.

La confirmacion llego despues, cuando una nueva pasada encontro que la etapa ya estaba
`Programado`. Esto valida que el envio de la reserva funciono, pero tambien muestra que
la revalidacion posterior necesitaba mas robustez.

## Comportamiento confirmado

- El bot detecta cupos reales para la sede requerida.
- El bot respeta la sede `LIMA-LA VICTORIA`.
- El bot puede seleccionar fecha y hora disponibles.
- El bot puede enviar CAPTCHA de reserva a 2captcha y usar la respuesta.
- El bot puede pulsar `Reservar` en el portal real.
- La cola puede detectar despues que una orden ya quedo en `Programado`.

## Brecha observada

La parte debil fue la confirmacion inmediata despues del click final:

- El portal no dejo la etapa `Programado` visible dentro del timeout de esa corrida.
- El bot marco el resultado como `reservation_unconfirmed`, aunque la reserva luego aparecio confirmada.
- La continuidad debia reforzarse con reintentos de validacion posterior, relogin o una lectura mas tolerante de la tabla de etapas.

## No versionar

No guardar en Git:

- `.env`
- tokens de Telegram
- claves de 2captcha
- contrasenas de clientes
- dumps o backups reales de PostgreSQL
- logs completos con datos sensibles
- screenshots o videos reales de clientes
