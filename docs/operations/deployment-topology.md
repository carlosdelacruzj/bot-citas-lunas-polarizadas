# Topologia operativa

Estado: vigente. Ultima verificacion: `2026-08-30`.

Este documento describe como iniciar, verificar y recuperar la topologia actual.

## Topologia heredada de rollback

```text
scripts/start-worker.ps1
  -> docker compose up -d
  -> appointment-bot-worker
       -> ContinuousWorker
       -> API local embebida
  -> PostgreSQL
  -> n8n supervisa externamente
```

Esta topologia embebida ya no es la arquitectura administrativa principal. Se
conserva solo como rollback local: el worker y la API de `8765` comparten
memoria con `ContinuousWorker`.

## Topologia actual

```text
PostgreSQL
  |-- appointment-bot-worker
  |-- appointment-bot-admin-api + dashboard + WhatsApp + schedulers
  |-- appointment-bot-telegram-control
  |-- captcha-shadow opcional
  |-- n8n monitor externo temporal durante la comparacion
```

El admin API y el worker comparten base y modulos `core`/`db`, pero no memoria.
Los comandos al worker deben persistirse antes de consumirse.

## Ejecucion manual minima del worker

```powershell
python -m pip install -e .
python -m playwright install chromium
docker compose up -d
appointment-bot-worker
```

En Windows, el camino recomendado sigue siendo:

```powershell
scripts/start-worker.ps1
```

En la maquina operativa, la tarea programada `AppointmentBotContinuousWorker`
ejecuta `scripts/start-runtime.pyw` con `pythonw.exe` al iniciar sesion. Ese host
sin consola ejecuta `scripts/start-runtime.ps1`, que inicia
el bootstrap del worker, `scripts/start-admin-dashboard.ps1`,
`scripts/start-telegram-control.ps1` y, solo cuando
`CAPTCHA_SHADOW_SERVICE_ENABLED=true`, `scripts/start-captcha-shadow.ps1` en
segundo plano. Cada bootstrap habilitado supervisa y reinicia su proceso sin
compartir memoria con los demás.

La tarea se crea o recupera con `scripts/install-startup-task.ps1`. Este diseno
no usa Windows Script Host, VBS ni `ExecutionPolicy Bypass`, y no deja una
ventana de `cmd` o PowerShell abierta en el escritorio.
El lanzador permanece como supervisor raíz de tres procesos obligatorios y del
CAPTCHA opcional, y comprueba su presencia cada 15 segundos. Si un supervisor
habilitado desaparece, inicia solo ese componente. La tarea programada permanece
`Running` y sus reglas de reinicio vuelven a ser efectivas si el propio
supervisor raíz termina.

## Procesos administrativos

Ejecucion local recomendada en tres procesos obligatorios y uno opcional:

```powershell
# Terminal 1
scripts/start-worker.ps1

# Terminal 2
scripts/start-admin-dashboard.ps1

# Terminal 3
scripts/start-telegram-control.ps1

# Terminal 4, solo con CAPTCHA_SHADOW_SERVICE_ENABLED=true
scripts/start-captcha-shadow.ps1
```

Abrir `http://127.0.0.1:8766/`. El admin API sirve el build Angular y entrega
una sesion local `HttpOnly`/`SameSite=Strict` para autorizar `/api/v1` sin
guardar el token en el navegador. Este modo solo acepta loopback y no abre CORS.

## Rollback y desarrollo

Para desarrollo del dashboard, ejecutar `appointment-bot-admin-api` y `npm
start` dentro de `dashboard/`. El proxy `dashboard/proxy.conf.cjs` conserva la
inyeccion del token fuera de Angular y apunta a `127.0.0.1:8766`.

## Compatibilidad con API embebida

El worker conserva su API embebida en `http://127.0.0.1:8765`. Si se necesita
rollback temporal del dashboard, cambiar `dashboard/proxy.conf.cjs` a `8765`.
Para validar la arquitectura vigente, usar `8766`. La API embebida puede
desactivarse reversiblemente con `WORKER_EMBEDDED_API_ENABLED=false`, pero solo
despues de retirar sus consumidores y completar una ventana operativa.

Telegram Control puede vigilar el lease real mediante
`TELEGRAM_WORKER_MONITOR_ENABLED=true`. Consulta autenticadamente
`GET /api/v1/worker` cada cinco minutos entre `07:30` y `18:00`, alerta tras tres
fallos consecutivos y no ejecuta reinicios. Mientras se compara con el workflow
anterior, mantener n8n y `8765` activos.

No levantar el admin API fuera de loopback sin `APPOINTMENT_BOT_API_TOKEN`.
No cambiar `.env` para pruebas temporales; usar variables de entorno de la
terminal cuando se necesite modificar host, puerto o sesion manual.

Validacion minima de esta topologia:

```powershell
Invoke-WebRequest http://127.0.0.1:8766/health
cd dashboard
npm run build
cd ..
python -m compileall src
python -m ruff check src tests
python -m pytest
```

Para el estado validado y el orden de trabajo usar `docs/project-status.md` y
`docs/roadmap/README.md`. Este archivo conserva solamente arranque y rollback.

## Seguridad operativa

- Mantener API en loopback para la primera version.
- No exponer dashboard a Internet.
- No guardar secretos en Angular.
- No versionar `.env`, logs, screenshots, videos, dumps ni `node_modules`.
- Usar `GET /health` para liveness.
- Usar `GET /api/v1/worker` para fase real y lease vigente del worker.
- Usar `worker_commands` para controlar el worker desde procesos que no tienen
  `ContinuousWorker` en memoria.
- Autorizar el receptor de Telegram con una lista explicita de `chat_id` y no
  registrar identificadores completos en logs.

## Rollback

Si una fase falla:

1. detener solo el nuevo proceso agregado en esa fase;
2. dejar `scripts/start-worker.ps1` y `appointment-bot-worker` como camino
   operativo;
3. revertir el commit de la fase;
4. validar `python -m compileall src`, `python -m ruff check src tests` y
   `python -m pytest`.

No mezclar cambios de topologia con cambios de reserva o schema en un mismo
commit.
