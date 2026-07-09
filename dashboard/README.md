# Dashboard

Frontend Angular local para operar el bot en modo lectura.

Esta fase implementa solo el paso 3 del plan de migracion:

- `GET /health`
- `GET /api/v1/worker`
- `GET /api/v1/service-orders`
- `GET /api/v1/runs`
- filtros locales de lectura
- copiado de snapshot sanitizado

No incluye CRUD, pagos, pausa, activacion, restart ni sesion manual.

## Ejecucion

Terminal 1:

```powershell
scripts/start-worker.ps1
```

Terminal 2:

```powershell
cd dashboard
npm install
npm start
```

El proxy de desarrollo envia `/api` y `/health` a
`http://127.0.0.1:8765`.

## Seguridad

- No guardar tokens, passwords ni secretos en el frontend.
- El API token se escribe manualmente y se mantiene solo en memoria del
  navegador.
- No usar `localStorage` ni `sessionStorage` para secretos.
- No acceder directo a PostgreSQL desde Angular.
- No reutilizar cookies ni sesiones Playwright del worker.
- No versionar `node_modules`, `dist` ni caches de Angular.

## Version

El proyecto fue generado con Angular CLI 20 porque el `@angular/cli` mas
reciente disponible al crear esta fase exige una version de Node superior a la
instalada en el entorno local.
