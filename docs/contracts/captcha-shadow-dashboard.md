# Contrato del dashboard de CAPTCHA sombra

Fecha de referencia original: 21 de julio de 2026. Actualizado el 13 de agosto
de 2026 con la cola de revisión dirigida.

> Estado actual al 9 de agosto de 2026: el runtime sombra carga solamente
> `v3_selected` y `v6_sequence_candidate`. Las tablas de tres modelos y las
> cifras de julio son evidencia historica de la implementacion inicial, no el
> gate vigente. `2Captcha` sigue siendo la autoridad de reserva; V6 necesita
> 500 muestras frescas posteriores al freeze y etiquetadas manualmente antes de
> poder reconsiderar esa frontera.

## Objetivo

El dashboard administrativo incorpora una vista `CAPTCHA` para revisar, con pocos clics, la
misma imagen enviada a 2Captcha y las predicciones locales disponibles. La cantidad de modelos es
dinámica y la vista no participa en la decisión operativa de reserva.

## Experiencia de uso

La vista muestra sin abrir modales:

- miniatura de la imagen original;
- fecha, orden, intento y referencia del evento;
- respuesta y tiempo de 2Captcha;
- respuesta, confianza y tiempo de inferencia de cada modelo almacenado en el evento;
- coincidencia o diferencia frente a 2Captcha;
- validación explícita del portal o estado pendiente.

Incluye búsqueda, filtros visibles, tamaños de página de 12, 24 y 48 elementos, paginación de
servidor y adaptación móvil. Nunca presenta una coincidencia con 2Captcha como respuesta correcta
si el portal no la validó.

## API administrativa

Angular consume únicamente rutas del mismo origen y autenticadas por la sesión administrativa:

```text
GET /api/v1/captcha-shadow/summary
GET /api/v1/captcha-shadow/events?page=1&page_size=12&q=&agreement=all&portal_status=all&review_scope=all
GET /api/v1/captcha-shadow/events/{event_id}/image
```

La API administrativa funciona como fachada del servicio local configurado en
`CAPTCHA_SHADOW_URL`. No entrega rutas absolutas de imágenes ni rutas de modelos al navegador.
La imagen solo se sirve si la ruta registrada resuelve dentro de `settings.screenshots_dir`.

La indisponibilidad del servicio sombra produce un estado degradado dentro de esta vista; no
impide cargar órdenes, finanzas, runs ni controles del worker.

## Paginación del servicio sombra

El servicio local acepta `limit`, `offset`, `q`, `agreement` y `portal_status`, y devuelve:

```json
{
  "total": 0,
  "limit": 12,
  "offset": 0,
  "events": []
}
```

Los filtros permitidos son:

- `agreement=all|match|mismatch|pending`;
- `portal_status=all|accepted|rejected|unverified`.
- `review_status=all|validated|pending`;
- `review_scope=all|targeted`.

`review_scope=targeted` se usa únicamente con pendientes y orden
`review_priority`. Incluye, en este orden, decisiones cuya respuesta operativa
fue V6, anomalías o confianza V6 bajo `0.60/0.60`, discrepancias con la
referencia externa, desacuerdos V3/V6 y una muestra estable del `6.25%` de los
acuerdos seleccionada por el primer byte del SHA-256. Cada evento devuelve
`review_priority_reason`; `review_scope=all` conserva la consulta completa.

## Tiempos

`inference_ms` mide cada modelo local. `external_solve_ms` mide desde antes de llamar a 2Captcha
hasta recibir su respuesta. El bot lo guarda en el outbox PostgreSQL junto al `event_id`, de modo
que la fachada puede incorporarlo sin depender de analizar logs.

Los dos eventos anteriores a este contrato se completan con los tiempos reconstruidos de sus
logs: 1374 ms y 12617 ms.

## Rendimiento y refresco

La vista se carga únicamente al seleccionarla. El auto-refresco mantiene filtros y página, y
actualiza solo los datos de CAPTCHA cuando esa vista está activa. Las imágenes usan carga diferida
desde el navegador.

## Muestras del observador sin clientes

Cuando el observador general encuentra una cita y no existen órdenes activas, conserva hasta la
cantidad configurada en `OBSERVER_CAPTCHA_SAMPLE_LIMIT`. En producción se usan quince CAPTCHA
originales consecutivos. Cada imagen se registra como un evento independiente:

```text
{run_id}:observer:captcha-1
...
{run_id}:observer:captcha-15
```

Estas muestras:

- no se envían a 2Captcha y no generan consumo externo;
- sí se persisten en el outbox y se procesan por los modelos sombra activos;
- conservan los tiempos `inference_ms` de cada modelo;
- aparecen en el dashboard como `Solo modelos locales` y `2Captcha: No enviado`;
- no se presentan como aceptadas por el portal porque nunca se envían al formulario.

