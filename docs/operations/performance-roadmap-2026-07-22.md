# Hoja de ruta de rendimiento - 22-07-2026

> Documento historico ejecutado. No contiene trabajo pendiente vigente; usar
> `docs/roadmap/README.md` para prioridades actuales.

## Objetivo

Mejorar progresivamente la detección y reserva de cupos sin perder estabilidad,
sin aumentar la presión sobre el portal de forma brusca y sin mezclar cambios
que impidan identificar qué produjo cada resultado.

Esta hoja de ruta cubre:

1. más intentos dentro de una sesión autenticada.
2. más turnos para órdenes prioritarias sin aumentar la carga total.
3. menor intervalo entre consultas.
4. uso progresivo del bot local de CAPTCHA.
5. reducción del tiempo crítico entre disponibilidad y clic en Reservar.
6. métricas y guardas automáticas para continuar o revertir.

## Línea base

Periodo principal: 13-07-2026 al 22-07-2026.

| Métrica | Línea base |
|---|---:|
| Corridas | 8,038 |
| Reservas confirmadas por corridas automáticas | 37 |
| `slot_lost` | 39 |
| Errores | 16, aproximadamente 0.2% |
| HTTP 403 / 429 | 0 |
| CAPTCHA p90, 13 al 18 de julio | 12.05 s |
| CAPTCHA p90, 20 al 22 de julio | 7.16 s |
| Disponibilidad a resultado p90, 13 al 18 de julio | 18.56 s |
| Disponibilidad a resultado p90, 20 al 22 de julio | 13.94 s |

La conversión de envíos compatibles se mantiene cerca del 49%. La estabilidad
es buena, pero todavía se pierde aproximadamente un cupo por cada reserva
confirmada.

## Reglas de ejecución

### Una variable activa por etapa

No cambiar simultáneamente:

- intentos por sesión.
- intervalos del observer.
- ponderación de prioridades.
- decisión de CAPTCHA usada para reservar.
- pasos críticos previos al clic.

La única excepción son cambios de observabilidad que no alteren el portal ni la
selección de órdenes.

### Dos evaluaciones diferentes

Cada etapa necesita:

1. **Evaluación de estabilidad:** mínimo tres días operativos completos, de
   lunes a sábado.
2. **Evaluación de efectividad:** mínimo 20 cupos compatibles con intento real
   de reserva.

Tres días sin cupos permiten decidir si el sistema es estable, pero no permiten
afirmar que mejoró la conversión.

### Detención anticipada

No es necesario esperar tres días si aparece:

- más de un HTTP `403` o `429` en 30 minutos.
- un `recovery_backoff` causado por defensa del portal.
- tasa diaria de error superior a `0.5%`.
- sesiones repetidas que alcanzan el límite de 120 segundos.
- credenciales o sesiones cruzadas entre clientes.

Ante una de estas condiciones se revierte la última variable y se documenta el
incidente.

## Calendario propuesto

| Etapa | Activación más temprana | Observación mínima | Decisión más temprana |
|---|---|---|---|
| Paso 1: cuatro intentos | 23-07-2026 | 23, 24 y 25 de julio | 25-07 después de las 18:00 |
| Paso 2: prioridad ponderada | 27-07-2026 | tres días con cola mixta | 29-07 después de las 18:00 |
| Paso 3: intervalos 7–11 s | 30-07-2026 | 30, 31 de julio y 1 de agosto | 01-08 después de las 18:00 |
| Paso 4: CAPTCHA local | recolección inmediata | mínimo 200 etiquetas validadas | al alcanzar la muestra |
| Paso 5: ruta crítica | análisis inmediato | tres días o 20 intentos por cambio | después del paso 3 |
| Paso 6: guardas y panel | desarrollo inmediato | no altera el experimento | antes del paso 3 |

Las fechas son las más tempranas posibles. Se desplazan si una etapa no reúne
la muestra necesaria o si continúa activa una orden con prioridad exclusiva.

## Paso 1 - Cuatro intentos por sesión

Estado: **aplicado el 22-07-2026; pendiente de observación**.

Configuración:

```dotenv
OBSERVER_SESSION_SECONDS=120
OBSERVER_MAX_ATTEMPTS=4
OBSERVER_INTERVAL_MIN_SECONDS=8
OBSERVER_INTERVAL_MAX_SECONDS=13
```

El cambio se carga en el siguiente arranque del worker, el 23-07-2026. Debe
observarse durante el jueves 23, viernes 24 y sábado 25.

