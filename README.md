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
python -m appointment_bot.main
```

Por defecto el navegador se abre visible (`HEADLESS=false`) para poder mirar que pasa paso a paso.

## Configuracion

Variables iniciales:

```env
TARGET_URL=
LOGIN_USERNAME=
LOGIN_PASSWORD=
HEADLESS=false
BLOCK_HEAVY_ASSETS=true
SCREENSHOT_ON_ERROR=true
SCREENSHOT_ON_RELEVANT_RESULT=true
DEBUG_SNAPSHOTS=false
LOG_LEVEL=INFO
CLEANUP_RETENTION_DAYS=14
RUN_JITTER_MIN_SECONDS=30
RUN_JITTER_MAX_SECONDS=120
RUN_TIMEOUT_SECONDS=180
LOCK_STALE_MINUTES=10
ERROR_BACKOFF_THRESHOLD=3
ERROR_BACKOFF_SECONDS=1800
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
- `RUN_TIMEOUT_SECONDS`: limite global de una revision en Linux.
- `LOCK_STALE_MINUTES`: tiempo para considerar viejo un lock abandonado.
- `ERROR_BACKOFF_THRESHOLD`: errores consecutivos antes de pausar.
- `ERROR_BACKOFF_SECONDS`: pausa aplicada luego de demasiados errores.
- `HEARTBEAT_ENABLED`: envia un aviso periodico de que el bot sigue activo.
- `HEARTBEAT_INTERVAL_HOURS`: frecuencia del aviso periodico.

## Instalacion En VPS Ubuntu

Instalar dependencias base:

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

## Configuracion Recomendada En VPS

Para DigitalOcean o cualquier VPS Ubuntu, usar una configuracion similar:

```env
HEADLESS=true
BLOCK_HEAVY_ASSETS=true
SCREENSHOT_ON_ERROR=true
SCREENSHOT_ON_RELEVANT_RESULT=true
DEBUG_SNAPSHOTS=false
TELEGRAM_ENABLED=true
TELEGRAM_NOTIFY_UNAVAILABLE=false
CLEANUP_RETENTION_DAYS=14
RUN_JITTER_MIN_SECONDS=30
RUN_JITTER_MAX_SECONDS=120
RUN_TIMEOUT_SECONDS=180
LOCK_STALE_MINUTES=10
ERROR_BACKOFF_THRESHOLD=3
ERROR_BACKOFF_SECONDS=1800
HEARTBEAT_ENABLED=true
HEARTBEAT_INTERVAL_HOURS=24
```

Probar Telegram:

```bash
appointment-bot-test-telegram
```

Probar una revision manual:

```bash
python -m appointment_bot.main
```

## Ejecucion Programada

Ejecutar el bot con una frecuencia frecuente pero controlada usando `cron` o `systemd timer`. Para buscar cita de forma activa, usar cada 5 o 10 minutos. Evitar loops infinitos sin pausa y ejecuciones simultaneas.

Ejemplo de `cron` cada 10 minutos:

```cron
*/10 * * * * cd /ruta/al/proyecto && /ruta/al/proyecto/.venv/bin/python -m appointment_bot.main
```

Ejemplo mas intensivo cada 5 minutos:

```cron
*/5 * * * * cd /ruta/al/proyecto && /ruta/al/proyecto/.venv/bin/python -m appointment_bot.main
```

El bot evita solapamientos con un lock en `state/`, agrega jitter antes de cada revision y entra en backoff si acumula errores consecutivos.

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

## Seguridad Y Limites

Este proyecto no debe usarse para saltar captchas, colas virtuales, controles anti-bot ni restricciones del sitio. Si aparece un captcha o control manual, el flujo debe detenerse o requerir intervencion humana.

El bot solo revisa disponibilidad. No selecciona fecha, no selecciona hora y no confirma reservas. Si detecta botones finales como Confirmar, Guardar, Reservar o Finalizar, los registra en logs y no los presiona.
