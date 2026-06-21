# Bot De Citas Para Lunas Polarizadas

Bot Python que mantiene una cola de ordenes en PostgreSQL, revisa disponibilidad con una
sesion Playwright independiente por orden y reserva automaticamente cuando corresponde.

## Componentes

- Worker continuo: selecciona la orden prioritaria, monitorea y procesa la cola rapida.
- API local: salud, estado, pausa, reanudacion, ordenes e historial.
- PostgreSQL: ordenes, credenciales cifradas, estado, pagos y ejecuciones.
- Telegram: alertas y screenshots generados directamente por el bot.
- Video opcional: conserva solamente sesiones con reserva confirmada.
- n8n: supervision externa; no inicia corridas manuales.

## Instalacion

```powershell
python -m pip install -e .
python -m playwright install chromium
docker compose up -d
```

Generar una clave Fernet y guardarla fuera del repositorio:

```powershell
python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
```

Configurar como minimo `TARGET_URL`, `APPOINTMENT_DATABASE_URL`,
`APPOINTMENT_CREDENTIAL_KEYS`, las credenciales observadoras y las variables de Telegram.
La primera clave Fernet cifra; las siguientes permiten leer claves anteriores durante una
rotacion.

## Ejecucion

```powershell
appointment-bot-worker
```

En Windows, `scripts/start-worker.ps1` levanta PostgreSQL, espera su health check y reinicia el
worker ante errores o solicitudes controladas. `scripts/start-worker-hidden.vbs` permite
iniciarlo sin ventana.

Administrar ordenes:

```powershell
appointment-bot-client order-add --document DNI --priority 10
appointment-bot-client orders
appointment-bot-client pause order-DNI
appointment-bot-client activate order-DNI
appointment-bot-client done order-DNI
appointment-bot-client paid order-DNI --amount-paid 120
```

## API

El worker sirve la API en `APPOINTMENT_BOT_API_HOST` y `APPOINTMENT_BOT_API_PORT`.
Cuando se publica fuera de loopback, el puerto debe limitarse por firewall y todas las
operaciones administrativas requieren `APPOINTMENT_BOT_API_TOKEN`.
`POST /api/v1/worker/restart`
realiza un reinicio controlado del host supervisado.
Si escucha fuera de loopback, `APPOINTMENT_BOT_API_TOKEN` es obligatorio.

```text
GET  /health
GET  /api/v1/worker
GET  /api/v1/service-orders
POST /api/v1/service-orders
GET  /api/v1/runs
GET  /api/v1/runs/{run_id}
POST /api/v1/worker/pause
POST /api/v1/worker/resume
POST /api/v1/worker/restart
```

n8n debe consultar salud/estado y enviar `Authorization: Bearer <token>`. No existen endpoints
para disparar corridas: el worker es el unico orquestador interno.

## Video De Reservas

`RECORD_CLIENT_SESSIONS=true` graba temporalmente cada sesion. Si no se confirma una reserva,
el archivo se elimina. Si se confirma, se guarda en `RECORD_CLIENT_VIDEO_DIR`; la conversion a
MP4 depende de FFmpeg y de `RECORD_CLIENT_VIDEO_FINAL_MP4`.

## Verificacion

```powershell
python -m compileall src
python -m ruff check src tests
python -m pytest -q
```

No se versionan `.env`, logs, screenshots, videos, datos ni dumps PostgreSQL.
