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

1. Selección: los nuevos runs registran lectura de opciones, postback de fecha,
   estabilización de hora y candidatos. No se eliminó ninguna espera.
2. CAPTCHA: se cuentan respuestas mayores a 3, 5, 10 y 20 segundos. No se
   cambió proveedor, timeout ni reintento de `captcha_invalid`.
3. Secuencia: las tandas se agrupan por sede/fecha/hora y se separan cuando hay
   más de cinco minutos entre eventos. La cifra es un proxy, no inventario del
   portal. La concurrencia sigue desactivada.
4. `fetch_probe`: permanece observacional y nunca autoriza una reserva.
5. Calendario: el bot no realiza búsquedas los domingos.

## Registro de decisiones

| ID | Observacion | Decision actual |
| --- | --- | --- |
| OBS-001 | Línea base comparable | Promovida explícitamente |
| OBS-002 | Desglose de selección | Acumular muestras nuevas |
| OBS-003 | Variabilidad CAPTCHA | Medir; no cambiar proveedor |
| OBS-004 | Supervivencia secuencial | Medir; no activar concurrencia |
| OBS-005 | Correlación `fetch_probe` | Mantener observacional |

## Regla para un experimento futuro

Registrar hipótesis, riesgo, rango, muestra mínima y métricas antes; aplicar un
solo cambio; medir conversión, p50, p90, `slot_lost` y defensas después; decidir
conservar, ampliar observación o revertir.
