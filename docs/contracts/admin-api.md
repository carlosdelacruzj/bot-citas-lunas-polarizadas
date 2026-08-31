# Contrato de Admin API

Estado: vigente. Ultima verificacion: `2026-08-31`.

Codigo propietario: `src/appointment_bot/services/local_api.py` y
`src/appointment_bot/services/api/`.

Admin API es la unica frontera administrativa para dashboard, Telegram y n8n.
No ejecuta el navegador de reservas: persiste comandos y datos para que el
worker los aplique de forma segura.

## Proceso propietario

El proceso de Admin API:

- sirve la API y el dashboard compilado;
- administra la sesion local del dashboard;
- posee el perfil persistente y dispatcher de WhatsApp;
- inicia schedulers de recordatorios y revision post-cita;
- recupera preflights que quedaron pendientes;
- lee y escribe PostgreSQL mediante servicios de dominio.

## Autenticacion

Las rutas administrativas `/api/v1/*` y `/api/v2/*` exigen autenticacion
estricta.

- integraciones usan `Authorization: Bearer <token>`;
- el dashboard servido por Admin API puede usar cookie local `HttpOnly`,
  `SameSite=Strict`;
- el token no se incluye en bundles, query strings, logs ni respuestas;
- si falta configuracion segura, la API falla cerrado con
  `configuration_error`.

`GET /health` puede usarse para liveness, pero una respuesta HTTP no prueba que
WhatsApp, PostgreSQL, worker o schedulers esten funcionales.

## Superficies

El catálogo exacto vive en los routers. Los grupos estables son:

- ordenes, busqueda, credenciales, preflight y restricciones;
- pagos, finanzas, calidad y cierre mensual;
- worker, comandos, controles, salud y rafagas;
- runs, actividad, evidencia y CAPTCHA;
- bandeja del operador;
- citas, recordatorios y seguimiento post-cita;
- plantillas, mensajes, jobs y conciliacion WhatsApp;
- sesiones manuales controladas;
- reporte mensual v2.

`GET /api/v1/monthly-summary` permanece disponible hasta el final del
`2026-09-03`; su retiro esta previsto desde el `2026-09-04`. Los consumidores deben usar
`GET /api/v2/monthly-summary`; v1 emite `Deprecation`, `Sunset` y un enlace a
la version sucesora.

No mantener aqui un inventario exhaustivo de URLs: debe verificarse en
`local_api.py` y los routers antes de agregar o retirar una ruta.

## Bandeja del operador

`GET /api/v1/operator-inbox` es el contrato canonico de Pendientes.

Devuelve:

- `summary`: total y conteos por dominio;
- `items`: una sola siguiente accion por orden;
- `captcha`: contador separado, actualmente excluido de la cola comercial.

La precedencia evita duplicar una orden con varias tarjetas. Las acciones
incluyen corregir credenciales, resolver varios tramites pendientes, reanudar,
completar contacto, cobrar, preparar postpago y revisar comunicaciones.
Contactos y datos sensibles se entregan enmascarados salvo en flujos autorizados
de detalle.

El frontend no debe reconstruir esta logica desde `/service-orders`.

## Ordenes y preflight

Una creación acepta, entre otros datos, `service_type`, `reservation_price` y
restricciones por orden. El backend valida combinaciones y nunca sobreescribe un
precio persistido con el default global.

Un HTTP `201` confirma persistencia, no activacion. El consumidor debe releer
hasta observar preflight validado y estado `ready` antes de asumir que la orden
busca cupos.

Las respuestas de lista son resumidas y enmascaradas. El dashboard solicita
`GET /api/v1/service-orders?projection=dashboard`, que omite diagnostico y
campos sin consumidor visual; una llamada sin `projection` conserva el payload
completo de compatibilidad. El detalle autorizado permanece separado en
`GET /api/v1/service-orders/{order_id}`. Credenciales completas solo atraviesan
endpoints y procesos autorizados; no se devuelven por defecto.

