# Dashboard

Frontend Angular local para operar el bot.

La primera version fue de solo lectura. Desde el paso 7 tambien incluye acciones
administrativas con confirmacion visible:

- `GET /health`
- `GET /api/v1/worker`
- `GET /api/v1/service-orders`
- `GET /api/v1/service-orders/{order_id}` solo al abrir edicion protegida
- `GET /api/v1/runs`
- `GET /api/v1/runs/{run_id}` sin detalles crudos
- `POST /api/v1/service-orders`
- `POST /api/v1/service-orders/{order_id}/contact`
- `POST /api/v1/service-orders/{order_id}/payment/paid`
- `POST /api/v1/service-orders/{order_id}/pause`
- `POST /api/v1/service-orders/{order_id}/activate`
- `POST /api/v1/service-orders/{order_id}/done`
- `POST /api/v1/service-orders/{order_id}/no-charge`
- `POST /api/v1/service-orders/{order_id}/close`
- `POST /api/v1/service-orders/{order_id}/split-programs`
- `POST /api/v1/worker/restart`
- `GET /api/v1/worker/commands`
- `GET /api/v1/manual-sessions`
- `POST /api/v1/manual-session/open`
- `POST /api/v1/manual-session/close`
- filtros locales de lectura
- copiado de snapshot sanitizado
- orden seleccionada centrada en siguiente accion valida
- modales navegables por teclado y controles tactiles responsive

La sesion manual esta deshabilitada por defecto. Para permitirla en local:

```powershell
$env:MANUAL_SESSION_ENABLED='true'
```

## Ejecucion

Ruta recomendada, en dos terminales:

Terminal 1, worker:

```powershell
scripts/start-worker.ps1
```

Terminal 2, admin API y dashboard:

```powershell
scripts/start-admin-dashboard.ps1
```

Abrir `http://127.0.0.1:8766/`. El script construye Angular y el admin API sirve
el build y la API en el mismo origen. La sesion administrativa se entrega en
una cookie local `HttpOnly` y no expone el token a Angular.

## Rollback y desarrollo con proxy

El camino anterior sigue disponible sin modificar `.env`:

Terminal 1:

```powershell
scripts/start-worker.ps1
```

Terminal 2:

```powershell
appointment-bot-admin-api
```

Terminal 3:

```powershell
cd dashboard
npm start
```

El target `8765` sigue siendo valido para operar temporalmente contra la API
embebida del worker mientras se conserva compatibilidad.

## Estado y mejoras pendientes

La superficie administrativa base, el detalle sanitizado de runs, el flujo de
tarea y la accesibilidad estan completados. La entrega local se ejecuta en el
orden definido por
[`docs/roadmap/README.md`](../docs/roadmap/README.md). El estado global
esta en [`docs/project-status.md`](../docs/project-status.md).

## Seguridad

- No guardar tokens, passwords ni secretos en el frontend.
- El API token no se escribe en la UI. El proxy local
  `dashboard/proxy.conf.cjs` lo lee desde `.env` o desde la variable de entorno
  `APPOINTMENT_BOT_API_TOKEN` y agrega el header `Authorization` solo del lado
  del servidor de desarrollo.
- El listado, filtros y snapshots usan documento y WhatsApp enmascarados. Los
  valores completos se solicitan solo para la orden abierta en edicion y se
  descartan al cerrar el modal.
- No usar `localStorage` ni `sessionStorage` para secretos.
- No acceder directo a PostgreSQL desde Angular.
- No reutilizar cookies ni sesiones Playwright del worker.
- No exponer password ni cookies en respuestas de sesion manual.
- No versionar `node_modules`, `dist` ni caches de Angular.
- No inventar restricciones de reserva. Si una orden no tiene restricciones,
  enviar `null` u omitir esos campos.
- Las fuentes validas son TikTok, Facebook y WhatsApp. Los errores del backend
  identifican el campo y se muestran con la etiqueta correspondiente.

## Version

El proyecto fue generado con Angular CLI 20 porque el `@angular/cli` mas
reciente disponible al crear esta fase exige una version de Node superior a la
instalada en el entorno local.
