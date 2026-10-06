# Estado actual del proyecto

Estado verificado documentalmente: `2026-09-19`; [corte de preparacion para 6.4](../reports/architecture/pre64-readiness-2026-09-19.md).

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
- esquema PostgreSQL requerido por el codigo: `v76`; [registro secuencial](architecture/database-migrations.md) con 62 pasos desde `v14`;
- una sesion Playwright nueva por cliente, sin compartir cookies ni contexto;
- propiedad exclusiva por cuenta entre worker, preflight, revision post-cita y sesiones manuales, con cierre visible hasta terminar Chromium;
- intentos inciertos admiten consulta manual protegida del expediente, sin nuevos envios ni conciliacion automatica;
- ordenes regulares y de disponibilidad restringida con precio y reglas por
  orden;
- reservas, pagos, comunicaciones y seguimiento post-cita persistidos;
- dashboard con bandeja comercial canonica y pantallas operativas separadas;
- CAPTCHA grafico de aprendizaje en almacenamiento frio; el CAPTCHA HTML se
  resuelve localmente antes de sede o reserva con contrato estricto, y una
  variacion no reconocida pausa globalmente el worker;
- apertura y reapertura, incluido el observador, esperan el panel visible antes del CAPTCHA;
- WhatsApp conserva `sent`, `uncertain`, confirmacion tecnica y conciliacion
  manual como hechos distintos.

## Arquitectura vigente

[Configuracion por dominio](architecture/domain-configuration.md) con grupos explicitos por consumidor y copias por cliente; la fachada plana esta retirada.

### Worker

El worker inyecta al motor puertos de runs, alertas, CAPTCHA y oportunidad; el
motor conserva Playwright, reglas y resultados sin importar DB ni servicios.
Claims, leases e intentos protegen cada submit. La cuenta observadora generica abre
el primer expediente disponible sin filtrar su estado porque solo consulta; las
cuentas de clientes exigen expediente exacto, sin cita verificada e historial conciliado.
### Admin API

Telegram vive en `services/telegram/`, con transportes, polling, estado, router, conversaciones y presentacion separados; Telegram Control conserva solo el entrypoint; su auditoria pasa por Admin API.
Admin API declara GET, POST y PUT en `services/api/`, con handlers por dominio
en `api/handlers/`; `LocalApiHandler` conserva solo transporte HTTP. Es la frontera para
ordenes, preflight, pagos, finanzas, bandeja de pendientes, worker, controles,
salud, citas, recordatorios, revision post-cita, plantillas y trabajos WhatsApp;
altas, cobros y confirmaciones entran por casos de uso con transaccion explicita.
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

1. Nueva orden busca coincidencia exacta por WhatsApp normalizado o usuario y permite elegir contacto y cuentas del historial (hasta diez resultados). Solo una seleccion explicita reutiliza credenciales; cierre y fallo limpian el formulario. Se crea con contacto, credenciales, servicio, precio y restricciones; una cuenta con servicios terminados abre otra orden sin reutilizar su expediente ni pago.
2. El preflight valida identidad y acceso antes de habilitar la busqueda.
3. El preflight descuenta reservas anteriores y consulta citas incluso con un
   expediente. Uno elegible se guarda automaticamente; varios requieren decidir
   uno o todos. Citas existentes e historial incierto bloquean nuevas reservas.
   Dashboard muestra motivos; avisos incluyen solo el alcance seleccionado.
4. Con dos o mas clientes activos, sus cuentas rotan en busqueda directa; con uno, alterna cliente y observador auxiliar; sin clientes, rota cuentas auxiliares validadas. Cada turno usa sesion aislada y cadencia global de al menos 30 segundos; las auxiliares descansan 180 segundos.
5. Cada revision filtra localmente las fechas y consulta hasta dos compatibles; para clientes recorre los horarios permitidos de la mas cercana antes de pasar a la siguiente, dentro de la ventana de tiempo. El observador comprueba hasta dos horarios por actualizacion; admite un unico envio. Al cambiar fecha, una respuesta vacia o identica termina temprano solo con actualizacion confirmada y estable; sin confirmacion, el timeout detiene la revision. Salida vacia observada sin clientes; aceptacion con clientes pendiente. Cupos en `0` se descartan sin repetir solicitudes ni backoff tecnico.
6. La seleccion usa validacion DOM atomica; fecha/hora reproducidas y captura canonica encolan un unico aviso de texto asincrono antes del CAPTCHA o del boton de reserva. La foto queda local, sin segundo aviso de disponibilidad; se conservan avisos del resultado de reserva. Avisos y evidencia se deduplican por dia de deteccion en Lima.
7. La captura exige seleccion visible exacta, cupos positivos y boton habilitado estables, sin carga ASP.NET; una espera fallida conserva diagnostico y detiene el flujo. Una seleccion valida archiva su screenshot canonico; antes de resolver o
   enviar exige formulario, tokens, honeypot y firma estructural conocidos. Si
   falla la evidencia o el contrato, pausa sin iniciar el intento.
