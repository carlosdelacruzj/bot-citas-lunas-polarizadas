# Contratos y clientes HTTP por dominio

Fecha de corte: `2026-09-08`. Evidencia de cierre tecnico de `6.2` contra la
base `7c4cd54`; no representa una aceptacion natural ni estado vivo del portal.

## Resultado

Se retiro `appointment-api.service.ts` (1778 lineas) tras migrar todos sus
consumidores. Los 81 contratos originales y 69 metodos conservan su propietario
por dominio. Transporte y presentacion de errores son compartidos, sin estado
global de negocio ni reexports del cliente anterior.

| Dominio | Cliente HTTP: lineas | Contratos: lineas |
| --- | ---: | ---: |
| Ordenes | 146 | 146 |
| Finanzas | 128 | 289 |
| Mensajes | 146 | 147 |
| Seguimiento | 52 | 173 |
| CAPTCHA | 121 | 209 |
| Operaciones | 79 | 175 |

El transporte tiene 27 lineas; errores 33; respuesta compartida de acciones 22;
unions compartidas 8. Se reutilizan los modelos existentes de paquetes,
restricciones y resolucion de expedientes.

## Equivalencia y rutas

Comparacion AST contra el cliente anterior, normalizando trivia, el acceso al
transporte y aliases de tipos:

- los 81 contratos conservan sus campos y tipos equivalentes;
- 63 metodos conservan su contenido normalizado;
- cuatro lecturas delegan a transporte: detalle de orden, detalle de run,
  exportacion CAPTCHA y adjunto WhatsApp;
- dos metodos agregan codificacion a segmentos antes interpolados directamente:
  `runServiceOrderAction` y `getWhatsAppReview`;
- cero metodos perdidos; 15 consumidores migrados sin cambio normalizado de
  logica, salvo imports, tipo equivalente e inyeccion/acceso al cliente;
- 37 interpolaciones de URLs revisadas: todos los segmentos de ruta estan
  codificados; consultas mediante `URLSearchParams` o `encodeURIComponent`;
- cero consumidores productivos o de tests de `AppointmentApiService`.

Las cuatro lecturas conservan GET, respuesta, Blob, errores y scopes anteriores.
POST/PUT conservan sus bodies y no tienen reintentos. El cierre de sesiones por
beacon al salir del documento conserva su mecanismo anterior.

Esta comparacion estructural no demuestra todos los comportamientos posibles;
se completa con compilacion, pruebas y revision de las seis diferencias.

## Estados y contratos sensibles

Se extraen seis aliases compartidos: documento, servicio, preflight, modo de
recordatorios, cierre financiero y estado de paquete WhatsApp. El modo de
sesion manual tambien tiene una sola autoridad. Estados particulares permanecen
en su dominio, por ejemplo `WhatsAppActionState` y `PostAppointmentOutcome`.
Los estados abiertos del servidor, como fase del worker, conservan `string`.

`ServiceOrder` conserva `projection=dashboard`; `ServiceOrderDetail` conserva
los campos autorizados adicionales. Payloads de credenciales y alta son tipos
separados. La prueba existente de alta verifica tambien consulta de lista,
ausencia de campos sensibles en su fixture y detalle por identificador codificado.

Se elige la alternativa de fixtures contractuales prevista en el plan:

- muestras sinteticas completas de alta, credenciales, pago, respuesta de
  accion, lista/detalle y preparacion WhatsApp, con `satisfies`;
- las 18 respuestas simuladas de navegacion pasan de JSON sin comprobacion
  contractual a TypeScript validado por `npm run typecheck`;
- esa comprobacion detecto `status` ausente en el fixture de plantillas; se
  corrigio a `ok`, conforme al contrato existente;
- las pruebas existentes consumen los fixtures; no se agregan casos nuevos;
- los fixtures no entran en el bundle productivo ni contienen datos reales.

Son muestras contrastadas con los DTO; no son validadores runtime exhaustivos
ni detectan automaticamente cambios del servidor vivo. La validacion no
realiza pagos, creaciones, reservas, reinicios o envios reales.

## Validacion y medicion

- Typecheck, build y 14 pruebas unitarias de frontend: pasan.
- Smoke existente: ocho pantallas, persistencia de busqueda, cero errores de
  JavaScript, 409 simulado y cero mutaciones inesperadas; pasa.
- Compileall, Ruff y guarda de arquitectura: pasan; 318 modulos Python,
  una excepcion previa, cero ciclos.
- Python: 181 pruebas y 24 subtests pasan.
- Documentacion: limites y enlaces validos; `git diff --check` del cambio pasa.
  Evidencia operacional generada preexistente queda fuera de estos commits.

| Medicion | Base 6.1 | Cierre 6.2 |
| --- | ---: | ---: |
| Bundle inicial | 570.05 kB | 572.83 kB |
| Transferencia estimada | 140.57 kB | 141.12 kB |

Aumento inicial: 2.78 kB, aproximadamente 0.49%. Continuan las advertencias de
535 kB iniciales y 30 kB de CSS de App (30.04 kB); presupuestos intactos.

`6.3` conserva cargas parciales, frescura por tarjeta y cancelacion de detalle;
`6.4` conserva estilos y accesibilidad. Este cierre no modifica los pendientes
de aceptacion natural de `5.5.5` y `2.6`.
