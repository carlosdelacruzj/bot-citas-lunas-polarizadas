# Estado maestro del proyecto

Última revisión integral: `2026-08-01`.

Este archivo es la fuente principal para entender dónde está el proyecto. Debe
actualizarse cuando se termina, valida o descarta un cambio relevante. Las
tareas futuras y su orden viven únicamente en
[`roadmap/README.md`](roadmap/README.md).

## Resumen ejecutivo

El sistema ya funciona como una operación comercial completa: recibe y
prioriza órdenes, monitorea el portal, realiza reservas con confirmación
estricta, conserva evidencia, permite administración local y remota, registra
pagos y automatiza seguimientos por WhatsApp sin bloquear el motor de citas.

Estado verificado el `2026-07-28`:

| Área                  | Estado                   | Lectura actual                                                                                            |
| --------------------- | ------------------------ | --------------------------------------------------------------------------------------------------------- |
| Worker de reservas    | En espera nocturna       | `127.0.0.1:8765/health` no responde antes del arranque diario; verificar el siguiente inicio supervisado. |
| Admin API y dashboard | Operativos               | `127.0.0.1:8766`; `api_only` no significa que el worker esté apagado.                                     |
| PostgreSQL            | Operativo                | PostgreSQL 16 en Docker, saludable.                                                                       |
| Telegram remoto       | Operativo                | Consultas, clientes, reglas, prioridad, credenciales y control del worker.                                |
| CAPTCHA sombra        | Operativo                | Servicio CUDA en `127.0.0.1:8787`; solo observa, 2Captcha conserva autoridad.                             |
| WhatsApp automático   | Operativo con vigilancia | Emisor único en Admin API, cola durable y sin reintentos automáticos ambiguos.                            |
| Dashboard             | Operativo                | Build Angular correcto; bundle inicial de `501.24 kB`.                                                    |
| Calidad Python        | Operativa                | Ruff y `compileall` correctos; pytest tiene `59 passed`.                                                  |

## Resultado comercial acumulado

Datos consultados en PostgreSQL al `2026-07-28`:

| Periodo               | Órdenes | Reservas confirmadas |  Pagos | Ingreso cobrado |
| --------------------- | ------: | -------------------: | -----: | --------------: |
| Junio 2026            |       9 |                    4 |      3 |          S/ 120 |
| Julio 2026, días 1-28 |      85 |                   81 |     76 |        S/ 3,025 |
| **Acumulado**         |  **94** |               **85** | **79** |    **S/ 3,145** |

- Ticket promedio de julio: `S/ 39.80`.
- Pagos pendientes actuales: `2`, por `S/ 80`.
- TikTok aporta `S/ 2,240` del ingreso de julio.
- Estas cifras son ingresos cobrados, no utilidad neta.

## Punto de partida técnico

La referencia estable del motor de reserva sigue siendo:

- tag `best-performing-2026-07-12`;
- commit `a43c6a1`;
- confirmación estricta, leases, intentos persistidos y reglas por orden;
- ruta normal observada cercana a 6.5-7.3 segundos cuando CAPTCHA responde
  rápido.

Los cambios posteriores ampliaron administración, observabilidad y
comunicación. No reemplazan ese baseline para comparar regresiones del motor.

## Qué se realizó en julio

### Reserva y cola

- Primera reserva automática efectiva y reconciliación posterior.
- El mensaje explícito de éxito del portal confirma la reserva sin reabrir el
  trámite; si ese mensaje falta, la etapa `Programado` conserva la validación
  secundaria. Esta decisión operativa evita añadir latencia a la ruta exitosa.
- Registro durable de `reservation_attempts`, submission pendiente y heartbeat.
- Prioridad, prioridad exclusiva y restricciones por fecha, hora, día y rangos
  excluidos.
- Corregido el `2026-07-30`: se eliminaron las promociones automáticas de
  prioridad y el diferimiento de un cupo compatible hacia otra orden. Las
  prioridades `100/200` son controles manuales de las próximas sesiones; una
  sesión que ya detectó un cupo válido reserva para su propio cliente. A igual
  prioridad, el bloque de observación vuelve a respetar el orden de registro
  sin adelantar órdenes por tener o no restricciones.
