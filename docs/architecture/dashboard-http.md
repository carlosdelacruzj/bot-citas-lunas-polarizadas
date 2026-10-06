# HTTP y contratos del dashboard

Cada fachada consume un cliente HTTP de su dominio. No hay un cliente global
ni reexports de compatibilidad con el antiguo `AppointmentApiService`.

| Directorio bajo `dashboard/src/app/api/` | Responsabilidad |
| --- | --- |
| `orders/` | Ordenes, alta, credenciales, restricciones, expedientes, catalogo y sesiones manuales |
| `finance/` | Pagos, movimientos, calidad, cierre y resumen mensual v2 |
| `messages/` | Plantillas, preparacion WhatsApp, revision, conciliacion, borradores y adjuntos |
| `followups/` | Recordatorios y revision post-cita |
| `captchas/` | Muestreo, autoridad, revision, calidad y exportacion |
| `operations/` | Salud, worker, comandos, oportunidades, runs y bandeja |
| `shared/` | Transporte, presentacion de errores y respuesta generica de acciones |
| `states/` | Unions cerradas compartidas por contratos y formularios |

Cada dominio declara `*.contracts.ts` y un `*-api.client.ts`. Los imports de
contratos son de tipo; un dominio importa solo los tipos que necesita de otro.
Catalogo comercial, reglas de fechas y resolucion de expedientes conservan sus
modelos especificos existentes, sin duplicarlos en cada cliente.

## Transporte y comportamiento

`ApiTransport` comparte `HttpClient`, GET, POST, PUT y Blob. Conserva cookies,
interceptores, errores HTTP y la cancelacion de `RequestScope`; no almacena
datos, decide transiciones ni reintenta peticiones.

Los clientes conservan endpoints, bodies, metodos HTTP, parametros, defaults y
desempaquetado de respuestas. Todo identificador interpolado en una ruta pasa
por `encodeURIComponent`, incluidos los segmentos de accion y clase de revision
WhatsApp. Las consultas usan `URLSearchParams` o valores codificados.
Los adjuntos recibidos como URL del servidor se descargan como Blob sin
reconstruir su ruta. El cierre por beacon al salir sigue en el ciclo de vida
de Ordenes.

`apiErrorMessage` conserva el mensaje de conflictos y errores de campos. HTTP
aceptado no significa comando aplicado, pago completado ni WhatsApp entregado.
La semantica pertenece a [Admin API](../contracts/admin-api.md) y sus dominios.

## Autoridad de tipos y datos sensibles

Las unions compartidas de documento, servicio, preflight, sesion manual,
recordatorios, cierre financiero y paquete WhatsApp tienen una sola definicion.
Los estados especificos, como `WhatsAppActionState` y `PostAppointmentOutcome`,
permanecen en su contrato propietario. Los consumidores reutilizan esos tipos
o accesos indexados. Los estados abiertos, incluida la fase del worker,
conservan `string` y no rechazan futuras fases desconocidas.

`ServiceOrder` es la proyeccion resumida de dashboard, solicitada expresamente
con `projection=dashboard`. `ServiceOrderDetail` agrega los campos autorizados
de detalle. El tipo de listado no contiene documento ni WhatsApp sin enmascarar,
y ninguno de estos tipos incluye password. Los payloads de alta y
credenciales estan separados de las respuestas.

## Verificacion contractual

`api/testing/` contiene fixtures sinteticos con `satisfies` contra los contratos:
alta, credenciales, pagos, lista/detalle, paquete WhatsApp y respuestas de las
ocho pantallas. `npm run typecheck` incluye estos archivos; las pruebas existentes
de API y el smoke los consumen. No se importan desde el bundle productivo.

Esta es la alternativa de fixtures prevista en `6.2`, no un validador runtime
de todas las respuestas. Detecta cambios incompatibles entre DTO y muestras;
no descubre por si sola una desviacion del servidor vivo. Al cambiar un contrato,
hay que contrastarlo con su handler y mantener el fixture correspondiente.

Las lecturas de detalle de orden y ejecucion aceptan `RequestScope`; cerrar o
cambiar de seleccion cancela el GET. Las reglas de publicacion y frescura estan
en [cargas parciales](dashboard-loading.md). Las mutaciones no reciben reintentos.
