# Incidente de backoff por fechas fuera de rango del 24-07-2026

> Postmortem historico. La restriccion horaria descrita en el corte fue retirada
> posteriormente; solo el roadmap vigente puede mantener trabajo pendiente.

## Estado

Incidente diagnosticado. Mejora implementada y cargada en el worker el
24-07-2026 a las 17:35, pendiente de confirmacion con una nueva aparicion real
de varias fechas fuera de rango.

Este documento conserva el motivo del cambio antes de modificar la logica. Si la
correccion produce una regresion, debe usarse como referencia para distinguir el
comportamiento que se queria corregir de las protecciones que deben conservarse.

## Resumen

La orden `order-***`, correspondiente a un cliente identificado y oculto, permitia citas
desde el 05-08-2026 hasta el 18-08-2026.

El 24-07-2026 a las 16:52 hora Lima, el portal mostro fechas y horas disponibles,
pero todas estaban fuera del rango:

- 21-08-2026: 09:00, 10:00, 11:00 y 12:00;
- 19-08-2026: 12:00.

El bot descarto correctamente esos horarios. Sin embargo, la captura tecnica de
evidencia comparo dos selecciones distintas y genero el error:

```text
La sede, fecha u hora seleccionadas cambiaron antes de enviar la reserva.
```

El error activo un backoff general de 1,800 segundos. El worker permanecio vivo,
pero no reviso nuevas oportunidades durante 30 minutos.

## Linea de tiempo

Todas las horas siguientes usan `America/Lima`.

| Hora | Evento |
| --- | --- |
| 16:52:26 | Comenzo el run `20260724-165226-a106493e`. |
| 16:52:29 | El portal presento 19-08-2026 y 21-08-2026. |
| 16:52:30-16:52:32 | El bot recorrio los horarios y los descarto por la regla de fecha maxima. |
| 16:52:34 | Se guardo la captura de error. |
| 16:52:37 | El run termino como `error`, sin intento de reserva. |
| 16:52:38 | Comenzo el backoff de 30 minutos. |
| 17:22:38 | El bot volvio a ingresar al portal. |
| 17:22:50 | Detecto que la etapa ya estaba `Programado` para el 12-08-2026 a las 12:00. |

La cita del 12-08-2026 esta dentro del rango, pero fue registrada por un tercero
durante la espera. El bot solamente reconocio el estado `Programado` cuando
termino el backoff.

## Evidencia confirmada

- `/health` mostro `worker_running=true` y `reason=backoff`: el proceso no
  estaba apagado.
- `worker_state` registro la orden, el error y `next_check_at` treinta minutos
  despues.
- El run fallo con `error_type=AppointmentWorkflowUnavailable`.
- El run guardo `reservation_attempted=false` y
  `reservation_confirmed=false`.
- No se resolvio CAPTCHA y no aparece `Clicking reservation button` para Juan.
- No existe una fila de `reservation_attempts` para esta ejecucion.
- El primer run posterior al backoff termino `completed` al encontrar la etapa
  `Programado` con fecha `12/08/2026 12:00`.
- La orden termino `reserved_payment_pending`, con estado operativo
  `programmed` y sin `next_allowed_at`.

La evidencia no permite afirmar que el 12-08-2026 estuviera visible exactamente
a las 16:52. En esa lectura concreta el portal solamente mostro 19-08-2026 y
21-08-2026. Lo comprobable es que el backoff incorrecto impidio nuevas
revisiones durante los treinta minutos siguientes.

## Causa tecnica

El recorrido de `select_available_appointment()` debe seguir buscando despues
de encontrar una fecha fuera de rango, porque una opcion posterior todavia
puede ser compatible. Ese comportamiento debe conservarse.

El defecto aparece cuando hay varias fechas no compatibles:

1. `appointment_selection.py` guarda el primer horario bloqueado como
   `blocked_evidence_result`.
2. El recorrido continua para buscar una opcion compatible.
3. Al cambiar de fecha, la seleccion visible del formulario deja de coincidir
   con la fecha y hora almacenadas en el primer resultado.
4. `monitor.py` envia el resultado a
   `capture_blocked_captcha_evidence()`.
5. La validacion previa a la captura compara la seleccion actual contra la
   seleccion almacenada y lanza `AppointmentWorkflowUnavailable`.
6. El resultado pierde su clasificacion
   `partial / blocked_by_order_rule` y pasa a ser un error generico.
7. `WorkerErrorPolicy.apply_order_backoff()` detiene el avance de la cola
   durante `ERROR_BACKOFF_SECONDS=1800`.

En este incidente se conservo como evidencia 21-08-2026 12:00, pero al terminar
el recorrido el formulario estaba en 19-08-2026 12:00. Esa diferencia produjo
el error.

## Mejora acordada

La correccion debe aplicarse en dos niveles.

### 1. Mantener sincronizada la evidencia bloqueada

- Recorrer todas las fechas y horas antes de concluir que ninguna es compatible.
- No terminar en el primer horario fuera de rango, porque podria existir uno
  permitido mas adelante.
- Si no existe una opcion compatible, volver a seleccionar explicitamente la
  fecha y hora elegidas para evidencia.
- Leer otra vez el formulario y construir el resultado desde esa seleccion
  confirmada.
- Terminar como `partial` con `blocked_by_order_rule=true`.

### 2. Evitar un backoff general por fallos de evidencia

- La captura de evidencia de un horario bloqueado nunca debe convertirse en una
  autorizacion de reserva.
