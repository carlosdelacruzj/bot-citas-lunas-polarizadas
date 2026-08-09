# Manual operativo

## Validacion de clientes nuevos

Toda orden nueva queda fuera de la cola hasta que una sesion independiente
ingresa al portal, obtiene el nombre del titular y confirma que existe al menos
un tramite pendiente. En el dashboard se muestra `Validacion pendiente`,
`Validando acceso`, `Acceso validado` o `Validacion fallida`.

Si falla, revisar el mensaje visible en la orden y la captura guardada en
`screenshots/preflight/`, corregir el tipo de documento o la contrasena y usar
`Volver a validar`. No activar manualmente la orden: el backend bloquea esa
accion hasta completar el control. El comando `appointment-bot-client
order-add` realiza la misma validacion de forma sincrona y termina con codigo 1
si la cuenta no pasa el control.

## Flujo rápido de cobranza

El dashboard permite registrar un pago desde la tabla, el resumen mensual o el
panel de la orden sin abrir el formulario general. La ventana compacta propone
el monto acordado, incluye accesos rápidos para S/40 y S/50, y conserva una sola
confirmación antes de modificar el estado financiero.

Después de registrar el pago, el operador puede preparar inmediatamente el
paquete post-pago. Esta transición nunca confirma el envío automáticamente: los
mensajes y archivos continúan sujetos a revisión manual.

El panel separa las acciones frecuentes de contacto, restricciones y pago. Los
indicadores de pagos pendientes funcionan también como filtros y el número
completo de WhatsApp puede copiarse o abrirse desde el detalle protegido.

## Seguimiento post-cita

La vista **Post-cita** lista las reservas confirmadas y permite consultar el
estado posterior mediante una sesión aislada y de solo lectura. Guarda fechas,
estados, expediente, placa y el texto del mensaje para uso interno autenticado.
Uso, límites y rollback en
[`post-appointment-followup-2026-08-09.md`](post-appointment-followup-2026-08-09.md).

## Arranque recomendado

En Windows, la tarea programada `AppointmentBotContinuousWorker` ejecuta
`scripts/start-runtime.pyw` mediante `pythonw.exe` al iniciar sesion. Ese host
sin consola ejecuta el supervisor PowerShell y levanta en segundo plano todo el
entorno local:

- Docker y PostgreSQL;
- worker y API de salud en `127.0.0.1:8765`;
- build Angular, admin API y dashboard en `127.0.0.1:8766`.
- receptor independiente de control remoto por Telegram.
- supervisor del servicio sombra de CAPTCHA en `127.0.0.1:8787`.

La tarea se instala o recupera con:

```powershell
.\scripts\install-startup-task.ps1
```

`start-runtime.ps1` permanece activo como supervisor raiz. Cada 15 segundos
comprueba los supervisores de worker, Admin API, Telegram y CAPTCHA sombra, y
recupera solamente el que haya terminado. La tarea debe mostrarse como
`Running`; un estado `Ready` indica que el supervisor raiz no esta activo.
`pythonw.exe` evita dejar una ventana de consola abierta sin recurrir a VBS.

El admin/dashboard se reinicia si su proceso termina. No hace falta abrir
`npm start`: el admin API sirve directamente el build Angular.

Para un arranque manual sin la tarea programada, usar tres terminales:

Terminal 1:

```powershell
scripts/start-worker.ps1
```

Terminal 2:

```powershell
scripts/start-admin-dashboard.ps1
```

Terminal 3:

```powershell
scripts/start-telegram-control.ps1
```

Abrir `http://127.0.0.1:8766/`. El admin API sirve Angular y usa una sesión
local `HttpOnly`/`SameSite=Strict`; no exponer ni redirigir este puerto fuera de
loopback.

Los recursos del dashboard local se sirven con revalidación obligatoria para
evitar que una pestaña recargada conserve un build anterior durante cambios de
interfaz. Una pestaña que ya estaba abierta debe actualizarse una vez después de
publicar un build nuevo.

Rollback/desarrollo: ejecutar `appointment-bot-admin-api` y `npm start` dentro
de `dashboard/`. El proxy sigue apuntando a `127.0.0.1:8766`.

## Control remoto por Telegram

