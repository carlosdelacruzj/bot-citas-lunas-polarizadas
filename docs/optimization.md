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
| OBS-006 | Ráfaga multicliente después de una detección real | Mejora futura en evaluación; no implementada ni aprobada para producción |

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

## Hipótesis futura: ráfaga multicliente

Estado al `2026-07-31`: **en evaluación**. La concurrencia productiva continúa
desactivada. Esta sección no autoriza implementación ni activación.

### Objetivo

Aprovechar una liberación de varios cupos sin mantener tres observadores
consultando durante toda la jornada. El flujo normal conservaría una sola
sesión. Una disponibilidad real iniciaría temporalmente un pool deslizante de
hasta tres clientes:

1. la sesión que detectó el cupo continúa inmediatamente su propia reserva;
2. se abren en paralelo hasta dos sesiones Playwright nuevas para otras órdenes
   `ready` compatibles;
3. cada reserva confirmada libera una posición y permite abrir el siguiente
   cliente elegible;
4. el pool se mantiene en un máximo de tres sesiones hasta agotar clientes
   elegibles, perder la disponibilidad o alcanzar un límite operativo;
5. al terminar la ráfaga se cierran las sesiones auxiliares y vuelve el
   observador secuencial normal.

No se mantendrán sesiones auxiliares autenticadas mientras esperan. Una muestra
de `56` sesiones del log del `2026-07-30` mostró:

| Tramo desde el inicio de la orden | p50 | p90 | máximo observado |
| --- | ---: | ---: | ---: |
| Login completado | 1.325 s | 1.580 s | — |
| Panel listo | 1.912 s | 2.339 s | — |
| Primera lectura de cupos | 3.220 s | 3.677 s | 5.504 s |

Estos tiempos permiten evaluar sesiones nuevas en frío, pero no demuestran
todavía que los cupos sobrevivan lo suficiente ni que tres accesos simultáneos
sean aceptados por el portal.

### Disparador

La ráfaga solo podría comenzar por disponibilidad completa confirmada por el
flujo normal o `reload_probe`. No deben activarla:

- `fetch_probe`;
- una señal parcial sin fecha y hora seleccionables;
- una captura de evidencia;
- una reserva incierta;
- un resultado histórico o una alerta repetida.

### Selección y aislamiento

- Máximo tres sesiones activas en total, incluida la que detectó.
- Solo órdenes `ready`, reclamables y compatibles con la fecha/hora observada.
- Prioridad `DESC` y antigüedad `ASC` para elegir el siguiente cliente.
- Nunca dos sesiones para la misma cuenta del portal.
- Navegador, contexto, cookies, credenciales, lease, heartbeat, `run_id` e
  intento de reserva independientes por orden.
- Una orden con submission pendiente, lease ajeno, credenciales inválidas o
  resultado incierto no entra al pool.
- `registered` o `Programado` termina esa orden y habilita el siguiente cliente.
- `slot_lost` conserva la orden según sus reglas normales, pero no la repite
  automáticamente dentro de la misma ráfaga.

### Cierre y guardas

El diseño debe definir una condición global de fin; un solo `Sin Cupos` no
alcanza mientras otras sesiones siguen procesando. Punto de partida para una
prueba controlada:

- cerrar cuando todas las sesiones activas completen una ronda sin cupos y no
  exista una señal positiva reciente durante `10–15` segundos;
- duración máxima de ráfaga de `60–90` segundos;
- límite inicial de `10` clientes procesados por ráfaga;
- detener y cerrar sesiones auxiliares ante `403`, `429`, defensa general,
  pérdida de lease o fallo de coordinación;
- nunca repetir automáticamente un submit ambiguo;
- permitir pausa y apagado del worker sin dejar navegadores o claims huérfanos.

### Métricas obligatorias

Antes de activar debe existir instrumentación para:

- identificador y duración de cada ráfaga;
- clientes elegibles, iniciados, omitidos y reemplazados;
- tiempo de la detección inicial al panel y primera lectura de cada auxiliar;
- máximo de sesiones concurrentes y memoria consumida;
- disponibilidad observada por sesión;
- `registered`, `slot_lost`, `reservation_unconfirmed`, errores, `403` y `429`;
- gasto y latencia CAPTCHA por ráfaga;
- cantidad de reservas adicionales atribuibles a la concurrencia.

### Próximos pasos

1. No mezclar esta hipótesis con otro cambio de intervalos, CAPTCHA o selección.
2. Diseñar el controlador del pool separado del flujo de reserva individual.
3. Preparar una bandera desactivada por defecto y límites configurables.
4. Validar primero apertura/cierre, claims y cancelación sin enviar reservas.
5. Ejecutar una prueba controlada con cuentas autorizadas cuando exista una
   ventana real.
6. Comparar contra la operación secuencial y decidir conservar, ajustar o
   descartar.

## Regla para un experimento futuro

Registrar hipótesis, riesgo, rango, muestra mínima y métricas antes; aplicar un
solo cambio; medir conversión, p50, p90, `slot_lost` y defensas después; decidir
conservar, ampliar observación o revertir.