- Si la seleccion cambia durante esa captura, registrar el diagnostico y
  conservar el resultado `partial / blocked_by_order_rule`.
- No crear `reservation_attempts`, no resolver CAPTCHA y no pulsar `Reservar`.
- No aplicar un backoff general ni impedir que las siguientes ordenes sean
  procesadas.
- Una variacion transitoria de fecha u hora debe provocar una nueva lectura
  corta, no una espera de treinta minutos.

Tambien debe corregirse la semantica historica: capturar una imagen de CAPTCHA
sin enviar la reserva no debe presentarse como
`reservation_attempted=true`.

## Contratos que no deben cambiar

- Una fecha fuera de `minimum_date` y `maximum_date` sigue bloqueada.
- `minimum_hour`, `allowed_weekdays` y `excluded_date_ranges` siguen siendo
  obligatorios.
- La busqueda conserva el orden vigente de fechas y horas.
- La identidad, la sede, la fecha y la hora deben validarse antes de cualquier
  envio real.
- Una seleccion incompatible nunca debe llegar al clic de reserva.
- Una fecha bloqueada encontrada primero no debe ocultar una fecha compatible
  encontrada despues.
- Los fallos posteriores a un envio real conservan las protecciones de
  confirmacion, idempotencia y `reservation_attempts`.

## Criterios de aceptacion

1. Varias fechas fuera de rango producen `partial / blocked_by_order_rule`, no
   `error`.
2. Si una opcion posterior cumple el rango, el bot la selecciona e intenta
   reservar normalmente.
3. La fecha y hora de la evidencia coinciden con la seleccion visible.
4. Un fallo al capturar evidencia bloqueada no activa un backoff general.
5. Las siguientes ordenes de la cola continuan sin esperar 1,800 segundos.
6. No se crea un intento de reserva si no hubo intencion de enviar.
7. No aparece `Clicking reservation button` para una opcion bloqueada.
8. Las validaciones de identidad, sede, fecha, hora y disponibilidad permanecen
   activas antes de un envio real.

## Implementacion aplicada

- `appointment_selection.py` recuerda un candidato bloqueado, pero continua
  recorriendo todas las opciones para no perder una cita compatible posterior.
- Si ninguna opcion cumple, vuelve a localizar la fecha y hora por su texto y
  usa los valores actuales del portal para seleccionarlas.
- La evidencia solo se marca como sincronizada cuando la lectura estable
  coincide con esa fecha y hora.
- Si la fecha u hora desaparecen o cambian, se conserva
  `partial / blocked_by_order_rule` con diagnostico, sin iniciar una reserva.
- `reservation_flow.py` aisla cualquier fallo de captura no transaccional. Una
  pausa administrativa sigue devolviendo `paused`; los demas fallos de
  evidencia no escalan a backoff.
- `run_reporting.py` ya no considera `blocked_by_order_rule` ni
  `priority_deferred` como `reservation_attempted=true`.
- El contrato de seguridad documenta que capturar un CAPTCHA sin resolverlo ni
  pulsar `Reservar` no constituye un intento.

No fue necesario relajar `WorkerErrorPolicy`: el caso queda clasificado y
contenido antes de llegar a la politica general de errores.

## Verificacion realizada

- `python -m compileall src`: correcto.
- Ruff sobre los tres modulos modificados: correcto.
- Pruebas existentes de notificaciones y resumen de evidencia: 10 correctas.
- Escenario focalizado con 19-08-2026 y 21-08-2026, ambos bloqueados: termino
  `partial` con evidencia sincronizada.
- Escenario con 21-08-2026 bloqueado y 18-08-2026 compatible despues: selecciono
  18-08-2026 y conservo el flujo normal.
- Fallo forzado al capturar evidencia bloqueada: termino `partial`, sin
  excepcion y con `reservation_attempted=false`.
- `slot_lost` y `registered` conservaron `reservation_attempted=true`.
- El worker se reinicio de forma controlada, se reanudo y quedo en
  `monitoring_observer`, sin pausa ni errores.

Estas verificaciones no enviaron reservas reales. La validacion productiva final
se completara cuando el portal vuelva a presentar varias fechas fuera de rango;
en ese momento debe cumplirse la seccion de criterios de aceptacion.

## Senales de regresion o motivo de rollback

Revisar o revertir la correccion si ocurre cualquiera de estos casos:

- el bot deja de recorrer opciones posteriores despues de una fecha bloqueada;
- una cita compatible se omite porque antes aparecio una incompatible;
- la evidencia muestra una fecha u hora diferente a la evaluada;
- una opcion fuera de rango llega a CAPTCHA resuelto o al clic de reserva;
- se reduce la validacion de identidad o de seleccion antes del envio;
- se producen envios duplicados o se altera la proteccion de idempotencia;
- los errores de una reserva realmente enviada dejan de quedar protegidos por
  el estado correspondiente.

No se debe revertir solamente porque un horario bloqueado termine como
`partial`: ese es el resultado esperado.

## Alcance previsto del cambio

La implementacion debe ser pequena y concentrarse en:

- `reservation_engine/appointment_selection.py`;
- `reservation_engine/monitor.py`;
- `reservation_engine/reservation_flow.py`;
- la clasificacion de backoff solamente si la proteccion local no resulta
  suficiente.

No se deben cambiar reglas de negocio, prioridades, ventanas de monitoreo,
credenciales, `.env` ni la confirmacion de reservas reales.
