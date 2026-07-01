# Bitacora de optimizacion de reservas

Archivo curado y automatico con casos de exito o casi-exito. No reemplaza
PostgreSQL ni los logs completos; resume tiempos y evidencia util para mejorar el
flujo sin guardar nombres completos ni credenciales.

## 2026-06-20 01:12:29 - worker-lease-conflict - operational

- Run: backfill-20260620-worker-lease-conflict
- Corrida/attempt: arranque de worker continuo
- Sede: no aplicaba
- Cita observada: no aplicaba
- Origen deteccion: operativo
- Resultado: El worker fallo por `Another host owns the continuous worker lease`.
- Confirmacion posterior: No aplicaba.
- Tiempos:
  - Cupo detectado -> fin reserva: no aplicaba
  - Seleccion fecha/hora: no aplicaba
  - Imagen CAPTCHA: no aplicaba
  - 2captcha: no aplicaba
  - Llenar CAPTCHA -> click: no aplicaba
  - Click -> respuesta portal: no aplicaba
  - Click -> screenshot confirmacion: no aplicaba
- Contexto operativo:
  - Modo monitoreo: continuous worker
  - Reload probe: no aplicaba
  - Refresco sede confirmado: no aplicaba
  - Refresco sede cambio opciones: no aplicaba
  - Refresco sede elapsed: no aplicaba
- Evidencia:
  - Screenshot principal: no registrado
  - Log relacionado: logs/run-20260620-011227.log
- Observacion tecnica:
  - Caso usado para optimizar estabilidad: un segundo host podia impedir el worker real. La mejora posterior fue tratar el lease como condicion controlada y evitar hosts duplicados.

## 2026-06-23 09:57:06 - order-40342829 - completed

- Run: backfill-20260623-programado-order-40342829
- Corrida/attempt: revision de cola
- Sede: no registrada en el evento final
- Cita observada: Programado, fecha/hora no visible en la linea final
- Origen deteccion: process-stages
- Resultado: La etapa `Separa Cita Peritaje` ya estaba en `Programado`; no habia una cita pendiente por reservar.
- Confirmacion posterior: Programado detectado en esta corrida.
- Tiempos:
  - Cupo detectado -> fin reserva: no aplicaba
  - Seleccion fecha/hora: no aplicaba
  - Imagen CAPTCHA: no aplicaba
  - 2captcha: no aplicaba
  - Llenar CAPTCHA -> click: no aplicaba
  - Click -> respuesta portal: no aplicaba
  - Click -> screenshot confirmacion: no aplicaba
- Contexto operativo:
  - Modo monitoreo: cola
  - Reload probe: no
  - Refresco sede confirmado: no registrado
  - Refresco sede cambio opciones: no registrado
  - Refresco sede elapsed: no registrado
  - Cambio de usuario: orden anterior termino como `Sin Cupos`; esta orden aparecio `Programado` sin que el bot detectara cupo ni enviara reserva en esa ventana.
- Evidencia:
  - Screenshot principal: screenshots/process-stages-20260623-095657-0a9b6b0c-order-40342829-4d515b59994346b8b31ce6051aeb5ad9.png
  - Log relacionado: logs/run-20260623-074302.log
- Observacion tecnica:
  - Caso importante para optimizacion: el estado cambio a `Programado` sin que el bot observara el cupo ni ejecutara el cambio. Esto sugiere que pudo existir una disponibilidad no capturada, una accion externa o una confirmacion previa que solo se hizo visible al revisar etapas.

## 2026-06-24 16:20:40 - order-45244121 - completed

- Run: backfill-20260624-programado-order-45244121
- Corrida/attempt: revision de cola dentro de ventana 15:55-16:30
- Sede: no registrada en el evento final
- Cita observada: 13/07/2026 11:00
- Origen deteccion: process-stages
- Resultado: La etapa `Separa Cita Peritaje` ya estaba en `Programado`; no habia una cita pendiente por reservar.
- Confirmacion posterior: Programado detectado en esta corrida.
- Tiempos:
  - Cupo detectado -> fin reserva: no aplicaba
  - Seleccion fecha/hora: no aplicaba
  - Imagen CAPTCHA: no aplicaba
  - 2captcha: no aplicaba
  - Llenar CAPTCHA -> click: no aplicaba
  - Click -> respuesta portal: no aplicaba
  - Click -> screenshot confirmacion: no aplicaba