`GET /api/v1/service-packages` entrega el catalogo comercial definido por core:
claves, etiquetas, montos, saldo, tasa y combinaciones de `service_type`. Es la
fuente del formulario de alta y de los textos financieros del dashboard.

El contacto WhatsApp se normaliza en backend. Un numero peruano de nueve
digitos recibe `+51`; formatos internacionales validos conservan `+`.

`POST /api/v1/service-orders/{order_id}/program-resolution` es la unica ruta
administrativa para resolver varios expedientes pendientes. Exige la firma del
listado observado, actor y una decision `one`, `all` o `pause`. `one` identifica
un pendiente de forma unica; `all` exige condiciones comerciales confirmadas y
archiva el padre tras crear todos los hijos en una sola transaccion. La respuesta
puede incluir `communication_preview`, que nunca equivale a envio.

Conflictos de este flujo usan codigos estables, entre ellos
`program_listing_stale`, `program_target_not_unique`,
`program_resolution_financial_allocation_required` y
`program_integral_charge_required`. La ruta anterior `split-programs` permanece
solo como guardia de compatibilidad y responde
`explicit_program_resolution_required`; ningun consumidor nuevo debe usarla.

## Comandos del worker

Pausa, reanudacion, restart y controles persistentes se registran con actor,
motivo y resultado. Admin API no simula exito por aceptar el comando. El cliente
debe distinguir `pending`, `applied`, `failed`, `expired` y rechazo por trabajo
activo.

El contrato detallado vive en [`worker-control.md`](worker-control.md).

## Citas y recordatorios

Los recordatorios se consultan y actualizan mediante `GET` y `POST` en la
superficie `/api/v1/appointment-reminders`. Plantillas, modo y scheduler son
controles separados. Autoridad, lotes y deduplicacion se rigen por
[`appointment-followups.md`](appointment-followups.md).

La revision post-cita es de solo lectura y expone resumen, conteos por filtro,
frescura y acciones manuales seguras. `GET /api/v1/post-appointment-followups`
acepta `filter`, `search`, `sort`, `direction`, `limit`, `offset` e
`include_upcoming`; `limit` se acota a `1..500`. El dashboard pagina en servidor
y pide `include_upcoming=true` solo al cargar la vista. Una llamada sin query
conserva temporalmente la respuesta historica completa para consumidores
anteriores. Una preparacion no equivale a envio.

## WhatsApp

El worker y los flujos de negocio encolan trabajo durable; Admin API es el unico
dispatcher del perfil persistente. Las rutas manuales son respaldo diagnostico,
no un segundo emisor automatico.

Los estados tecnicos, componentes del paquete, conciliacion y plantillas se
rigen por [`whatsapp.md`](whatsapp.md). `uncertain` nunca se reintenta desde la
API por conveniencia.

## Sesion manual

La apertura controlada admite modos `auto`, `appointment`, `portal` y
`diagnostic`. El modo de cita exige una orden apta; portal y diagnostico se
detienen en limites definidos y conservan trazas sanitizadas. Solo puede existir
una sesion compatible con los recursos activos.

La apertura responde `409` con codigo estable si encuentra lease de worker,
intento activo, preflight incompatible, trabajo de navegador u otra sesion de
la misma cuenta. El listado conserva sesiones `opening`, `active`, `closing` y
`close_timeout`; solicitar cierre no equivale a que Chromium ya termino.
`POST /api/v1/worker/restart` responde `409 manual_session_active` mientras el
inventario contenga una de esas sesiones.

## Errores

Las respuestas de error usan mensaje claro y codigo estable cuando existe. No
incluyen credenciales, tokens, DOM completo ni datos internos innecesarios.

Codigos HTTP esperados:

- `400`: payload o transicion invalida;
- `401/403`: autenticacion o permiso;
- `404`: recurso inexistente;
- `409`: conflicto, revision obsoleta o trabajo activo incompatible;
- `422`: regla de dominio incumplida;
- `500/503`: fallo interno o dependencia no disponible.

Un cliente no debe convertir automaticamente `409`, timeout o error ambiguo en
un segundo submit.
