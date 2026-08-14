# Canario de ruta critica de reserva

Vigente desde `2026-08-11`. Este cambio reduce esperas anteriores al clic sin
retirar ninguna validacion de sede, fecha, hora, cupos o identidad.

## Comportamiento

- Al seleccionar una hora se instala un observador temporal del DOM y del
  `PageRequestManager` de ASP.NET.
- El camino rapido exige que el postback haya terminado, que fecha y hora sigan
  siendo las esperadas y que dos snapshots DOM separados por `150 ms` sean
  iguales.
- Si la senal no llega en `750 ms`, el observer no puede instalarse, aparece una
  excepcion o los snapshots difieren, se ejecuta automaticamente el algoritmo
  anterior: espera fija de `500 ms` mas snapshots separados por `750 ms`.
- Las tres validaciones pre-submit siguen existiendo. Cada una lee sede, fecha,
  hora y cupos en una sola evaluacion DOM; la identidad conserva su relectura
  estable independiente. Ante error o campos esperados ausentes se restauran
  automaticamente las lecturas Playwright separadas.

## Medicion

Cada resultado conserva en `selection_observation`:

- `hour_stabilization_seconds`;
- `hour_stabilization_modes`: `event_atomic`, `legacy_fallback` o `legacy`;
- `hour_signal_seconds`, `hour_fallback_seconds` y
  `hour_fallback_reasons`;
- cantidad de snapshots atomicos usados.

`reservation_timing` separa ademas:

- validacion inicial y posterior al solver;
- llenado del campo CAPTCHA;
- validacion DOM final;
- persistencia de la intencion de submit;
- tramo total `captcha_filled -> reserve_click_started`.

El log de Telegram ya registra `telegram_immediate_alert_queued enqueue_ms`.
Las muestras CAPTCHA adicionales controladas por el operador no forman parte de
la comparacion de velocidad.

Gate inicial: revisar las primeras `10` selecciones reales. No ampliar otros
parametros durante la muestra. Exigir cero cambios de seleccion no detectados,
cero errores internos nuevos y trazas completas. Comparar p50/p90 contra la
referencia de seleccion cercana a `1.70 s`; informar por separado cualquier
fallback.

Al cierre operativo del `2026-08-11`, ambas banderas cargan como `true`. El
worker termino normalmente a las `18:00` y su supervisor mantiene el siguiente
inicio a las `07:30`; por ello, la primera medicion productiva empezara en ese
inicio sin abrir una sesion artificial fuera de la ventana diaria.

## Rollback

Los dos cambios se pueden desactivar por separado:

```dotenv
APPOINTMENT_SELECTION_EVENT_DRIVEN_ENABLED=false
APPOINTMENT_ATOMIC_VALIDATION_ENABLED=false
```

Despues se solicita un reinicio controlado cuando no exista una orden ni un
submission activo. El primer valor restaura las esperas `500/750 ms`; el
segundo restaura las lecturas separadas. No requiere migracion ni elimina
evidencia. Si solo falla una parte, se desactiva unicamente su bandera.

No matar una sesion durante un submit pendiente. Un fallback aislado no exige
rollback: ya ejecuta el camino anterior dentro de la misma sesion. Rollback
manual si hay fallos repetidos, diferencias de seleccion, incremento de errores
internos o ausencia de telemetria.