- Contexto operativo:
  - Modo monitoreo: observer / cola
  - Reload probe: no
  - Refresco sede confirmado: no registrado
  - Refresco sede cambio opciones: no registrado
  - Refresco sede elapsed: no registrado
  - Cambio de usuario: siguiente orden inicio a los 0.040s; la cola podia cambiar de usuario muy rapido cuando una orden ya estaba `Programado`.
- Evidencia:
  - Screenshot principal: screenshots/process-stages-20260624-162029-c2f2c9f1-order-45244121-e62f3c3cf89043be92621b6e1ef24008.png
  - Log relacionado: logs/run-20260624-162025.log
- Observacion tecnica:
  - Caso importante porque el estado `Programado` aparecio dentro de una ventana caliente sin que el bot hubiera detectado cupo ni hecho la reserva. Debe considerarse al evaluar huecos entre consultas y cambios externos.

## 2026-06-24 16:20:50 - order-74705542 - completed

- Run: backfill-20260624-programado-order-74705542
- Corrida/attempt: revision de cola dentro de ventana 15:55-16:30
- Sede: no registrada en el evento final
- Cita observada: 11/07/2026 11:00
- Origen deteccion: process-stages
- Resultado: La etapa `Separa Cita Peritaje` ya estaba en `Programado`; no habia una cita pendiente por reservar.
- Confirmacion posterior: Programado detectado en esta corrida.
- Tiempos:
  - Cupo detectado -> fin reserva: no aplicaba
  - Seleccion fecha/hora: no aplicaba
  - Imagen CAPTCHA: no aplicaba
  - 2captcha: no aplicaba
  - Llenar CAPTCHA -> click: no aplicaba
  - Click -> respuesta portal: no aplicaba
  - Click -> screenshot confirmacion: no aplicaba
- Contexto operativo:
  - Modo monitoreo: observer / cola
  - Reload probe: no
  - Refresco sede confirmado: no registrado
  - Refresco sede cambio opciones: no registrado
  - Refresco sede elapsed: no registrado
  - Cambio de usuario: order-45244121 -> order-74705542 en alrededor de 0.040s; ambas ordenes terminaron `Programado`.
- Evidencia:
  - Screenshot principal: screenshots/process-stages-20260624-162041-20064b89-order-74705542-a3feea1f2a2c4f428335bc5fbd7348ba.png
  - Log relacionado: logs/run-20260624-162025.log
- Observacion tecnica:
  - Segundo caso consecutivo de `Programado` no originado por una deteccion visible de cupo. Sirve para comparar cambios externos contra cadencia del bot y para validar que la lectura de etapas era util aunque no capturara el momento exacto del cupo.

## 2026-06-24 - fetch-probe-modal - technical

- Run: backfill-20260624-fetch-probe
- Corrida/attempt: cambio tecnico de deteccion
- Sede: LIMA-LA VICTORIA
- Cita observada: no hubo positivo registrado antes del 25
- Origen deteccion: fetch_probe
- Resultado: Se agrego la lectura tipo ASP.NET/fetch con modal abierto y sede seleccionada para reducir falsos `Sin Cupos`.
- Confirmacion posterior: No aplicaba.
- Tiempos:
  - Cupo detectado -> fin reserva: no aplicaba
  - Seleccion fecha/hora: no aplicaba
  - Imagen CAPTCHA: no aplicaba
  - 2captcha: no aplicaba
  - Llenar CAPTCHA -> click: no aplicaba
  - Click -> respuesta portal: no aplicaba
  - Click -> screenshot confirmacion: no aplicaba
- Contexto operativo:
  - Modo monitoreo: normal con respaldo fetch
  - Reload probe: no aplicaba
  - Refresco sede confirmado: no registrado
  - Refresco sede cambio opciones: no registrado
  - Refresco sede elapsed: no registrado
- Evidencia:
  - Screenshot principal: no registrado
  - Referencia tecnica: `fetch_probe` / `modal_must_remain_open` en detalles de disponibilidad.
- Observacion tecnica:
  - Hito usado para optimizacion: el fetch probe no debia reservar por si solo, pero servia para detectar fechas/horas cuando la lectura visible del modal podia quedar corta. No se encontro un positivo anterior al 25 con este origen.

## 2026-06-24 18:37:33 - daily-cutoff-resume - operational