El proceso `appointment-bot-telegram-control` recibe comandos sin compartir
memoria con el worker. En la primera version admite:

- `/estado`;
- `/clientes [pagina]`;
- `/cliente ORDER_ID`;
- `/reglas ORDER_ID`;
- `/ultimos_errores`;
- `/prioridad ORDER_ID VALOR`;
- `/reglas_editar ORDER_ID`;
- `/cliente_nuevo`;
- `/captchas`;
- `/pausar`;
- `/reanudar`;
- `/reiniciar`;
- `/ayuda`;
- `/cancelar`.

Solo responde al `TELEGRAM_CHAT_ID` configurado. Opcionalmente,
`TELEGRAM_CONTROL_CHAT_IDS` permite una lista separada por comas. Un chat fuera
de esa lista se ignora sin revelar informacion.

El receptor usa long polling y guarda el siguiente `update_id` en
`.runtime/telegram-control-offset.json`. Antes de iniciarlo se puede comprobar
Telegram y la Admin API sin consumir mensajes:

```powershell
appointment-bot-telegram-control --check
```

El bot no ejecuta PowerShell ni consulta PostgreSQL directamente. `/estado`
consulta el Admin API autenticado; `worker_running` se calcula con el lease
vigente del worker y `outside_hot_window` significa activo pero esperando.

Los tres comandos que cambian el worker muestran botones `Confirmar` y
`Cancelar`. La confirmacion vence en dos minutos y solo puede consumirse una
vez. Despues de confirmar, Telegram espera el estado terminal de
`worker_commands` y comprueba el efecto real antes de anunciar exito. Un HTTP
`202` por si solo nunca se presenta como accion completada.

Las consultas operativas separan indice y detalle deliberado:

- `/clientes` muestra ocho ordenes por pagina y acepta el numero de pagina;
- `/cliente` trata al titular identificado por el portal como cliente y muestra
  por separado a la persona de contacto; incluye documento y WhatsApp
  completos, ademas de estado, prioridad, reserva y pago;
- `/reglas` muestra fechas, dias permitidos y rangos excluidos;
- `/ultimos_errores` revisa las ultimas 50 ejecuciones y muestra como maximo
  cinco incidentes saneados.

Las credenciales no aparecen en el menu ni en los paneles de clientes. El
comando historico `/credenciales ORDER_ID` se conserva temporalmente para
compatibilidad. `/cliente_nuevo` es el flujo de alta manual explicito:
la contrasena se recibe en el chat autorizado, permanece temporalmente en
memoria hasta confirmar y se muestra completa en el resumen y comprobante para
que el unico operador pueda verificarla. No se incluye en logs ni auditoria.
Tokens, cookies, datos de cifrado, leases y detalles crudos de runs nunca se
muestran.

El receptor registra acciones en `remote_control_audit` con actor hasheado,
accion, objetivo, resultado y fecha, sin guardar el texto escrito ni datos
sensibles. Aplica limites por chat y avisa `CONTROL REMOTO DISPONIBLE` despues
de iniciar o recuperarse.

`/menu` abre la interfaz principal con botones. Prioriza clientes, alta manual,
busqueda guiada, estado, resumen y sistema. Al pulsar
`Buscar cliente`, el receptor espera el nombre, contacto, documento, WhatsApp u
orden y devuelve botones; no es necesario recordar `/buscar TEXTO`.

El botón `Etiquetar CAPTCHA` y `/captchas` abren la misma cola de revisión humana
que usa el dashboard. Telegram envía primero el evento pendiente más antiguo y
muestra una opción por respuesta única; cuando varios modelos coinciden, sus
nombres aparecen agrupados en el mismo botón. El operador puede elegir una
predicción, pulsar `Escribir otra respuesta` y enviar exactamente cinco letras o
números, omitir la imagen durante esa sesión o salir. Cada guardado abre
automáticamente el siguiente CAPTCHA y actualiza el progreso.

La sesión vence después de diez minutos sin actividad. Cada imagen genera un
token nuevo, por lo que los botones de mensajes anteriores quedan obsoletos. El
guardado pasa por Admin API, comprueba que el evento todavía no tenga etiqueta y
registra al actor remoto sin exponer el chat. Esta revisión no interviene en una
reserva activa: 2Captcha conserva la única respuesta enviada al portal.

