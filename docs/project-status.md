# Estado actual del proyecto

Estado verificado documentalmente: `2026-09-01`.

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
  operativa, con locks, CI reproducible y cobertura critica por riesgo;
- esquema PostgreSQL requerido por el codigo y base operativa: `v74`;
- una sesion Playwright nueva por cliente, sin compartir cookies ni contexto;
- propiedad exclusiva por cuenta entre worker, preflight, revision post-cita y
  sesiones manuales, con cierre visible hasta terminar Chromium;
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
entre clientes. El lease global se renueva en un thread independiente durante
toda la vida del worker; su perdida cancela admision y submit conservadoramente,
sin depender del heartbeat separado del claim de orden.

### Admin API

Admin API vive en `src/appointment_bot/services/api/` y es la frontera para
ordenes, preflight, pagos, finanzas, bandeja de pendientes, worker, controles,
salud, citas, recordatorios, revision post-cita, plantillas y trabajos WhatsApp.
Telegram y n8n no ejecutan SQL, PowerShell ni logica del navegador directamente.
Telegram Control revisa cada cinco minutos el lease real del worker mediante
Admin API entre `07:30` y `18:00`; alerta tras tres fallos y nunca reinicia por
su cuenta. El monitor n8n anterior esta inactivo; su export previo permanece
como rollback local durante la observacion de siete dias.

### Persistencia

PostgreSQL es la fuente de verdad para ordenes, credenciales cifradas, pagos,
intentos, reservas, comandos, mensajes y auditoria. `.runtime/`, screenshots,
videos y reportes son soporte o evidencia; no sustituyen el estado persistido.
La evidencia compacta rota por mes con agregados diarios y un manifiesto
estable; el snapshot bajo `docs/` conserva solo el mes activo.

## Flujo de una orden

1. Se crea con contacto, credenciales, servicio, precio y restricciones.
2. El preflight valida identidad y acceso antes de habilitar la busqueda.
3. Un unico expediente `PENDIENTE` sigue el flujo normal; varios pendientes
   pausan la orden hasta elegir uno, todos o mantenerla pausada desde Dashboard
   o Telegram, sin WhatsApp automatico.
4. El worker monitorea dentro de los limites configurados.
5. Cada cupo se contrasta con las reglas exactas de la orden.
6. La seleccion usa estabilizacion por eventos y validacion DOM atomica; si la
   lectura no es concluyente vuelve automaticamente al camino conservador.
7. Una seleccion valida conserva y archiva su screenshot canonico antes de
   CAPTCHA o submit, incluso si queda bloqueada por regla o procede de una
   reobservacion; si falla esa evidencia, no inicia el intento.
8. La reserva solo se confirma con evidencia suficiente del portal.
9. Pago y comunicaciones siguen estados independientes.
10. Citas y recordatorios alimentan el seguimiento previo y posterior.

Una incompatibilidad de fecha es `partial / blocked_by_order_rule`; no activa
backoff general. Si la seleccion incompatible quedo sincronizada, posee captura
canonica previa y no inicio reserva, puede activar auxiliares compatibles; un
`partial` generico conserva el fallback secuencial. Un submit ambiguo nunca se
reintenta automaticamente.

## Servicios y precios

Cada orden conserva su propio `service_type` y `reservation_price`.
El catalogo de `core/service_packages.py` gobierna claves, etiquetas y montos;
Admin API lo entrega al dashboard y Telegram consume la misma autoridad.

- servicio regular: valor predeterminado `S/50`;
- disponibilidad restringida: valor guiado habitual `S/70`;
- monto personalizado: definido por el operador antes del preflight.
- tramite integral: `S/160`, con primer abono `S/80`, tasa oficial `S/71.40`
  y saldo final `S/80` registrados desde el paquete guiado.

La disponibilidad restringida exige una ventana cerrada y al menos una regla
aplicable. El precio acordado gobierna pago y mensajes futuros; no se reconstruye
desde un valor global.

El tramite integral se registra despues de que el operador recibe el primer
abono, paga la tasa y crea la cuenta/solicitud. El alta persiste el abono y el
costo de la tasa; al reservar, el mensaje de cobro usa solo el saldo pendiente.
Exige cobro, montos fijos y pago acumulado de `S/160`; reintentos identicos no
duplican recibo ni costo. Una correccion con historia financiera o un cierre sin
cobro falla cerrado hasta disponer de una correccion contable auditada.

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
| `/captchas` | Superficie dedicada; CAPTCHA no forma parte de Pendientes. |

**Pendientes** consume `GET /api/v1/operator-inbox`. El total excluye CAPTCHA y
reune acceso, pausas, contacto, cobro, postpago y comunicaciones. Incluye
busqueda, filtros, severidad y siguiente accion. El dato temporal disponible
sigue siendo el ultimo cambio de la orden, no el nacimiento real de la tarea.

