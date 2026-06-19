# Obtener Lunas Polarizadas

Automatizador personal para revisar manualmente la disponibilidad de citas en una pagina web.

La primera version se ejecuta a mano, muestra el resultado por consola, escribe logs y guarda screenshots cuando ocurre un error. Las capturas de cada paso se pueden activar solo cuando se necesite depurar. Cuando la disponibilidad no se puede determinar, guarda un diagnostico de texto sanitizado para facilitar el ajuste de selectores y textos.

## Requisitos

- Python 3.12
- Navegadores de Playwright

## Instalacion Local En Windows

Crear y activar un entorno virtual:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
```

Instalar dependencias:

```powershell
python -m pip install -e .
python -m playwright install chromium
```

Crear el archivo de configuracion local:

```powershell
Copy-Item .env.example .env
```

Editar `.env` con la URL y credenciales reales. No compartas ese archivo.

## Ejecucion

```powershell
appointment-bot
```

`appointment-bot` ejecuta la cola multi-cliente con PostgreSQL. El modo de una sola cuenta queda disponible solo para depuracion manual:

```powershell
python -m appointment_bot.main
```

## Configuracion

Variables iniciales:

```env
TARGET_URL=
LOGIN_USERNAME=
LOGIN_PASSWORD=
APIKEY_2CAPTCHA=
HEADLESS=false
BLOCK_HEAVY_ASSETS=true
AUTO_RESERVE=true
SCREENSHOT_ON_ERROR=true
SCREENSHOT_ON_RELEVANT_RESULT=true
SCREENSHOT_DEVICE_SCALE_FACTOR=2
RECORD_VIDEO=false
RECORD_VIDEO_DIR=videos
RECORD_VIDEO_WIDTH=1920
RECORD_VIDEO_HEIGHT=1080
RECORD_VIDEO_SEND_TELEGRAM=false
RECORD_CLIENT_SESSIONS=false
RECORD_CLIENT_VIDEO_FINAL_MP4=true
RECORD_CLIENT_VIDEO_DIR=videos/reservations
DEBUG_SNAPSHOTS=false
LOG_LEVEL=INFO
CLEANUP_RETENTION_DAYS=14
RUN_JITTER_MIN_SECONDS=30
RUN_JITTER_MAX_SECONDS=120
RUN_TIMEOUT_SECONDS=420
LOCK_STALE_MINUTES=10
ERROR_BACKOFF_THRESHOLD=3
ERROR_BACKOFF_SECONDS=1800
MONITOR_WINDOW_SECONDS=300
MONITOR_MAX_ATTEMPTS=4
MONITOR_INTERVAL_MIN_SECONDS=80
MONITOR_INTERVAL_MAX_SECONDS=100
APPOINTMENT_DATABASE_URL=
QUEUE_MAX_RESERVATIONS_PER_RUN=0
QUEUE_DELAY_MIN_SECONDS=5
QUEUE_DELAY_MAX_SECONDS=15
HEARTBEAT_ENABLED=false
HEARTBEAT_INTERVAL_HOURS=24
CONTINUOUS_WORKER_ENABLED=false
CONTINUOUS_INTERVAL_MIN_SECONDS=45
CONTINUOUS_INTERVAL_MAX_SECONDS=75
SESSION_ROTATION_SECONDS=1500
SESSION_RETRY_DELAYS_SECONDS=10,30,60
LOGIN_TIMEOUT_SECONDS=60
POSTBACK_TIMEOUT_SECONDS=30
READ_TIMEOUT_SECONDS=15
RESERVATION_TIMEOUT_SECONDS=180
APPOINTMENT_BOT_API_HOST=127.0.0.1
APPOINTMENT_BOT_API_PORT=8765
APPOINTMENT_BOT_API_TOKEN=
TELEGRAM_ENABLED=false
TELEGRAM_BOT_TOKEN=
TELEGRAM_CHAT_ID=
TELEGRAM_NOTIFY_UNAVAILABLE=false
```

Para activar Telegram, crear un bot con BotFather, enviarle un mensaje y obtener el `chat.id` con `getUpdates`. Luego configurar solo el `.env` local:

```env
TELEGRAM_ENABLED=true
TELEGRAM_BOT_TOKEN=token_real
TELEGRAM_CHAT_ID=chat_id_real
TELEGRAM_NOTIFY_UNAVAILABLE=false
```

Para probar Telegram sin abrir la pagina web:

```powershell
appointment-bot-test-telegram
```

Para depurar visualmente cada paso, usar:

```env
DEBUG_SNAPSHOTS=true
```

Para grabar un video diagnostico real del flujo observador sin reservar:

```powershell
appointment-bot-record-video
```

El comando pausa temporalmente el worker si la API local esta disponible, inicia sesion sin
grabar, abre una segunda sesion autenticada con grabacion y guarda el `.webm` en `videos/`.
No pulsa el boton final `Reservar`. Para enviarlo por Telegram si el archivo no es demasiado
grande:

```powershell
appointment-bot-record-video --send-telegram
```

El video diagnostico es horizontal y esta pensado para revision interna. Para TikTok conviene
crear despues una version vertical editada y sin datos reales.

Para una demo movil real con mejor encuadre:

```powershell
appointment-bot-record-video --mobile-demo
```

Este comando genera el WebM base, un MP4 `appointment-bot-mobile-demo-final-...mp4` y una
version adicional `appointment-bot-mobile-demo-zoom-final-...mp4` con zoom al modal y al boton
`Reservar Cita`.

Para generar una version vertical MP4 lista para revisar antes de publicar en TikTok:

```powershell
appointment-bot-tiktok-video
```

El comando usa el ultimo `videos/appointment-bot-diagnostic-*.webm` y exporta un MP4 en
`videos/tiktok/`. Por defecto usa el estilo `scenes`: arma una demo vertical con portada,
zoom por escenas y capturas sanitizadas del flujo, para evitar que el portal horizontal se
vea diminuto en celular. Tambien se puede indicar la entrada manualmente:

```powershell
appointment-bot-tiktok-video --input videos\appointment-bot-diagnostic-YYYYMMDD-HHMMSS.webm
```

Para generar una version de respaldo con el video horizontal completo dentro del formato
vertical:

```powershell
appointment-bot-tiktok-video --style full-frame
```

Requiere `ffmpeg` y `ffprobe` instalados en Windows. Si no estan en el `PATH`, el comando
intenta encontrarlos en la instalacion local de winget.

Para ejecucion mas rapida, mantener:

```env
HEADLESS=true
BLOCK_HEAVY_ASSETS=true
SCREENSHOT_ON_RELEVANT_RESULT=true
SCREENSHOT_DEVICE_SCALE_FACTOR=2
DEBUG_SNAPSHOTS=false
```

`CLEANUP_RETENTION_DAYS` borra automaticamente logs, screenshots y diagnosticos antiguos al inicio de cada ejecucion.

Variables operativas para ejecucion frecuente:

- `RUN_JITTER_MIN_SECONDS` y `RUN_JITTER_MAX_SECONDS`: espera aleatoria antes de revisar.
- `AUTO_RESERVE`: si es `true`, cuando detecta fecha y hora seleccionables elige ambas,
  recorre las fechas hasta encontrar una hora, valida la seleccion, resuelve captcha e
  intenta reservar. Los textos generales de disponibilidad sin opciones reales solo
  generan una alerta parcial.
- `BLOCK_HEAVY_ASSETS`: bloquea fuentes y multimedia, pero nunca imagenes porque el
  CAPTCHA de reserva depende de ellas.
- `SCREENSHOT_DEVICE_SCALE_FACTOR`: escala de captura. El valor recomendado `2` mejora la
  legibilidad de la evidencia enviada como foto a Telegram.
- `RECORD_VIDEO`: activa grabacion de video en contextos Playwright que usen la configuracion.
  El comando `appointment-bot-record-video` fuerza la grabacion aunque esta variable siga en
  `false`.
- `RECORD_VIDEO_DIR`: carpeta local para videos diagnosticos. No se versiona.
- `RECORD_VIDEO_WIDTH` y `RECORD_VIDEO_HEIGHT`: resolucion del video. Para diagnostico se
  recomienda `1920x1080`.
- `RECORD_VIDEO_SEND_TELEGRAM`: envia el video diagnostico por Telegram si el archivo no supera
  el limite configurado.
- `RECORD_CLIENT_SESSIONS`: graba sesiones de clientes reales durante el worker continuo o cola.
  Si no hay reserva confirmada, el video temporal se elimina.
- `RECORD_CLIENT_VIDEO_FINAL_MP4`: convierte el video confirmado a MP4 local con mejor calidad.
- `RECORD_CLIENT_VIDEO_DIR`: carpeta local para videos de reservas confirmadas. No se versiona.
- `RUN_TIMEOUT_SECONDS`: limite global mediante `SIGALRM` en sistemas compatibles. En
  Windows no existe ese timeout global; los timeouts de Playwright y el supervisor de
  salud del worker limitan y reinician operaciones estancadas.
- `LOCK_STALE_MINUTES`: compatibilidad con locks antiguos. El lock actual usa propiedad
  verificable y bloqueo del sistema operativo durante toda la vida del proceso.
- `ERROR_BACKOFF_THRESHOLD`: errores consecutivos antes de pausar.
- `ERROR_BACKOFF_SECONDS`: pausa aplicada luego de demasiados errores.
- `MONITOR_WINDOW_SECONDS`: segundos que una ejecucion permanece revisando dentro de la misma sesion. `0` conserva una sola revision.
- `MONITOR_MAX_ATTEMPTS`: maximo de revisiones dentro de la sesion de monitoreo.
- `MONITOR_INTERVAL_MIN_SECONDS` y `MONITOR_INTERVAL_MAX_SECONDS`: espera aleatoria entre revisiones internas cuando `MONITOR_WINDOW_SECONDS` esta activo.
- `APPOINTMENT_DATABASE_URL`: conexion PostgreSQL obligatoria para historial, clientes y estados.
- `QUEUE_MAX_RESERVATIONS_PER_RUN`: maximo de reservas confirmadas por ejecucion de cola.
  `0` permite procesar todos los clientes pendientes.
- `QUEUE_DELAY_MIN_SECONDS` y `QUEUE_DELAY_MAX_SECONDS`: pausa aleatoria entre clientes despues de una reserva o intento relevante.
- `HEARTBEAT_ENABLED`: envia un aviso periodico de que el bot sigue activo.
- `HEARTBEAT_INTERVAL_HOURS`: frecuencia del aviso periodico.
- `CONTINUOUS_WORKER_ENABLED`: activa el trabajador residente de Windows.
- `CONTINUOUS_INTERVAL_MIN_SECONDS` y `CONTINUOUS_INTERVAL_MAX_SECONDS`: intervalo
  aleatorio entre consultas dentro de una misma sesion.
- `SESSION_ROTATION_SECONDS`: edad maxima de la sesion antes de cerrar y volver a iniciar
  con la misma cuenta prioritaria.
- `SESSION_RETRY_DELAYS_SECONDS`: esperas progresivas después de fallos de sesion.
- `LOGIN_TIMEOUT_SECONDS`, `POSTBACK_TIMEOUT_SECONDS`, `READ_TIMEOUT_SECONDS` y
  `RESERVATION_TIMEOUT_SECONDS`: limites por operacion del trabajador continuo.

## Worker Continuo En Windows

La V2 mantiene un solo trabajador y una sola sesion Playwright activa. Cuando existen
clientes pendientes monitorea el primero por prioridad; cuando no existen usa la cuenta
observadora de `.env`. El trabajador ignora `MONITOR_WINDOW_SECONDS` y
`MONITOR_MAX_ATTEMPTS`, consulta cada 45 a 75 segundos y rota preventivamente la sesion
cada 25 minutos.

Configurar en `.env`:

```env
CONTINUOUS_WORKER_ENABLED=true
CONTINUOUS_INTERVAL_MIN_SECONDS=45
CONTINUOUS_INTERVAL_MAX_SECONDS=75
SESSION_ROTATION_SECONDS=1500
SESSION_RETRY_DELAYS_SECONDS=10,30,60
LOGIN_TIMEOUT_SECONDS=60
POSTBACK_TIMEOUT_SECONDS=30
READ_TIMEOUT_SECONDS=15
RESERVATION_TIMEOUT_SECONDS=180
```

Probar el worker en primer plano:

```powershell
appointment-bot-worker
```

Para operacion diaria se recomienda el Programador de tareas de Windows. La tarea debe
ejecutar `scripts/start-worker.ps1`, que inicia Docker Desktop si hace falta, levanta
PostgreSQL con `docker compose up -d`, espera a que el contenedor este `healthy` y recien
despues inicia el worker. Crear la tarea una sola vez:

```powershell
$project = (Get-Location).Path
$script = Join-Path $project "scripts\start-worker.ps1"
$action = New-ScheduledTaskAction `
  -Execute "powershell.exe" `
  -Argument "-NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File `"$script`"" `
  -WorkingDirectory $project