- Run: backfill-20260624-daily-cutoff-resume
- Corrida/attempt: cierre diario del worker
- Sede: no aplicaba
- Cita observada: no aplicaba
- Origen deteccion: operativo
- Resultado: El bootstrap registro que el worker esperaria hasta 07:30 despues del corte diario.
- Confirmacion posterior: No aplicaba.
- Tiempos:
  - Cupo detectado -> fin reserva: no aplicaba
  - Seleccion fecha/hora: no aplicaba
  - Imagen CAPTCHA: no aplicaba
  - 2captcha: no aplicaba
  - Llenar CAPTCHA -> click: no aplicaba
  - Click -> respuesta portal: no aplicaba
  - Click -> screenshot confirmacion: no aplicaba
- Contexto operativo:
  - Modo monitoreo: daily_cutoff
  - Reload probe: no aplicaba
  - Refresco sede confirmado: no aplicaba
  - Refresco sede cambio opciones: no aplicaba
  - Refresco sede elapsed: no aplicaba
- Evidencia:
  - Screenshot principal: no registrado
  - Log relacionado: logs/worker-bootstrap-20260624.log
- Observacion tecnica:
  - Hito usado para optimizar huella y estabilidad: despues de las 18:00 no debian iniciar nuevas consultas, y el reinicio quedaba diferido hasta 07:30 o reinicio de PC.

## 2026-06-25 09:44:32 - deteccion-multicliente - available

- Run: backfill-20260625-deteccion-cupos
- Corrida/attempt: 1 por orden durante la ventana efectiva
- Sede: LIMA-LA VICTORIA
- Cita observada: 13/07/2026 10:00, 11:00 y 12:00
- Origen deteccion: normal
- Resultado: Se detectaron opciones reales de fecha y hora con AUTO_RESERVE desactivado.
- Confirmacion posterior: No aplicaba; no se intento reservar en esta version.
- Tiempos:
  - Cupo detectado -> fin reserva: no aplicaba
  - Seleccion fecha/hora: alrededor de 1.8s a 1.9s por orden despues de abrir panel
  - Imagen CAPTCHA: no aplicaba
  - 2captcha: no aplicaba
  - Llenar CAPTCHA -> click: no aplicaba
  - Click -> respuesta portal: no aplicaba
  - Click -> screenshot confirmacion: no aplicaba
- Contexto operativo:
  - Modo monitoreo: normal
  - Reload probe: no
  - Refresco sede confirmado: no registrado
  - Refresco sede cambio opciones: no registrado
  - Refresco sede elapsed: no registrado
  - Cambio de usuario: order-70569448 -> order-09329652 -> order-42334486 -> order-70569448 -> order-09329652 durante 09:43:50 a 09:44:32
- Evidencia:
  - Screenshot principal: screenshots/result-available-20260625-094350-30b436e5-order-70569448-0d535a3ac0f74fb2bd2f78ac832da2a8.png
  - Screenshot adicional: screenshots/result-available-20260625-094359-73d1ecf7-order-09329652-e28365ea7a46479dabc91d928a119307.png
  - Screenshot adicional: screenshots/result-available-20260625-094407-c4622ac0-order-42334486-1f6904e5164d490e956a338b17d1cf9e.png
- Observacion tecnica:
  - El flujo normal detecto cupos reales y la ventana duro menos de un minuto. La mejora principal era reducir el intervalo entre consultas dentro de ventanas calientes.

## 2026-06-30 08:39:00 - order-42334486 - reservation_unconfirmed

- Run: 20260630-083738-eb808447
- Corrida/attempt: 2
- Sede: LIMA-LA VICTORIA
- Cita observada: 15/07/2026 11:00
- Origen deteccion: normal
- Resultado: CAPTCHA resuelto, click en Reservar enviado, confirmacion inmediata no validada.
- Confirmacion posterior: Programado detectado en una pasada posterior alrededor de 09:31:15.
- Tiempos:
  - Cupo detectado -> fin reserva: alrededor de 48.5s desde deteccion disponible hasta fin de corrida
  - Seleccion fecha/hora: alrededor de 1.8s
  - Imagen CAPTCHA: alrededor de 0.2s
  - 2captcha: alrededor de 23.0s
  - Llenar CAPTCHA -> click: alrededor de 0.1s
  - Click -> respuesta portal: alrededor de 0.3s
  - Click -> screenshot confirmacion: alrededor de 1.3s
