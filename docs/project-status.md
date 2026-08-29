# Estado actual del proyecto

Estado verificado documentalmente: `2026-08-29`.

Este archivo responde solo **como funciona el sistema hoy**. El trabajo futuro
y su prioridad viven exclusivamente en
[`roadmap/README.md`](roadmap/README.md). Los detalles de implementaciones
cerradas, incidentes y mediciones fechadas se recuperan desde Git mediante
[`history/`](history/) o viven como generados en `reports/`.

## Resumen ejecutivo

El sistema administra ordenes de busqueda y reserva de citas para lunas
polarizadas, conserva su estado en PostgreSQL y ofrece operacion mediante el
dashboard y Telegram. El worker ejecuta monitoreo y reservas; Admin API es la
frontera unica para controles, consultas y comandos; n8n solo orquesta desde el
exterior.

Estado general:

- arquitectura `worker + Admin API + PostgreSQL + dashboard + Telegram`
  operativa;
- esquema PostgreSQL actual: `v67`;
- una sesion Playwright nueva por cliente, sin compartir cookies ni contexto;
- ordenes regulares y de disponibilidad restringida con precio y reglas por
  orden;
- reservas, pagos, comunicaciones y seguimiento post-cita persistidos;
- dashboard con bandeja comercial canonica y pantallas operativas separadas;
- CAPTCHA grafico de aprendizaje en almacenamiento frio; el CAPTCHA HTML
  matematico se resuelve localmente con reglas estrictas;
- WhatsApp conserva `sent`, `uncertain`, confirmacion tecnica y conciliacion
  manual como hechos distintos.

## Arquitectura vigente

### Worker

El worker continuo toma ordenes listas desde PostgreSQL, abre una sesion
Playwright aislada por orden, aplica restricciones, preserva claims y leases, y
registra intentos, screenshots y resultados. Nunca comparte sesion de navegador
entre clientes.

### Admin API

Admin API vive en `src/appointment_bot/services/api/` y es la frontera para
ordenes, preflight, pagos, finanzas, bandeja de pendientes, worker, controles,
salud, citas, recordatorios, revision post-cita, plantillas y trabajos WhatsApp.
Telegram y n8n no ejecutan SQL, PowerShell ni logica del navegador directamente.

### Persistencia

PostgreSQL es la fuente de verdad para ordenes, credenciales cifradas, pagos,
intentos, reservas, comandos, mensajes y auditoria. `.runtime/`, screenshots,
videos y reportes son soporte o evidencia; no sustituyen el estado persistido.

## Flujo de una orden

1. Se crea con contacto, credenciales, servicio, precio y restricciones.
2. El preflight valida identidad y acceso antes de habilitar la busqueda.
3. El worker monitorea dentro de los limites configurados.
4. Cada cupo se contrasta con las reglas exactas de la orden.
5. Una seleccion valida conserva screenshot antes de CAPTCHA o submit.
6. La reserva solo se confirma con evidencia suficiente del portal.
7. Pago y comunicaciones siguen estados independientes.
8. Citas y recordatorios alimentan el seguimiento previo y posterior.

Una incompatibilidad de fecha es `partial / blocked_by_order_rule`; no activa
backoff general. Un submit ambiguo nunca se reintenta automaticamente.

## Servicios y precios

Cada orden conserva su propio `service_type` y `reservation_price`.

- servicio regular: valor predeterminado `S/50`;
- disponibilidad restringida: valor guiado habitual `S/70`;
- monto personalizado: definido por el operador antes del preflight.

La disponibilidad restringida exige una ventana cerrada y al menos una regla
aplicable. El precio acordado gobierna pago y mensajes futuros; no se reconstruye
desde un valor global.

## Dashboard vigente

| Ruta | Responsabilidad |
|---|---|
| `/pendientes` | Siguiente accion comercial por orden. |
| `/resumen` | Salud y resumen operativo. |
| `/ordenes` | Alta, busqueda y detalle de ordenes. |
| `/actividad` | Eventos y diagnostico. |
| `/seguimiento` | Citas, recordatorios y revisiones post-cita. |
| `/finanzas` | Cobros, costos, cierres y diferencias. |
| `/mensajes` | Plantillas y trazabilidad de comunicaciones. |
| `/captchas` | Compatibilidad; CAPTCHA no forma parte de Pendientes. |