8. La reserva solo se confirma con evidencia suficiente del portal.
9. Pago y comunicaciones siguen estados independientes.
10. Citas y recordatorios alimentan el seguimiento previo y posterior.

Una incompatibilidad es `partial / blocked_by_order_rule`, sin backoff general.
Sin fetch alternativo, reobservacion tras submit ni segundo envio por CAPTCHA rechazado. Ante respuestas confirmadas sin cupos conserva hasta 15 actualizaciones/120 segundos, incluso tras consultar fechas sin horarios; cada actualizacion renueva solo la seleccion, nunca el envio. Recarga en el intento 8. Cada revision
nueva vuelve a las fechas mas proximas. Sin ordenes `ready`, un recorrido adicional completa fotos (hasta dos comprobaciones adicionales tras la deteccion principal), con avance diario por sede en runs; avisa tambien por cada cupo adicional verificado y fotografiado, con deduplicacion diaria. Conserva pausas y descansos; aceptacion natural de estos avisos pendiente.
Un submit ambiguo nunca se reintenta. Demasiadas solicitudes aplican 15 minutos a la orden; indisponibilidad temporal aplica al menos 3 minutos a toda la cuenta.
El observador detiene globalmente la rotacion ante defensas; un rechazo explicito de credenciales registra perdida de acceso por cuenta, conserva pagos/cierres y sigue rotando sin descanso global hasta revalidar esa cuenta.

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
sigue siendo el ultimo cambio de la orden, no el nacimiento real de la tarea. **Resumen** permite pausar y reanudar mediante comandos durables; la pausa espera una frontera segura, conserva historial y backoffs, y solo suspende nuevas revisiones y mediciones del portal. Con reserva automatica desactivada, un cupo seleccionable conserva su foto y pausa antes de cualquier clic de reserva.

**Citas y recordatorios** separa proximas citas, casos que requieren revision e
historial. Permite anticipacion de `1..3` dias y mantiene el seguimiento post-cita
conservador y paginado en PostgreSQL/API. Busqueda, filtros, orden y paginas no
requieren descargar el historial completo. Proximas citas pagina localmente el
resultado ya filtrado y ordenado, con tamanos de `5`, `10` o `20`. Los
recordatorios tienen modos
`disabled`, `dry_run` y `live`; ya no existe un modo canario ni una lista
especial de ordenes de prueba.

Contrato: [`contracts/appointment-followups.md`](contracts/appointment-followups.md).

El [dashboard por dominio](architecture/dashboard-domains.md) conserva `App`
como shell. Los seis dominios poseen estado, comandos y [clientes HTTP propios](architecture/dashboard-http.md).
Vistas y modales consumen puertos estrechos; listas y detalles autorizados siguen separados.
Las [cargas parciales](architecture/dashboard-loading.md) muestran error y frescura por bloque y cancelan lecturas obsoletas.

Cerrar, cancelar o fallar un alta elimina password, documento y contacto. Las
confirmaciones y la copia diagnostica no muestran esos datos personales.

Las rafagas de oportunidad y la reobservacion unica posterior a un `slot_lost`
son capacidades estables. Su admision se gobierna en PostgreSQL con
`enabled`, `disabled` y, para rafagas, `draining`; el breaker conserva prioridad
sobre cualquier modo. La capacidad configurada es de tres sesiones Playwright
aisladas: un detector y hasta dos auxiliares compatibles, con preferencia por
disponibilidad restringida.

## Comunicaciones WhatsApp

