# Estado maestro del proyecto

Última revisión integral y documental: `2026-08-17`.

Este archivo es la fuente principal para entender dónde está el proyecto. Debe
actualizarse cuando se termina, valida o descarta un cambio relevante. Las
tareas futuras y su orden viven únicamente en
[`roadmap/README.md`](roadmap/README.md).

## Resumen ejecutivo

El sistema ya funciona como una operación comercial completa: recibe y
prioriza órdenes, monitorea el portal, realiza reservas con confirmación
estricta, conserva evidencia, permite administración local y remota, registra
pagos y automatiza seguimientos por WhatsApp sin bloquear el motor de citas.

Estado verificado el `2026-08-11`:

| Área                  | Estado                   | Lectura actual                                                                                            |
| --------------------- | ------------------------ | --------------------------------------------------------------------------------------------------------- |
| Worker de reservas    | Operativo                | `127.0.0.1:8765/health` responde `ok`, con `worker_running=true`; el reinicio controlado ya no hereda una pausa y sus controles dejan auditoría durable. |
| Admin API y dashboard | Operativos               | `127.0.0.1:8766/health` responde `ok`, con `worker_running=false` y razón `api_only`.                     |
| PostgreSQL            | Operativo                | PostgreSQL 16 saludable; esquema `v58` agrega conciliación durable de trabajos WhatsApp ambiguos, preservando recordatorios, fechas normalizadas, autoridad CAPTCHA, calidad financiera y outbox Telegram. |
| Telegram remoto       | Operativo sin prueba     | La alerta urgente de cupo se persiste y envía fuera de la ruta de reserva, con deduplicación y hasta tres intentos; esta revisión no envió mensajes de prueba. |
| CAPTCHA local         | Rollback a 2Captcha      | 2Captcha volvió a ser la autoridad persistente desde el siguiente CAPTCHA; V6 queda fuera de admisión con sus contadores y evidencia preservados. |
| WhatsApp automático   | Operativo con vigilancia | Emisor único en Admin API, cola durable y sin reintentos automáticos ambiguos.                            |
| Dashboard             | Operativo                | Angular `20.3.27`, build correcto y `npm audit --omit=dev` sin vulnerabilidades. La vista principal prioriza cobros, reservas, pendientes y evolución diaria; el análisis y cierre quedan plegados. |
| Calidad Python        | Operativa                | Último corte completo: Ruff y `compileall` correctos; pytest tiene `59 passed`.                           |

Modo operativo verificado el `2026-08-17`: `AUTO_RESERVE=true`. La activación
se aplicó en un límite seguro, después de pausar y cerrar la sesión Playwright
sin cupos, y se cargó mediante reinicio controlado. El worker nuevo quedó
saludable, no pausado y monitoreando las órdenes `ready`. El primer cupo real
posterior cerró el canario con dos reservas automáticas confirmadas para
`01/09/2026 12:00`: detector y sesión auxiliar separada resolvieron suma HTML
local, aplicaron esperas de `1.004 s` y `1.330 s`, enviaron POST exactos
`39 / 30 / 9` con honeypot vacío y terminaron tanto en mensaje explícito de
éxito como en evidencia posterior **Programado**. El burst cerró sin circuito,
sin pérdida de lease y con ambas corridas `registered`.

## Resultado comercial acumulado

Datos consultados en PostgreSQL al `2026-08-09`:

| Periodo               | Órdenes | Reservas confirmadas |  Pagos | Ingreso cobrado |
| --------------------- | ------: | -------------------: | -----: | --------------: |
| Junio 2026            |       9 |                    4 |      3 |          S/ 120 |
| Julio 2026            |      89 |                   83 |     78 |        S/ 3,105 |
| Agosto 2026, días 1-9 |      19 |                   21 |     20 |          S/ 930 |
| **Acumulado**         | **117** |              **108** | **101** |   **S/ 4,155** |

- Ticket promedio de julio: `S/ 39.81`; agosto al corte: `S/ 46.50`.
- Pagos pendientes actuales: `2`, con saldo total de `S/ 70`.
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

## Capacidades implementadas y cambios recientes

### Reserva y cola

- Primera reserva automática efectiva y reconciliación posterior.
- El mensaje explícito de éxito del portal confirma la reserva sin reabrir el
  trámite; si ese mensaje falta, la etapa `Programado` conserva la validación
  secundaria. Esta decisión operativa evita añadir latencia a la ruta exitosa.
- Registro durable de `reservation_attempts`, submission pendiente y heartbeat.
- Desde el `2026-08-11`, la ruta productiva ya no genera la captura de página
  completa `preenvio` entre el llenado del CAPTCHA y el clic en **Reservar**.
  El intento durable conserva en su lugar la selección validada, el origen del
  resolutor, el `decision_id` y la hora UTC del último gate, sin persistir la
  respuesta CAPTCHA. Las capturas históricas no se eliminan; siguen vigentes la
  evidencia `cupo`, la imagen CAPTCHA usada y la respuesta posterior del portal.
- La alerta urgente de disponibilidad ya no espera la red de Telegram antes de
  resolver el CAPTCHA o enviar la reserva. El callback persiste un payload
  allowlisted en `telegram_alert_outbox`; un dispatcher separado conserva la
  hora real de envío, deduplica por cupo y realiza hasta tres intentos. Una
  caída posterior a la aceptación de Telegram pero anterior al `sent` puede
  producir un duplicado, pero nunca debe frenar el submit.
- Implementado el `2026-08-11`: la estabilización de fecha/hora usa como canario
  el `endRequest` de ASP.NET, cambios DOM y dos snapshots atómicos separados por
  `150 ms`. Si la señal no llega en `750 ms` o las lecturas difieren, vuelve en
  la misma sesión a las esperas anteriores `500/750 ms`. Las tres validaciones
  anteriores al submit permanecen; sede, fecha, hora y cupos se leen juntos y
  la identidad conserva su relectura estable. Dos banderas independientes
  restauran completamente ambos comportamientos anteriores tras reinicio.
  `selection_observation` y `reservation_timing` separan estrategia, fallback,
  llenado, validación final y persistencia. La aceptación real queda abierta
  hasta revisar `10` selecciones compatibles sin contar muestreo de entrenamiento.
  Las dos banderas cargan con valor efectivo `true`; el worker cerró normalmente
  por el corte diario de las `18:00` y el supervisor las cargará en su siguiente
  inicio programado de las `07:30`, sin forzar una sesión fuera de horario.
- Prioridad, prioridad exclusiva y restricciones por fecha, día y rangos
  excluidos.
- Implementado el `2026-08-02`: el horario dejó de ser una restricción
  comercial. Dashboard, Telegram y CLI ya no lo solicitan; la API rechaza un
  valor horario nuevo y el motor ignora cualquier valor histórico. Las reglas
  vigentes son fecha mínima, fecha máxima, días permitidos y rangos excluidos.
- Implementado el `2026-08-02`: las fechas visibles se ordenan de menor a mayor
  y, dentro de la fecha compatible más próxima, se intenta primero el horario
  más temprano. El flujo dejó de depender del orden accidental del portal.
- Implementado el `2026-08-02`: `blocked_by_order_rule` actualiza el resultado y
  mueve naturalmente la orden detrás de las demás revisadas, pero no establece
  `next_allowed_at`. Los cooldowns largos permanecen reservados para errores
  técnicos, CAPTCHA rechazado o resultados ambiguos.
- Implementado el `2026-08-02`: cada selección conserva en
  `selection_observation` las combinaciones fecha/hora realmente leídas y todas
  las fechas visibles al comenzar. Si el detector puede reservar, envía de
  inmediato sin recorrer fechas adicionales; si sus reglas lo bloquean, el
  recorrido ya necesario conserva todas las combinaciones encontradas.
- Implementado el `2026-08-02`: una detección arma una cadena secuencial de
  hasta `10` clientes compatibles y `300` segundos. La orden detectora reserva
  primero si puede; después se priorizan la prioridad manual exclusiva, los
  segundos trámites y la mayor cobertura de oportunidades. La cadena continúa
  tras cada reserva y termina al confirmarse que ya no hay cupos, vencer la
  ventana, agotarse los candidatos o aparecer un resultado técnico ambiguo.
- Implementado y ampliado el `2026-08-09`: `OBS-006` opera con dos posiciones.
  Cuando el detector confirma fecha y hora seleccionables, continúa su reserva
  y abre en paralelo un auxiliar compatible, priorizando al otro usuario del
  bloque activo. Si cualquiera confirma `registered`, su posición toma el
  siguiente usuario compatible. La ráfaga recorre toda la fotografía inicial
  de usuarios compatibles mientras las reservas confirmadas mantengan activa
  alguna rama, con `300` segundos para admitir sesiones nuevas y un ciclo
  auxiliar de cinco consultas durante `20` segundos con `reload_probe` en el
  tercer intento.
  Claims, heartbeats, navegadores, CAPTCHA e intentos permanecen aislados por
  orden. `OPPORTUNITY_BURST_ENABLED=false` restaura la cadena secuencial sin
  migración ni reversión de datos. La primera jornada con cupos reales produjo
  dos ráfagas, cuatro auxiliares y cuatro reservas confirmadas; el segundo lote
  confirmó tres clientes en unos `33 s`. La aceptación continúa abierta hasta
  reunir `10` ráfagas y `30` auxiliares.
- Implementado el `2026-08-09`: después de un `slot_lost` explícito, la misma
  sesión autenticada ejecuta una única reobservación de hasta `12` segundos,
  cinco lecturas y un `reload_probe` en la tercera. No consume otro CAPTCHA
  mientras no reaparezca una fecha y hora compatibles. Si encuentra otro cupo,
  crea un segundo `reservation_attempt` durable; el primero ya quedó cerrado
  como `rejected`. El segundo resultado siempre termina la ventana, por lo que
  no existen reobservaciones recursivas ni reintentos de resultados ambiguos.
  `SLOT_LOST_REOBSERVATION_ENABLED=false` restaura el cierre inmediato sin
  migración. El `2026-08-10` tres `slot_lost` reales iniciaron la reobservación:
  las tres recuperaron disponibilidad, dos segundos intentos volvieron a perder
  el cupo y uno terminó en reserva confirmada.
- Corregido el `2026-08-10`: el segundo intento OBS-007 reutilizaba
  `run_id:order_id:captcha-1` y mezclaba en CAPTCHA sombra la primera imagen con
  la respuesta externa posterior, aunque las sesiones y respuestas enviadas al
  portal permanecían separadas. El `reobservation_id` ahora forma parte de los
  IDs del CAPTCHA final y de entrenamiento. Los HTTP `400` permanentes se
  descartan del outbox conservando el error; se reconciliaron `12` colisiones
  históricas verificadas y el pendiente volvió a cero.
- Corregido el `2026-08-11`: `cupos-unicos` tomaba la primera imagen de una
  ejecución OBS-007 pero la nombraba con la fecha y hora del resultado final.
  Cada intento y reobservación ahora transporta una asociación explícita entre
  cupo y captura, y archiva todos los cupos distintos de la secuencia. Se
  repararon los dos nombres/contenidos inconsistentes del `2026-08-10` sin
  borrar las capturas originales.
