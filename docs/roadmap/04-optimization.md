# Optimizacion de reservas

## Estado comprobado

- Ruta normal repetible cercana a 6.5-7.3 segundos con CAPTCHA rapido.
- Cambio entre clientes de 0-2 segundos.
- Reglas y diferimiento evitan intentos incompatibles.
- `reload_probe` no fue necesario en las reservas rapidas observadas.
- `fetch_probe` detecta señales, pero aun no prueba conversion.

## P0 - Linea base y objetivo

Ejecutar despues del reporte semanal de operaciones.

1. Fijar p50/p90 por tramo y tasa por resultado exacto.
2. Separar cupos compartidos de intentos independientes.
3. Definir objetivo: aumentar `registered / intentos compatibles`, no solo
   reducir segundos.
4. Registrar cada experimento con antes, cambio, despues y decision.

## P1 - Seleccion de fecha y hora

1. Medir selectores y esperas que forman el tramo cercano a 1.7 segundos.
2. Eliminar esperas redundantes solo con evidencia DOM estable.
3. Conservar revalidacion previa al submit y screenshot en fallos.
4. Probar un cambio por vez contra conversion y `slot_lost`.

## P1 - Variabilidad de CAPTCHA

1. Medir frecuencia de respuestas mayores a 3, 5, 10 y 20 segundos.
2. Revisar timeout y politica de cancelacion sin crear reintentos infinitos.
3. Evaluar proveedor alterno solo con comparacion controlada de latencia,
   exactitud, costo y seguridad.
4. Mantener reintento de `captcha_invalid`; exigir evidencia de una recuperacion
   exitosa antes de declararlo optimizacion cumplida.

## P1 - Orden y concurrencia de clientes

1. Medir cuantos cupos sobreviven despues de la primera reserva de una tanda.
2. Comparar secuencia actual con concurrencia limitada y segura.
3. Mantener sesion nueva, lease y confirmacion independiente por orden.
4. No aumentar concurrencia si crecen defensas, 429 o errores de sesion.

## P2 - Fetch probe

1. Correlacionar señal temprana, aparicion de hora y reserva confirmada.
2. Mantenerlo observacional hasta acumular evidencia suficiente.
3. Retirarlo si agrega carga sin anticipacion util o aumenta defensas.

Criterio general de cierre: una optimizacion solo se conserva si mejora
conversion o reduce p90 sin debilitar confirmacion, leases ni evidencia.