`/cliente_nuevo` solicita tipo y numero de documento, contrasena, nombre de
contacto, fuente y WhatsApp opcional. Luego permite crear sin restricciones o
configurar fecha minima, fecha maxima, dias permitidos y rangos excluidos. Solo
el boton final crea la orden; esta nace en validacion y Telegram
espera el preflight antes de indicar acceso correcto, revision necesaria o
validacion todavia en curso. Tanto antes como despues del alta muestra documento,
contrasena, contacto, WhatsApp y las cuatro restricciones completas.

Si `applicant_name` esta vacio o contiene solamente el numero de documento, se
muestra `Titular no identificado por el portal`; no se presenta el documento
como si fuera un nombre. El contacto conserva su nombre independiente porque no
necesariamente es el titular.

`/prioridad` muestra el valor anterior y nuevo antes de guardar. El editor
`/reglas_editar` pregunta en cuatro pasos:

1. fecha minima: `DD-MM-YYYY`, `igual` o `quitar`;
2. fecha maxima: `DD-MM-YYYY`, `igual` o `quitar`;
3. dias permitidos mediante botones o dias ISO, por ejemplo `1,3,6`;
4. fechas excluidas como `10-08-2026 al 12-08-2026`, separando varios rangos
   con `;`.

La conversacion vence en cinco minutos por inactividad. Ningun paso modifica la
orden; solo el boton final `Confirmar` envia el conjunto completo. Despues de
guardar, el receptor vuelve a consultar la orden y solo anuncia exito si los
valores persistidos coinciden. Si la orden todavía no fue validada, programa el
preflight y espera su resultado.

Todas las fechas visibles o ingresadas por el operador usan `DD-MM-YYYY`. El
receptor convierte internamente a ISO `YYYY-MM-DD` solamente al comunicarse con
la Admin API y PostgreSQL.

## Salud y calendario

- `http://127.0.0.1:8765/health`: vida del worker.
- Dashboard `/api/v1/worker`: fase real del worker.
- `outside_hot_window` con `worker_running=true`: espera saludable.
- Las búsquedas automáticas funcionan de lunes a sábado; domingo no abre
  sesiones ni consulta el portal.

## Ajustes controlados del observer

Cada cambio de frecuencia debe modificar una sola variable, conservar una línea
base y definir criterios de continuidad y reversión. El ajuste iniciado el
22-07-2026 aumenta los intentos por sesión de tres a cuatro sin cambiar los
intervalos de `8–13 s`. Su línea base y seguimiento están documentados en
[`observer-tuning-2026-07-22.md`](observer-tuning-2026-07-22.md).
La secuencia completa de optimizaciones, esperas y condiciones de avance se
mantiene en
[`performance-roadmap-2026-07-22.md`](performance-roadmap-2026-07-22.md).

La ráfaga que abre un auxiliar al detectar disponibilidad, sus límites,
telemetría y rollback por bandera están en
[`opportunity-burst-canary-2026-08-09.md`](opportunity-burst-canary-2026-08-09.md).

## Cambiar prioridad desde el dashboard

1. Abrir **Órdenes** y seleccionar la orden.
2. Pulsar **Editar**.
3. En **Prioridad de búsqueda**, ingresar un entero no negativo y confirmar.
4. Usar `0–99` para cola normal, `100–199` para enfoque o `200` para enfoque
   exclusivo.

El valor solo cambia por una acción explícita del operador; una reserva
confirmada no aumenta automáticamente la prioridad de otras órdenes. Con
prioridad `0`, las órdenes equivalentes conservan el orden de registro. La
prioridad elige las próximas sesiones que entran a observación, pero una sesión
que ya detectó un cupo compatible debe reservarlo inmediatamente para su propio
cliente.

El límite de observación representa órdenes que se rotan, no workers paralelos.
Si dos órdenes deben ocupar los dos espacios de rotación, asignar `100` a cada
una por separado. Con `200` se selecciona una sola orden, se limpia su pausa por
reglas y cualquier exclusivo anterior vuelve a `100`. Los siguientes cambios de
prioridad entran en la siguiente selección y no requieren reiniciar el worker.

## Consultar contacto operativo