- Implementado el `2026-08-10`: PostgreSQL `schema v50` conserva cada ráfaga
  OBS-006 con `burst_id`, candidatos, detector, auxiliares, posiciones, lease,
  primera lectura, tiempos de reserva allowlisted, resultados y causa de
  cierre. OBS-007 conserva una secuencia durable que enlaza el primer intento
  `slot_lost`, sus observaciones, el segundo intento y el resultado final,
  incluso fuera de una ráfaga. Estos datos no dependen de la retención corta de
  `runs`.
- Implementado el `2026-08-10`: un control singleton persistido y versionado
  permite activar, desactivar o drenar OBS-006/OBS-007 desde Admin API,
  dashboard y Telegram. El estado inicial `inherit` respeta las banderas
  actuales; un circuit breaker durable cierra admisiones ante defensa,
  `403/429`, pérdida de lease posterior al intento, resultado no confirmado o
  fallo de coordinación. El límite duro sigue siendo dos sesiones.
- Los clientes de la cadena posterior fuerzan
  `RESERVATION_CAPTCHA_SAMPLE_LIMIT=1`: el muestreo adicional solo puede ocurrir
  en la sesión detectora y no multiplica su demora por cada cuenta siguiente.
- Corregido el `2026-07-30`: se eliminaron las promociones automáticas de
  prioridad. Las prioridades `100/200` siguen siendo controles manuales de las
  próximas sesiones y una sesión que detecta un cupo válido para su propio
  cliente reserva inmediatamente.
- Implementado el `2026-08-01` y ampliado el `2026-08-02`: si la orden detectora
  no puede usar el cupo por sus reglas, el worker busca hasta diez órdenes
  compatibles con cualquiera de las oportunidades observadas, las recorre sin
  la pausa normal y mantiene un contexto Playwright nuevo por orden. La misma
  cadena se inicia después de una reserva del detector si quedan candidatos.
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
  descansa un valor aleatorio entre `1` y `2` segundos. Solo se hace un
  `reload_probe` completo después del
  intento `8`; al terminar el intento `15` se cierra esa sesión y se rota al
  siguiente cliente con un contexto Playwright nuevo.
- Implementado el `2026-08-09`: el portal dejó de entregar las reglas CSS de
  su modal aunque conservó las mismas clases HTML. Antes y después de abrir el
  panel, el worker y las sesiones manuales comprueban los estilos calculados.
  Solo ante la firma conocida —panel transparente, sin radio, sombra, recorte
  ni espaciado— se restaura localmente la apariencia anterior. Un diseño nativo
  válido elimina el fallback y un estado no reconocido queda intacto. El replay
  aislado confirmó `fallback_applied -> healthy`, retiro automático del estilo,
  cero cambios en los controles y chequeos de `3.6-9.6 ms`; falta observar el
  primer modal real posterior al despliegue.
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
- Implementado el `2026-08-08`: las sesiones manuales distinguen modo
  `appointment` para órdenes listas y modo `portal` para consulta de órdenes
  pausadas, reservadas con pago pendiente, pagadas o archivadas. El segundo
  solo inicia sesión y deja el portal visible; no abre citas, selecciona sede
  ni cambia el estado administrativo. El dashboard conserva pago y postpago
  como acciones principales y ofrece **Abrir portal** como acción secundaria.
- Corregido el `2026-08-01`: la actualización automática del dashboard conserva
  la vista en su posición. El indicador de refresco vive dentro del encabezado
  y ya no inserta ni retira una franja que desplazaba el contenido en cada
  consulta periódica.
- Implementado el `2026-08-14`: **Medir flujo manual** abre una tercera sesión
  `diagnostic` desde el portal, antes del modal. Registra de forma incremental
  cambios de controles, nombres y longitudes de campos, POST y estados HTTP.
  Solo conserva valores allowlisted de sede, fecha y hora; no guarda password,
  cookies, respuesta CAPTCHA, tokens ASP.NET completos ni el cuerpo crudo. Si
  el honeypot contiene datos, bloquea el envío y deja el incidente en el
  informe local. Las órdenes `ready` exponen además **Abrir con medición**
  directamente junto a **Abrir sesión** en la tabla; la acción secundaria
  permanece también dentro de **Más acciones**.
- Ampliado el `2026-08-15` y verificado el `2026-08-17`: la sesión diagnóstica
  intercepta las escrituras JavaScript sobre la propiedad y el atributo
  `value` del honeypot. Conserva
  únicamente vacío/no vacío, longitudes antes/después y si hubo cambio; cada
  POST resume además presencia, vacío y longitud realmente serializada. El
  bloqueo anterior al envío con contenido permanece y el valor nunca se
  persiste. Las diez sesiones diagnósticas disponibles produjeron `111/111`
  POST del formulario de citas con el honeypot presente y vacío. Siete fueron
  POST manuales de **Reservar**: conservaron exactamente los mismos `39`
  nombres de campo y el mismo patrón `30` con contenido / `9` vacíos, y los
  siete recibieron HTTP `200`. Ese estado solo confirma la respuesta HTTP; dos
  de esos envíos ya estaban además correlacionados con evidencia visual del
  portal en **Programado**.
- Corregido el `2026-08-09`: los avisos toast son informativos y ya no prolongan
  durante `2.2` segundos los estados de operación del dashboard. Los bloqueos
  globales y específicos terminan al completar la API y el refresco necesario,
  aunque el aviso continúa visible. El cierre de sesiones manuales usa un estado
  independiente por `session_id`: cada fila muestra **Cerrando…** y permite
  solicitar en paralelo el cierre de otras sesiones sin desbloquear dos veces
  la misma. El cambio no modifica Admin API, reservas ni envíos.
- Implementado el `2026-08-09`: el dashboard incorpora **Post-cita** para
  revisar manualmente cada reserva confirmada en una sesión Playwright aislada
  y de solo lectura. PostgreSQL `schema v49` conserva eventos históricos,
  expediente, placa y etapas con fecha, hora, estado, texto/clase de mensaje y
  continuidad posterior. Los textos quedan restringidos a la API administrativa
  y no se propagan a comunicaciones ni reportes públicos. La
  vista separa cita próxima, fecha pasada sin actualización, avance, cierre,
  observación con o sin avance, credenciales cambiadas y error técnico. No
  altera cola, reservas, CAPTCHA, pagos ni mensajes. Operación y rollback:
  [`operations/post-appointment-followup-2026-08-09.md`](operations/post-appointment-followup-2026-08-09.md).
  La primera consulta real controlada leyó seis etapas de una orden conocida y
  produjo `observation_no_progress`: una observación, cita pasada y las tres
  etapas posteriores aún pendientes. No se ejecutaron CAPTCHA, reservas,
  comunicaciones ni capturas.
  La primera revisión completa terminó el mismo día: `108/108` reservas
  confirmadas con último estado disponible. Resultado: `47` citas próximas,
  `26` completadas, `16` accesos perdidos, `9` en progreso, `6` observaciones
  sin avance y `4` esperando actualización. El lote
  secuencial de las `107` pendientes tomó `20 min 44 s`, usó pausas de `4-7`
  segundos y no produjo errores generales del portal, CAPTCHA, reservas,
  mensajes ni capturas.
- Corregido el `2026-08-09`: **Post-cita** dejó de renderizar `108` expedientes
  completos de corrido. Ahora comparte el patrón de controles de **Órdenes**,
  con búsqueda por cliente/expediente/placa/mensaje, cinco filtros con conteo,
  orden configurable, fichas numeradas, páginas de `5/10/20` y rango visible.
  Las seis etapas permanecen dentro de un detalle expandible: el conector ocupa
  únicamente la fila de marcadores, cada nodo muestra su número y en móvil el
  recorrido cambia a una línea vertical. El CSS quedó encapsulado, usa
  `--ink-muted` y retiró las clases globales ambiguas `good/warn/bad` de esta
  vista. La semántica de color evalúa el recorrido completo: `Atendido`,
  `Programado`, `Por programar`, mensajes `OK` y etapas con fecha son verdes;
  una observación solo se pinta roja si no existe continuidad posterior. Si el
  trámite avanzó, el comentario se conserva visible pero la etapa se considera
  satisfactoria. Etapas futuras sin fecha permanecen neutrales.
- Ajustado el `2026-08-09`: los casos `access_lost` se conservan como historial
  interno, pero salen de la vista predeterminada **En seguimiento**, de la
  métrica **Requieren atención** y de la paginación operativa. El filtro
  **Historial sin acceso** permite consultar la última instantánea y cuándo se
  perdió el acceso; esas fichas figuran archivadas y no ofrecen **Revisar
  ahora**. Los errores técnicos continúan separados y sí permanecen
  accionables. No se borraron revisiones ni textos y no se añadieron
  recordatorios o reintentos automáticos.
- Corregido el `2026-08-09`: el orden **Reserva** de **Órdenes** ya no compara
  el texto `DD/MM/YYYY`. Un parser común normaliza `DD/MM/YYYY`, `DD-MM-YYYY`,
  `YYYY-MM-DD` y timestamps, combina fecha con hora y mantiene valores ausentes
  al final. La prueba contra las `108` reservas activas produjo un recorrido
  ascendente real desde `10/07/2026 09:00` hasta `29/08/2026 08:00`, sin
  agrupar primero por día. La paginación de Órdenes muestra además siempre
  `Página X de Y` y sus cabeceras ordenables exponen `aria-sort`.
- Resumen mensual, finanzas, bandeja de pendientes y edición segura de
  credenciales.
- Implementado el `2026-08-10` en paralelo con la muestra pasiva de Fase 1: el
  contrato comercial v2 separa eventos del periodo, cohorte de altas y atención
  viva. MTD se compara contra los mismos días del mes anterior y los meses
  cerrados se comparan por separado. Cada tasa conserva numerador, denominador,
  cobertura y corte; el endpoint v1 permanece como rollback.
- PostgreSQL `v54` conserva `acquisition_source` en la orden. Las altas nuevas
  congelan la fuente recibida al crearse; `113` órdenes históricas se marcaron
  explícitamente como `historical_backfill` y `6` continúan sin fuente, por lo
  que esa migración no se presenta como prueba del origen original.
- El contacto comercial requiere ausencia simultánea de teléfono y username
  para figurar como faltante. El centro de calidad financiera separa datos
  reales, estimados y pendientes, conversiones faltantes y pagos con diferencia
  contra lo acordado. El único caso actual de `S/10` permanece sin clasificar:
  la API exige descuento, condonación o corrección con motivo y responsable.
- El cierre financiero mensual conserva saldos, recargas, consumo, reembolsos,
  conciliación y responsable. Bloquea meses actuales/futuros, datos pendientes,
  pagos sin resolver y balances inconsistentes. `is_complete` solo significa
  conversión monetaria completa; costos unitarios, margen porcentual, CAC y
  ROAS continúan ocultos hasta reconciliar captura y atribución.
- Retirado el `2026-08-07`: el registro por invitaciones dejó de formar parte
  del dashboard, Admin API, Telegram y arranque. PostgreSQL v43 elimina su tabla
  local; el alta manual de clientes permanece disponible.
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
  preflight, `document_type`, el contrato de restricciones vigente entonces y muestreo CAPTCHA
  sombra. Se actualizaron únicamente las pruebas; no fue necesario relajar ni
  modificar código productivo. La suite completa quedó en `59 passed`.