El tiempo de 2Captcha se muestra únicamente en los intentos reales de reserva donde exista
`external_solve_ms`. Para las muestras del observador se muestra `No aplica`.

## Estado implementado

Implementado y activado el 21 de julio de 2026:

- build Angular de producción completado;
- dashboard administrativo reiniciado en `http://127.0.0.1:8766/`;
- API confirmó dos eventos, tres predicciones por evento y ambas imágenes disponibles;
- filtro `Coinciden` devolvió dos eventos;
- filtro de portal `Aceptados` devolvió un evento;
- una búsqueda por respuesta sanitizada devolvió el evento esperado;
- tiempos históricos de 2Captcha visibles: 1374 ms y 12617 ms;
- worker reiniciado con captura futura de `external_solve_ms` activa;
- dispatcher durable reiniciado con `pending=0`.

La revisión visual automatizada no estuvo disponible en esta sesión. La validación cubrió
compilación Angular, contratos de tipos, respuestas HTTP reales, filtros, paginación y entrega de
imágenes; queda recomendada una revisión visual humana breve desde la pestaña `CAPTCHA`.

## Navegación escalable del dashboard

Desde el 21 de julio de 2026 las pestañas superiores se reemplazan por una navegación lateral:

- sidebar persistente en escritorio, con grupos `Operación`, `Administración` y `Automatización`;
- modo contraído de iconos para ganar espacio horizontal, recordado localmente;
- drawer superpuesto en móvil, abierto desde un único botón `Menú`;
- selección de vista en un clic y cierre automático del drawer después de navegar;
- título de la vista activa, estado del worker y actualización permanecen visibles en la cabecera;
- contadores de órdenes, runs, finanzas y CAPTCHA continúan junto a su opción.

No se usa carrusel porque ocultaría destinos y requeriría desplazamiento adicional. El sidebar
permite añadir nuevos módulos sin volver a apilar controles en la parte superior.

Implementación validada con el build Angular de producción y activada en
`http://127.0.0.1:8766/`. El bundle desplegado contiene la navegación agrupada, el control de
colapso y el drawer móvil; el dashboard respondió HTTP 200 con sesión local, mientras el worker y
el servicio CAPTCHA permanecieron saludables. La revisión visual automatizada siguió
indisponible, por lo que se mantuvo la validación estructural y responsive mediante el build.

## Validación de muestras del observador

La captura queda limitada a un único lote configurable por cita detectada:

- la detección inicial conserva y encola hasta quince muestras disponibles;
- antes de cada imagen se vuelve a comprobar que no haya clientes activos;
- si aparece un cliente, el lote se interrumpe para priorizarlo;
- la comprobación de confirmación no vuelve a capturar imágenes;
- cada muestra se ejecuta en los tres modelos locales y conserva un tiempo independiente;
- 2Captcha no se invoca para estos eventos y sus campos permanecen vacíos.

Se reprocesaron de forma controlada las cinco muestras reales conservadas el 20 de julio de 2026.
El resultado fue de cinco eventos, quince predicciones locales y cero envíos a 2Captcha. El outbox
terminó sin elementos pendientes. Los tiempos observados, en milisegundos, fueron:

| Muestra | `v1_real` | `v2_scratch` | `v2_selected` |
| --- | ---: | ---: | ---: |
| 1 | 40.630 | 5.639 | 32.432 |
| 2 | 17.607 | 18.375 | 51.924 |
| 3 | 25.719 | 17.566 | 12.985 |
| 4 | 10.549 | 3.035 | 2.490 |
| 5 | 12.773 | 5.047 | 3.293 |

El dashboard permite aislar estos registros con `Origen: Observador local`. En cada tarjeta muestra
la respuesta y el tiempo de los tres modelos, además del total local. Para estas muestras indica
`2Captcha: No enviado` y `No aplica`; en una reserva real continúa mostrando la respuesta y
`external_solve_ms` cuando 2Captcha haya participado.

## Validación humana y dataset de entrenamiento

El dashboard incorpora el acceso directo `Validar pendientes`. La respuesta debe contener
exactamente cinco caracteres `A-Z0-9` y puede confirmarse con estos atajos:

- si los tres modelos coinciden, se muestra una única respuesta para validar con un clic;
- si dos coinciden y uno difiere, se muestran las dos opciones indicando cuántos modelos apoyan
  cada respuesta;
- si los tres difieren, se solicita directamente la lectura manual;
- el ingreso manual permanece disponible para corregir incluso cuando exista consenso o mayoría.

Después de validar, las respuestas iguales a la etiqueta humana se marcan en verde y las distintas
en rojo. Elegir una predicción es una confirmación humana explícita, no una aprobación automática
del modelo.

Los avisos de éxito se ocultan automáticamente después de 3.5 segundos; los errores permanecen
entre 5 y 6 segundos. Ningún mensaje bloquea la navegación. Si una imagen ya tiene etiqueta, elegir
otra respuesta o guardar un valor manual distinto solo abre una confirmación dentro de la tarjeta.
La etiqueta no cambia hasta pulsar `Confirmar cambio`; `Cancelar` restaura el valor vigente. Las
primeras validaciones continúan guardándose con un único clic.

