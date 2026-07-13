# Linea base observacional de optimizacion

- Rango: `2026-07-06` a `2026-07-12` (America/Lima, inclusivo).
- Runs: 4416.
- Intentos compatibles: 37.
- `registered`: 15.
- Conversion base: `40.5%` (`registered / intentos compatibles`).

No se modificaron clics, esperas, CAPTCHA, orden, concurrencia ni confirmacion.

## Tiempos base

| Tramo | n | p50 | p90 |
| --- | ---: | ---: | ---: |
| Deteccion a fin | 50 | 6.977s | 11.283s |
| Seleccion fecha/hora | 50 | 1.719s | 1.891s |
| CAPTCHA | 31 | 1.359s | 3.047s |

## CAPTCHA

- Mayor a 3s: 4.
- Mayor a 5s: 3.
- Mayor a 10s: 3.
- Mayor a 20s: 1.

## Cupos compartidos y secuencia

- Tandas compartidas observadas: 5.
- Grupos independientes: 20.
- Intentos posteriores al primero: 6.
- `registered` posteriores: 4.
- Proxy de supervivencia: 66.7%.
Este proxy no afirma el inventario interno del portal; mide resultados posteriores sobre la misma sede/fecha/hora.

## Fetch probe

- Senales: 3.
- Con hora util visible: 0.
- Confirmadas en la propia corrida: 0.
- Defensas asociadas: 0.
Permanece observacional y no autoriza reservas.

## Instrumentacion desde este corte

- Runs historicos con desglose de selectores: 0.
- Los nuevos runs guardaran lectura de opciones, postback de fecha, estabilizacion de hora y cantidades candidatas.
- No se elimino ninguna espera; primero se acumularan muestras con DOM estable.

## Decision actual

- Mantener el flujo productivo sin cambios funcionales.
- No cambiar proveedor/timeout CAPTCHA ni activar concurrencia.
- Revisar esta linea base cuando existan nuevas muestras reales.
