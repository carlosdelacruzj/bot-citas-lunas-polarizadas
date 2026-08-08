# Estado maestro del proyecto

Última revisión integral: `2026-08-08`.

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
| Telegram remoto       | Operativo                | Alta manual, clientes, cuatro reglas de fecha y control del worker.                                       |
| CAPTCHA sombra        | Operativo                | Servicio CUDA en `127.0.0.1:8787`; solo observa, 2Captcha conserva autoridad.                             |
| WhatsApp automático   | Operativo con vigilancia | Emisor único en Admin API, cola durable y sin reintentos automáticos ambiguos.                            |
| Dashboard             | Operativo                | Build Angular correcto; bundle inicial de `499.64 kB`.                                                    |
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
- Corregido el `2026-08-01`: la actualización automática del dashboard conserva
  la vista en su posición. El indicador de refresco vive dentro del encabezado
  y ya no inserta ni retira una franja que desplazaba el contenido en cada
  consulta periódica.
- Resumen mensual, finanzas, bandeja de pendientes y edición segura de
  credenciales.
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

### Control remoto

- Menú de Telegram con clientes, alta manual, búsqueda, resumen y estado.
- Alta manual y edición guiada de cuatro restricciones de fecha y prioridad;
  consultar credenciales existentes dejó de ser una acción visible.
- Pausa, reanudación y reinicio mediante Admin API y comandos persistidos.
- Expiración de conversaciones, botones obsoletos rechazados y un solo flujo
  guiado por chat.
- Simplificado el `2026-08-01`: se retiró por completo el etiquetado manual de
  CAPTCHA desde Telegram, junto con sus variables y scripts exclusivos. El menú
  dejó de mostrar recientes y credenciales, agrupó sistema con errores y la
  búsqueda ahora solicita el término como una conversación guiada.
- `/cliente_nuevo` crea una orden de forma manual. Solicita tipo y número de documento,
  contraseña, contacto, fuente, WhatsApp opcional y permite omitir o configurar
  las cuatro restricciones de fecha. Por decisión del único operador autorizado, la
  confirmación y el comprobante posterior muestran todos los datos, incluida la
  contraseña, para poder detectar errores; el alta también informa el resultado
  real del preflight cuando termina dentro de la espera.

### Evidencia y CAPTCHA

- Evidencia organizada por fecha y resumen compacto.
- Corregido el `2026-08-02`: las bitácoras Markdown ya no escriben nombres de
  clientes, `order_id` completos ni respuestas CAPTCHA. Las entradas nuevas del
  1 de agosto se sanitizaron antes de versionarlas.
- CAPTCHA original utilizado para el solver.
- Servicio local en modo sombra, cola durable y revisión humana desde el
  dashboard.
- El modelo local no participa en la decisión de reserva; 2Captcha sigue siendo
  la respuesta enviada al portal.
- Implementado el `2026-08-01`: el flujo real admite muestreo CAPTCHA opcional
  mediante `RESERVATION_CAPTCHA_SAMPLE_LIMIT`. El valor `1` conserva el
  comportamiento anterior; un valor mayor guarda y refresca las muestras
  previas y envía únicamente la última a 2Captcha. Las imágenes adicionales
  quedan registradas en sombra como datos de entrenamiento y nunca se envían
  al portal.
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
- Terminado el experimento, el `.env` productivo volvió a
  `RESERVATION_CAPTCHA_SAMPLE_LIMIT=1`: cada intento conserva el CAPTCHA que
  realmente usa, pero ya no añade los `3.6 s` observados por las nueve muestras
  extra antes de competir por el cupo.
- Corregido el mismo día: la ruta de evidencia bloqueada ahora conserva
  `run_id` y `order_id`, y registra tanto las nueve muestras previas como la
  final en CAPTCHA sombra. Los 20 originales ya capturados fueron recuperados
  y quedaron pendientes de revisión humana, cada uno con tres predicciones.
- Integrado el `2026-08-02`: el candidato `v3_finetuned_from_v2` quedó como
  `v3_selected` en el servicio sombra. Es el mejor resultado global hasta ahora:
  frente a `v2_selected` subió de `90/98` a `93/98` en la misma prueba temporal disponible,
  de `143/150` a `147/150` en el holdout humano y de `76/78` a `77/78` en el
  corte sombra independiente. El servicio carga cuatro modelos y el dashboard
  identifica a v3 como seleccionado, pero 2Captcha conserva toda la autoridad
  operativa.
- Las 78 imágenes del corte sombra excluido del entrenamiento se reprocesaron
  con v3 para mostrarlas en Calidad. Las 157 imágenes usadas para entrenarlo no
  se reprocesaron, evitando presentar exactitud de entrenamiento como evidencia
  independiente. Los CAPTCHA nuevos sí ejecutan los cuatro modelos.
- Auditado el `2026-08-07`: el primer corte prospectivo posterior a v3 contiene
  `126` CAPTCHA recibidos entre el 3 y el 5 de agosto, todos revisados
  manualmente. `v3_selected` obtuvo `119/126` (`94.44%`), empatado con
  `v2_selected`; `v2_scratch` obtuvo `120/126` (`95.24%`) y `v1_real`
  `118/126` (`93.65%`). v2 seleccionado y v3 discreparon solo en dos casos:
  cada uno resolvió correctamente uno, mientras ambos fallaron juntos en seis.
