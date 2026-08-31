# Arquitectura actual

Ultima verificacion: `2026-08-30`.

## Procesos

### Admin API

Proceso administrativo en loopback. Sirve el dashboard compilado, autentica la
sesion local, expone routers, persiste comandos y posee:

- dispatcher y perfil persistente de WhatsApp;
- scheduler de recordatorios;
- scheduler de revision post-cita;
- recuperacion de preflights pendientes.

No ejecuta el navegador de reservas.

### Worker

Consume ordenes y comandos desde PostgreSQL, mantiene heartbeat y abre una
sesion Playwright nueva por cliente. Es propietario del monitoreo, seleccion,
CAPTCHA de la reserva, submit y confirmacion.

### Telegram

Cliente operativo de Admin API. No conoce credenciales de PostgreSQL, no ejecuta
SQL y no inicia PowerShell directamente. Su receptor incluye un monitor
autenticado del lease del worker, sin reinicios automaticos.

### CAPTCHA sombra

Supervisor opcional. `start-runtime.ps1` solo lo incluye cuando
`CAPTCHA_SHADOW_SERVICE_ENABLED` está habilitado. Su ausencia no debe impedir
reservas con el CAPTCHA HTML actual.

### Dashboard

Angular se sirve desde Admin API en operacion normal. El proxy de desarrollo
apunta a Admin API; la API embebida del worker se conserva solo como frontera de
compatibilidad/rollback, no como destino administrativo principal.

## Dependencias

```text
Dashboard -----> Admin API -----> PostgreSQL <----- Worker -----> Portal
Telegram ------>     |                 ^               |
n8n ----------->     +-> WhatsApp      +---------------+
                     +-> Recordatorios/Post-cita

CAPTCHA sombra (opcional) -----> PostgreSQL/artefactos
```

## Fronteras

- Admin API valida y persiste intencion administrativa.
- Worker decide cuando una operacion del navegador es segura.
- PostgreSQL es la fuente compartida; archivos runtime no sustituyen estado.
- WhatsApp tiene un solo perfil propietario.
- el monitor externo anterior de n8n esta inactivo; n8n no contiene logica
  critica ni opera el navegador y su export local sirve solo como rollback
  durante la observacion.
- cada orden tiene contexto Playwright aislado;
- worker, preflight, revision post-cita y sesion manual coordinan propiedad por
  cuenta mediante el lease persistido de la orden.

## Comandos y controles

Pausa, reanudacion, restart y cambios de control viajan por comandos persistidos
con actor, estado y resultado. Un comando aceptado no equivale a aplicado. El
worker usa leases y puntos seguros para evitar cortar reservas o rafagas.

## Autenticacion

Integraciones usan bearer. El dashboard servido puede usar cookie local
`HttpOnly`, `SameSite=Strict`. Las rutas administrativas fallan cerrado si no
existe configuracion segura.

## Codigos de salida

- `0`: cierre normal;
- `75`: reinicio coordinado solicitado;
- `76`: detencion coordinada solicitada.

Los supervisores interpretan estos codigos; no deben convertir cualquier salida
en reinicio infinito.

## Fuentes de detalle

- API y auth: [`../contracts/admin-api.md`](../contracts/admin-api.md)
- Worker: [`../contracts/worker-control.md`](../contracts/worker-control.md)
- Reserva: [`../contracts/reservation-safety.md`](../contracts/reservation-safety.md)
- Operacion: [`../operations/README.md`](../operations/README.md)

El catálogo de endpoints se verifica en `services/local_api.py` y
`services/api/`; no se duplica aqui.