- Consolidado documentalmente el `2026-08-09`: se revisaron los `40` archivos
  existentes bajo `docs/`, se reescribió el roadmap como única cola futura y
  se clasificaron contratos, runbooks, snapshots e historia. No se eliminó
  evidencia única. El inventario vive en
  [`history/documentation-audit-2026-08-09.md`](history/documentation-audit-2026-08-09.md).

### Control remoto

- Reorganizado el `2026-08-23`: el menú principal se limita a **Pendientes**,
  **Buscando cupo**, **Por cobrar**, alta, búsqueda, citas/resumen y estado; sus
  tres listas diarias muestran contadores reales. Historial, errores,
  oportunidades y CAPTCHA quedan en **Herramientas**, y CAPTCHA solo aparece
  cuando el runtime lo declara activo. La cola contiene únicamente órdenes
  `ready`; pausados y bloqueos pasan a **Pendientes**.
- `GET /api/v1/operator-inbox` centraliza una sola siguiente acción por orden:
  acceso, pausa, contacto, WhatsApp inicial, cobro o revisión postpago. Telegram
  muestra los casos ambiguos de WhatsApp pero nunca los reintenta ni resuelve sin
  la evidencia visual y nota auditada del dashboard.
- **Por cobrar** muestra cita, contacto enmascarado, acordado, abonado y saldo.
  **Confirmar pago completo** encola postpago; **Registrar abono** guarda el total
  acumulado, conserva `pending` y no encola comunicaciones. Ambos usan fotografía
  esperada y confirmación; Telegram no permite cerrar por debajo de lo acordado.
- Las prioridades visibles quedaron alineadas con dashboard: Normal `0`,
  Enfocada `100` y Exclusiva `200`. Las revalidaciones, reglas, prioridades,
  pagos y controles del sistema requieren confirmación y relectura de estado.
- Implementado el `2026-08-23`: una orden pendiente cuyo preflight clasifica
  `invalid_credentials` ofrece **Corregir acceso** directamente en la bandeja
  **Pendientes** y en su panel contextual de Telegram. El bot solicita solo la
  nueva contraseña en chat privado autorizado,
  intenta borrar inmediatamente ese mensaje, vuelve a comprobar que el acceso no
  haya cambiado, exige confirmación y reutiliza el contrato de Admin API que pausa
  la cuenta y sus subórdenes mientras ejecuta un nuevo preflight automático. Para
  otros fallos se conserva **Reintentar validación**; no se presenta ese reintento
  cuando repetir las mismas credenciales rechazadas sería inútil. Admin API y el
  receptor se recargaron de forma aislada a las `11:45-11:46`; health, polling y
  check local regresaron correctos sin reiniciar el worker ni enviar mensajes de
  prueba.
  Cada botón de la bandeja incluye además el nombre del cliente para que varias
  acciones del mismo tipo no resulten ambiguas.
- Validación del cambio: `compileall`, Ruff, `59 passed`, build Angular,
  `git diff --check` y `telegram_control --check` correctos. Admin API y el
  receptor Telegram fueron reiniciados de forma controlada después de comprobar
  cero submissions, trabajos WhatsApp, sesiones manuales y ráfagas activas;
  `/api/v1/operator-inbox` respondió en vivo sin enviar mensajes ni registrar pagos.
- Desde el `2026-08-21`, los registros de WhatsApp aceptan un celular peruano
  de nueve dígitos sin prefijo y lo normalizan a `+51` antes de persistirlo o
  preparar cualquier envío. Los números con código internacional se conservan.
- Alta manual y edición guiada de cuatro restricciones de fecha y prioridad;
  `/credenciales` y `/recientes` fueron retirados del despacho. Las mutaciones
  exigen chat privado y usuario autorizado mediante `TELEGRAM_CONTROL_USER_IDS`;
  sin lista separada, el usuario debe coincidir con el chat privado allowlisted.
- Pausa, reanudación y reinicio mediante Admin API y comandos persistidos.
- Corregido el `2026-08-11`: el reinicio embebido y el comando persistido
  comparten una sola transición que cancela y detiene el ciclo con
  `paused=false`. El proceso nuevo ya no puede heredar como pausa la detención
  temporal usada para reiniciar.
- Desde el `2026-08-11`, pausa, reanudación y reinicio dejan una entrada
  sanitizada en `remote_control_audit`. Los comandos diferidos enlazan la
  auditoría con su `command_id`; el control embebido registra el canal local.
- Implementado el `2026-08-14`: el modal **Reiniciar worker** conserva por
  defecto todos los backoffs y ofrece una opción explícita para liberar solo
  errores técnicos seguros. La variante siempre usa el comando persistido de
  reinicio y elimina únicamente `order_state.next_allowed_at` cuando la orden
  sigue `ready`, el último run terminó `error` sin intento de reserva, no existe
  un `reservation_attempt` activo, no hubo resultado de submit y el mensaje no
  contiene una señal de defensa del portal. `reservation_unconfirmed`,
  `captcha_invalid`, `403/429`, submissions ambiguos y otros estados protegidos
  conservan su espera. El error y sus contadores permanecen disponibles para
  diagnóstico; la respuesta y `remote_control_audit` registran cuántos
  backoffs se liberaron y cuántos siguieron protegidos.
- Expiración de conversaciones, botones obsoletos rechazados y un solo flujo
  guiado por chat.
- Simplificado el `2026-08-01`: se retiró el etiquetado antiguo de CAPTCHA que
  escribía en un CSV separado, junto con sus variables y scripts exclusivos.
  Implementado nuevamente el `2026-08-08` sobre la cola sombra vigente: Telegram
  muestra el pendiente más antiguo, agrupa respuestas iguales de los modelos,
  permite elegir una, escribir cinco caracteres manualmente u omitir, guarda por
  Admin API y avanza automáticamente. La sesión vence tras `10` minutos de
  inactividad y cada imagen invalida los botones anteriores.
- `/cliente_nuevo` crea una orden de forma manual. Solicita tipo y número de documento,
  contraseña, contacto, fuente, WhatsApp opcional y permite omitir o configurar
  las cuatro restricciones de fecha. La conversación concede tres minutos por
  paso, permite retroceder y conserva dos minutos para confirmar. La contraseña
  queda oculta en confirmación/comprobante; Telegram intenta borrar el mensaje
  de entrada y entrega una revelación separada, borrable y eliminada automáticamente
  tras dos minutos. El alta informa el resultado real del preflight cuando termina
  dentro de la espera.
- Implementado el `2026-08-25`: `/cliente_nuevo` exige elegir el servicio antes
  de activar el monitoreo. **Estándar - S/50** conserva las restricciones
  habituales; **Día elegido - S/70** solicita un único día de la semana y lo
  persiste en `allowed_weekdays`, por lo que el motor solo puede reservar lunes,
  martes, miércoles, jueves, viernes, sábado o domingo, según lo elegido. Esa
  regla se combina con fecha mínima, fecha máxima y fechas excluidas opcionales:
  el motor busca únicamente el día elegido dentro de esos límites;
  **Monto personalizado** permite una excepción explícita. El comprobante de
  Telegram muestra servicio, precio y alcance, PostgreSQL `v60`
  conserva `service_type` y `reservation_price`, y el aviso inicial de WhatsApp
  usa una sola plantilla para todos los servicios: muestra servicio, precio,
  condiciones de búsqueda y fechas excluidas cuando existan, además de advertir
  que la disponibilidad depende de la PNP. El precio se
  fija antes de reservar, se copia al pago y se preserva si la orden ya está
  reservada o pagada. `compileall`, Ruff, las `59` pruebas existentes, una
  creación aislada en schema temporal, los tres recorridos locales de Telegram
  y el build Angular quedaron correctos; el build conserva un warning de
  presupuesto inicial de `2.42 kB`. Tras esperar el cierre de dos sesiones
  manuales, PostgreSQL quedó en `v60`, Admin API regresó saludable y el receptor
  Telegram pasó `--check`. No se reinició el worker, no se crearon clientes
  reales ni se enviaron comunicaciones.
- Actualizado el `2026-08-20`: la captura de WhatsApp en `/cliente_nuevo` ofrece
  una elección explícita entre **Número**, **Usuario** y **Omitir WhatsApp**.
  Telegram valida únicamente el tipo elegido; para usuario acepta el valor con
  o sin `@` y lo normaliza antes de crear la orden. Un error recuperable renueva
  el tiempo del paso sin guardar el valor rechazado.
- Corregido el `2026-08-22`: un timeout local después de persistir el alta ya no
  convierte la operación en un falso `failed`. El POST de creación dispone de
  `15` segundos y, si su respuesta queda ambigua, Telegram busca la orden por el
  documento, exige una única orden principal y vuelve a comprobar credenciales,
  contacto y restricciones antes de continuar. Si la orden ya existe registra
  `applied` con `confirmation=recovered_after_*`; si falla únicamente el
  seguimiento posterior informa que el alta quedó registrada y prohíbe repetirla.
  La auditoría conserva etapa y causa sanitizada sin contraseña ni documento.
  La simulación local confirmó recuperación tras timeout y rechazo HTTP real;
  `compileall`, Ruff, las `59` pruebas existentes y `telegram_control --check`
  quedaron correctos.

### Evidencia y CAPTCHA

- Evidencia organizada por fecha y resumen compacto.
- Corregido el `2026-08-02`: las bitácoras Markdown ya no escriben nombres de
  clientes, `order_id` completos ni respuestas CAPTCHA. Las entradas nuevas del
  1 de agosto se sanitizaron antes de versionarlas.
- CAPTCHA original utilizado para el solver.
- Servicio local en modo sombra, cola durable y revisión humana desde el
  dashboard o Telegram; ambas interfaces guardan en la misma fuente de verdad.
- El botón **Etiquetar CAPTCHA** y `/captchas` recorren en orden los eventos no
  etiquetados. Las respuestas repetidas de varios modelos aparecen como una sola
  opción con sus modelos asociados; **Escribir otra respuesta**, **Omitir** y
  **Salir** cubren los demás casos. Antes de guardar se exige que el evento siga
  sin etiqueta para no pisar una revisión realizada desde la otra interfaz.
- Desde el `2026-08-13`, **Etiquetar CAPTCHA** y `/captchas` ya no presentan los
  pendientes de forma exhaustiva. La cola dirigida prioriza toda decisión del
  canario V6, anomalías o baja confianza, desacuerdos V3/V6 y una muestra de
  control determinista del `6.25%` de los acuerdos por prefijo SHA-256. Los
  demás eventos no se borran: permanecen en **Historial > Pendientes**. En el
  corte de activación se redujo la tarea manual de `1,015` pendientes a `84`
  prioritarios: `2` decisiones V6, `8` desacuerdos y `74` controles, sin
  anomalías pendientes. Esta selección no reentrena ni promociona modelos.
- Desde el `2026-08-10`, V6 participa en un canario acotado de `20` decisiones
  reales. V3 sigue solo en sombra. 2Captcha permanece como fallback ante baja
  confianza, formato inválido, timeout, servicio no saludable, circuito abierto
  o límite agotado; no se autorizó un reemplazo total sin fallback.
- Implementado el `2026-08-09`: el servicio sombra residente ejecuta únicamente
  `v3_selected` como control y `v6_sequence_candidate` como candidata sobre
  CAPTCHA nuevos. V1, las dos variantes V2, V4 y V5 dejaron de consumir GPU,
  pero sus checkpoints, métricas y predicciones históricas permanecen intactos.
  El dashboard y Telegram siguen leyendo eventos antiguos de forma dinámica.
