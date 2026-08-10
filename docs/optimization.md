# Optimizacion observacional

Última revisión: `2026-08-09`.

## Limite acordado

La etapa actual mide los cambios ya autorizados `OBS-006` y `OBS-007` sin
introducir simultaneamente otros cambios de clics, esperas, proveedor CAPTCHA,
orden, leases o confirmacion. Cualquier variacion adicional requiere revisar
primero la evidencia con el usuario.

El objetivo es aumentar `registered / intentos compatibles`, no reducir tiempo
aisladamente. `blocked_by_order_rule` y `priority_deferred` no cuentan como
intentos compatibles.

## Fuentes vigentes

- Línea base promovida: `reports/optimization/latest.md`.
- Reportes fechados: `reports/optimization/observation-*.md`.
- Reporte semanal: `reports/operations/latest.md`.
- Evidencia compacta: `docs/evidence-summary.md` y
  `docs/evidence-index.csv`.

El reporte operacional comparable más reciente cubre `2026-08-01` a
`2026-08-08`: `5,299` runs, `78` intentos compatibles, `20 registered` y
`57 slot_lost`. La observación del mismo rango se generó sin `--set-baseline`;
por tanto, no reemplaza automáticamente la línea base promovida.

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
   portal. La rafaga `OBS-006` esta activa con maximo dos sesiones, pero sigue
   pendiente de su primera validacion con disponibilidad real.
4. `fetch_probe`: permanece observacional y nunca autoriza una reserva.
5. Calendario: el bot no realiza búsquedas los domingos.

## Registro de decisiones

| ID | Observacion | Decision actual |
| --- | --- | --- |
| OBS-001 | Línea base comparable | Promovida explícitamente |
| OBS-002 | Desglose de selección | Muestra suficiente; conservar sin cambios |
| OBS-003 | Variabilidad CAPTCHA | El corte 1-8 agosto no tuvo respuestas mayores de 10 s; conservar configuración y seguir midiendo |
| OBS-004 | Supervivencia secuencial | Corte vigente: 1/6 intentos posteriores (`16.7%`); justifica ráfaga de dos sesiones, no ampliar a tres |
| OBS-005 | Correlación `fetch_probe` | Sin señales nuevas; mantener observacional |
| OBS-006 | Ráfaga multicliente después de una detección real | Dos sesiones y cola compatible continua implementadas; pendiente de validación real |
| OBS-007 | Reobservación después de `slot_lost` | Misma sesión durante 12 s, cinco lecturas y un reload; implementada con un solo segundo submit posible y pendiente de validación real |

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
- Decisión histórica: no cambiar selección, concurrencia, confirmación ni
  proveedor; evaluar el polling de CAPTCHA a 5 segundos tras 30 nuevos submits
  o una semana completa. Esa condición ya se cumplió y su lectura vigente está
  en el corte siguiente.

## Corte 2026-08-01 a 2026-08-08

- `5,299` runs y `78` intentos compatibles.
- `20 registered` (`25.6%`) y `57 slot_lost` (`73.1%`). El incremento de
  reservas absolutas frente a semanas anteriores provino de mayor volumen y no
  demuestra una mejora de conversión.
- CAPTCHA p50/p90 de `1.641/7.256 s`; ninguna respuesta superó `10 s`.
- Seis tandas compartidas generaron seis intentos posteriores y un
  `registered` posterior: proxy de supervivencia secuencial de `16.7%`.
- Hubo dos señales de defensa. El reporte no las atribuye por sí solo al ciclo,
  pero impide asumir que más carga paralela será gratuita.
- Decisión previa al canario: conservar configuración y validar el handoff
  secuencial. Después de este corte el usuario autorizó `OBS-006` con dos
  sesiones y rollback por bandera; no se alteró la línea base histórica.

## Arquitectura secuencial y ráfaga OBS-006

- `OBSERVER_ACTIVE_ORDER_LIMIT=2` solo limita las órdenes elegidas por la
  consulta. El worker reclama y ejecuta una sola en
  `_run_observer_order_block()`.
- Después de detectar oportunidades se construye una lista compatible de hasta
  diez clientes y `300` segundos. `queue_traversal.py` la recorre con un bucle
  secuencial, un contexto Playwright por cliente y sin pausa artificial.
- El detector compatible reserva primero. Luego se conserva el orden vigente:
  prioridad manual exclusiva, segundo trámite y mayor cobertura de las
  oportunidades observadas.
- Los candidatos posteriores fuerzan una sola muestra CAPTCHA. Cada orden
  mantiene claim y heartbeat durante su ejecución y un resultado ambiguo no se
  reintenta.
- Elevar `OBSERVER_ACTIVE_ORDER_LIMIT` o
  `OPPORTUNITY_HANDOFF_MAX_CANDIDATES` por sí solo no abre sesiones en paralelo.
  La ráfaga usa un coordinador separado y conserva esa cadena como fallback
  cuando `OPPORTUNITY_BURST_ENABLED=false`.

## Ráfaga multicliente OBS-006

Estado al `2026-08-09`: **ráfaga deslizante de dos sesiones implementada**. Se
cargó mediante un reinicio controlado del worker y todavía no tiene validación
con cupos reales.

### Objetivo

Aprovechar una liberación de varios cupos sin mantener varios observadores
consultando durante toda la jornada. El flujo normal conserva una sola sesión.
Una disponibilidad real inicia temporalmente un pool deslizante de hasta dos
sesiones y todos los clientes compatibles disponibles:

1. la sesión que detectó el cupo continúa inmediatamente su propia reserva;
2. se abre en paralelo una sesión Playwright nueva para otra orden `ready`
   compatible, priorizando al usuario que ya estaba en el bloque activo;
3. cada reserva confirmada libera una posición y permite abrir el siguiente
   cliente elegible;
