# Extraccion completa de dominios del dashboard

Fecha de corte: `2026-09-08`. Artefacto de validacion de `6.1`; no representa
el estado vivo del worker ni una aceptacion operacional natural.

## Alcance

Los seis dominios previstos poseen estado, consultas, formularios, comandos,
confirmaciones y formato especifico. `App` pasa de 4988 a 289 lineas, incluyendo
imports y proveedores; su clase conserva composicion y delegacion de eventos.
`OrdersListFacade` ya existia al inicio de este cierre y sigue compartida.

| Dominio | Archivos principales | Lineas al corte |
| --- | --- | ---: |
| Ordenes y alta | `orders.facade.ts` / `orders-list.facade.ts` | 1226 / 470 |
| Finanzas y pagos | `finance.facade.ts` | 596 |
| WhatsApp y mensajes | `messages.facade.ts` / `message-template-editor.facade.ts` | 699 / 340 |
| Seguimiento | `followups.facade.ts` / `followup-workspace.facade.ts` | 355 / 531 |
| CAPTCHA | `captchas.facade.ts` | 919 |
| Resumen, actividad y salud | `operations.facade.ts` | 760 |

Navegacion conserva 378 lineas de router, refresh y cancelacion; UI conserva
224 de confirmaciones, modal y foco; presentacion compartida contiene 79 de
funciones puras. Ninguna de estas tres clases guarda un agregado de datos de
los seis dominios. El contrato y cliente HTTP se conservan para `6.2`.

## Equivalencia y consumidores

Comparacion estructural contra `b148f0d`, normalizando espacios, visibilidad,
decoradores de eventos y accesos `this.dominio.miembro`:

- 495 miembros anteriores coinciden en contenido normalizado;
- cinco miembros cambian por delegacion: constructor, destructor,
  `refreshCommonData`, `refreshViewData` y `closeModal`;
- cero miembros de negocio/coordinacion sin destino; las dos dependencias de
  infraestructura anteriores (`api`, `orderList`) se inyectan donde se usan;
- constructor: efecto de error en UI y suscripcion de router en Navegacion;
- destructor: conserva cancelaciones, timers, unsubscribe y cierre por beacon,
  delegando cada limpieza al propietario;
- cargas: mismas consultas, scopes y publicacion coordinada; se agrupan salud
  y ordenes y se delegan ramas de vista. CAPTCHA conserva su consulta auxiliar
  opcional y propaga cancelacion;
- cierre de modal: conserva hidratacion y limpieza sensible; el formulario
  WhatsApp lo limpia su dominio.

La normalizacion es evidencia estructural, no una demostracion formal de
equivalencia de todos los estados posibles. Se revisaron las cinco delegaciones
y la separacion de las ramas de carga antes de ejecutar la validacion.

Vistas, modales y panel de expedientes reciben `Pick` por consumidor mediante
tokens y `useExisting`. No quedan consumidores de `DashboardViewFacade`; se
elimino el archivo y su proveedor. `App`, las vistas, los modales y Navegacion
no inyectan `AppointmentApiService`. Los editores por vista conservan su vida
util anterior y los componentes retienen solo su interaccion con DOM.

## Medicion incremental

Cada bloque paso typecheck, build, las 14 pruebas unitarias existentes y el
smoke existente antes del siguiente bloque. No se agregaron casos de test.

| Bloque | Bundle inicial | Transferencia estimada |
| --- | ---: | ---: |
| Base con listado extraido | 553.51 kB | 139.64 kB |
| Ordenes y alta | 557.49 kB | 139.09 kB |
| Finanzas y pagos | 559.05 kB | 139.23 kB |
| Mensajes y editor | 560.55 kB | 139.37 kB |
| Seguimiento y recordatorios | 561.25 kB | 139.46 kB |
| CAPTCHA | 562.24 kB | 139.64 kB |
| Operaciones y shell, cierre | 570.05 kB | 140.57 kB |

Incremento final: 16.54 kB iniciales, aproximadamente 2.99%; transferencia
estimada +0.93 kB. Continuan las advertencias del presupuesto inicial de
535 kB y CSS de App de 30 kB (30.04 kB). No se elevaron presupuestos.

## Validacion al corte

- `npm run typecheck` y `npm run build`: pasan.
- `npm run test:unit`: 14 pruebas existentes pasan; consumidores de modales
  migrados a los nuevos puertos.
- `npm run test:e2e`: un caso existente pasa, ampliado a las ocho pantallas,
  persistencia de busqueda al volver, cero errores JavaScript, una respuesta
  409 controlada por fetch y cero mutaciones inesperadas.
- Fixtures sinteticos de API, sin datos reales; todas las peticiones API del
  smoke se interceptan. No acredita un pago, reserva o envio real.
- `python -m compileall -q src` y Ruff: pasan.
- `python -m pytest -q`: 181 pruebas y 24 subtests pasan.
- Guarda de arquitectura Python: 318 modulos, una excepcion previa, cero ciclos.
- `scripts/check-documentation.ps1`: pasa; estado actual en 250 lineas y enlaces validos.
- `git diff --check` del cambio: pasa; evidencia operacional generada preexistente
  permanece fuera de los commits de este refactor.

Se conservan para sus propios puntos la division HTTP (`6.2`), cargas parciales
(`6.3`) y accesibilidad/estilos (`6.4`). `5.5.5` y `2.6` siguen requiriendo
evidencia natural; este refactor no realiza envios ni reinicios para obtenerla.