- Corte prospectivo V6 revisado el `2026-08-10`: `475` imágenes únicas,
  frescas y etiquetadas manualmente posteriores al freeze. V6 obtuvo `474/475`
  (`99.79%`) y v3 `460/475` (`96.84%`). Las muestras cubren una sola jornada y
  cinco órdenes, pero `430/475` pertenecen a una sola orden. Por autorización
  explícita del operador, esa evidencia se consideró suficiente para un canario
  híbrido limitado, no para retirar 2Captcha.
  V3 y V6 coincidieron en `459/475`; las `459/459` coincidencias fueron
  correctas y las `16` discrepancias incluyen el único error de V6. Esta
  cobertura observada de `96.63%` favorece el fallback por unanimidad, no el
  reemplazo total.
  Al llegar a `500` debe recalcularse por `image_sha256` contra etiqueta humana;
  ese corte decidirá la ampliación o cierre del canario, no elimina el fallback.
- Activado el `2026-08-10`: PostgreSQL `v51` persiste modo, límite, umbrales,
  contadores, fuente elegida, resultado del portal y circuito. V6 se admite solo
  con `min_char_confidence >= 0.60` y
  `sequence_confidence_product >= 0.60`, con timeout de `500 ms`. En la cohorte
  de 475, esos umbrales habrían admitido `473/475` sin incluir el único error de
  V6. El primer `captcha_invalid`, una respuesta local inválida o un resultado
  ambiguo abre el circuito. Un timeout o fallo transitorio aislado usa 2Captcha
  solo para ese intento; tres fallos técnicos consecutivos abren el circuito.
  El rollback persistente es `mode=2captcha` y aplica al siguiente CAPTCHA sin
  editar `.env`.
- Corregido el `2026-08-11`: las dos primeras decisiones productivas V6
  resolvieron localmente, pero el adaptador intentó leer los atributos
  inexistentes `request_ms` e `inference_ms` al devolver el resultado. Dos
  oportunidades compatibles terminaron en `error` antes de escribir el CAPTCHA
  o pulsar **Reservar**, sin `reservation_attempts` ni submits pendientes. El
  adaptador usa ahora `local_request_ms` y `local_inference_ms`; ambas decisiones
  quedaron cerradas como
  `not_submitted_internal_error`, sin contarlas como aceptación o rechazo. El
  worker se reinició de forma controlada. La tercera decisión V6 recorrió la
  ruta corregida, llegó al submit y el portal respondió `slot_lost`, sin
  fallback, `captcha_invalid` ni apertura del circuito. La cuarta decisión
  resolvió localmente en `0.141 s`, fue aceptada por el portal y terminó en la
  primera reserva confirmada con autoridad V6. El canario queda en `4/20`, con
  `16` decisiones locales restantes, una confirmación, un `slot_lost`, dos
  errores internos previos al submit y cero fallbacks. La ruta pasa
  `compileall`, Ruff, `59 passed` y validación productiva del adaptador; la
  efectividad del modelo continúa bajo revisión durante las primeras `20`
  decisiones.
- Corregido el `2026-08-13`: el timeout observado el día anterior no correspondió
  a una inferencia V6 lenta. La inferencia registrada fue `13.403 ms`, pero el
  request superó `500 ms` porque el flujo encolaba `/v1/predict` y luego hacía
  otra llamada síncrona con el mismo `event_id`; ambas podían competir por el
  lock global y repetir V6, además de esperar V3, persistencia y el recálculo de
  estadísticas. La autoridad usa ahora `/v1/predict/authority`, que ejecuta y
  persiste solo `v6_sequence_candidate`; al recibir el resultado, el outbox
  durable completa únicamente el modelo sombra faltante. El servicio aplica
  single-flight por evento, no recalcula estadísticas en la respuesta crítica y
  devuelve tiempos separados de cola, preprocesamiento, inferencia,
  persistencia y total. Se conserva el timeout de `500 ms`, el fallback inmediato
  a 2Captcha y el breaker inmediato para resultados inválidos; los fallos
  técnicos transitorios requieren tres eventos consecutivos. El canario conserva
  `4/20`, circuito cerrado y sin cambio de umbrales. Los cinco fallbacks
  persistidos desde el incidente corresponden al timeout inicial y a cuatro
  decisiones posteriores con `circuit_open`; esas cuatro terminaron confirmadas
  por el portal mediante 2Captcha. No son rechazos de V6 ni consumen nuevas
  admisiones locales.
- Aplicado el `2026-08-14`: el operador solicitó volver a 2Captcha y el control
  persistente quedó en `mode=2captcha`, efectivo desde el siguiente CAPTCHA,
  sin reiniciar el worker ni resetear el circuito o los contadores. El corte se
  conserva en `5` decisiones locales, `2` confirmaciones locales, cero rechazos
  locales y `5` fallbacks. Antes del cambio se comprobó que no existían una
  sesión Playwright activa, submissions vivas de órdenes operativas ni ráfagas
  en ejecución. Una fila `unknown` del 3 de julio pertenece a una orden ya
  archivada y se preservó sin modificación.
- El rollback de autoridad no corrige el incidente que lo precedió: dos cupos
  reales del `2026-08-14` (`17/08/2026 12:00` y `31/08/2026 09:00`) fallaron
  antes de invocar cualquier resolutor porque la imagen CAPTCHA del panel no
  terminó de cargar ni pudo capturarse tras dos intentos. Ambas corridas
  terminaron `error`, sin clic en **Reservar** ni filas nuevas en
  `reservation_attempts`, y la segunda activó el backoff general configurado de
  `1800` segundos. Debe diagnosticarse la carga/captura del CAPTCHA del portal
  por separado si vuelve a ocurrir bajo 2Captcha.
- Corregido en código el `2026-08-14`: el portal reemplazó el CAPTCHA gráfico
  por una suma renderizada como texto HTML en
  `#MainContent_idUcitas_lblCaptchaOperacion`; ya no existe una imagen CAPTCHA
  descargable en ese panel. El flujo reconoce exclusivamente el formato
  estricto `N + N = ?`, calcula la suma localmente, conserva una captura de
  `.captcha-suma` como evidencia y valida otra vez la firma del desafío y el
  honeypot vacío inmediatamente antes del submit. Un DOM ambiguo, una expresión
  distinta o un cambio de firma bloquean el envío. El CAPTCHA gráfico heredado
  conserva 2Captcha como autoridad; las sumas HTML no pasan por V3/V6, 2Captcha
  ni el dataset sombra de cinco caracteres. El refresco compara la firma de la
  expresión nueva. El `2026-08-17`, siete POST manuales de **Reservar** cerraron
  la referencia estructural y confirmaron el honeypot vacío; dos contaban además
  con correlación visual hasta **Programado**.
  La ruta automática de suma incorpora desde ese corte una espera aleatoria
  configurable de `1-2 s` después de llenar la respuesta. Antes, después y en
  el instante previo al clic vuelve a revisar el formulario; tras la espera
  repite selección, firma matemática y honeypot. Un campo protegido con datos,
  un campo nuevo no vacío o la ausencia de sede, fecha, hora, CAPTCHA o botón
  bloquea el envío. El POST real se observa pasivamente y conserva solo nombres,
  longitudes, hashes cortos de tokens y valores operativos allowlisted para
  compararlo con la referencia manual, nunca el cuerpo crudo ni la respuesta.
  El replay Chromium positivo capturó intent, clic, POST y HTTP `200`; el replay
  negativo llenó el honeypot durante la espera y bloqueó antes del intent y del
  POST. `compileall`, Ruff y `59 passed` quedaron correctos; `git diff --check`
  pasó en el alcance del cambio.
  El primer canario productivo ocurrió el `2026-08-17` a las `10:57` hora Lima:
  el detector y una sesión auxiliar independiente reservaron el mismo cupo
  compatible de `01/09/2026 12:00`. Las tres auditorías de cada orden pasaron,
  los hashes de tokens permanecieron estables, los dos POST reales coincidieron
  exactamente con `39 / 30 / 9`, el honeypot tuvo longitud cero y no aparecieron
  campos inesperados, faltantes ni protegidos con contenido. El portal respondió
  en `297 ms` y `265 ms`; ambas reservas quedaron `confirmed`, con evidencia
  posterior exacta en **Programado**. La telemetría persistente usa `field_name`
  para conservar el nombre técnico de cada control sin habilitar nombres
  personales ni valores sensibles a través del sanitizador general.
  La revisión posterior de los dos
  cupos que dispararon el incidente confirmó además que la captura `cupo` nunca
  se creó: su gate esperaba una imagen CAPTCHA y rechazó la suma HTML antes del
  screenshot. La evidencia de disponibilidad queda ahora desacoplada del
  CAPTCHA, tiene fallback a página completa y se archiva inmediatamente en
  `cupos-unicos` al estabilizar fecha y hora, antes de resolver o enviar. Un
  error posterior ya no puede impedir ese archivo único. Falta comprobar el
  resultado visual con el siguiente cupo real. El worker se pausó al terminar
  una sesión `Sin Cupos`, se reinició con frontera segura y quedó reanudado con
  un lease nuevo; las sesiones manuales del Admin API permanecieron intactas.
- Puesta en reserva fría el `2026-08-20`: el CAPTCHA matemático continúa con
  cálculo local, firma y honeypot, mientras el productor sombra y el supervisor
  CUDA quedan apagados mediante controles separados. V3/V6, los checkpoints
  anteriores, los `3,177` eventos y sus etiquetas se preservan sin ejecutar
  inferencia nueva. El dashboard oculta CAPTCHA y lo excluye de **Pendientes**
  cuando la capacidad está apagada; la ruta directa vuelve a **Resumen**. Si el
  portal recupera el CAPTCHA gráfico, 2Captcha conserva la reserva y una alerta
  Telegram mensual deduplicada informa que la sombra requiere reactivación
  explícita.
- Actualizado el dashboard el `2026-08-10`: **Capturas CAPTCHA** separa ahora
  cantidad de muestras, validación de restricciones y autoridad final. Muestra
  resolutor efectivo, progreso `V6/20`, confirmaciones, rechazos, fallbacks,
  circuito y acciones confirmadas para activar V6 o volver a 2Captcha. El texto
  anterior que afirmaba que 2Captcha siempre resolvía el final fue retirado.
  Los estilos exclusivos de esta vista se cargan con el componente lazy de
  Resumen; el presupuesto inicial de aviso pasó de `520` a `525 kB` y el build
  queda en `521.65 kB` sin warnings.
- Implementado el `2026-08-01`: el flujo real admite muestreo CAPTCHA opcional
  mediante `RESERVATION_CAPTCHA_SAMPLE_LIMIT`. Desde el `2026-08-08`, el
  dashboard permite activarlo o desactivarlo y conservar un total entre `2` y
  `50` en PostgreSQL (`schema v47`), sin editar `.env` ni reiniciar el worker.
  Desactivado aplica un total efectivo de `1`; activado guarda y refresca las
  muestras previas y envía únicamente la última a 2Captcha. El valor queda fijo
  durante el lote en curso y los cambios empiezan en el siguiente lote CAPTCHA.
  El modo rápido mantiene una guarda independiente que siempre fuerza `1`. El
  panel separa visualmente modo, cantidad, efecto del próximo intento y estado
  guardado para evitar confundir el total elegido con el total efectivo. El
  bloque usa separación explícita de `16-24 px`, tarjetas internas respiradas,
  resultado aislado y acción final dividida por borde. El presupuesto CSS se
  amplió de `27/30 kB` a `30/33 kB`; el build vigente queda en `504.21 kB` sin
  warning.