- Contexto operativo:
  - Modo monitoreo: normal
  - Reload probe: no
  - Refresco sede confirmado: no registrado
  - Refresco sede cambio opciones: no registrado
  - Refresco sede elapsed: no registrado
  - Cambio de usuario: order-70569448 -> order-42334486 en alrededor de 6.5s
- Evidencia:
  - Screenshot principal: screenshots/result-available-20260630-083738-eb808447-order-42334486-d20c73d69f2549348a88b4614e6a4c66.png
  - Screenshot adicional: screenshots/reservation-confirmation-20260630-083738-eb808447-order-42334486-dc4f3a341ec74204b3017959d023cdb0.png
  - Screenshot adicional: screenshots/process-stages-20260630-083738-eb808447-order-42334486-17645429f5d04ddab4e25bdf539d2742.png
- Observacion tecnica:
  - El flujo normal detecto el cupo; reload_probe no fue necesario. El tramo mas lento fue 2captcha. La confirmacion inmediata quedo debil y requirio revalidacion posterior.

## 2026-06-30 20:33:22 - observer-reload-probe - unavailable

- Run: backfill-20260630-observer-reload-probe
- Corrida/attempt: revision manual observer
- Sede: LIMA-LA VICTORIA
- Cita observada: Sin Cupos
- Origen deteccion: reload_probe
- Resultado: No se detectaron cupos, pero la prueba confirmo que el observer recargaba y re-seleccionaba sede antes de confirmar `Sin Cupos`.
- Confirmacion posterior: No aplicaba.
- Tiempos:
  - Cupo detectado -> fin reserva: no aplicaba
  - Seleccion fecha/hora: no aplicaba
  - Imagen CAPTCHA: no aplicaba
  - 2captcha: no aplicaba
  - Llenar CAPTCHA -> click: no aplicaba
  - Click -> respuesta portal: no aplicaba
  - Click -> screenshot confirmacion: no aplicaba
- Contexto operativo:
  - Modo monitoreo: observer manual
  - Reload probe: si
  - Refresco sede confirmado: no registrado
  - Refresco sede cambio opciones: no registrado
  - Refresco sede elapsed: no registrado
- Evidencia:
  - Screenshot principal: no registrado
  - Log relacionado: logs/run-20260630-203306.log
- Observacion tecnica:
  - Este caso no fue exito de reserva; se conserva como hallazgo tecnico porque explico la brecha del reload_probe y la necesidad de mantener paridad con la seleccion real de sede.
## 2026-07-01 12:03:52 - order-70569448 - captcha_invalid

- Run: 20260701-120135-471698c3
- Corrida/attempt: 3
- Sede: LIMA-LA VICTORIA
- Cita observada: 06/07/2026 08:00
- Origen deteccion: reload_probe
- Resultado: CAPTCHA enviado, el portal respondio con mensaje de codigo valido de captcha y no confirmo Programado.
- Confirmacion posterior: No confirmada; la orden sigue lista para reintento.
- Tiempos:
  - Cupo detectado -> fin reserva: 63.485s
  - Seleccion fecha/hora: 1.766s
  - Imagen CAPTCHA: 0.235s
  - 2captcha: 33.609s
  - Llenar CAPTCHA -> click: 0.218s
  - Click -> respuesta portal: 0.110s
  - Click -> screenshot confirmacion: 10.750s
- Contexto operativo:
  - Modo monitoreo: normal
  - Reload probe: si
  - Refresco sede confirmado: si
  - Refresco sede cambio opciones: si
  - Refresco sede elapsed: 641ms
- Evidencia:
  - Screenshot principal: screenshots\reservation-confirmation-***-120135-471698c3-order-***-5cf7f2011a64470dbb8b5859499ff39e.png
  - Screenshot adicional: screenshots\process-stages-***-120135-471698c3-order-***-e75eb9dea878470b938aa8aae0f12b1f.png
  - Screenshot adicional: screenshots\result-available-***-120135-471698c3-order-***-5971552f6194480f9baf4ca35937541a.png
- Observacion tecnica:
  - El reload_probe aporto el cupo: antes del reload habia Sin Cupos y despues aparecio 06/07/2026 08:00 con 30 cupos. El tramo mas lento fue 2captcha (33.609s), pero la respuesta fue rechazada por el portal.
