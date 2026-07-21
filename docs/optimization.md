# Optimizacion observacional

## Limite acordado

La etapa actual mide sin modificar clics, esperas, proveedor CAPTCHA,
reintentos, orden, concurrencia, leases, sesiones ni confirmacion. Un cambio
funcional requiere revisar primero la evidencia con el usuario.

El objetivo es aumentar `registered / intentos compatibles`, no reducir tiempo
aisladamente. `blocked_by_order_rule` y `priority_deferred` no cuentan como
intentos compatibles.

## Fuentes vigentes

- Línea base promovida: `reports/optimization/latest.md`.
- Reportes fechados: `reports/optimization/observation-*.md`.
- Reporte semanal: `reports/operations/latest.md`.
- Evidencia compacta: `docs/evidence-summary.md` y
  `docs/evidence-index.csv`.

La línea base solo cambia con:

```powershell
appointment-bot-client optimization-observation `
  --start YYYY-MM-DD --end YYYY-MM-DD --set-baseline
```

## Observaciones activas

1. Selección: la muestra del 13 al 18 de julio reunió 75 selecciones de cliente.
   El p50/p90 total fue 1.703/1.797 segundos; el postback de fecha fue
   0.282/0.297 segundos y la estabilización de hora 1.390/1.453 segundos. La
   selección permanece estable y no justifica un cambio funcional ahora.
2. CAPTCHA: en la muestra del 13 al 18 de julio, 19 de 57 respuestas superaron
   10 segundos. Diecisiete quedaron alrededor de 12 segundos, patrón compatible
   con el polling de 10 segundos del SDK instalado. Los CAPTCHA de más de 10
   segundos terminaron en 16 `slot_lost` y 3 `registered`; los de hasta 10
   segundos terminaron en 13 `slot_lost` y 25 `registered`.
3. Secuencia: las tandas se agrupan por sede/fecha/hora y se separan cuando hay
   más de cinco minutos entre eventos. La cifra es un proxy, no inventario del
   portal. La concurrencia sigue desactivada.
4. `fetch_probe`: permanece observacional y nunca autoriza una reserva.
5. Calendario: el bot no realiza búsquedas los domingos.

## Registro de decisiones

| ID | Observacion | Decision actual |
| --- | --- | --- |
| OBS-001 | Línea base comparable | Promovida explícitamente |
| OBS-002 | Desglose de selección | Muestra suficiente; conservar sin cambios |
| OBS-003 | Variabilidad CAPTCHA | Experimento aprobado: polling de 5 segundos desde 2026-07-19 |
| OBS-004 | Supervivencia secuencial | Bajó de 66.7% a 37.5% con muestra pequeña; no activar concurrencia |
| OBS-005 | Correlación `fetch_probe` | Sin señales nuevas; mantener observacional |

## Cierre semanal 2026-07-13 a 2026-07-18

- Runs: 5,356; intentos compatibles del reporte: 61.
- Resultados: 28 `registered`, 29 `slot_lost` y 4 `Programado/completed`
  informados por separado.
- La conversión publicada de 45.9% usa los 61 intentos como denominador. Para
  comparar exclusivamente submits atribuibles al bot, 28 de 57 terminaron
  `registered` (49.1%), frente a 15 de 31 (48.4%) en la línea base. La
  eficiencia quedó estable; el aumento de reservas provino del mayor volumen.
- Selección estable: p50 1.703 segundos y p90 1.797 segundos.
- CAPTCHA con cola lenta: p90 12.046 segundos frente a 3.047 segundos en la
  línea base; esta es la principal oportunidad medible.
- Una señal de red `ERR_NETWORK_CHANGED`; no fue un `403`, `429` ni bloqueo
  confirmado del portal.
- Decisión: no cambiar selección, concurrencia, confirmación ni proveedor. El
  único experimento aprobado usa polling de CAPTCHA a 5 segundos, que respeta
  el mínimo recomendado por 2Captcha. Se evaluará tras 30 nuevos submits o una
  semana completa.

## Regla para un experimento futuro

Registrar hipótesis, riesgo, rango, muestra mínima y métricas antes; aplicar un
solo cambio; medir conversión, p50, p90, `slot_lost` y defensas después; decidir
conservar, ampliar observación o revertir.