4. el pool se mantiene en un máximo de dos sesiones hasta agotar clientes
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

La evidencia más reciente refuerza esa incertidumbre: entre el 1 y el 8 de
agosto solo existieron seis intentos posteriores comparables y uno reservó. El
beneficio teórico de paralelizar es evitar que cada auxiliar pague en serie sus
aproximadamente `3.2-3.7 s` hasta la primera lectura, además del tiempo de
CAPTCHA y submit del cliente anterior. Sin embargo, todavía no se midió cuántas
de esas ventanas habrían sobrevivido con auxiliares simultáneos ni el efecto de
la carga sobre el portal.

Conclusión: la implementación es técnicamente viable y queda limitada a dos
sesiones concurrentes. La evidencia todavía no permite afirmar cuánto mejorará
la conversión; la decisión depende de las primeras ráfagas reales. No se
ampliará a tres sesiones.

### Disparador

La ráfaga solo comienza por disponibilidad completa confirmada por el
flujo normal o `reload_probe`. No deben activarla:

- `fetch_probe`;
- una señal parcial sin fecha y hora seleccionables;
- una captura de evidencia;
- una reserva incierta;
- un resultado histórico o una alerta repetida.

### Selección y aislamiento

- Máximo dos sesiones activas en total, incluida la que detectó.
- `OPPORTUNITY_BURST_MAX_CLIENTS=0` elimina el límite fijo y carga toda la cola
  compatible observada al iniciar. Un valor positivo recupera un techo total.
- Tres sesiones solo se evalúan después de cerrar la muestra sin incidentes.
- Solo órdenes `ready`, reclamables y compatibles con la fecha/hora observada.
- Reutilizar la selección compatible vigente: prioridad manual exclusiva,
  segundos trámites y mayor cobertura de oportunidades; no crear un segundo
  criterio de orden dentro del controlador concurrente.
- Nunca dos sesiones para la misma cuenta del portal.
- Navegador, contexto, cookies, credenciales, owner token de claim, heartbeat,
  `run_id` e intento de reserva independientes por orden.
- Una orden con submission pendiente, lease ajeno, credenciales inválidas o
  resultado incierto no entra al pool.
- Solo `registered` confirmado habilita el siguiente cliente. `Programado`
  encontrado al entrar cierra esa orden, pero no se atribuye a la ráfaga.
- Un primer `slot_lost` explícito conserva la sesión durante una única ventana
  de `12` segundos, cinco lecturas y un reload. Si reaparece otro horario se
  permite un segundo intento durable; ese segundo resultado siempre cierra la
  reobservación y nunca inicia otra ventana.

### Cierre y guardas

Un solo `Sin Cupos` termina esa sesión, pero no cancela otra que sigue
procesando. La ráfaga termina al quedarse sin sesiones activas. Sus guardas son:

- admitir sesiones nuevas durante un máximo de `300` segundos;
- cada auxiliar sin cupos hace hasta cinco consultas durante `20` segundos y un
  `reload_probe` en el tercer intento;
- sin límite fijo de clientes con el valor activo `0`; la fotografía inicial de
  órdenes compatibles y los cinco minutos siguen siendo límites finitos;
- detener reemplazos nuevos ante `403`, `429`, defensa general, pérdida de
  lease o fallo de coordinación; las sesiones ya enviadas terminan su
  reconciliación;
- nunca repetir automáticamente un submit ambiguo; detener la admisión de
  auxiliares nuevos y permitir que los ya enviados terminen su reconciliación;
- permitir pausa y apagado del worker sin dejar navegadores o claims huérfanos.

### Métricas obligatorias

La telemetría implementada debe permitir revisar:

- identificador y duración de cada ráfaga;
- clientes elegibles, iniciados, omitidos y reemplazados;
- tiempo de la detección inicial al panel y primera lectura de cada auxiliar;
- máximo de sesiones concurrentes y memoria consumida;
- disponibilidad observada por sesión;
- `registered`, `slot_lost`, `reservation_unconfirmed`, errores, `403` y `429`;
- gasto y latencia CAPTCHA por ráfaga;
- cantidad de reservas adicionales atribuibles a la concurrencia.

### Criterio de decisión

La ráfaga no se evalúa por velocidad aislada. Debe acumular al menos `10`
ráfagas reales y `30` ejecuciones auxiliares, y compararse contra la cadena
secuencial. Para avanzar a tres sesiones deben cumplirse todos estos puntos:

- cero navegadores, claims o heartbeats huérfanos;
- cero duplicados y cero reintentos de resultados ambiguos;
- ningún aumento atribuible de `403`, `429`, defensas o
  `reservation_unconfirmed`;
- memoria y cierre estables durante pausa, corte diario y apagado;
- reservas adicionales observables por tanda, no solo menor latencia.

Si aparece un incidente de coordinación o defensa, la bandera vuelve a
desactivada y el flujo secuencial continúa siendo el fallback completo.

### Próximos pasos

1. No mezclar la ráfaga con otro cambio de intervalos, CAPTCHA o selección.
2. Observar la primera ráfaga real y confirmar preferencia del usuario en
   espera, máximo de dos sesiones, reemplazo, claims y cierre.
3. Ante cualquier defensa o incertidumbre, aplicar
   `OPPORTUNITY_BURST_ENABLED=false` y conservar la cadena secuencial.
4. Reunir la muestra mínima, comparar contra la operación secuencial y decidir
   descartar, mantener dos sesiones o evaluar una ampliación futura.

## Regla para un experimento futuro

Registrar hipótesis, riesgo, rango, muestra mínima y métricas antes; aplicar un
solo cambio; medir conversión, p50, p90, `slot_lost` y defensas después; decidir
conservar, ampliar observación o revertir.