**Citas y recordatorios** separa proximas citas, casos que requieren revision e
historial. Permite anticipacion de `1..3` dias y mantiene el seguimiento post-cita
conservador y paginado en PostgreSQL/API. Busqueda, filtros, orden y paginas no
requieren descargar el historial completo. Proximas citas pagina localmente el
resultado ya filtrado y ordenado, con tamanos de `5`, `10` o `20`. Los
recordatorios tienen modos
`disabled`, `dry_run` y `live`; ya no existe un modo canario ni una lista
especial de ordenes de prueba.

Contrato: [`contracts/appointment-followups.md`](contracts/appointment-followups.md).

El contrato entre el contenedor Angular y sus vistas esta tipado. La lista de
ordenes usa una proyeccion especifica del dashboard; el endpoint completo de
compatibilidad y el detalle autorizado permanecen separados.

Cerrar, cancelar o fallar un alta elimina password, documento y contacto. Las
confirmaciones y la copia diagnostica no muestran esos datos personales.

Las rafagas de oportunidad y la reobservacion unica posterior a un `slot_lost`
son capacidades estables. Su admision se gobierna en PostgreSQL con
`enabled`, `disabled` y, para rafagas, `draining`; el breaker conserva prioridad
sobre cualquier modo. La capacidad configurada es de tres sesiones Playwright
aisladas: un detector y hasta dos auxiliares compatibles, con preferencia por
disponibilidad restringida.

## Comunicaciones WhatsApp

Las plantillas editables se versionan en PostgreSQL. Cada trabajo nuevo congela
texto, clave y revision al prepararse; editar una plantilla no modifica trabajos
historicos ni ya encolados. Los paquetes postpago historicos tambien conservan
texto congelado. El runtime ya no reconstruye mensajes desde pasos antiguos ni
emite el alias financiero `is_complete`; el contrato usa `conversion_complete`.

Reglas vigentes:

- un unico perfil persistente de WhatsApp pertenece a Admin API;
- albumes y paquetes postpago conservan confirmacion por componentes;
- `sent` requiere evidencia tecnica suficiente;
- un reloj o indicador pendiente visible veta la confirmacion;
- los intentos distinguen preparacion, interaccion, confirmacion observada y
  confirmacion persistida; solo la preparacion demostrable puede quedar
  `failed`;
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

Cada recibo pertenece al par exacto pago/orden, es inmutable y posee indices por
pago, orden y fecha. PostgreSQL bloquea su actualizacion, borrado y cascadas que
eliminen caja historica. Una correccion solo puede representarse como otro
movimiento negativo referenciado, con motivo y actor; todavia no existe una
accion operativa para crearlo.

`historical_backfill` conserva el monto acumulado, no cada fecha. Finanzas y
resumen usan `payment_receipts` para ingreso, cobros y serie diaria; atribuyen
cada abono a su fecha de caja y marcan comparaciones no concluyentes. Resumen y
contrato: [`resumen-del-negocio.md`](resumen-del-negocio.md), [`contracts/finance.md`](contracts/finance.md).

## Seguridad operativa

- no modificar `.env` sin autorizacion explicita;
- no reintentar submits ni envios ambiguos;
- antes de reiniciar, revisar submissions, leases, sesiones, rafagas y trabajos
  WhatsApp activos;
- una orden especial solo queda activa tras releer preflight validado y `ready`;
- preservar screenshots de cupos unicos antes de CAPTCHA o submit;
- videos de reserva son evidencia local sensible y se graban sin mascaras;
- no publicar dumps, credenciales, placas, expedientes ni respuestas CAPTCHA;
- respuestas CAPTCHA no entran en reportes, runs, reservas, CSV ni Markdown;
- auditoria usa dashboard local, Telegram hasheado o huella SHA-256 del bearer;
- reescribir el historial Git requiere autorizacion independiente.

## Limitaciones abiertas

- Pendientes no posee aun `actionable_since`, vencimiento ni responsable
  persistidos por tarea;
- la rafaga de tres sesiones esta implementada, pero aun requiere comparacion
  natural contra el baseline de dos sesiones;
- faltan observaciones naturales de algunos flujos WhatsApp, post-cita y cierre;
- el primer tramite integral natural posterior a `v74` debe validar abono, tasa, saldo, mensaje y resumen sin crear un caso de prueba;
- salud compuesta, backup externo, retencion y restore necesitan cierre;
- mensajes y algunos detalles del dashboard aun pueden reducir su transporte;
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

Para dashboard: `npm ci` y `npm run build` desde `dashboard/`. Un build correcto no
sustituye validacion visual real ni observacion natural.

## Regla de mantenimiento

Reemplazar el estado anterior, dejar lo futuro en roadmap, mantener menos de 250 lineas y verificar enlaces y `git diff --check`.