- Corrección para que fechas fuera de rango no provoquen un backoff general de
  30 minutos.
- Corregido el `2026-07-31`: dos rechazos explícitos de CAPTCHA ya no se tratan
  como un fallo técnico general. La orden afectada recibe un cooldown propio de
  `120` segundos y el worker continúa con los demás clientes elegibles; los
  backoffs largos se conservan para resultados ambiguos o defensas reales del
  portal.
- Implementado el `2026-08-01`: cada orden observada conserva el modal abierto y
  ejecuta hasta `15` consultas ligeras de sede. Después de la primera consulta,
  cada intento fuerza `vacío -> LIMA-LA VICTORIA`, espera el postback completo y
  descansa un valor aleatorio entre `2` y `4` segundos. Solo se hace un
  `reload_probe` completo después del
  intento `8`; al terminar el intento `15` se cierra esa sesión y se rota al
  siguiente cliente con un contexto Playwright nuevo.
- Auditado el `2026-08-01`: los valores operativos del ciclo `15/1-2/8`, la sede,
  el límite de clientes activos, el cooldown por CAPTCHA, los intentos de
  CAPTCHA por reserva y el corte diario se pueden modificar desde `.env`. Los
  dos últimos dejaron de ser literales fijos en el flujo productivo. El `.env`
  local y `.env.example` quedaron organizados y comentados por función; las
  constantes que permanecen en código son detalles técnicos de protocolo,
  estabilidad de UI, leases y lotes internos, no políticas operativas.
- Validado en portal real el `2026-08-01` con dos usuarios y contextos
  Playwright independientes: cada sesión completó `15` consultas, la primera
  atravesó el `reload_probe` y luego se produjo la rotación esperada. Ambas
  terminaron `unavailable`, sin CAPTCHA, errores ni reservas, y el worker cerró
  liberando su lease. Se conservaron dos MP4 mediante una anulación temporal de
  diagnóstico; el flujo normal de `RECORD_CLIENT_SESSIONS` elimina videos si no
  existe una reserva confirmada.
- Implementada y validada en portal real el `2026-08-01` la telemetría durable
  por selección de sede. Cada evento conserva intento, fase, POST detectado,
  URL sin query string, estado HTTP, latencia, tamaño declarado cuando existe,
  fallo de red, finalización ASP.NET y firmas de fecha/hora antes y después. El
  historial sobrevive al `reload_probe` y queda dentro de `runs.details_json`.
  Una sesión real produjo los `30` eventos esperados: `15` selecciones de La
  Victoria, `14` vaciados y `1` selección posterior al reload; todos fueron
  POST HTTP `200`, completaron `endRequest`, quedaron confirmados y no tuvieron
  fallos. Los headers llegaron en `32-282 ms` y la actualización estable en
  `297-313 ms`.
- Ajustado el `2026-08-01`: la espera del toggle es aleatoria y el rango
  operativo se redujo a `1-2` segundos. Cada pausa sortea nuevamente un entero
  entre
  `OBSERVER_SITE_TOGGLE_INTERVAL_MIN_SECONDS=1` y
  `OBSERVER_SITE_TOGGLE_INTERVAL_MAX_SECONDS=2`. La variable antigua singular
  sigue aceptada como fallback para instalaciones que todavía no migraron.

### Arquitectura y operación

- Separación modular de reserva, worker, base de datos, reportes y API.
- Admin API independiente mediante `worker_commands`.
- Dashboard Angular con vistas, rutas, carga diferida, estados y modales
  separados.
- Resumen mensual, finanzas, bandeja de pendientes y edición segura de
  credenciales.
- Arranque supervisado en Windows para worker, dashboard, Telegram y CAPTCHA
  sombra.
- El arranque automático ya no usa VBS ni `ExecutionPolicy Bypass`; una tarea
  programada ejecuta directamente el lanzador PowerShell versionado.
- Los cuatro supervisores quedan desacoplados y vigilados por un supervisor raíz
  persistente. La tarea programada permanece activa, revisa su presencia cada
  15 segundos y recupera individualmente el que desaparezca.