- Los 46 intervalos consecutivos medidos en el muestreo del observador tuvieron
  `0.390 s` de mediana y `0.406 s` de p90 por CAPTCHA adicional. Un límite de
  `5` agrega aproximadamente `1.6 s` antes de iniciar 2Captcha. La opción queda
  desactivada por defecto.
- Primera medición productiva del `2026-08-01`, con el límite local en `10`:
  dos cupos incompatibles capturaron diez CAPTCHA cada uno antes de terminar
  como `partial / blocked_by_order_rule`. Las nueve muestras adicionales
  agregaron `3.609 s` y `3.625 s`; cada ciclo de captura y refresco promedió
  aproximadamente `0.402 s`. No hubo submit, consumo de 2Captcha ni reserva,
  por lo que todavía falta medir el impacto completo sobre una reserva real.
- Terminado el experimento, el control productivo quedó desactivado: cada
  intento conserva el CAPTCHA que realmente usa, pero no añade los `3.6 s`
  observados por las nueve muestras extra antes de competir por el cupo. El
  `.env` permanece como fallback seguro y no es el control operativo diario.
- Corregido el mismo día: la ruta de evidencia bloqueada ahora conserva
  `run_id` y `order_id`, y registra tanto las nueve muestras previas como la
  final en CAPTCHA sombra. Los 20 originales ya capturados fueron recuperados
  y quedaron pendientes de revisión humana, cada uno con tres predicciones.
- Integrado el `2026-08-02`: el candidato `v3_finetuned_from_v2` quedó como
  `v3_selected` en el servicio sombra. Es el mejor resultado global hasta ahora:
  frente a `v2_selected` subió de `90/98` a `93/98` en la misma prueba temporal disponible,
  de `143/150` a `147/150` en el holdout humano y de `76/78` a `77/78` en el
  corte sombra independiente. El servicio carga cuatro modelos y el dashboard
  identificaba a v3 como seleccionado; en ese corte histórico 2Captcha
  conservaba toda la autoridad operativa. El estado vigente es el canario V6
  descrito arriba.
- Las 78 imágenes del corte sombra excluido del entrenamiento se reprocesaron
  con v3 para mostrarlas en Calidad. Las 157 imágenes usadas para entrenarlo no
  se reprocesaron, evitando presentar exactitud de entrenamiento como evidencia
  independiente. Desde el `2026-08-09`, los CAPTCHA nuevos ejecutan únicamente
  `v3_selected` y `v6_sequence_candidate`; los demás modelos permanecen como
  historia comparable.
- Auditado el `2026-08-07`: el primer corte prospectivo posterior a v3 contiene
  `126` CAPTCHA recibidos entre el 3 y el 5 de agosto, todos revisados
  manualmente. `v3_selected` obtuvo `119/126` (`94.44%`), empatado con
  `v2_selected`; `v2_scratch` obtuvo `120/126` (`95.24%`) y `v1_real`
  `118/126` (`93.65%`). v2 seleccionado y v3 discreparon solo en dos casos:
  cada uno resolvió correctamente uno, mientras ambos fallaron juntos en seis.
- Los cuatro modelos coincidieron correctamente en las `15/15` referencias
  confirmadas por el portal dentro de ese corte, una muestra insuficiente para
  diferenciarlos. Ese resultado prospectivo no confirmó la ventaja histórica
  de v3 y entonces mantuvo a 2Captcha como única autoridad; fue supersedido
  por el canario V6 acotado y con fallback descrito arriba.
- Corregido el `2026-08-08`: los CAPTCHA capturados únicamente para documentar
  un cupo incompatible (`blocked_by_order_rule` o `priority_deferred`) se
  conservan en disco, historial y CAPTCHA sombra, pero dejaron de enviarse por
  Telegram. La alerta urgente deduplicada de disponibilidad se mantiene; el
  barrido diferido excluye esos reportes diagnósticos y nunca usa un CAPTCHA
  como foto sustituta cuando no existe evidencia operativa normal.

### Comunicación y cobro

- Álbum único con evidencia y QR de Yape.
- Seguimiento postpago separado con PDFs y textos.
- Cola durable de trabajos WhatsApp con estados recuperables y auditables.
- Admin API como único propietario del perfil persistente de WhatsApp Web.
- Fallos de WhatsApp no bloquean reservas ni Telegram.
- Implementado el `2026-08-20`: **Pendientes** ya no usa `Revisar orden` como
  navegación sin efecto. Los trabajos de álbum o postpago `failed/uncertain`
  abren una conciliación de solo lectura que conserva el error técnico y el
  paquete previamente preparado sin abrir WhatsApp ni iniciar otro intento.
  El operador puede confirmar que el paquete ya estaba completo, completar
  manualmente solo el texto o PDF faltante y confirmarlo, o cerrar sin envío
  con una nota obligatoria. PostgreSQL `v58` guarda resolución, nota, actor y
  fecha aparte del estado técnico original; la bandeja se refresca al cerrar y
  las órdenes archivadas ya no reaparecen por un preflight fallido antiguo.
  Una resolución manual queda en auditoría central. No se conciliaron ni
  reenviaron automáticamente los casos históricos durante el despliegue.
  Validación viva: schema `v58`, Admin API aislada saludable, bundle
  `main-5C222H75.js`, los tres postpagos pendientes recuperables con `4` pasos,
  `2` PDF y texto completo, ruta inválida `400` sin escritura, `compileall`,
  Ruff, `59 passed`, build Angular y `git diff --check`. No había navegador
  conectado para la aprobación visual interactiva.
- Endurecido el `2026-08-20` sin cambiar la arquitectura ni los disparadores:
  el álbum permite una sola segunda apertura segura del menú antes de elegir
  archivos; la búsqueda por `@usuario` repite una vez únicamente antes de
  escribir; y el postpago no pasa al texto hasta que desaparece la vista previa
  y aparecen las dos burbujas salientes confirmadas de los PDF. Un segundo clic
  de documentos solo es posible si la vista previa continúa demostrablemente
  abierta. Si ya desapareció pero falta confirmación, el trabajo permanece
  `uncertain` sin otro clic. Las fases de fallo distinguen menú no abierto,
  input sin soporte múltiple y vista previa no cerrada/no confirmada.
  Tras el primer caso real posterior se retiró el `Escape` previo a la segunda
  apertura: WhatsApp puede interpretarlo como cierre de la conversación. El
  segundo intento exige ahora que el compositor del chat continúe visible; si
  desapareció, termina antes de seleccionar archivos o intentar enviar.
  El reenvío real de `order-74702632` validó esa corrección a las `15:44`:
  la primera apertura volvió a no mostrar el menú, la segunda conservó el chat
  y el álbum de dos elementos quedó `sent`. Esta evidencia acepta el caso del
  álbum; postpago y búsqueda por usuario conservan su aceptación pendiente.
  `compileall`, Ruff, las `59` pruebas existentes y `git diff --check` quedaron
  correctos para los archivos del cambio.
- Implementado el `2026-08-17`: recordatorios diarios para las reservas
  confirmadas del dia siguiente. PostgreSQL `v56` normaliza
  `reservations.appointment_day`, conserva un corte diario y crea trabajos
  idempotentes por reserva/fecha. La cola exige primero un resumen diario
  existente y terminal; los recordatorios permanecen bloqueados mientras
  cualquier resumen de esa fecha siga activo. Justo antes de enviar se
  revalidan fecha Lima, reserva vigente, contacto y texto; un dato obsoleto
  termina `skipped` sin abrir WhatsApp. Admin API aloja el programador y el
  dashboard muestra fecha objetivo, barrera y conteos. La capacidad permanece
  La autoridad operativa ya no depende de las banderas antiguas de `.env`: el
  control PostgreSQL quedo en `live`, revision `2`, despues de completar el
  primer lote real. El dry-run previo sobre el `2026-08-18` encontro `8`
  elegibles, cero contactos faltantes y cero fechas invalidas.
- Visibilidad ampliada el `2026-08-17`: Resumen conserva un acceso compacto y
  la nueva pantalla `Seguimiento` separa Proximas citas, Post-cita e Historial.
  Los ocho elegibles se muestran con busqueda, orden y contacto enmascarado;
  `/post-cita` sigue funcionando como redireccion. Build Angular correcto con
  `530.57 kB`; queda pendiente la aprobacion visual real porque no habia un
  navegador conectado durante esta implementacion.
  Admin API se reinicio aisladamente en una frontera segura y sirvio el bundle
  `main-64TD5UPN.js`; el worker continuo saludable y no se enviaron mensajes.
- Configuracion ampliada el `2026-08-17`: `Seguimiento > Proximas citas`
  permite editar la plantilla con `{nombre}`, `{fecha}`, `{hora}` y `{sede}`,
  previsualizarla, restaurar el texto recomendado y guardar los modos
  `disabled`, `dry_run`, `canary` o `live`. PostgreSQL conserva revision e
  historial; el canario exige 1 o 2 ordenes elegibles y canario/productivo
  requieren segunda confirmacion. La migracion parte desactivada y no envia.
  Validacion viva: schema `v57`, API PID `38408`, bundle `main-4TE6ORXA.js`,
  `8` candidatos, cero trabajos, `59` pruebas y build `532.65 kB`. La revision
  visual humana permanece pendiente.
- Corregido el `2026-08-21`: el canario de recordatorios validaba correctamente
  una o dos ordenes, pero al persistirlas aplicaba el ocultamiento de datos al
  `order_id` y guardaba `order-***`, por lo que ninguna seleccion coincidia en
  la conciliacion. El identificador interno se conserva ahora integro y la
  pantalla muestra el detalle devuelto por la API si un guardado es rechazado.
- Primer lote real de recordatorios completado el `2026-08-17`: el resumen de
  `16` evidencias termino antes de admitir clientes y los `8/8` recordatorios
  cerraron `sent`, sin fallos, incertidumbre, omisiones ni duplicados. La
  revision encontro que el saludo usaba el nombre del contacto de WhatsApp;
  para lotes futuros `{nombre}` usa exclusivamente el nombre de la persona que
  asistira al peritaje. Vista previa y backend comparten tambien la misma fecha
  textual. Los ocho mensajes historicos no se reenvian. Admin API recargo la
  correccion en PID `30048` y sirve `main-5RIZKUNK.js`; el control permanece
  `live`, revision `2`.
- Al corte de las 18:00 se encola un resumen diario idempotente al número
  personal configurado fuera del repositorio: primero envía el texto fechado y
  luego todas las imágenes de `cupos-unicos`. El primer caso real del 30 de
  julio cargó cuatro miniaturas, pero cerró el navegador con tres imágenes aún
  pendientes y solo una llegó al teléfono. El trabajo quedó reconciliado a
  `uncertain`; ahora se exige confirmar cada imagen saliente antes de cerrar.
  El reintento manual autorizado terminó `sent` con las cuatro imágenes
  confirmadas.
