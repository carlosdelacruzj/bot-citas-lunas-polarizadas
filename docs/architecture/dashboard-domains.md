# Dominios del dashboard

`App` compone proveedores, router, vistas diferidas y modales. Delega los
eventos del documento; no guarda estado de negocio ni realiza peticiones HTTP.

## Propiedad del estado

| Dominio | Propietario | Responsabilidad |
| --- | --- | --- |
| Ordenes | `OrdersFacade` | Alta, seleccion, detalle, credenciales, restricciones, acciones y sesiones manuales |
| Listado de ordenes | `OrdersListFacade` | Consulta, filtros, orden, paginacion, preferencias y contadores compartidos |
| Finanzas | `FinanceFacade` | Resumen mensual, movimientos, formularios y registro de pagos |
| Mensajes | `MessagesFacade` | Preparacion WhatsApp, revision, conciliacion y coleccion de plantillas |
| Plantilla en edicion | `MessageTemplateEditorFacade` | Borrador, variables, preview, guardado y conflicto de version |
| Seguimiento | `FollowupsFacade` | Consultas post-cita, filtros del servidor, revisiones y solicitudes cancelables |
| Espacio de seguimiento | `FollowupWorkspaceFacade` | Recordatorios, controles, filtros locales y paginacion |
| CAPTCHA | `CaptchasFacade` | Datos, aprendizaje, revision, muestreo, calidad y controles de autoridad |
| Operaciones | `OperationsFacade` | Bandeja, resumen, actividad, salud, worker, oportunidad y copia diagnostica |

Los editores de plantillas y seguimiento se proveen en su componente: un
borrador nuevo por entrada a la vista, como antes. Los otros propietarios se
proveen una vez en `App`; navegar conserva seleccion, filtros y datos cargados.

## Puertos y colaboracion

`dashboard-domain.ports.ts` declara tokens de inyeccion con `Pick` de los
miembros consumidos. Cada vista, modal o colaborador tiene una superficie
explicita; no recibe `App` ni una union global de todos los dominios. Las
referencias a clases en ese archivo son imports de tipo, sin ciclo de runtime.
`useExisting` enlaza cada puerto con la instancia del propietario.

Los flujos entre dominios resuelven sus puertos al usarlos mediante getters,
para permitir colaboracion sin ciclos de construccion del inyector. Un pago
puede refrescar la orden seleccionada; el resumen puede solicitar datos a
Finanzas y CAPTCHA, sin crear copias de sus propietarios.

`DashboardNavigation` conserva router, frescura por vista, timers, generaciones
y scopes de cancelacion. Despacha las cargas a sus propietarios y coordina su
limpieza al destruir el shell. No contiene el cliente HTTP ni datos de negocio.

`DashboardUi` conserva modal activo, foco, notificaciones, bloqueo de acciones y
confirmacion compartida. Cada dominio construye su accion y limpia sus propios
formularios. `DashboardPresentation` contiene solo formato puro compartido.

Los componentes retienen interaccion con DOM, como cursor del editor y apertura
del dialogo de recordatorios. Los templates conservan estructura y estilos;
sus bindings apuntan a los puertos o editores correspondientes.

## Fronteras conservadas

El cliente HTTP y sus DTO permanecen en `appointment-api.service.ts`; los tipos
extraidos del antiguo shell estan en `dashboard-domain.contracts.ts`.
La carga coordinada conserva el comportamiento previo de `Promise.all` y las
barreras de generacion. No se modifica el contrato de reservas, pagos ni envios
ambiguos. Cerrar o fallar un alta mantiene la limpieza de datos sensibles.

La division del cliente HTTP, cargas parciales y encapsulacion visual tienen
alcance propio en [6.2 a 6.4](../roadmap/development-hardening-plan.md).