- La tarea usa `pythonw.exe` y `scripts/start-runtime.pyw` como host sin consola;
  no depende de VBS, Windows Script Host ni una ventana visible de PowerShell.
- La recuperación se validó cerrando únicamente el supervisor de Telegram:
  reapareció con otro PID en el siguiente ciclo, conservó intactos los procesos
  Python existentes y Admin API/CAPTCHA continuaron saludables.
- El mantenimiento local del 28 de julio eliminó `447.34 MB` de artefactos
  regenerables u obsoletos: un respaldo antiguo y un perfil de prueba de
  WhatsApp Web, la caché de Angular y reportes temporales de estado y
  diagnóstico. Se conservaron el perfil activo, `dashboard/node_modules`,
  `dashboard/dist` y toda la evidencia histórica versionada.
- La limpieza estática del 28 de julio retiró `198` líneas sin consumidores:
  seis funciones Python, un conjunto de selectores obsoleto, cuatro métodos y
  dos asignaciones sin uso en Angular, además del proxy JSON reemplazado por
  `proxy.conf.cjs`. Compilación, lint, TypeScript y build conservaron el mismo
  comportamiento observable.
- El reporte general PNG de `reports/daily/` se retiró por falta de uso,
  incluyendo su generación automática al cierre y el comando `daily-report`.
  El corte diario conserva `18:00` como valor configurado, la revisión final de
  órdenes listas permanece habilitada y el reinicio de las 07:30 no cambia.
- La retención de 14 días ahora recorre las subcarpetas de logs, capturas y
  videos, elimina directorios vacíos y conserva explícitamente evidencia de
  reserva, disponibilidad, fallos, defensas, CAPTCHA originales, preflight y
  paquetes de WhatsApp. Antes solo inspeccionaba archivos directamente bajo
  cada raíz y dejaba intactas todas las carpetas fechadas.
- La base depuró `91` mensajes marcados explícitamente como prueba, sin
  referencias desde la cola automática. La limpieza diaria ahora elimina
  mensajes de prueba y eventos CAPTCHA ya procesados después de `14` días, y
  comandos del worker aplicados después de `90` días. No alcanza mensajes
  reales, comandos pendientes o fallidos, trabajos WhatsApp, órdenes, pagos,
  reservas ni intentos.
- Los `395` archivos de paquetes WhatsApp conservaron sus rutas y hashes, pero
  ahora comparten `55` contenidos físicos mediante un almacén local inmutable.
  La migración recuperó `91.04 MB`; las nuevas constancias, imágenes de pago y
  PDFs se deduplican por SHA-256, con copia normal como fallback si el sistema
  de archivos no admite enlaces físicos.
- Se retiraron `10` módulos de compatibilidad que solo reexportaban símbolos y
  las fachadas públicas de cinco paquetes. Código, tests y entrypoints importan
  ahora desde `core`, `db`, `reports`, `reservation_engine` y `worker` en su
  módulo propietario. `queue_runtime.py` y los selectores CAPTCHA se conservaron
  porque todavía contienen lógica activa.
- Los 11 fallos de pytest se clasificaron como contratos de prueba obsoletos:
  preflight, `document_type`, cinco restricciones por orden y muestreo CAPTCHA
  sombra. Se actualizaron únicamente las pruebas; no fue necesario relajar ni
  modificar código productivo. La suite completa quedó en `59 passed`.

### Control remoto

- Menú de Telegram con búsqueda, recientes, resumen y estado.
- Alta guiada de clientes y edición de reglas, prioridad y credenciales.
- Pausa, reanudación y reinicio mediante Admin API y comandos persistidos.
- Expiración de conversaciones, botones obsoletos rechazados y un solo flujo
  guiado por chat.
- Simplificado el `2026-08-01`: se retiró por completo el etiquetado manual de
  CAPTCHA desde Telegram, junto con sus variables y scripts exclusivos. El menú
  dejó de mostrar recientes y credenciales, agrupó sistema con errores y la
  búsqueda ahora solicita el término como una conversación guiada.

### Evidencia y CAPTCHA

- Evidencia organizada por fecha y resumen compacto.
- CAPTCHA original utilizado para el solver.
- Servicio local en modo sombra, cola durable y revisión humana desde el
  dashboard.