- Corregido el `2026-08-13`: el resumen atrasado del 12 de agosto confirmó el
  texto, pero dos intentos de su álbum de 21 imágenes quedaron en la vista
  previa sin accionar el botón de envío. La ruta de álbum ahora prioriza el
  botón semántico `Enviar/Send` ya usado por los textos, vuelve a intentarlo
  mientras la vista previa siga abierta, usa `Enter` si el clic no la cierra y
  conserva el clic por coordenadas solo como fallback. El intento con `Enter`
  cerró la vista previa y dejó imágenes con doble check azul, pero el detector
  no pudo contar las 21 por la virtualización del historial y conservó
  `uncertain`; requiere confirmación del operador antes de reconciliar o enviar
  únicamente la publicación pendiente. Los intentos anteriores permanecen
  `uncertain`.
- Implementado el `2026-08-13`: los resúmenes diarios dividen sus imágenes en
  paquetes secuenciales de hasta cuatro. Cada paquete debe quedar confirmado
  antes de adjuntar el siguiente; el último puede contener menos de cuatro. Si
  un paquete queda ambiguo, el trabajo se detiene como `uncertain` e informa el
  número de paquete y cuántas imágenes anteriores estaban confirmadas. La
  publicación de TikTok solo se intenta después de confirmar todos los
  paquetes. La confirmación identifica mensajes nuevos por firma durable para
  tolerar que WhatsApp virtualice imágenes anteriores del historial.
- Validado y ajustado el `2026-08-13`: el primer cierre real con paquetes envió
  `10` imágenes como `4 + 4 + 2`; los tres paquetes quedaron confirmados y la
  publicación se intentó solo después del último. El texto final llegó completo
  y la evidencia muestra doble check azul, pero esa marca apareció en el límite
  de los `15` segundos y el trabajo terminó como falso `uncertain`. La espera de
  texto ahora es de `30` segundos, seguida por `3` segundos de gracia y una
  relectura adicional después de guardar la captura final. Si aun así no existe
  una burbuja saliente nueva y confirmada, se conserva `uncertain` sin reintento.
- Pruebas deliberadas del `2026-08-13`: `retry-5` partió por error del trabajo
  parcial `retry-4`, cuyo `message_text` estaba vacío para no repetir el resumen;
  por eso envió las `21` imágenes y TikTok, pero no el encabezado. La confirmación
  del operador corrigió ese registro de `sent` a `uncertain`. `retry-6` se creó
  desde el trabajo original y envió el texto exacto **Resumen de cupos únicos
  hoy 12 de agosto de 2026**, seguido de seis paquetes
  `4 + 4 + 4 + 4 + 4 + 1` y la publicación. Las capturas muestran el resumen y
  TikTok como burbujas nuevas con doble check azul. La inspección DOM confirmó
  que el estado `Leído` sí se reconocía; el falso `uncertain` ocurría porque
  WhatsApp renderiza los `17` emojis del texto como imágenes y `text_content()`
  los omitía. La verificación posterior al clic ya no vuelve a comparar los
  `749` caracteres: el contenido completo se valida en el compositor antes de
  enviar y luego solo se exige compositor vacío más una burbuja saliente nueva
  con estado enviado, entregado o leído. Se conserva la espera `30 + 3` y
  `uncertain` sin reintento si falta cualquiera de esas señales. `retry-6` se
  reconcilió a `sent` por evidencia, sin otro reenvío.
- Corregido el `2026-08-07`: el álbum automático posterior a una reserva ya no
  considera suficiente que desaparezca la vista previa. Espera hasta `60`
  segundos por las dos imágenes salientes confirmadas por WhatsApp; si no
  aparecen, conserva una captura propia del mensaje, termina `uncertain` y no
  se reintenta. El ajuste responde a un caso real que figuró `sent` aunque el
  cliente no recibió el primer álbum y necesitó un envío manual.
- Implementado el `2026-08-07`: cada alta, corrección de credenciales o
  revalidación manual abre un ciclo de preflight con un solo envío del
  formulario. Los resultados `validated`, `no_pending_request` e
  `invalid_credentials` encolan un aviso de registro idempotente al WhatsApp
  del contacto. Los errores técnicos, timeouts y monitoreos posteriores no
  generan mensajes al cliente.
- Los avisos de registro comparten el emisor durable de Admin API y exigen una
  nueva burbuja saliente confirmada. El dashboard expone tipo, ciclo y estado;
  `uncertain` es terminal y nunca produce un reintento automático. Un preflight
  que quedó `running` al reiniciar pasa a fallo técnico y requiere revalidación
  manual, evitando un segundo intento de acceso dentro del mismo ciclo.
- Corregido el `2026-08-25`: una burbuja de texto con reloj `msg-time` podía
  coincidir a la vez con una etiqueta accesible genérica y cerrar como falso
  `sent`. La primera guarda retiró esas coincidencias amplias, pero el siguiente
  aviso real reveló el caso inverso: WhatsApp mostró el texto completo con doble
  check y el detector lo dejó `uncertain` porque contaba marcadores ocultos y ya
  no aceptaba el estado accesible exacto. La confirmación ahora considera solo
  iconos visibles, mantiene un reloj visible como veto y admite exclusivamente
  las etiquetas completas `Enviado`, `Entregado` o `Leído` y sus equivalentes
  en inglés; textos genéricos como `Enviado correctamente` no confirman nada.
  El contexto permanece abierto si vence la espera y nunca se reintenta un
  posible envío. Una reproducción DOM aislada cubrió reloj visible, reloj
  oculto con entrega exacta, check estructural, lectura exacta y reloj más
  check. El caso real de las `15:14` no fue reenviado ni conciliado durante la
  corrección.
- Corregido el `2026-08-08`: un diálogo de WhatsApp bloqueó el primer aviso
  real dirigido por `@usuario` antes de abrir el chat. La ruta ahora guarda
  captura única, cierra solamente controles seguros, vuelve a resolver el mismo
  resultado único y permite un solo segundo clic antes de escribir. Si no puede
  abrirlo, informa fase `chat_not_opened`; nunca usa clic forzado ni reintenta
  después de una acción de envío. El dashboard expone el error operativo
  resumido y conserva la traza completa en la base y logs.
- Después de las imágenes, el mismo trabajo diario enviará una publicación para
  TikTok lista para copiar. Se genera sin IA ni tokens mediante 138,240
  combinaciones deterministas; precio, pago, WhatsApp y advertencias permanecen

- Corregido el `2026-08-25`: la confirmación incierta de los PDF ya no corta el
  texto de pago confirmado cuando el único clic de documentos cerró la vista
  previa y WhatsApp devolvió el compositor normal. En ese caso el flujo envía
  el texto como una acción distinta, conserva los PDF como `uncertain` y nunca
  repite su clic. El resultado y la alerta Telegram detallan por separado
  `documents` y `payment_confirmation`, guardan una captura final y solo marcan
  el paquete completo como `sent` si ambos componentes quedan confirmados. El
  cambio responde a tres postpagos reales cuyos PDF aparecieron enviados pero
  cuya comprobación automática devolvió `0/3`; el operador informó que tuvo que
  completar manualmente el texto en algunos casos. No se reenviaron ni se
  conciliaron automáticamente esos trabajos históricos.

### Destinatarios de WhatsApp por usuario

- Desde el `2026-08-07`, cada contacto puede guardar un numero y un nombre de
  usuario de WhatsApp. Si existen ambos, todos los envios usan el numero; el
  `@usuario` solo actua como alternativa cuando falta el numero.
- La busqueda por usuario exige un unico resultado dentro de la seccion
  `Chats`. Conserva el nombre que WhatsApp muestra en esa fila y confirma el
  mismo valor en el encabezado antes de escribir texto o adjuntar archivos. De
  esta forma funciona tanto con alias visibles como con contactos guardados
  bajo un nombre local; un resultado ausente, ambiguo o distinto falla sin
  enviar y no se reintenta automaticamente.
- La capacidad cubre avisos de validacion inicial, evidencia y cobro de reserva,
  seguimiento postpago y preparaciones manuales. El resumen diario conserva su
  destinatario telefonico configurado.
- Dashboard, Admin API y `/cliente_nuevo` aceptan `@usuario`; el esquema v45
  conserva ambos identificadores sin interpretar los digitos de un alias como
  telefono.
  fijos, y PostgreSQL conserva el texto exacto antes de enviarlo. La prueba real
  confirmó el texto completo con doble check azul después de normalizar la
  representación interna de emojis del compositor y la burbuja saliente. La
  confirmación también tolera la virtualización del historial sin confundir una
  nueva burbuja con otra publicación idéntica anterior.
- Precio comercial vigente alineado a `S/50 por trámite` en publicaciones,
  seguimiento y órdenes registradas desde el `2026-08-02`. PostgreSQL v42
  fijó `S/40` en las `99` órdenes preexistentes y dejó `S/50` como precio por
  defecto para nuevas altas; los dos pagos pendientes conservaron `S/40`.
- Las capturas originales de `cupos-unicos` quedaron aprobadas como fuente de
  la futura sección pública `Cupos encontrados recientemente`. La integración
  con Cloudinary y la selección máxima de tres imágenes están documentadas,
  pero todavía no se implementaron ni se subieron recursos externos.
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
- Corregido y validado el `2026-08-21`: la primera guarda contra un segundo clic
  trató la presencia del compositor como prueba de que la vista previa había
  cerrado, pero WhatsApp también muestra ese compositor debajo de la vista previa
  de documentos. El flujo reconoce ahora los controles visibles de la vista
  previa, realiza un solo clic y nunca repite el envío; la confirmación exige el
  compositor y todas las burbujas salientes nuevas. El reenvío autorizado de
  `order-72687222` confirmó en tráfico real `3/3` PDF y el texto completo para
  `@AlvaFigueroa`; PostgreSQL guardó el nuevo mensaje `sent` y el intento técnico
  original quedó `uncertain / completed_missing` con nota y auditoría. Pasaron
  `compileall`, Ruff, `59` pruebas y `git diff --check` sobre los archivos del
  cambio.
- La bandeja cruza evidencia `sent` y trabajos automáticos durables antes de
  pedir intervención. Dejó fuera `54` seguimientos históricos sin trabajo
  automático y reconoció como resueltos `2` fallos con envío posterior. Los
  `2` pagos actuales permanecen accionables.
- La clasificación es derivada y no destructiva: no se borraron mensajes, no se
  alteraron pagos y no se envió WhatsApp retroactivo.
- Reconciliado el `2026-08-08`: el operador confirmó que el resumen del 7 de
  agosto llegó correctamente y la captura posterior muestra la publicación
  completa con doble check azul. El falso `uncertain` ocurría porque la
  confirmación dejaba de revisar selectores alternativos al encontrar una
  estructura anterior sin coincidencia. Ahora acumula firmas de todas las
  estructuras soportadas y usa evidencias únicas por trabajo. Solo
  `daily_slot_summary:2026-08-07` pasó a `sent`; no hubo reenvío ni se alteraron
  los días anteriores.
- Corregido el `2026-08-09`: el resumen dominical sin imágenes confirmó el
  texto de cierre, pero clasificó el trabajo completo como `uncertain` cuando
  no reconoció automáticamente la nueva burbuja de la publicación de TikTok.
  La captura durable y la confirmación del operador muestran ambos textos con
  doble check azul. `daily_slot_summary:2026-08-09` se reconcilió a `sent` con
  `attempt_count=1`, sin reenvío. El detector acepta ahora la marca de
  enviado/entregado/leído del contenedor genérico y Telegram informa por
  separado resumen, imágenes y publicación. Una ambigüedad real sigue siendo
  terminal y nunca genera reintento automático.
