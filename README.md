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
worker ante errores o solicitudes controladas. `scripts/start-runtime.pyw` inicia sin consola
el supervisor `scripts/start-runtime.ps1` mediante la tarea programada instalada por
`scripts/install-startup-task.ps1`. Si otro host ya tiene el lease del worker, el proceso sale con un
reinicio controlado y el script espera antes de intentar de nuevo. El script tambien evita
iniciar un segundo `appointment_bot.worker.host` local si ya hay uno corriendo.
El supervisor raiz permanece activo y recupera por separado worker, Admin API, Telegram o
el servicio CAPTCHA local cuando desaparece su supervisor.

Administrar ordenes:

```powershell
appointment-bot-client order-add --document DNI --priority 10 --contact-name NOMBRE --contact-source whatsapp
appointment-bot-client orders
appointment-bot-client pause order-DNI
appointment-bot-client activate order-DNI
appointment-bot-client done order-DNI
appointment-bot-client paid order-DNI --amount-paid 120
appointment-bot-client status-report order-DNI
appointment-bot-client status-report
```

Checkpoint probado: [hitos operativos](docs/history/milestones.md).
Esa version fue la primera que detecto cupos reales en `LIMA-LA VICTORIA` para el
`13/07/2026` y envio alerta `[AVAILABLE]` por Telegram; se conserva como referencia
para comparar futuras corridas.

`status-report` genera fichas PNG con las consultas realizadas al portal entre las 06:00 y
las 20:00 del dia actual. Al indicar una orden crea una sola ficha; sin argumentos genera
fichas para todas las ordenes activas en `reports/status/`. Las fichas usan el horario de
Lima, muestran el documento enmascarado y se nombran con el cliente y la hora de generacion.

Desde `WORKER_DAILY_CUTOFF_TIME` (18:00 por defecto) el worker no inicia nuevas consultas. Si una consulta comenzo antes del
corte, permite que termine junto con cualquier cola de reserva derivada de ella y luego
cierra el worker y su API. La revision final de ordenes listas se conserva, pero ya no se
genera una imagen de reporte general.

La configuracion productiva vigente concentra las revisiones densas en
`OBSERVER_HOT_WINDOWS=07:10-18:00`, hora de Lima. Fuera de esa ventana espera entre
`OUTSIDE_HOT_WINDOW_MIN_SECONDS=1200` y
`OUTSIDE_HOT_WINDOW_MAX_SECONDS=2400`, o hasta la siguiente ventana si esta mas cerca.
Cada orden conserva su propia sesion Playwright. Con el toggle ligero activo ejecuta hasta
`OBSERVER_SITE_TOGGLE_ATTEMPTS=15` consultas de sede, con una pausa aleatoria nueva de
`1-2` segundos en cada lectura y un unico `reload_probe` despues del intento `8`; al
terminar rota al siguiente cliente. `OBSERVER_SESSION_SECONDS=120` sigue siendo el limite
de la sesion observadora y los valores base `OBSERVER_MAX_ATTEMPTS` e
`OBSERVER_INTERVAL_MIN/MAX_SECONDS` quedan para el recorrido que no usa el toggle ligero.
`OBSERVER_REQUIRED_SITE=LIMA-LA VICTORIA` fija la unica sede valida; si el portal no la
ofrece, el bot falla con un mensaje claro en vez de seleccionar otra sede. El worker
continuo no envia Telegram por resultados rutinarios `Sin Cupos`; Telegram queda reservado
para disponibilidad, reservas, errores, bloqueos y estados que requieren accion.
Cuando se detecta disponibilidad dentro de una ventana caliente, el worker puede extender la
rotacion hasta `OBSERVER_HOT_WINDOW_EXTENSION_SECONDS` despues del fin de esa ventana para
intentar reservar a los demas usuarios sin abrir nuevas busquedas indefinidas.
Durante la cola rapida se envia un aviso inmediato de disponibilidad solo texto; las fotos,
videos y evidencias completas se mandan al terminar la cola para no bloquear segundos criticos.

Cada revision del worker continuo agrega metricas en `observer_window_metrics`, agrupadas
por fecha, ventana, fuente, estado y sede. La tabla guarda conteos, errores, duracion
acumulada y el ultimo resultado visto para decidir con datos que ventanas conviene mantener.

## Revision De Optimizaciones

Antes de cambiar ventanas calientes, frecuencia de requests, CAPTCHA, concurrencia o
limpieza de evidencia, empezar por
[`docs/project-status.md`](docs/project-status.md) y respetar el orden de
[`docs/roadmap/README.md`](docs/roadmap/README.md). La ruta rapida de evidencia es:
`docs/evidence-index.csv` para filtrar eventos, `docs/evidence-summary.md` para lectura
digerida, y las bitacoras largas solo cuando un caso lo amerita. Para regenerar un resumen
desde PostgreSQL:

```powershell
appointment-bot-client evidence-summary --days 7 --output-dir reports/evidence
```

En modo recuperacion se recomienda `AUTO_RESERVE=false`, `QUEUE_MAX_RESERVATIONS_PER_RUN=1`
y Telegram activo para que una persona confirme manualmente cuando aparezca una alerta. Si
se activa `AUTO_RESERVE=true`, la cadena multi-cliente solo nace de una disponibilidad real
y respeta `QUEUE_MAX_RESERVATIONS_PER_RUN` (`0` permite recorrer todos los candidatos del
lote). La cuenta detectora intenta reservar en su misma sesion. Con `OBS-006` activo, una
fecha y hora seleccionables pueden abrir en paralelo una unica sesion auxiliar compatible
mientras el detector continua; nunca hay mas de dos sesiones concurrentes. Cada posicion
que termina en `registered` puede tomar el siguiente candidato mediante un contexto
Playwright nuevo y aislado.

Si el worker acumula `UNAVAILABLE_STREAK_LIMIT` resultados seguidos de `Sin Cupos`, o si
detecta senales de defensa del portal como CAPTCHA inesperado, HTTP 403/429 o sesion
cerrada, entra en `recovery_backoff` entre `RECOVERY_BACKOFF_MIN_SECONDS` y
`RECOVERY_BACKOFF_MAX_SECONDS`. Esto evita insistir cuando el portal podria estar marcando
la sesion, IP o expediente.
Un rechazo de contrasena mueve la orden al final de la rotacion. Al segundo rechazo, la
orden se pausa y el worker continua con las demas; actualizar la clave y ejecutar
`appointment-bot-client activate order-DNI` reinicia ese contador.

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

## Documentacion

- Estado unico de trabajo cumplido: [`docs/project-status.md`](docs/project-status.md).
- Orden obligatorio de mejoras: [`docs/roadmap/README.md`](docs/roadmap/README.md).
- Arquitectura y migracion historica: [`docs/architecture/`](docs/architecture/).
- Contratos estables: [`docs/contracts/`](docs/contracts/).
- Arranque, salud y rollback: [`docs/operations/README.md`](docs/operations/README.md).
- Hitos historicos: [`docs/history/milestones.md`](docs/history/milestones.md).