- El modelo local no participa en la decisión de reserva; 2Captcha sigue siendo
  la respuesta enviada al portal.

### Comunicación y cobro

- Álbum único con evidencia y QR de Yape.
- Seguimiento postpago separado con PDFs y textos.
- Cola durable de trabajos WhatsApp con estados recuperables y auditables.
- Admin API como único propietario del perfil persistente de WhatsApp Web.
- Fallos de WhatsApp no bloquean reservas ni Telegram.
- Al corte de las 18:00 se encola un resumen diario idempotente al número
  personal configurado fuera del repositorio: primero envía el texto fechado y
  luego todas las imágenes de `cupos-unicos`. El primer caso real del 30 de
  julio cargó cuatro miniaturas, pero cerró el navegador con tres imágenes aún
  pendientes y solo una llegó al teléfono. El trabajo quedó reconciliado a
  `uncertain`; ahora se exige confirmar cada imagen saliente antes de cerrar.
  El reintento manual autorizado terminó `sent` con las cuatro imágenes
  confirmadas.
- Después de las imágenes, el mismo trabajo diario enviará una publicación para
  TikTok lista para copiar. Se genera sin IA ni tokens mediante 138,240
  combinaciones deterministas; precio, pago, WhatsApp y advertencias permanecen
  fijos, y PostgreSQL conserva el texto exacto antes de enviarlo. La prueba real
  confirmó el texto completo con doble check azul después de normalizar la
  representación interna de emojis del compositor y la burbuja saliente. La
  confirmación también tolera la virtualización del historial sin confundir una
  nueva burbuja con otra publicación idéntica anterior.
- El texto postpago ya no se considera enviado por una espera fija después del
  clic: debe desaparecer del compositor y aparecer como un nuevo mensaje
  saliente. Si los PDF salieron pero el texto no se confirma, el trabajo queda
  `uncertain`, sin marcar el paquete completo como `sent` ni reintentarlo.
- El caso parcial del 30 de julio quedó reconciliado en PostgreSQL como
  `uncertain`/`prepared`; no se creó ni encoló un reenvío automático.
- El siguiente postpago real llegó completo pero reveló un falso `uncertain`:
  WhatsApp cambió las burbujas a `msg-container`. La confirmación reconoce esa
  estructura solo cuando contiene el texto completo y una marca saliente; el
  caso comprobado se reconcilió a `sent` sin reenviar.
- La bandeja cruza evidencia `sent` y trabajos automáticos durables antes de
  pedir intervención. Dejó fuera `54` seguimientos históricos sin trabajo
  automático y reconoció como resueltos `2` fallos con envío posterior. Los
  `2` pagos actuales permanecen accionables.
- La clasificación es derivada y no destructiva: no se borraron mensajes, no se
  alteraron pagos y no se envió WhatsApp retroactivo.

## Rendimiento observado

| Periodo     | Runs conservados | Intentos | `registered` | `slot_lost` | Errores |
| ----------- | ---------------: | -------: | -----------: | ----------: | ------: |
| 13-19 julio |            5,356 |       61 |           28 |  29 (47.5%) |      14 |
| 20-25 julio |            4,662 |       43 |           20 |  17 (39.5%) |       3 |

La última semana muestra menos errores y menor proporción de `slot_lost`, pero
todavía se necesita una muestra mayor antes de atribuir la mejora a un solo
cambio.

La tabla `runs` conserva actualmente información desde el 11 de julio. Para
periodos anteriores deben usarse los reportes y documentos versionados; no se
debe reconstruir una comparación histórica únicamente desde la base viva.

## Fallos, límites y riesgos vigentes

1. La suite local está en verde, pero no sustituye una validación real del
   recorrido cupo -> reserva -> confirmación exacta en el portal.
2. WhatsApp Web depende de una interfaz externa cambiante. Un resultado
   ambiguo nunca debe reintentarse automáticamente.
   La confirmación estricta del texto postpago ya incorporó la estructura DOM
   observada en un envío real, pero requiere vigilancia ante cambios futuros.
3. La corrección del backoff por fechas fuera de rango está validada en
   escenarios controlados, pero falta confirmarla ante otro caso real
   equivalente.