Medir:

- lecturas y sesiones por hora.
- logins por cada 100 lecturas.
- duración p50 y p90 de sesión.
- errores, timeouts, 403, 429 y recovery backoff.
- sesiones que llegan al límite de 120 segundos.

Avanzar si:

- no aparecen defensas del portal.
- los errores permanecen por debajo de `0.5%`.
- disminuyen los logins por cada 100 lecturas.
- las lecturas por hora se mantienen o aumentan.

Revertir a tres intentos si falla cualquiera de las condiciones de seguridad.

Documento detallado:
[`observer-tuning-2026-07-22.md`](observer-tuning-2026-07-22.md).

## Paso 2 - Prioridad ponderada

Objetivo: dar más revisiones a las órdenes urgentes sin hacer más consultas
globales al portal.

Comportamiento propuesto:

- prioridad `0–99`: peso `1`.
- prioridad `100–199`: peso `2`.
- prioridad `200`: enfoque exclusivo ya implementado.

Ejemplo con una orden normal y una enfocada:

```text
enfocada -> enfocada -> normal -> repetir
```

Esto distribuye las sesiones existentes; no abre dos navegadores ni duplica la
carga.

Condición previa:

- el paso 1 debe superar la evaluación de estabilidad.
- deben existir al menos dos órdenes `ready`.
- no debe estar activa una prioridad `200`, porque el modo exclusivo impediría
  observar la ponderación.

Desarrollo más temprano: domingo 26-07-2026, cuando el worker no realiza
consultas. Activación más temprana: lunes 27-07-2026.

Medir:

- proporción real de sesiones por prioridad.
- tiempo máximo sin revisión de una orden normal.
- lecturas globales por hora.
- errores y conversión por prioridad.

Avanzar si la orden `100` recibe aproximadamente el doble de turnos sin dejar
órdenes normales sin revisar durante periodos excesivos.

La implementación debe incluir una bandera de configuración para volver a la
rotación uniforme sin revertir código.

## Paso 3 - Reducir intervalos a 7–11 segundos

Objetivo: aumentar aproximadamente entre 10% y 15% las oportunidades de lectura
sin duplicar la frecuencia.

Cambio propuesto:

```dotenv
OBSERVER_INTERVAL_MIN_SECONDS=7
OBSERVER_INTERVAL_MAX_SECONDS=11
```

No modificar `OBSERVER_MAX_ATTEMPTS=4` durante esta etapa.

Condiciones previas:

- paso 1 estable.
- paso 2 estable o pospuesto explícitamente porque no existe una cola mixta.
- cero 403/429 en la etapa anterior.
- error diario inferior a `0.5%`.

Activación más temprana: jueves 30-07-2026. Observación: 30 y 31 de julio y
1 de agosto.

Medir:

- lecturas reales por hora.
- separación p50 y p90 entre lecturas.
- 403, 429, CAPTCHA inesperado y recovery backoff.
- errores de red y tiempos de actualización de sede.
- conversión cuando existan al menos 20 intentos compatibles.

Reversión inmediata: volver a `8–13 s`.

No evaluar todavía intervalos menores a seis segundos.

## Paso 4 - CAPTCHA local con respaldo de 2Captcha

Objetivo: reducir los casos donde el CAPTCHA consume entre 7 y 12 segundos, sin
enviar respuestas locales poco confiables al portal.

Este trabajo tiene dos caminos que pueden avanzar en paralelo:

### Recolección y validación

Puede continuar desde ahora porque el modo sombra no altera la reserva.

Muestra mínima antes de usar un modelo local:

- al menos 200 CAPTCHA únicos con respuesta validada.
- precisión mínima de `98%` sobre datos no usados para entrenar.
- latencia p90 local menor o igual a `1.5 s`.
- respuestas con formato válido en al menos `99.5%`.
- resultados separados por modelo, no solo por consenso.

La precisión debe calcularse contra una respuesta confirmada por el operador o
aceptada por el portal. La coincidencia con 2Captcha por sí sola no es verdad
absoluta.

### Activación gradual

1. modo sombra: modelos y 2Captcha responden, pero solo se guarda la comparación.
2. modo asistido: el dashboard propone una respuesta para revisión humana.
3. canario: usar respuesta local únicamente con confianza alta en un porcentaje
   pequeño de intentos.
4. producción con fallback: si no hay confianza o respuesta dentro del límite,
   continuar con 2Captcha.

