# Contrato de Admin API

Estado: vigente. Ultima verificacion: `2026-08-29`.

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
- reportes mensuales v1/v2.

No mantener aqui un inventario exhaustivo de URLs: debe verificarse en
`local_api.py` y los routers antes de agregar o retirar una ruta.

## Bandeja del operador

`GET /api/v1/operator-inbox` es el contrato canonico de Pendientes.

Devuelve:

- `summary`: total y conteos por dominio;
- `items`: una sola siguiente accion por orden;
- `captcha`: contador separado, actualmente excluido de la cola comercial.

La precedencia evita duplicar una orden con varias tarjetas. Las acciones
incluyen corregir credenciales, reanudar, completar contacto, cobrar, preparar
postpago y revisar comunicaciones. Contactos y datos sensibles se entregan
enmascarados salvo en flujos autorizados de detalle.

El frontend no debe reconstruir esta logica desde `/service-orders`.

## Ordenes y preflight

Una creación acepta, entre otros datos, `service_type`, `reservation_price` y
restricciones por orden. El backend valida combinaciones y nunca sobreescribe un
precio persistido con el default global.

Un HTTP `201` confirma persistencia, no activacion. El consumidor debe releer
hasta observar preflight validado y estado `ready` antes de asumir que la orden
busca cupos.

Las respuestas de lista son resumidas y enmascaradas. Credenciales completas
solo atraviesan endpoints y procesos autorizados; no se devuelven por defecto.

El contacto WhatsApp se normaliza en backend. Un numero peruano de nueve
digitos recibe `+51`; formatos internacionales validos conservan `+`.

## Comandos del worker

Pausa, reanudacion, restart y controles persistentes se registran con actor,
motivo y resultado. Admin API no simula exito por aceptar el comando. El cliente
debe distinguir `pending`, `applied`, `failed`, `expired` y rechazo por trabajo
activo.

El contrato detallado vive en [`worker-control.md`](worker-control.md).

## Citas y recordatorios

Los recordatorios se consultan y actualizan mediante `GET` y `POST` en la
superficie `/api/v1/appointment-reminders`. Plantillas, modo y scheduler son
controles separados.

La revision post-cita es de solo lectura y expone resumen paginado, frescura y
acciones manuales seguras. Una preparacion no equivale a envio.

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
