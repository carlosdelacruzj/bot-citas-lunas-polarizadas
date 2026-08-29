# Dashboard operativo

Dashboard Angular para operar ordenes, pendientes, citas, comunicaciones,
finanzas y diagnostico a traves de Admin API.

## Desarrollo

```powershell
npm install
npm start
```

El proxy de desarrollo apunta a Admin API. Para validar la topologia completa:

```powershell
powershell -ExecutionPolicy Bypass -File ../scripts/start-admin-dashboard.ps1
```

## Build

```powershell
npm run build
```

## Rutas

| Ruta | Dominio |
|---|---|
| `/pendientes` | Bandeja canonica del operador. |
| `/resumen` | Salud y resumen. |
| `/ordenes` | Alta, busqueda y detalle. |
| `/actividad` | Diagnostico y eventos. |
| `/seguimiento` | Citas, recordatorios y post-cita. |
| `/finanzas` | Cobros, costos y cierres. |
| `/mensajes` | Plantillas y comunicaciones. |
| `/captchas` | Compatibilidad y calidad CAPTCHA. |

No mantener aqui una lista exhaustiva de endpoints. La fuente es
`src/app/appointment-api.service.ts` y el contrato está en
[`../docs/contracts/admin-api.md`](../docs/contracts/admin-api.md).

## Convenciones

- La logica comercial canonica pertenece al backend; por ejemplo, Pendientes
  consume `/api/v1/operator-inbox`.
- No guardar tokens en el bundle, URL o almacenamiento persistente del browser.
- Cargar detalle pesado solo cuando la vista lo necesita.
- Mantener foco, contraste, teclado y `prefers-reduced-motion`.
- Un build correcto no sustituye revision visual en `360`, `768`, `1024` y
  `1440 px`.

Versiones exactas se consultan en `package.json`; no se duplican aqui.
