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