- Los cuatro modelos coincidieron correctamente en las `15/15` referencias
  confirmadas por el portal dentro de ese corte, una muestra insuficiente para
  diferenciarlos. El resultado prospectivo no confirma la ventaja histórica de
  v3 y mantiene a 2Captcha como única autoridad operativa.

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
- Implementado el `2026-08-07`: una reserva impaga puede cerrarse como
  `uncollectible` sin fingir un pago ni borrar la deuda histórica. La orden se
  archiva, conserva `charge_required=true` y su pago pasa a `written_off`, por
  lo que deja de inflar la cobranza accionable y los saldos pendientes.
- Los pagos `pending` admiten un `amount_paid` parcial. El resumen mensual y la
  lista de cobros muestran el saldo `amount_agreed - amount_paid`, mientras los
  ingresos realizados siguen contando exclusivamente pagos con estado `paid`.

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
   El muestreo opcional de reservas reales aumenta los datos disponibles, pero
   también retrasa el submit unos `0.4 s` por muestra adicional y puede elevar
   el riesgo de perder el cupo.
   v3 mejora a `v2_selected` en los holdouts históricos comparables, pero en el
   primer lote prospectivo quedó en `119/126` (`94.44%`): empató con
   `v2_selected` y quedó un acierto detrás de `v2_scratch`. Con siete errores ya
   acumulados, aunque acertara las muestras restantes terminaría en `493/500`
   (`98.6%`), por debajo del requisito de más de 99%. Se necesitan más datos para
   analizar errores y entrenar una nueva candidata, cuyo corte prospectivo debe
   comenzar nuevamente después de su entrenamiento.
8. La evidencia versionada está sanitizada, pero sigue siendo telemetría
   operacional y debe revisarse antes de compartir.
9. Kaspersky puede clasificar lanzadores ocultos y persistentes como amenaza.
   El reemplazo PowerShell reduce esa superficie, pero debe vigilarse el
   historial del antivirus después de reinicios y actualizaciones de firmas.
10. La cadena dirigida por oportunidades ya funciona de forma secuencial,
    con sesiones aisladas, sin pausa artificial, hasta diez candidatos y cinco
    minutos. Conserva combinaciones y telemetría de duración, pero falta
    validarla ante el próximo caso real y medir cuántos milisegundos transcurren
    hasta cada submit. La ráfaga concurrente `OBS-006` sigue siendo solo una
    mejora futura: antes de activarla debe aislar claims, heartbeats e intentos,
    definir guardas globales y demostrar que añade reservas sin aumentar
    defensas, resultados inciertos ni errores operativos.

## Validación del corte

- `python -m ruff check src tests`: correcto.
- `python -m compileall -q src`: correcto.
- `npm run build`: correcto.
- `python -m pytest -q`: `59 passed`.
- Destinatario por usuario: esquema v45 aplicado; resolucion local comprobo
  usuario solo, prioridad del numero y rechazo de alias como telefono. La prueba
  de solo lectura abrio dos veces `@diego.durand` con el alias visible y dos
  veces `@CARBENBOPA` presentado como el contacto guardado `CARLOS BORASINO`.
  En los cuatro casos confirmo la misma fila en el encabezado y no escribio ni
  envio mensajes.
- Retiro de invitaciones: dashboard activo, ruta anterior responde `404`,
  Telegram valida correctamente y PostgreSQL quedó en esquema v43 sin la tabla
  `hosted_registration_contacts`.
- Admin API, PostgreSQL y CAPTCHA sombra: saludables; CAPTCHA sombra carga
  `v1_real`, `v2_scratch`, `v2_selected` y `v3_selected` en CUDA, con v3 como
  referencia visual; worker pendiente del siguiente arranque diario.
- Corte CAPTCHA prospectivo consultado directamente en la base sombra:
  `126/500` muestras revisadas; v3 `119/126`, sin eventos nuevos después del
  `2026-08-05`. El servicio fue reiniciado y está saludable desde el
  `2026-08-06`, pero todavía no recibió otra muestra.
- PostgreSQL v46 aplicado: una deuda histórica vencida y sin destinatario quedó
  archivada como `uncollectible/written_off`; otro pago conserva `S/20`
  abonados sobre `S/40`. El resumen mensual devuelve `2` cobros accionables por
  `S/70`: saldos de `S/20` y `S/50`. No se encoló ni envió WhatsApp durante el
  ajuste.
- WhatsApp del `2026-08-08`: `compileall`, Ruff, dashboard y `59` pruebas
  correctos. Admin API fue recuperada por su supervisor y sirve el bundle
  `main-IPC33IQD.js`; PostgreSQL conserva el resumen del 7 de agosto como
  `sent`. No se realizó ningún envío de prueba.

## Regla de mantenimiento

Después de cada cambio relevante:

1. actualizar este archivo si cambió el estado, una capacidad, un riesgo, una
   métrica o una validación;
2. actualizar [`roadmap/README.md`](roadmap/README.md) si una tarea avanzó,
   terminó, se bloqueó o cambió de prioridad;
3. mover el detalle largo a `operations/`, `contracts/`, `history/` o un
   documento de incidente;
4. no convertir reportes generados ni bitácoras en listas paralelas de tareas.