Al seleccionar una orden se abre un panel lateral con el detalle administrativo:
nombre, WhatsApp completo, fuente, reglas, reserva, pago, trámite y acciones. El
panel no reduce ni desplaza la tabla y se cierra con **Cerrar**, `Esc` o pulsando
fuera. En móvil ocupa la pantalla completa. La tabla, los filtros, los snapshots
y las copias masivas continúan usando el número enmascarado para no exponer todos
los contactos a la vez.

## Flujo simplificado del operador

- La tabla muestra solo cliente, estado, reserva, pago y una acción
  contextual; prioridad, reglas, cierre y trámite permanecen en el panel lateral.
- El identificador técnico `order_id` no aparece en la tabla principal; se
  conserva en el panel lateral para diagnósticos. La tabla usa nombre, documento
  enmascarado y fuente para reconocer al cliente.
- La acción principal cambia según la orden: abrir sesión, activar, registrar
  pago o ver detalle.
- El panel ofrece accesos directos para editar, pausar/activar y gestionar otros
  cierres, además de presets **Cola normal** (`0`), **Enfoque 100** y
  **Exclusivo 200**.
- Las órdenes listas usan **Sesión manual** y llegan al panel de citas. Las
  pausadas, reservadas con pago pendiente, pagadas o archivadas muestran
  **Abrir portal** como acción secundaria: inicia sesión para consulta y no
  ejecuta automáticamente el trámite, el panel de citas ni la selección de
  sede. El navegador sigue siendo interactivo; cualquier acción manual dentro
  del portal es responsabilidad del operador.
- Las confirmaciones y resultados usan SweetAlert2 con mensajes claros; las
  acciones de lectura o navegación no solicitan confirmación innecesaria.
- La navegación por teclado conserva el foco al abrir y cerrar el panel.
- Al cerrar una sesión manual, la fila desaparece inmediatamente y el backend
  fuerza la limpieza del registro si Playwright no termina en ocho segundos.
- La lista de sesiones identifica **Operativa** o **Consulta**, conserva el
  estado de la orden al momento de abrir y muestra si la preparación terminó o
  falló sin cerrar automáticamente el navegador de diagnóstico.

## Resumen mensual

La vista **Resumen** permite elegir un mes y muestra ingresos realmente
cobrados, reservas, altas, ticket promedio, conversión, comparación con el mes
anterior, ingresos diarios y resultados por fuente. Los cobros pendientes y las
órdenes activas aparecen separados como trabajo por atender. Pulsar un pendiente
abre directamente su orden en el panel operativo.

Las fechas se agrupan en `America/Lima`: `paid_at` para ingresos, `reserved_at`
para reservas y `created_at` para órdenes nuevas. No sumar el importe pendiente
al ingreso cobrado.

## Bandeja accionable

La vista **Pendientes** muestra decisiones actuales, no deuda histórica de
comunicaciones. Para WhatsApp usa el envío real confirmado y el trabajo durable
creado por la automatización:

- los clientes pagados anteriores a la automatización no aparecen solo por no
  tener un postpago `sent`;
- un trabajo `failed` o `uncertain` desaparece si existe evidencia posterior de
  un envío real exitoso;
- `queued`, `blocked` y `running` no piden una segunda acción mientras el
  dispatcher conserva responsabilidad;
- un resultado ambiguo abre la orden para revisión y nunca reintenta el envío;
- pagos pendientes y contactos incompletos siguen visibles hasta resolverse.

Los paquetes históricos permanecen consultables. Esta clasificación no borra
mensajes ni envía seguimientos retroactivos.

## Formato de fecha y hora

Toda fecha visible del dashboard usa `DD-MM-YYYY`. Las horas usan formato de 24
horas `HH:mm` y los timestamps completos `DD-MM-YYYY HH:mm:ss`, siempre en la
zona `America/Lima`. Los controles HTML de captura pueden conservar internamente
`YYYY-MM-DD`, porque ese es el formato técnico exigido por el navegador.

## Recuperación

### Worker

1. Revisar health, fase, `next_check_at` y último error.
2. No reiniciar si está esperando fuera de ventana.
3. Si no responde, cerrar solo el worker y ejecutar `scripts/start-worker.ps1`.
4. Confirmar health y fase.

### Admin API y dashboard