Registro individual y conjunto son plantillas editables en Mensajes, versionadas en PostgreSQL. Cada trabajo congela
texto, clave y revision al prepararse; editar una plantilla no modifica trabajos
historicos ni ya encolados. Los paquetes postpago historicos tambien conservan
texto congelado. El runtime ya no reconstruye mensajes desde pasos antiguos ni
emite el alias financiero `is_complete`; el contrato usa `conversion_complete`.

Reglas vigentes:

- un unico perfil persistente pertenece a Admin API; [infraestructura modular](architecture/whatsapp-browser.md) en `browser/whatsapp/`;
- albumes y paquetes postpago conservan confirmacion por componentes;
- `sent` requiere evidencia tecnica suficiente;
- un reloj o indicador pendiente visible veta la confirmacion;
- los intentos distinguen preparacion, interaccion, confirmacion observada y
  confirmacion persistida; solo la preparacion demostrable puede quedar
  `failed`;
- `uncertain` preserva contexto y nunca genera reintento automatico;
- conciliacion conserva el resultado tecnico; registro, album y postpago admiten reintento manual deduplicado de fallo total, con revision del chat si es incierto;
- llegada al destinatario y lectura son afirmaciones separadas.

La aceptacion natural se rige por
[`operations/whatsapp-natural-acceptance.md`](operations/whatsapp-natural-acceptance.md).

## Citas, recordatorios y post-cita
Los recordatorios usan plantilla versionada, modos separados y barreras de
deduplicacion. El scheduler post-cita usa una sesion de solo lectura, pausas de
`4-7` segundos y maximo `20` casos diarios. Un lote ambiguo se detiene.

Estado de cita, recordatorio, revision post-cita y comunicacion permanece
separado para no presentar una preparacion como envio ni un envio como lectura.

La [consulta manual de empresas](operations/company-reservations.md) revisa reservas pasadas con hasta cuatro sesiones aisladas y reporte local actualizable.

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
- videos locales cubren fallos, resultados desconocidos e interacciones de reserva; diagnosticos quedan protegidos de purga y enlazados al run;
- no publicar dumps, credenciales, placas, expedientes ni respuestas CAPTCHA;
- respuestas CAPTCHA no entran en reportes, runs, reservas, CSV ni Markdown;
- auditoria usa dashboard local, Telegram hasheado o huella SHA-256 del bearer;
- reescribir el historial Git requiere autorizacion independiente.

## Limitaciones abiertas

- Pendientes no posee aun `actionable_since`, vencimiento ni responsable
  persistidos por tarea;
- la aceptacion natural ya cubre la rama sin CAPTCHA final, rafagas, album, postpago, recordatorios, post-cita y recuperacion; su [muestra y limites](../reports/acceptance/natural-acceptance-2026-09-07.md) no garantizan resultados futuros;
- la comparacion de rafagas no prueba mayor eficacia y es anterior al cambio de CAPTCHA del portal;
- existen avisos `no_pending_request` enviados tecnicamente; falta revisar sus componentes y los de WhatsApp posteriores a la extraccion. El cierre diario sigue sin aceptacion completa; los conteos fechados estan en el corte de preparacion;
- el primer tramite integral natural posterior a `v74` debe validar abono, tasa, saldo, mensaje y resumen sin crear un caso de prueba;
- salud compuesta, backup externo, retencion y restore necesitan cierre;
- mensajes y algunos detalles del dashboard aun pueden reducir su transporte;
- busqueda acotada y rotacion estan validadas en aislamiento; [corte de activacion](../reports/architecture/bounded-search-rotation-2026-09-19.md), worker pausado y aceptacion natural pendiente.
- 6.4 no esta iniciada: quedan encapsulacion, foco, teclado, contraste, responsive y presupuestos de bundle/CSS;
- no quedan ciclos; un import inverso conocido sigue baselinado y CI impide deuda nueva.
- el entorno aislado del lock pasa pruebas, cobertura, `pip check` y auditoria Python; el Python compartido conserva el conflicto ajeno `torch/setuptools`. Auditoria frontend: 11 avisos moderados, sin altos ni criticos al corte.

La prioridad y criterios de cierre estan en [`roadmap/README.md`](roadmap/README.md).

## Validacion base

```powershell
python -m compileall -q src
python -m ruff check src tests
python -m pytest -q
git diff --check
```

Para dashboard: `npm ci`, `npm run test:unit`, `npm run test:e2e`, `npm run typecheck`
y `npm run build` desde `dashboard/`; el smoke usa API simulada y no ejecuta mutaciones reales.