Cada validación:

- se guarda separada de `external_answer` y de las predicciones;
- usa el SHA-256 de la imagen como identidad para evitar duplicados;
- conserva revisiones anteriores cuando una respuesta se corrige;
- copia la imagen a un dataset inmutable antes de depender de la retención de screenshots;
- actualiza un CSV mínimo compatible con el entrenador y un manifiesto trazable.

Los artefactos se encuentran en el proyecto `test-captcha`:

```text
outputs/human_validated_captchas/images/<sha256>.png
outputs/human_validated_captchas/labels.csv
outputs/human_validated_captchas/manifest.csv
```

`labels.csv` tiene las columnas `filename,answer` que consume `recognizer.src.train`. Para añadir
estas etiquetas a una ejecución futura se usan como dataset adicional:

```powershell
python -m recognizer.src.train `
  --extra-csv outputs/human_validated_captchas/labels.csv `
  --extra-data-root outputs/human_validated_captchas/images
```

La etiqueta humana es la referencia autorizada. El consenso de los tres modelos sirve para
priorizar revisión, pero nunca se incorpora automáticamente como verdad. Una respuesta de
2Captcha solo es evidencia fuerte cuando `portal_accepted=true`.

## Cola de revisión e historial compacto

La vista CAPTCHA se divide en dos modos dentro del mismo apartado:

- `Revisar` muestra una sola imagen, sus opciones únicas y el ingreso manual. Al guardar avanza
  automáticamente. Las teclas `1` a `3` eligen opciones, `Enter` confirma un consenso y las flechas
  izquierda/derecha navegan por el lote cargado.
- `Historial` presenta filas compactas paginadas. Cada fila contiene miniatura, etiqueta humana,
  tipo de consenso, origen y tiempo local; las respuestas, confianzas, correcciones y datos técnicos
  aparecen únicamente al desplegarla.

La cola se ordena en el servidor por valor de revisión: tres respuestas distintas, mayoría 2–1 y
consenso de menor a mayor confianza. El guardado elimina el evento de pendientes y carga el
siguiente. Cuando la cola está vacía se muestra `Todo validado`.

En Historial permanecen visibles solo la búsqueda y `Todos / Pendientes / Validados`. Origen,
portal y coincidencia se encuentran detrás del botón `Filtros`; el tamaño de página se movió al pie.
Los eventos del observador no muestran un bloque vacío de 2Captcha. Los modelos se presentan como
`Modelo A`, `Modelo B` y `Modelo C`, conservando sus identificadores técnicos en los datos.

La cabecera se redujo a una línea con servicio, total, validados, pendientes y entregas en cola.
El 21 de julio de 2026 la activación confirmó 10 eventos, 10 etiquetas humanas y 0 pendientes; el
historial priorizado colocó primero el evento con desacuerdo entre modelos.

## API de calidad y exportación

La fachada administrativa calcula calidad sin convertir las respuestas de los modelos ni el
consenso en etiquetas. La referencia de exactitud es siempre la última validación humana asociada
al SHA-256 de cada imagen. Si una misma imagen aparece en varios eventos, se evalúa una sola vez
usando su evento más reciente.

```text
GET /api/v1/captcha-shadow/quality
GET /api/v1/captcha-shadow/quality/cases?type=wrong&page=1&page_size=12
GET /api/v1/captcha-shadow/dataset/export
```

`quality` entrega por modelo muestra evaluada, aciertos, exactitud, confianza promedio —separada
entre aciertos y errores— y tiempos promedio, p50 y p90. También separa unanimidad, mayoría,
respuestas totalmente distintas, unanimidad incorrecta y mayoría incorrecta. La evolución usa
semanas ISO; `trend_ready` solo es verdadero con al menos dos semanas y treinta imágenes validadas.
Los percentiles usan interpolación lineal. Los tiempos de 2Captcha se deduplican por evento desde
el outbox PostgreSQL antes de calcular promedio, p50 y p90.

Los tipos de caso permitidos son `wrong`, `high_confidence_wrong`, `unanimous_wrong`,
`majority_wrong` y `disagreement`. La confianza alta comienza en `0.9`. Estas listas son
paginadas y no exponen rutas locales ni rutas de modelos.

La exportación produce `captcha-human-validated-dataset.zip` con `labels.csv`, `manifest.csv` e
`images/<sha256>.png`. Solo incluye etiquetas humanas vigentes. Antes de crear el ZIP, cada imagen
debe existir dentro de `settings.screenshots_dir` y su contenido debe coincidir con el SHA-256
registrado. Si una imagen no supera esa verificación, la descarga completa se rechaza para evitar
un dataset parcial o incorrecto.