1. Revisar `http://127.0.0.1:8766/health`.
2. Cerrar solo admin-dashboard.
3. Ejecutar `scripts/start-admin-dashboard.ps1 -SkipBuild`; reconstruir sin el
   flag si falta el build.
4. Comprobar órdenes y runs.

## Reportes

```powershell
appointment-bot-client weekly-report --start YYYY-MM-DD --end YYYY-MM-DD
appointment-bot-client optimization-observation --start YYYY-MM-DD --end YYYY-MM-DD
```

Las salidas vigentes están en `reports/operations/latest.md` y
`reports/optimization/latest.md`. Agregar `--notify` al reporte semanal solo
cuando se desee enviar sus alertas por Telegram.

## Prueba base y envio asistido por WhatsApp

La línea base manual, sus hitos y tiempos están documentados en
[`whatsapp-manual-trace-2026-07-22.md`](whatsapp-manual-trace-2026-07-22.md).
El primer trazado completo iniciado desde el dashboard está en
[`whatsapp-dashboard-trace-2026-07-22.md`](whatsapp-dashboard-trace-2026-07-22.md).
La serie manual del álbum de evidencias y el flujo acordado —álbum automático
con evidencia y QR de Yape, validación manual del pago y postpago automático—
están en
[`whatsapp-evidence-validation-2026-07-23.md`](whatsapp-evidence-validation-2026-07-23.md).

El dashboard no usa la API de Meta. En `Ordenes`, usar `Probar post-pago`, ingresar
el numero propio con codigo de pais (por ejemplo, `+51987654321`) y pulsar
`Preparar prueba post-pago`. El sistema muestra el destinatario, los textos y
los PDF sin abrir WhatsApp ni enviar. Despues de revisarlos, `Enviar prueba por
WhatsApp` presenta una confirmacion final y realiza un unico intento. La prueba
usa una cita de demostracion y los PDFs configurados en
`.runtime/whatsapp-followup/followup-details.json`, sin tocar ordenes reales.

Para validar el album inicial, usar `Probar evidencias`, ingresar el numero propio
y pulsar `Crear prueba de evidencias`. El dashboard muestra la constancia, el QR
de Yape y ambos textos sin abrir WhatsApp. `Enviar prueba por WhatsApp` exige una
confirmacion final y realiza un unico intento automatico. Playwright carga las dos
imagenes, coloca el texto combinado, pulsa Enviar, espera el regreso al chat normal
y cierra la sesion.

En una orden real, `Enviar por WhatsApp` crea el paquete y prepara inmediatamente el
album para revision en el dashboard: muestra constancia, imagen de pago y sus
textos. `Enviar por WhatsApp` presenta una confirmacion final y luego ejecuta el
mismo intento automatico validado por el simulacro. Solo registra `sent` cuando
desaparecen las miniaturas y regresa el chat normal; despues cierra la sesion. Si
el resultado posterior al clic es ambiguo, conserva el paquete sin confirmar y no
reintenta automaticamente. En el primer uso se debe escanear el QR y repetir la
preparacion.
El perfil queda solo en `.runtime/whatsapp-web-profile/` y no se versiona.

La configuracion privada del cobro se guarda en
`.runtime/whatsapp-payment/payment-details.json` junto a la imagen indicada por el
campo `image`. Nunca versionar ese directorio. El monto real se toma de PostgreSQL;
el simulacro usa S/ 40.00. La alternativa copiar/pegar permanece cerrada y solo se
muestra como respaldo cuando la preparacion automatica falla; incluye las dos
imagenes y sus respectivos textos.

Esta automatizacion local no es una integracion oficial de Meta. Usarla solo para
mensajes transaccionales esperados, uno por uno, sin campanas ni reintentos
agresivos. Un borrador nunca se considera enviado: cerrar la ventana o el asistente
mantiene el paquete en `prepared`; solo `Confirmar envio realizado` lo cambia a
`sent`.

Para clientes reales, `Preparar WhatsApp` se habilita en una reserva confirmada con
cobro pendiente. El sistema no agrega `51`: el contacto debe guardarse previamente
en formato internacional. En el detalle de una orden pendiente aparecen juntas las
acciones `Registrar pago` y `Enviar por WhatsApp`; esta ultima deja el album listo
para el envio humano final. El texto de confirmacion usa el mismo formateador que
Telegram. Preparar o confirmar el mensaje no registra el pago.

