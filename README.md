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

`appointment-bot` ejecuta la cola multi-cliente con SQLite. El modo de una sola cuenta queda disponible solo para depuracion manual:

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
DATABASE_PATH=data/appointment_bot.sqlite
QUEUE_MAX_RESERVATIONS_PER_RUN=0
QUEUE_DELAY_MIN_SECONDS=5
QUEUE_DELAY_MAX_SECONDS=15
HEARTBEAT_ENABLED=false
HEARTBEAT_INTERVAL_HOURS=24
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

Para ejecucion mas rapida, mantener:

```env
HEADLESS=true
BLOCK_HEAVY_ASSETS=true
SCREENSHOT_ON_RELEVANT_RESULT=true
DEBUG_SNAPSHOTS=false
```

`CLEANUP_RETENTION_DAYS` borra automaticamente logs, screenshots y diagnosticos antiguos al inicio de cada ejecucion.

Variables operativas para ejecucion frecuente:

- `RUN_JITTER_MIN_SECONDS` y `RUN_JITTER_MAX_SECONDS`: espera aleatoria antes de revisar.
- `AUTO_RESERVE`: si es `true`, cuando detecta fecha y hora seleccionables elige ambas,
  recorre las fechas hasta encontrar una hora, valida la seleccion, resuelve captcha e
  intenta reservar. Los textos generales de disponibilidad sin opciones reales solo
  generan una alerta parcial.
- `BLOCK_HEAVY_ASSETS`: bloquea recursos pesados para reducir consumo. En el flujo actual
  no afecta al captcha de reserva, porque el captcha utilizado por el bot sigue visible
  dentro del panel capturado. Si la web cambia la forma de cargarlo, se debe volver a validar.
- `RUN_TIMEOUT_SECONDS`: limite global de una revision en Windows y Linux. Debe superar
  `MONITOR_WINDOW_SECONDS` por al menos 60 segundos.
- `LOCK_STALE_MINUTES`: respaldo para limpiar locks ilegibles; si el lock contiene un PID
  activo, no se elimina aunque la ejecucion sea larga.
- `ERROR_BACKOFF_THRESHOLD`: errores consecutivos antes de pausar.
- `ERROR_BACKOFF_SECONDS`: pausa aplicada luego de demasiados errores.
- `MONITOR_WINDOW_SECONDS`: segundos que una ejecucion permanece revisando dentro de la misma sesion. `0` conserva una sola revision.
- `MONITOR_MAX_ATTEMPTS`: maximo de revisiones dentro de la sesion de monitoreo.
- `MONITOR_INTERVAL_MIN_SECONDS` y `MONITOR_INTERVAL_MAX_SECONDS`: espera aleatoria entre revisiones internas cuando `MONITOR_WINDOW_SECONDS` esta activo.
- `DATABASE_PATH`: ruta local de SQLite para historial, clientes y estados.
- `QUEUE_MAX_RESERVATIONS_PER_RUN`: maximo de reservas confirmadas por ejecucion de cola.
  `0` permite procesar todos los clientes pendientes.
- `QUEUE_DELAY_MIN_SECONDS` y `QUEUE_DELAY_MAX_SECONDS`: pausa aleatoria entre clientes despues de una reserva o intento relevante.
- `HEARTBEAT_ENABLED`: envia un aviso periodico de que el bot sigue activo.
- `HEARTBEAT_INTERVAL_HOURS`: frecuencia del aviso periodico.

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
DATABASE_PATH=data/appointment_bot.sqlite
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

## Endpoint Local Para n8n

Para pruebas locales con n8n en Docker, iniciar el endpoint:

```powershell
python -m appointment_bot.services.local_api
```

Desde n8n, llamar la cola:

```text
POST http://host.docker.internal:8765/run-queue
```

El endpoint devuelve JSON con `status`, `message`, `exit_code`, `details` y rutas de screenshots cuando existan. `details.results` es una lista JSON con el resultado de cada cliente. Si uno o mas clientes terminan con error o existe una reserva no confirmada, la cola devuelve `status=error`, `exit_code=1` y HTTP 500 para que n8n detecte el fallo. Una reserva solo se considera confirmada cuando aparecen el mensaje de exito y la etapa `Programado` con la fecha y hora seleccionadas. Las alertas de Telegram y las imagenes las envia el bot Python, no n8n.

El endpoint de una sola cuenta sigue disponible solo para depuracion:

```text
POST http://host.docker.internal:8765/run
```

## Clientes Y Cola Local

La cola usa SQLite local en `data/appointment_bot.sqlite`. Esta base guarda credenciales de clientes en texto plano para esta primera version; no la subas al repositorio y protege la PC donde se ejecuta.

Agregar o actualizar un cliente:

```powershell
appointment-bot-client add --id cliente-001 --name "Nombre Cliente" --username DNI --password CLAVE --priority 10
```

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

El bot evita solapamientos con un lock en `state/`, agrega jitter antes de cada revision y entra en backoff si acumula errores consecutivos.

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

Con n8n, el flujo recomendado es:

```text
Schedule Trigger -> HTTP Request POST http://host.docker.internal:8765/run-queue
```

n8n debe orquestar la ejecucion; las alertas de Telegram las envia el bot.

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
- que `appointment-bot-run-queue` crea historial en `data/appointment_bot.sqlite`
