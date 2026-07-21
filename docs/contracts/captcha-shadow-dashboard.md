# Contrato del dashboard de CAPTCHA sombra

Fecha de referencia: 21 de julio de 2026.

## Objetivo

El dashboard administrativo incorpora una vista `CAPTCHA` para revisar, con pocos clics, la
misma imagen enviada a 2Captcha y a los tres modelos locales. La vista es de solo lectura y no
participa en la decisión operativa de reserva.

## Experiencia de uso

La vista muestra sin abrir modales:

- miniatura de la imagen original;
- fecha, orden, intento y referencia del evento;
- respuesta y tiempo de 2Captcha;
- respuesta, confianza y tiempo de inferencia de `v1_real`, `v2_scratch` y `v2_selected`;
- coincidencia o diferencia frente a 2Captcha;
- validación explícita del portal o estado pendiente.

Incluye búsqueda, filtros visibles, tamaños de página de 12, 24 y 48 elementos, paginación de
servidor y adaptación móvil. Nunca presenta una coincidencia con 2Captcha como respuesta correcta
si el portal no la validó.

## API administrativa

Angular consume únicamente rutas del mismo origen y autenticadas por la sesión administrativa:

```text
GET /api/v1/captcha-shadow/summary
GET /api/v1/captcha-shadow/events?page=1&page_size=12&q=&agreement=all&portal_status=all
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
- sí se persisten en el outbox y se procesan por `v1_real`, `v2_scratch` y `v2_selected`;
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
- búsqueda `9M9FH` devolvió el evento esperado;
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