Despues de confirmar la transferencia y registrar el pago, una orden pagada muestra
`Enviar post-pago` como accion directa en la fila y en el detalle. Esta accion es
independiente del album de cobro: abre WhatsApp Web, adjunta los PDFs configurados en
`.runtime/whatsapp-followup/followup-details.json`, envia primero los PDFs y luego
envia el texto post-pago como segundo mensaje. Si WhatsApp confirma el envio, el
paquete queda registrado como enviado automaticamente y la accion pasa a
`Reenviar post-pago`. Usar `Confirmar envio post-pago` solo como respaldo si el
operador tuvo que enviarlo manualmente.

Desde el 25-07-2026, las ordenes nuevas usan disparadores automaticos persistentes.
Despues de la revision diferida y del intento de Telegram, el sistema encola el
album inicial sin bloquear el worker. Registrar el pago en `paid` encola el postpago
dentro de la misma transaccion. Cada flujo tiene un unico intento automatico,
deduplicacion por orden y recuperacion de trabajos que todavia no comenzaron. Los
resultados fallidos o inciertos se notifican por Telegram y quedan para revision
manual; nunca se reintentan solos. La decision, estados y reversion estan descritos
en
[`whatsapp-automatic-triggers-2026-07-25.md`](whatsapp-automatic-triggers-2026-07-25.md).

El Admin API es el unico proceso que consume estos trabajos y abre WhatsApp Web.
El worker solo los encola. Antes de consumir el intento, el Admin API valida su
propia sesion: una sesion sin vincular deja el trabajo en `blocked`, con
`attempt_count=0`, y vuelve a comprobarla sin adjuntar archivos. Un destinatario
invalido y un chat que no termina de cargar se registran como fallos distintos con
captura para revision.

El cierre diario de las 18:00 también encola un resumen idempotente al número
personal configurado: envía primero un texto con la fecha y después todas las
imágenes de `cupos-unicos`. Al final añade una publicación variable para TikTok
generada localmente sin IA ni tokens. El contrato y la primera validación real están en
[`whatsapp-daily-slot-summary-2026-07-30.md`](whatsapp-daily-slot-summary-2026-07-30.md).

La automatizacion espera a que el menu de adjuntos muestre una opcion real antes
de seleccionar archivos. Para el album normal exige un control con capacidad
multiple cuando hay dos imagenes; para post-pago limita `Documento` al menu de
adjuntos y no reutiliza coincidencias encontradas en mensajes antiguos del chat.

## Revision diferida de reservas confirmadas

Cuando una cola rapida termina normalmente porque ya no quedan ordenes con cupo, el
worker vuelve a abrir, en una sesion Playwright nueva por cliente, cada orden que
confirmo durante ese ciclo. Esta revision ocurre despues del ultimo intento y antes
de enviar la evidencia diferida de confirmacion: no agrega espera entre reservas ni
retrasa el siguiente cliente de la cola.

La revision exige encontrar exactamente `Separa Cita Peritaje` en estado
`Programado`. Entonces guarda un PNG nitido desde `Paterno`, `Materno` y `Nombres`
hasta esa fila, y reemplaza la evidencia principal de la reserva por una copia
estable apta para WhatsApp y por la imagen enviada en la secuencia de Telegram. Si
la revision falla, Telegram conserva como respaldo la captura original del momento
de confirmacion. No se pulsa ninguna accion de reserva.

El repaso no se ejecuta si la cola termino por pausa, limite de reservas, resultado
incierto o error tecnico. Un fallo individual de revision queda registrado con una
captura de error y no cambia la reserva ya confirmada ni detiene las demas revisiones.

## Simulacro de backup/restore

```powershell
scripts/verify-postgres-backup.ps1
```

El script restaura en una base temporal, compara tablas esenciales y elimina la
base y el dump al finalizar. Es una verificación de restaurabilidad, no una
política de backup durable. No versionar `.dump`, `.sql` ni `backups/`.

## Evidencia

Seguir [`evidence-policy.md`](evidence-policy.md). La primera lectura es
`docs/evidence-summary.md`, luego `docs/evidence-index.csv`; las bitácoras
extensas viven en `reports/evidence/history/`.