La primera evaluación puede hacerse cuando existan 200 etiquetas validadas o el
01-08-2026, lo que ocurra después. No hay una fecha segura de activación si la
muestra todavía no alcanza el mínimo.

Medir:

- exactitud por modelo.
- cobertura de respuestas de alta confianza.
- latencia p50 y p90.
- CAPTCHA inválidos aceptados para envío.
- tiempo ahorrado frente a 2Captcha.
- precisión posterior confirmada por el portal.

## Paso 5 - Reducir la ruta crítica antes de Reservar

Línea base aproximada de intentos recientes:

- selección de fecha y hora: `1.70 s` de mediana.
- CAPTCHA a clic: `1.59 s` de mediana, sin contar la espera del solver.
- confirmación y evidencia posterior: `1.41 s` de mediana.

La confirmación posterior al clic mejora reportes, pero no evita que el cupo se
pierda antes del envío. La prioridad de optimización es:

```text
disponibilidad -> selección -> CAPTCHA -> validación -> clic
```

El análisis del código puede comenzar durante las esperas de los pasos 1 a 3.
La activación debe ocurrir después del paso 3 para no mezclar variables.

Revisar, en este orden:

1. espera fija de estabilización de hora.
2. validaciones repetidas antes del clic.
3. costo del screenshot previo, sin eliminar la evidencia.
4. captura y escritura del CAPTCHA.
5. esperas que puedan sustituirse por señales reales del DOM.

Cada despliegue debe cambiar un solo punto y conservar:

- screenshot previo al envío.
- validación de persona, fecha y hora.
- idempotencia y registro de intento.
- confirmación estricta de `Programado`.

Objetivo inicial: reducir al menos un segundo del tiempo p50 hasta el clic sin
aumentar `reservation_unconfirmed`, CAPTCHA inválido ni reservas incorrectas.

## Paso 6 - Panel y guardas automáticas

Puede desarrollarse inmediatamente porque mostrar métricas no cambia la
frecuencia del portal.

El dashboard debe mostrar:

- lecturas por hora.
- sesiones y logins por hora.
- lecturas por login.
- duración p50 y p90 de sesión.
- CAPTCHA p50 y p90 por proveedor o modelo.
- tiempo disponibilidad a clic y a confirmación.
- `registered`, `slot_lost`, errores, 403 y 429.
- distribución de sesiones por prioridad.
- configuración activa y fecha de su último cambio.

Las guardas de comportamiento se activarán después de validar el paso 3:

- alerta inmediata por 403/429.
- alerta si error diario supera `0.5%`.
- sugerencia de reversión con el valor anterior.
- historial de cambios de configuración.
- comparación automática antes/después con ventanas equivalentes.

Al principio la reversión debe requerir confirmación del operador. No conviene
que el sistema cambie frecuencias automáticamente sin acumular evidencia.

## Trabajo permitido durante las esperas

Se puede avanzar sin invalidar la evaluación:

- construir paneles y consultas de solo lectura.
- etiquetar CAPTCHA y revisar desacuerdos.
- preparar código detrás de una bandera desactivada.
- revisar logs y generar comparaciones.
- auditar esperas de la ruta crítica.
- mejorar documentación.

No se debe:

- activar una segunda variable operativa.
- abrir observadores paralelos para la misma cuenta.
- reducir intervalos mientras se evalúan los cuatro intentos.
- usar el CAPTCHA local en reservas reales antes de superar las métricas.
- cambiar ventanas horarias durante una comparación.

## Informe obligatorio al cerrar cada etapa

Cada decisión debe dejar un documento con:

1. configuración anterior y nueva.
2. fecha y hora de activación.
3. periodo observado.
4. número de sesiones, lecturas y logins.
5. intentos compatibles, reservas y `slot_lost`.
6. errores y señales de defensa.
7. CAPTCHA y ruta crítica p50/p90.
8. decisión: mantener, extender observación o revertir.
9. siguiente fecha posible de cambio.

## Próxima decisión

La siguiente revisión está programada para el sábado 25-07-2026 después del
corte de las 18:00. Si el paso 1 supera las condiciones de estabilidad:

- se conserva `OBSERVER_MAX_ATTEMPTS=4`.
- el domingo 26 puede implementarse la ponderación detrás de una bandera.
- el lunes 27 puede activarse el paso 2 si existe una cola mixta y no hay una
  prioridad `200` activa.

Si no hay suficientes cupos compatibles, se podrá aprobar la estabilidad, pero
la conclusión sobre conversión quedará pendiente hasta reunir 20 intentos.