**Pendientes** consume `GET /api/v1/operator-inbox`. El total excluye CAPTCHA y
reune acceso, pausas, contacto, cobro, postpago y comunicaciones. Incluye
busqueda, filtros, severidad y siguiente accion. El dato temporal disponible
sigue siendo el ultimo cambio de la orden, no el nacimiento real de la tarea.

**Citas y recordatorios** separa proximas citas, casos que requieren revision e
historial. Permite anticipacion de `1..3` dias y mantiene el seguimiento post-cita
conservador y paginado.

## Comunicaciones WhatsApp

Las plantillas editables se versionan en PostgreSQL. Cada trabajo nuevo congela
texto, clave y revision al prepararse; editar una plantilla no modifica trabajos
historicos ni ya encolados.

Reglas vigentes:

- un unico perfil persistente de WhatsApp pertenece a Admin API;
- albumes y paquetes postpago conservan confirmacion por componentes;
- `sent` requiere evidencia tecnica suficiente;
- un reloj o indicador pendiente visible veta la confirmacion;
- `uncertain` preserva contexto y nunca genera reintento automatico;
- conciliacion manual registra la decision sin reescribir el resultado tecnico;
- llegada al destinatario y lectura son afirmaciones separadas.

La aceptacion natural se rige por
[`operations/whatsapp-natural-acceptance.md`](operations/whatsapp-natural-acceptance.md).

## Citas, recordatorios y post-cita

Los recordatorios usan plantilla versionada, modos separados y barreras de
deduplicacion. El scheduler post-cita usa una sesion de solo lectura, pausas de
`4-7` segundos y maximo `20` casos diarios. Un lote ambiguo se detiene.

Estado de cita, recordatorio, revision post-cita y comunicacion permanece
separado para no presentar una preparacion como envio ni un envio como lectura.

## Finanzas

Cobros realizados, saldos pendientes, costos reconocidos y overhead no medido
son categorias distintas. Un cierre mensual solo se consolida con datos
suficientes y conciliados; snapshots no sustituyen PostgreSQL.

El resumen estable vive en [`resumen-del-negocio.md`](resumen-del-negocio.md) y
el contrato en [`contracts/finance.md`](contracts/finance.md).

## Seguridad operativa

- no modificar `.env` sin autorizacion explicita;
- no reintentar submits ni envios ambiguos;
- antes de reiniciar, revisar submissions, leases, sesiones, rafagas y trabajos
  WhatsApp activos;
- una orden especial solo queda activa tras releer preflight validado y `ready`;
- preservar screenshots de cupos unicos antes de CAPTCHA o submit;
- videos de reserva son evidencia local sensible y se graban sin mascaras;
- no publicar dumps, credenciales, placas, expedientes ni respuestas CAPTCHA;
- reescribir el historial Git requiere autorizacion independiente.

## Limitaciones abiertas

- Pendientes no posee aun `actionable_since`, vencimiento ni responsable
  persistidos por tarea;
- faltan observaciones naturales de algunos flujos WhatsApp, post-cita y cierre;
- salud compuesta, backup externo, retencion y restore necesitan cierre;
- varias cargas del dashboard aun transportan mas detalle del necesario;
- quedan validaciones visuales y de accesibilidad en anchos representativos;
- existen ciclos y modulos grandes para refactor posterior.

La prioridad y criterios de cierre estan solo en
[`roadmap/README.md`](roadmap/README.md).

## Validacion base

```powershell
python -m compileall -q src
python -m ruff check src tests
python -m pytest -q
git diff --check
```

Para dashboard: `npm run build` desde `dashboard/`. Un build correcto no
sustituye validacion visual real ni observacion natural.

## Regla de mantenimiento

1. Reemplazar aqui el estado anterior; no agregar cronologia.
2. Actualizar el roadmap solo si cambia trabajo futuro o prioridad.
3. No acumular implementacion fechada; Git conserva la version anterior y
   `history/milestones.md` resume solo decisiones durables.
4. Mantener este archivo por debajo de `250` lineas.
5. Verificar enlaces y `git diff --check`.