- El corte de PostgreSQL del `2026-08-09` conserva `71` trabajos automáticos:
  `52 sent`, `3 failed` y `16 uncertain`; no existe un trabajo activo en ese
  corte. Es un inventario durable, no una tasa de entrega actual: incluye
  ambigüedades históricas de resúmenes diarios y no autoriza reintentos. Por
  tipo hay `21/2/2` álbumes de reserva `sent/failed/uncertain`, `22/1/2`
  postpagos, `4/0/11` resúmenes diarios y `3/0/1` avisos de registro.
- Implementado el `2026-08-07`: una reserva impaga puede cerrarse como
  `uncollectible` sin fingir un pago ni borrar la deuda histórica. La orden se
  archiva, conserva `charge_required=true` y su pago pasa a `written_off`, por
  lo que deja de inflar la cobranza accionable y los saldos pendientes.
- Los pagos `pending` admiten un `amount_paid` parcial. El resumen mensual y la
  lista de cobros muestran el saldo `amount_agreed - amount_paid`, mientras los
  ingresos realizados siguen contando exclusivamente pagos con estado `paid`.
- Endurecido el `2026-08-23`: Admin API separa el abono acumulado
  `payment/partial` del cierre `payment/paid`. Un abono permanece `pending` y no
  encola postpago; el cierre exige cubrir lo acordado salvo diferencia inferior
  explicitamente autorizada y motivada. Ambos caminos bloquean la orden y el
  pago durante la escritura, admiten una fotografia esperada para rechazar
  cambios concurrentes con `409`, y guardan la auditoria del actor en la misma
  transaccion financiera.

## Rendimiento observado

| Periodo       | Runs conservados | Intentos | `registered` | `slot_lost` | Errores/defensas |
| ------------- | ---------------: | -------: | -----------: | ----------: | ----------------: |
| 13-19 julio   |            5,356 |       61 |           28 |  29 (47.5%) |                14 |
| 20-25 julio   |            4,662 |       43 |           20 |  17 (39.5%) |                 3 |
| 1-8 agosto    |            5,299 |       78 |           20 |  57 (73.1%) |        2 defensas |

El corte del 1 al 8 de agosto aumentó el volumen, pero no la efectividad:
`20/78` intentos compatibles terminaron `registered` (`25.6%`) y `57/78`
terminaron `slot_lost`. No se debe presentar el mayor número absoluto de
reservas como una mejora del motor. Las dos señales de defensa requieren
correlación individual antes de atribuirlas al ciclo de observación.

En seis tandas compartidas hubo seis intentos posteriores al primero y solo uno
terminó `registered`, un proxy de supervivencia secuencial de `16.7%`. La
muestra confirma que existe una oportunidad para reducir el tiempo entre
clientes, pero todavía es demasiado pequeña para demostrar que la concurrencia
producirá más reservas netas.

La tabla `runs` conserva actualmente información desde el 27 de julio por la
retención de `14` días. Para
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
7. El CAPTCHA local todavía no tiene evidencia suficiente para retirar a
   2Captcha.
   El muestreo opcional de reservas reales aumenta los datos disponibles, pero
   también retrasa el submit unos `0.4 s` por muestra adicional y puede elevar
   el riesgo de perder el cupo.
   El corte prospectivo de v3 cerró como evidencia insuficiente y produjo la
   arquitectura v6. V6 alcanzó `487/490` (`99.39%`) en regresión protegida, pero
   ese resultado retrospectivo no autoriza producción. Debe superar más de 99%
   sobre al menos 500 CAPTCHA frescos posteriores a su congelación. Con `475`
   muestras se habilitó únicamente un canario V6 de `20` decisiones, con breaker
   en el primer rechazo/ambigüedad y fallback inmediato a 2Captcha.
8. La evidencia versionada está sanitizada, pero sigue siendo telemetría
   operacional y debe revisarse antes de compartir.
9. Kaspersky puede clasificar lanzadores ocultos y persistentes como amenaza.
   El reemplazo PowerShell reduce esa superficie, pero debe vigilarse el
   historial del antivirus después de reinicios y actualizaciones de firmas.
10. La cadena dirigida por oportunidades conserva su fallback secuencial de
    hasta diez candidatos y cinco minutos. `OBS-006` está implementada como
    ráfaga activa al próximo arranque: máximo dos sesiones, sin límite fijo de
    clientes compatibles y 300 segundos de admisión. La simulación aislada
    confirmó seis reemplazos auxiliares, agotamiento de cola, cierre sin cupos,
    expiración y rollback por bandera. El reinicio controlado posterior quedó
    `applied` y cargó la configuración; todavía falta validación real. El riesgo
    vigente es demostrar que añade reservas sin
    aumentar defensas, `reservation_unconfirmed`, pérdida de claims, memoria o
    errores operativos. Ante cualquiera de esas señales debe aplicarse
    `OPPORTUNITY_BURST_ENABLED=false` y continuar con el flujo secuencial.
11. La reobservación posterior a `slot_lost` reutiliza una sesión que ya envió
    una reserva y añade como máximo otro submit confirmado por una nueva
    disponibilidad. Su riesgo vigente es sumar carga durante una tanda; debe
    medirse recuperación, duración, CAPTCHA, defensas y cierre de intentos. Un
    `reservation_unconfirmed` nunca entra en esta ruta.
12. La telemetría durable de OBS-006/OBS-007 ya permite reconstruir el canario
    desde PostgreSQL, pero todavía no existe la muestra productiva mínima de
    `10` ráfagas y `30` auxiliares. No debe decidirse continuidad o escalamiento
    antes de completar y comparar ese corte.
13. El Resumen v1 todavía mezcla eventos, cohortes y atención actual, por lo que
    se conserva solo como rollback. El dashboard comercial usa el contrato v2;
    queda pendiente completar la conciliación histórica de costos y fuentes
    antes de habilitar margen porcentual, costos unitarios, CAC o ROAS.
14. No existe todavía un backup cifrado durable fuera de la PC ni monitoreo que
    sobreviva a la caída completa del equipo operativo.

## Validación del corte

- Canario de ruta crítica del `2026-08-11`: espera event-driven y lectura DOM
  atómica incorporadas con fallback automático, kill switches separados y
  telemetría durable. Procedimiento y rollback:
  [`operations/reservation-critical-path-canary-2026-08-11.md`](operations/reservation-critical-path-canary-2026-08-11.md).
- Optimización de alerta urgente del `2026-08-11`: la notificación inmediata
  pasó de `urlopen` síncrono a un outbox PostgreSQL `v55` y dispatcher propio.
  El payload durable excluye nombre, cuenta e identificadores del cliente; se
  conservan sede, fecha, hora y cupos. Observador general y órdenes activas usan
  el mismo formato breve, sin etiqueta de origen ni instrucciones extra. El muestreo CAPTCHA
  no fue modificado: continúa bajo el control manual existente, incluidos los
  tiempos adicionales cuando el operador lo activa. No se envió un Telegram
  de prueba.
- Mantenimiento integral del `2026-08-11`: se corrigió la transición de
  reinicio y la auditoría de controles, se retiraron tres miembros internos
  sin consumidores, se alinearon README y runbook con `15/1-2/8`, OBS-006 y la
  autoridad canaria V6, y n8n quedó limitado a `127.0.0.1:5678` conservando su
  volumen y el workflow activo. Angular se actualizó de `20.3.26` a `20.3.27`
  y `npm audit --omit=dev` quedó en cero vulnerabilidades. No se cambiaron
  intervalos, concurrencia, `.env`, reglas de reserva ni autoridad CAPTCHA.
- Fase 2 técnica del `2026-08-10`: PostgreSQL migró aditivamente de `v51` a
  `v54`; una creación limpia del esquema y `_validate_current_schema` pasaron
  dentro de una transacción revertida sin dejar schemas temporales. Los cinco
  endpoints de lectura v1/v2/finanzas respondieron `200` después de reiniciar
  únicamente Admin API con cero trabajos WhatsApp activos. Dos POST inválidos
  comprobaron el enrutado de cierre y reconciliación con `400` sin escribir
  datos. `compileall`, Ruff, `59 passed`, build Angular de `527.23 kB` sin
  warnings y `git diff --check` quedaron correctos.
- Ajuste de interfaz del `2026-08-10`: la semántica y controles de Fase 2 se
  conservaron, pero el Resumen volvió a una lectura operativa breve con cuatro
  cifras, gráfico de cobros diarios y cobros pendientes. Cohortes, fuentes,
  comparaciones ampliadas, calidad financiera y cierre mensual quedan plegados
  por defecto para evitar aglomeración visual.
- Simplificación adicional del `2026-08-10`: la vista normal ya no muestra
  cohortes ni vocabulario de auditoría. CAPTCHA, ráfagas, soporte, movimientos y
  revisión financiera aparecen como bloques cerrados que el operador abre solo
  cuando necesita cambiar o corregir algo.
- La revisión de Fase 2 confirmó `119` órdenes, `112` órdenes con reserva,
  `105` pagos y `S/4,355` cobrados acumulados. Agosto MTD separa `S/1,130` de
  eventos cobrados frente a `S/930` atribuibles a la cohorte creada en agosto.
  El único pago `paid != agreed` conserva diferencia `-S/10` sin causa y no fue
  modificado. No existe evidencia reconciliada suficiente para mostrar costo
  CAPTCHA por reserva, margen porcentual, CAC o ROAS.
- La inspección visual automatizada no pudo ejecutarse porque el navegador
  integrado no expuso ninguna instancia. El build, bundle servido y contratos
  HTTP están validados, pero no se afirma aprobación visual humana.

- Fase 1 técnica del `2026-08-10`: migración PostgreSQL `v49 -> v50` aplicada
  sin borrar datos; verificadas las cinco tablas nuevas y el control inicial
  `inherit/inherit`, revisión `0`, breaker cerrado. Las lecturas directas del
  contrato devolvieron HTTP lógico `200`, estado efectivo habilitado por las
  banderas vigentes y cero ráfagas históricas inventadas.
- Tres recorridos transaccionales con `ROLLBACK` validaron sobre PostgreSQL real
  la cabecera, candidato, detector, auxiliar, evento OBS-007, cierre y detalle;
  también comprobaron `draining -> breaker open -> reset -> disabled` sin
  marcar el drenaje aplicado antes de cerrar, el enlace anterior/siguiente y
  los timestamps de CAPTCHA, submit y confirmación. Todos dejaron cero filas de
  prueba y el control productivo siguió `inherit/inherit`, revisión `0`.
- Validación del mismo cambio: `python -m compileall -q src`, Ruff,
  `python -m pytest -q` con `59 passed`, build Angular con bundle inicial de
  `519.99 kB` y `git diff --check` correctos. No se abrió el portal, no se llamó
  a 2Captcha, no se envió Telegram/WhatsApp y no se creó una reserva.
- Admin API y el receptor Telegram se reiniciaron aisladamente después de
  comprobar cero submissions y trabajos WhatsApp activos. El endpoint nuevo
  respondió a través del proxy Angular con revisión `0`, breaker cerrado y
  ambos modos efectivos habilitados. El navegador integrado no estuvo
  disponible, por lo que no se afirma aprobación visual: el panel quedó
  validado por contrato y build.