$trigger = New-ScheduledTaskTrigger -AtLogOn
$settings = New-ScheduledTaskSettingsSet `
  -StartWhenAvailable `
  -RestartCount 999 `
  -RestartInterval (New-TimeSpan -Minutes 1) `
  -ExecutionTimeLimit ([TimeSpan]::Zero) `
  -MultipleInstances IgnoreNew
Register-ScheduledTask `
  -TaskName AppointmentBotContinuousWorker `
  -Action $action `
  -Trigger $trigger `
  -Settings $settings `
  -Force
Start-ScheduledTask AppointmentBotContinuousWorker
```

La tarea usa el directorio del repositorio como carpeta de trabajo. Si se ejecuta desde
otro entorno, definir `APPOINTMENT_BOT_WORKDIR` con la ruta que contiene `.env`.

La API alojada por el mismo proceso expone:

```text
GET  http://127.0.0.1:8765/health
GET  http://127.0.0.1:8765/status
POST http://127.0.0.1:8765/pause
POST http://127.0.0.1:8765/resume
```

`/pause` interrumpe la espera actual y cierra la sesion. `/resume` abre una sesion nueva.
`/run` y `/run-queue` devuelven HTTP 409 mientras el trabajador continuo esta activo.
El estado se persiste en PostgreSQL para que `/status` conserve la ultima actividad despues
de un reinicio. En este modo n8n no programa revisiones: solo supervisa `/health` y
`/status`, o solicita pausa y reanudacion.

`/health` permanece publico y solo informa salud operativa, sin datos de clientes.
`/status` y todos los endpoints POST requieren
`Authorization: Bearer <token>` cuando `APPOINTMENT_BOT_API_TOKEN` esta definido. La
salud tambien comprueba la antiguedad de la ultima revision; si el worker queda vivo pero
estancado, el proceso termina para que el Programador de tareas lo reinicie.

En n8n, supervisar `/health` sin token y considerar sano solo HTTP `200`,
`status=ok` y `worker_running=true`. Enviar alerta despues de tres fallos consecutivos.
Reservar `/status` para diagnostico y enviar `Authorization: Bearer <token>`; un `401` de
`/status` indica autenticacion ausente o incorrecta, no que la API este caida. Diferenciar
las alertas entre API inaccesible, worker degradado y autenticacion rechazada.

La API escucha en `127.0.0.1` por defecto. Si `APPOINTMENT_BOT_API_HOST` se cambia para
aceptar conexiones externas, es obligatorio definir el token. No publicar el puerto en
Internet.

## API Para Panel Futuro

El panel web futuro debe consumir la API local; no debe conectarse directo a PostgreSQL.
Todos los endpoints `/api/v1/*` requieren:

```text
Authorization: Bearer <APPOINTMENT_BOT_API_TOKEN>
```

Endpoints disponibles:

```text
GET  /api/v1/worker
GET  /api/v1/clients
POST /api/v1/clients
PATCH /api/v1/clients/{client_id}
POST /api/v1/clients/{client_id}/pause
POST /api/v1/clients/{client_id}/activate
POST /api/v1/clients/{client_id}/done
GET  /api/v1/runs?limit=50&offset=0
GET  /api/v1/runs/{run_id}
```

La API nunca devuelve contraseñas. La clave del cliente solo se acepta como campo de
escritura al crear o editar un cliente. El panel se agregara mas adelante en
`src/appointment_bot/panel/` y se servira desde:

```text
http://127.0.0.1:8765/panel
```

## Instalacion En PC Local

Por ahora la PC local es el entorno recomendado porque la pagina valida IP peruana. Mantener la PC encendida, con internet estable y con el Programador de tareas de Windows o n8n disparando el bot.

Para ejecutar la cola multi-cliente:

```powershell
appointment-bot
```

Para ejecutar una revision personal de depuracion, sin usar la cola:

```powershell
python -m appointment_bot.main
```

## Instalacion En VPS Ubuntu

Usar VPS solo si la IP de salida es aceptada por la pagina. Instalar dependencias base:

```bash
sudo apt update
sudo apt install -y git python3 python3-venv python3-pip
```

Clonar el repositorio:

```bash
git clone https://github.com/carlosdelacruzj/bot-citas-lunas-polarizadas.git
cd bot-citas-lunas-polarizadas
```


Crear entorno virtual e instalar el proyecto:

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -e .
python -m playwright install --with-deps chromium
```

Crear `.env` en el VPS:

```bash
cp .env.example .env
nano .env
```

No subir `.env` a GitHub. Cada maquina debe tener su propio `.env`.

## Configuracion Recomendada

Para la PC local o un servidor con IP aceptada por la pagina, usar una configuracion similar:

```env
HEADLESS=true
BLOCK_HEAVY_ASSETS=true
AUTO_RESERVE=true
SCREENSHOT_ON_ERROR=true
SCREENSHOT_ON_RELEVANT_RESULT=true
SCREENSHOT_DEVICE_SCALE_FACTOR=2
DEBUG_SNAPSHOTS=false
TELEGRAM_ENABLED=true
TELEGRAM_NOTIFY_UNAVAILABLE=false
CLEANUP_RETENTION_DAYS=14
RUN_JITTER_MIN_SECONDS=30
RUN_JITTER_MAX_SECONDS=120
RUN_TIMEOUT_SECONDS=420
LOCK_STALE_MINUTES=10
ERROR_BACKOFF_THRESHOLD=3
ERROR_BACKOFF_SECONDS=1800
MONITOR_WINDOW_SECONDS=300
MONITOR_MAX_ATTEMPTS=4
MONITOR_INTERVAL_MIN_SECONDS=80
MONITOR_INTERVAL_MAX_SECONDS=100
APPOINTMENT_DATABASE_URL=postgresql://appointment_bot:cambia-esto-localmente@127.0.0.1:5432/appointment_bot
QUEUE_MAX_RESERVATIONS_PER_RUN=0
QUEUE_DELAY_MIN_SECONDS=5
QUEUE_DELAY_MAX_SECONDS=15
HEARTBEAT_ENABLED=true
HEARTBEAT_INTERVAL_HOURS=24
```

Probar Telegram:

```bash
appointment-bot-test-telegram
```

Probar la cola:

```bash
appointment-bot
```

## Modo Programado Por n8n

Este modo es alternativo al worker continuo. Usarlo solo con:

```env
CONTINUOUS_WORKER_ENABLED=false
```

Para pruebas locales con n8n en Docker, iniciar el endpoint:

```powershell
python -m appointment_bot.services.local_api
```

Desde n8n, llamar la cola:

```text
POST http://host.docker.internal:8765/run-queue
```

El endpoint devuelve JSON sanitizado con `status`, `message`, `exit_code`, `details` y
nombres de screenshots cuando existan. `details.results` es una lista JSON con el
resultado de cada cliente. Si uno o mas clientes terminan con error o existe una reserva
no confirmada, la cola devuelve `status=error`, `exit_code=1` y HTTP 500 para que n8n
detecte el fallo. La etapa `Programado` es la evidencia principal de una reserva
confirmada. Las alertas de Telegram y las imagenes las envia el bot Python, no n8n.

El endpoint de una sola cuenta sigue disponible solo para depuracion y fuerza
`AUTO_RESERVE=false`; puede revisar disponibilidad, pero nunca enviar una reserva:

```text
POST http://host.docker.internal:8765/run
```

## PostgreSQL Para Datos Del Bot

PostgreSQL es la base operativa del bot. n8n no cambia: esta configuracion es solo para
los datos del appointment bot.

Levantar PostgreSQL:

```powershell
$env:APPOINTMENT_POSTGRES_PASSWORD = "cambia-esto-localmente"
docker compose up -d postgres
docker compose ps
```

Configurar la conexion en `.env` local:

```env
APPOINTMENT_DATABASE_URL=postgresql://appointment_bot:cambia-esto-localmente@127.0.0.1:5432/appointment_bot
```

Si `APPOINTMENT_DATABASE_URL` falta o PostgreSQL no esta disponible, el bot no arranca.

Validar conexion y datos:

```powershell
appointment-bot-client list
appointment-bot-worker
```

Backup manual de PostgreSQL:

```powershell
docker exec appointment-bot-postgres pg_dump `
  -U appointment_bot `
  -d appointment_bot `
  -F c `
  -f /tmp/appointment_bot.dump
docker cp appointment-bot-postgres:/tmp/appointment_bot.dump data/backups/appointment_bot.dump
```

## Clientes Y Cola Local

La cola usa PostgreSQL mediante `APPOINTMENT_DATABASE_URL`. El esquema tiene version y
migraciones aplicadas al abrir la base. El mantenimiento elimina historial antiguo y
referencias de capturas que ya no pertenecen a una ejecucion conservada. La base guarda
credenciales de clientes en texto plano para esta primera version; no la subas al
repositorio y protege la PC donde se ejecuta.

Agregar o actualizar un cliente:

```powershell
appointment-bot-client add --id cliente-001 --name "Nombre Cliente" --username DNI --priority 10
```

La clave se solicita de forma oculta para evitar dejarla en el historial de PowerShell.

Comandos utiles:

```powershell
appointment-bot-client list
appointment-bot-client pause cliente-001
appointment-bot-client activate cliente-001
appointment-bot-client done cliente-001
appointment-bot-probe-availability --json
```

`activate` vuelve a abrir un cliente completado, limpia su marca `done` y elimina cualquier
backoff anterior para que pueda regresar a la cola.

Ejecutar la cola:

```powershell
appointment-bot
```

La cola limpia archivos antiguos una vez al inicio y procesa clientes activos por prioridad.
Los clientes registrados o en estado `Programado` quedan fuera de ejecuciones posteriores.
El primer cliente pendiente mantiene una sola sesion abierta hasta 5 minutos y realiza como
maximo 4 revisiones. Si no confirma una reserva, la cola termina sin saltar al siguiente
cliente. Cuando confirma una reserva, cambia a modo rapido: espera entre 5 y 15 segundos,
abre una sesion nueva para el siguiente cliente y realiza una sola revision. Continua de
esta forma mientras se confirmen reservas y se detiene al primer resultado sin cupos,
parcial, incierto o con error.

Cuando no quedan clientes activos, la misma ejecucion usa las credenciales generales de
`.env` como cuenta observadora. El observador abre el panel mediante el postback ASP.NET
del boton oculto, revisa hasta 4 veces durante 5 minutos y nunca llama a 2Captcha ni pulsa
el boton final de reserva. Si encuentra fecha y hora, envia Telegram y devuelve
`status=available` con `details.mode=observer`.

Para identificar de donde llegan las fechas sin intentar reservar:

```powershell
appointment-bot-probe-availability --json
```

El comando abre Chromium visible y guarda en `diagnostics/` un HAR sanitizado y un resumen
JSON. No guarda cookies, cabeceras, cuerpos POST, respuestas, credenciales ni valores de
query string. `details.network_source` indica `webforms_postback`, `ajax`, `preloaded` o
`unknown`.

## Ejecucion Programada

Ejecutar el bot con una frecuencia frecuente pero controlada usando `cron` o `systemd timer`. Para buscar cita de forma activa, usar cada 5 o 10 minutos. Evitar loops infinitos sin pausa y ejecuciones simultaneas.

Ejemplo de `cron` cada 10 minutos:

```cron
*/10 * * * * cd /ruta/al/proyecto && /ruta/al/proyecto/.venv/bin/appointment-bot
```

Ejemplo mas intensivo cada 5 minutos:

```cron
*/5 * * * * cd /ruta/al/proyecto && /ruta/al/proyecto/.venv/bin/appointment-bot
```

El bot evita solapamientos con un lock en `state/` que registra propietario y token,
agrega jitter antes de cada revision y entra en backoff si acumula errores consecutivos.

Para aumentar revisiones sin hacer login en cada intento, activar una ventana corta de monitoreo:

```env
RUN_TIMEOUT_SECONDS=420
MONITOR_WINDOW_SECONDS=300
MONITOR_MAX_ATTEMPTS=4
MONITOR_INTERVAL_MIN_SECONDS=80
MONITOR_INTERVAL_MAX_SECONDS=100
```

Con esa configuracion, el primer cliente pendiente abre sesion una vez, revisa `Etapas
Tramite` y, si `Separa Cita Peritaje` esta `Pendiente`, revisa el modal hasta 4 veces
dentro de una ventana de 5 minutos. Si no hay cupo completo, termina la cola. Si reserva,
los siguientes clientes usan una sesion nueva y una sola revision para aprovechar los
cupos. Si la etapa ya esta `Programado`, el cliente se marca como terminado y se busca el
siguiente pendiente. El timeout deja margen para login, capturas, captcha y cierre.

Para 2Captcha se captura solamente el panel modal de reserva. Esa imagen temporal se
elimina inmediatamente despues de enviarla al proveedor y no se incluye entre las
evidencias remitidas a Telegram.

Si se eligio el modo programado por n8n, el flujo es:

```text
Schedule Trigger -> HTTP Request POST http://host.docker.internal:8765/run-queue
```

n8n orquesta la ejecucion solo en este modo. Con el worker continuo activo, n8n debe
supervisar `/health` y `/status` y no debe llamar `/run-queue`. Las alertas de Telegram
las envia el bot en ambos modos.

Para editar cron en el VPS:

```bash
crontab -e
```

Para ver logs del cron del sistema:

```bash
grep CRON /var/log/syslog
```

Los logs propios del bot quedan en `logs/`.

## Ajuste De Selectores

Como cada pagina web tiene formularios y textos distintos, probablemente haya que ajustar:

- `src/appointment_bot/flows/login.py`
- `src/appointment_bot/flows/appointments.py`

La primera version usa selectores genericos para el login y textos comunes para detectar disponibilidad. Si la web cambia o no coincide, el programa debe fallar con logs y screenshot para facilitar el ajuste.

## Validacion Manual

Antes de desplegar:

```powershell
python -m compileall src tests
python -m ruff check src tests
python -m ruff format --check src tests
python -m unittest discover
```

Al ejecutar, revisar:

- que abre la URL correcta
- que carga credenciales desde `.env`
- que intenta iniciar sesion
- que navega o permanece en la zona esperada
- que muestra en consola si hay cupo, no hay cupo o si no pudo determinarlo
- que crea logs en `logs/`
- que guarda screenshot en `screenshots/` cuando falla
- que guarda diagnosticos en `diagnostics/` si el resultado queda como indeterminado
- que actualiza estado operativo en `state/` para lock, backoff y heartbeat
- que `appointment-bot-client list` muestra clientes sin exponer claves
- que `appointment-bot-run-queue` crea historial en PostgreSQL
