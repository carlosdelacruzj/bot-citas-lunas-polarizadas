# Hitos operativos

Este archivo consolida los checkpoints historicos que antes estaban separados
por fecha. No es un roadmap; el estado actual vive en `../project-status.md`.

## 25 de junio de 2026 - Primera deteccion real de cupos

- Sede: `LIMA-LA VICTORIA`.
- Fecha observada: `13/07/2026`.
- Ventana: aproximadamente `09:43:54-09:44:32` Lima.
- Se detectaron horas 10:00, 11:00 y 12:00 para varias ordenes.
- El bot valido opciones seleccionables y envio Telegram `[AVAILABLE]`.
- Confirmo login, panel de citas, sesiones independientes, metricas por ventana
  y valor de usar intervalos cortos para cupos que duran menos de un minuto.
- No probo aun una reserva; solo deteccion real.

## 30 de junio de 2026 - Primera reserva automatica efectiva

- Orden: `order-42334486`.
- Cita: `15/07/2026 11:00`, `LIMA-LA VICTORIA`.
- El bot detecto, selecciono, resolvio CAPTCHA y pulso `Reservar`.
- La corrida inmediata termino `reservation_unconfirmed` porque no vio
  `Programado` dentro del timeout.
- Una pasada posterior encontro la etapa `Programado`; la reserva habia sido
  efectiva.
- El hito probo el envio real y expuso la necesidad de reconciliacion y
  confirmacion posterior robusta.
- Commit base registrado: `8526612`; el evento ocurrio con cambios locales
  adicionales, por lo que no corresponde atribuirlo solo a ese commit.

## 3 de julio de 2026 - Evidencia consolidada de deteccion y CAPTCHA

- Checkpoint base: `1f66865`.
- Consolido detecciones normales y por `reload_probe`, screenshots antes y
  despues, CAPTCHA exacto enviado y resultados `reservation_unconfirmed`.
- Confirmo que CAPTCHA invalido debe reintentarse solo ante rechazo explicito.
- Reafirmo que `reservation_unconfirmed` no equivale a reserva confirmada.
- En ese periodo CAPTCHA llegaba a 33-34 segundos y dominaba el tiempo.
- La evidencia detallada se conserva en
  `../../reports/evidence/history/reservation-optimization-log.md`.

## Evolucion posterior

Despues de estos hitos se agregaron confirmacion estricta, intentos persistidos,
leases con heartbeat, reglas por orden, cola priorizada, migracion modular,
admin API, dashboard y evidencia compacta. El estado consolidado y las metricas
vigentes estan en `../project-status.md`.

## 12 de julio de 2026 - Mejor baseline operativo

- Commit: `a43c6a1`.
- Tag: `best-performing-2026-07-12`.
- Motivo: es el corte con mejor combinacion observada de reservas `registered`,
  ruta normal cercana a 6.5-7.3 segundos con CAPTCHA rapido, cambio de usuario
  de 0-2 segundos, reglas por orden, migracion 9.7 y validacion operativa de
  worker, admin API y dashboard.
- Limite: `slot_lost` y outliers de 2captcha siguen existiendo; la marca no
  significa que la optimizacion haya terminado.
- Uso: si un cambio posterior afecta reservas, comparar primero contra este tag
  y revisar evidencia antes de hacer rollback.

## 9 de agosto de 2026 - Revisión integral y decisión sobre multisesión

- El corte operacional del 1 al 8 de agosto reunió `5,299` runs, `78` intentos
  compatibles, `20 registered` y `57 slot_lost`.
- En seis tandas compartidas hubo seis intentos posteriores y un
  `registered`, proxy de supervivencia secuencial de `16.7%`.
- Se confirmó en código que `OBSERVER_ACTIVE_ORDER_LIMIT=2` no abre dos
  navegadores en paralelo: el observer y la cadena de hasta diez candidatos
  continúan ejecutándose secuencialmente.
- Después de la revisión, el usuario autorizó implementar `OBS-006` como
  canario: detector + un auxiliar, tres clientes totales y reemplazo solo
  después de `registered`. La simulación aislada confirmó ambas rutas de
  reemplazo y el máximo de dos sesiones.
- La bandera `OPPORTUNITY_BURST_ENABLED=false` conserva como rollback la cadena
  secuencial anterior, sin migración ni reversión de datos. Tres sesiones sigue
  siendo una ampliación futura condicionada a evidencia sin defensas ni fallos
  de coordinación.
- Más tarde el mismo día se retiró el límite fijo de tres clientes para alinear
  la ráfaga con el objetivo de maximizar reservas: continúa con cada
  `registered` hasta agotar candidatos compatibles o 300 segundos, conservando
  siempre el techo de dos sesiones y el mismo rollback por bandera.
- El worker se reinició de forma controlada fuera de horario y sin orden activa;
  el comando terminó `applied` y el proceso volvió saludable a
  `outside_hot_window`, ya con la configuración ampliada cargada.
- La revisión inicial actualizó estado, resultado comercial, reportes,
  cadencia, worker y roadmap. La ampliación posterior sí fijó los valores de la
  ráfaga en el `.env` local; ninguna de las dos cambió la autoridad CAPTCHA.