- Revisión operativa del `2026-08-09`: Admin API `8766` y CAPTCHA sombra
  `8787` saludables; PostgreSQL saludable en Docker. El puerto `8765` no
  respondió durante el domingo y Admin API informó correctamente `api_only`.
- Reporte operacional actualizado para `2026-08-01` a `2026-08-08`: `5,299`
  runs, `78` intentos compatibles, `20 registered`, `57 slot_lost`, una etapa
  `Programado/completed` informada por separado y dos señales de defensa.
- Observación de optimización del mismo rango generada sin promoverla como nueva
  línea base y sin cambiar clics, esperas, CAPTCHA, orden ni concurrencia.
- Ráfaga `OBS-006`: la validación aislada confirmó detector más seis auxiliares
  registrados, máximo concurrente de dos, agotamiento de la cola compatible,
  cierre sin reservas nuevas, expiración y rollback desactivado sin consulta de
  candidatos. También corrigió dos carreras reproducibles con tareas
  instantáneas. No se considera validada en portal hasta observar un cupo real.
- Reobservación `OBS-007`: `compileall`, Ruff y las `59` pruebas existentes
  quedaron correctos. Una simulación aislada recorrió cuatro lecturas, utilizó
  exactamente un reload, encontró otro horario y terminó `registered`,
  conservando el `slot_lost` previo. Otra confirmó IDs durables distintos con
  el primero `rejected` y el segundo `confirmed`. No abrieron el portal, no
  llamaron a 2Captcha y no sustituyen la validación real.
- Reinicio controlado final de `OBS-007`: el worker estaba en `outside_hot_window`,
  sin orden activa; el comando persistido terminó `applied` y regresó saludable
  con `worker_running=true`, `current_order_id=null`. No se modificó `.env`.
- Reinicio controlado de `OBS-006`: se solicitó solo con fase
  `outside_hot_window` y `current_order_id=null`; el comando terminó `applied`
  y el worker regresó saludable a la misma fase sin orden activa.
- `python -m ruff check src tests`: correcto.
- `python -m compileall -q src`: correcto.
- `npm run build`: correcto, bundle inicial de `529.99 kB` y sin advertencias.
- `python -m pytest -q`: `59 passed`.
- Recordatorios de cita del `2026-08-17`: creacion limpia `v56`, migracion
  transaccional `v55 -> v56` y migracion viva correctas; `125` reservas
  normalizadas y cero confirmadas sin fecha interpretable. Una simulacion
  transaccional creo `8/8` trabajos una sola vez, creo `0/8` al repetir, expuso
  cero recordatorios antes del resumen, priorizo el resumen activo y libero los
  ocho solo despues de volverlo terminal. El rollback dejo cero trabajos de
  recordatorio reales. Admin API se reinicio aisladamente con cero sesiones,
  submissions o trabajos WhatsApp activos; el endpoint nuevo respondio con el
  modo desactivado/dry-run, `8` elegibles, cero contactos faltantes, cero fechas
  invalidas y cero trabajos persistidos. El worker permanecio saludable.
- Auditoría documental integral: `40` archivos clasificados, roadmap
  reorganizado por fases, índices actualizados y cero enlaces Markdown locales
  rotos en el inventario revisado.
- Evidencia versionada: el árbol actual fue saneado para retirar nombres,
  `order_id` completos y respuestas CAPTCHA de las bitácoras históricas. Los
  commits anteriores aún pueden contener esos valores; reescribir el historial
  Git requiere una operación separada y autorizada.
- Dependencias Angular: las seis alertas altas del corte `20.3.26` quedaron
  cerradas con Angular `20.3.27`; la auditoría productiva devuelve cero. La
  auditoría completa conserva tres alertas moderadas exclusivas de desarrollo
  en la cadena CLI/MCP/Hono; npm solo propone Angular CLI 21, por lo que no se
  aplicó ese salto mayor dentro de este mantenimiento compatible.
- Dashboard no bloqueante: el build Angular quedó correcto con bundle inicial
  de `504.46 kB`; no quedan llamadas `await this.showToast(...)` y el cierre
  manual se controla por `session_id`. La validación fue de código y build: no
  se cerraron sesiones reales ni se enviaron mensajes, y el navegador integrado
  no estuvo disponible para una repetición visual.
- UX de Post-cita y fechas de Órdenes: build Angular correcto con bundle
  inicial de `513.45 kB`; el parser cronológico se ejecutó sobre la respuesta
  real de Admin API y ordenó `108` citas de julio a agosto correctamente. La
  ventana de navegador integrada continuó no disponible, por lo que queda
  pendiente una aprobación visual de escritorio y móvil; no se sustituyó por
  una afirmación basada solo en build.
- Archivo de accesos perdidos: la consulta directa y el endpoint autenticado
  activo coincidieron en `108` históricos, `92` seguimientos visibles por
  defecto, `10` casos accionables y `16` accesos archivados. Antes del reinicio
  aislado se comprobaron cero trabajos WhatsApp `running`; Admin API regresó
  saludable en `8766`, `/post-cita` respondió `200` y el worker continuó en
  modo `api_only`. `compileall`, Ruff, `59 passed`, build Angular y
  `git diff --check` quedaron correctos.
- Proyecto `test-captcha`: `compileall`, Ruff y `28 passed`; servicio reiniciado
  de forma aislada y saludable en CUDA con v3 y v6.
- Destinatario por usuario: esquema v45 aplicado; resolucion local comprobo
  usuario solo, prioridad del numero y rechazo de alias como telefono. La prueba
  de solo lectura abrio dos veces `@diego.durand` con el alias visible y dos
  veces `@CARBENBOPA` presentado como el contacto guardado `CARLOS BORASINO`.
  En los cuatro casos confirmo la misma fila en el encabezado y no escribio ni
  envio mensajes.
- Retiro de invitaciones: dashboard activo, ruta anterior responde `404`,
  Telegram valida correctamente y PostgreSQL quedó en esquema v43 sin la tabla
  `hosted_registration_contacts`.
- Admin API, PostgreSQL y CAPTCHA sombra: saludables. Desde el `2026-08-09`,
  CAPTCHA sombra carga únicamente `v3_selected` y `v6_sequence_candidate` en
  CUDA para eventos nuevos, con v3 como referencia visual; `/health` y
  `/v1/models` confirmaron ambos después del reinicio aislado y el historial de
  los modelos retirados continúa consultable.
- El corte prospectivo V6 alcanzó `474/475` (`99.79%`) contra revisión humana;
  v3 obtuvo `460/475`. El servicio residente sigue saludable en CUDA y el
  control productivo V6 inició en `0/20`, con circuito cerrado y 2Captcha como
  fallback.
- PostgreSQL v46 aplicado: una deuda histórica vencida y sin destinatario quedó
  archivada como `uncollectible/written_off`; otro pago conserva `S/20`
  abonados sobre `S/40`. El resumen mensual devuelve `2` cobros accionables por
  `S/70`: saldos de `S/20` y `S/50`. No se encoló ni envió WhatsApp durante el
  ajuste.
- PostgreSQL v47 aplicado: el control CAPTCHA quedó desactivado, conserva total
  `10` y reporta total efectivo `1`. Admin API leyó y guardó ese mismo estado,
  el dashboard compilado contiene el control y el worker continúa detenido; no
  se abrió el portal, no se llamó a 2Captcha y no se creó ninguna reserva.
- PostgreSQL v48-v49 y seguimiento post-cita: migraciones aditivas aplicadas, Admin API
  reiniciada de forma aislada con cero trabajos WhatsApp `running` y salud
  `ok/api_only`. La ruta `/post-cita` y el endpoint interno listaron las `108`
  reservas confirmadas; `52` requieren primera revisión por fecha pasada. La
  consulta controlada inicial terminó con acceso correcto, `6` etapas, `1`
  observación y `observation_no_progress`.
  El barrido inicial posterior cubrió `108/108` órdenes. Los últimos registros
  conservan `92` accesos correctos y `16` credenciales rechazadas. El segundo
  barrido dirigido almacenó los textos de las `6` observaciones. Un caso quedó
  corregido a `completed` al abrir `*****/******`; sus seis etapas figuran
  `Atendido`. Otro padre sin reserva quedó archivado como contenedor y sus dos
  subtrámites confirmados permanecen separados con identidad enmascarada, ambos
  con `access_lost` por credenciales cambiadas.
- WhatsApp del `2026-08-08`: `compileall`, Ruff, dashboard y `59` pruebas
  correctos. Admin API fue recuperada por su supervisor y sirve el bundle
  `main-IPC33IQD.js`; PostgreSQL conserva el resumen del 7 de agosto como
  `sent`. No se realizó ningún envío de prueba.
- Confirmación diaria del `2026-08-09`: la simulación aislada reconoció un
  contenedor con doble check y produjo el detalle Telegram por componentes.
  `compileall`, Ruff, `59 passed` y `git diff --check` quedaron correctos. Admin
  API se reinició aisladamente con cero trabajos WhatsApp `running` y volvió
  saludable en `8766`; no se reinició el worker ni se envió contenido durante
  la validación o reconciliación.
- Telegram del `2026-08-08`: el notificador diferido ya no publica evidencia
  CAPTCHA de cupos incompatibles; la validación fue local y no realizó envíos
  de prueba. Falta observar el próximo caso real bloqueado para confirmar la
  ausencia de ruido en el chat operativo.

## Cadencia de revisión vigente

- **Cada domingo:** generar el reporte de la semana operativa cerrada, usando un
  rango explícito comparable y sin notificación externa salvo autorización.
- **Cada dos o tres días después de cambiar el observer:** revisar lecturas por
  hora, duración de sesiones, `slot_lost`, CAPTCHA, `403`, `429`, defensas y
  `recovery_backoff`; no cambiar otra variable durante ese corte.
- **En el siguiente caso real relevante:** validar modal CSS, ráfaga dirigida
  por oportunidades, reobservación posterior a `slot_lost` y sus rollbacks,
  backoff por reglas, CAPTCHA rechazado y entregas de WhatsApp según el tipo de
  evento observado.
- **Si se reactiva el canario V6:** continuar desde los contadores preservados,
  revisar fuente, confianza, resultado del portal y breaker después de cada
  reserva, y no resetear el circuito sin explicar su causa. Cada 100 CAPTCHA
  frescos se mantiene el corte V6 contra v3 sin reentrenar.
- **El primer día hábil de cada mes:** actualizar resultado comercial, cobros
  pendientes y dependencia de intervención humana.
- **Después del próximo reinicio de Windows:** comprobar tarea programada,
  supervisor raíz, Docker, Admin API, worker, Telegram, CAPTCHA y perfiles de
  navegador.

## Regla de mantenimiento

Después de cada cambio relevante:

1. actualizar este archivo si cambió el estado, una capacidad, un riesgo, una
   métrica o una validación;
2. actualizar [`roadmap/README.md`](roadmap/README.md) si una tarea avanzó,
   terminó, se bloqueó o cambió de prioridad;
3. mover el detalle largo a `operations/`, `contracts/`, `history/` o un
   documento de incidente;
4. no convertir reportes generados ni bitácoras en listas paralelas de tareas.