4. El cooldown corto por rechazo explícito de CAPTCHA está validado en código;
   falta observar el próximo rechazo real para confirmar que la cola continúa
   sin una espera global.
5. El ciclo ligero de sede ya se validó en portal real con dos usuarios y su
   telemetría HTTP/ASP.NET se comprobó en una sesión adicional con `30/30`
   respuestas HTTP `200`. Falta reunir varios días de operación productiva para
   vigilar latencia sostenida, cierres de sesión y señales `403/429`.
6. La operación depende de una PC Windows, red local, Docker y perfiles
   persistentes de navegador.
7. El CAPTCHA local todavía no tiene evidencia suficiente para sustituir a
   2Captcha.
8. La evidencia versionada está sanitizada, pero sigue siendo telemetría
   operacional y debe revisarse antes de compartir.
9. Kaspersky puede clasificar lanzadores ocultos y persistentes como amenaza.
   El reemplazo PowerShell reduce esa superficie, pero debe vigilarse el
   historial del antivirus después de reinicios y actualizaciones de firmas.
10. La integración de registros alojados está desplegada y activa en modo
   `controlled`. La prueba ficticia completa terminó en `accepted`, mantuvo el
   total de órdenes en `95` y confirmó la limpieza terminal en D1. Continúan
   bloqueados los datos reales y el modo `production` hasta completar respaldo
   externo de clave, revisión legal, procedimiento de incidente y autorización
   expresa. La Admin API sigue limitada a loopback.
11. La ráfaga multicliente `OBS-006` está documentada únicamente como mejora
    futura en evaluación. La concurrencia productiva sigue desactivada. Antes
    de implementarla debe aislar sesiones, claims, heartbeats e intentos por
    orden, definir guardas globales y demostrar que obtiene reservas adicionales
    sin aumentar defensas, resultados inciertos ni errores operativos.

## Validación del corte

- `python -m ruff check src tests`: correcto.
- `python -m compileall -q src`: correcto.
- `npm run build`: correcto.
- `python -m pytest -q`: `59 passed`.
- Admin API, PostgreSQL y CAPTCHA sombra: saludables; worker pendiente del
  siguiente arranque diario.
- integración alojada: Ruff y compilación Python correctos, dashboard Angular
  correcto, PostgreSQL `v39`, conector controlado activo y prueba remota
  ficticia aceptada sin crear órdenes.
- flujo local de invitaciones ajustado: WhatsApp obligatorio, nombre opcional y
  editable, advertencia por número repetido, reemplazo directo y comprobante
  visible con enlace y mensaje copiable.
- revisión UX/UI del flujo de invitaciones completada en código: estados
  diferenciados por una paleta semántica, confirmaciones integradas para
  reemplazar o revocar, jerarquía móvil conservada y texto del comprobante
  distinto para primera emisión y reemplazo.
- reemisión alojada corregida después de reproducir el HTTP `409`: la nueva
  invitación se inserta antes de enlazar y revocar la anterior, y las
  correcciones por credenciales incorrectas quedan admitidas explícitamente.
- segundo HTTP `409` local diagnosticado y corregido: el listado conserva ahora
  la invitación alojada más reciente por contacto y la reemisión reconcilia
  PostgreSQL mediante la referencia estable del contacto, después de comprobar
  que exista localmente y antes de modificar la invitación alojada.
- falsa desconexión posterior corregida: PostgreSQL no podía inferir el tipo de
  un parámetro opcional después de crear el reemplazo remoto y cerraba la
  petición sin respuesta. La consulta selecciona ahora explícitamente su clave;
  se sincronizó el contacto afectado y se revocaron cuatro accesos activos
  históricos, dejando una sola invitación vigente.

## Regla de mantenimiento

Después de cada cambio relevante:

1. actualizar este archivo si cambió el estado, una capacidad, un riesgo, una
   métrica o una validación;
2. actualizar [`roadmap/README.md`](roadmap/README.md) si una tarea avanzó,
   terminó, se bloqueó o cambió de prioridad;
3. mover el detalle largo a `operations/`, `contracts/`, `history/` o un
   documento de incidente;
4. no convertir reportes generados ni bitácoras en listas paralelas de tareas.
