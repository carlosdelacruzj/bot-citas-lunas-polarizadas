# Topologia operativa

Este documento describe como correr el sistema durante y despues de la
migracion.

## Topologia actual

```text
scripts/start-worker.ps1
  -> docker compose up -d
  -> appointment-bot-worker
       -> ContinuousWorker
       -> API local embebida
  -> PostgreSQL
  -> n8n supervisa externamente
```

El worker y la API local viven en el mismo proceso Python. La API puede
controlar el worker porque comparte memoria con `ContinuousWorker`.

## Topologia objetivo

```text
PostgreSQL
  |-- appointment-bot-worker
  |-- appointment-bot-admin-api + dashboard Angular local
  |-- appointment-bot-telegram-control
  |-- n8n supervisor externo
```

El admin API y el worker comparten base y modulos `core`/`db`, pero no memoria.
Los comandos al worker deben persistirse antes de consumirse.

## Ejecucion actual

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
ejecuta `scripts/start-runtime.ps1` directamente al iniciar sesion. Ese lanzador inicia
el bootstrap del worker, `scripts/start-admin-dashboard.ps1`,
`scripts/start-telegram-control.ps1` y `scripts/start-captcha-shadow.ps1` en
segundo plano. Cada bootstrap supervisa y reinicia su proceso sin compartir
memoria con los demas.

La tarea se crea o recupera con `scripts/install-startup-task.ps1`. Este diseno
no usa Windows Script Host ni `ExecutionPolicy Bypass`.
El lanzador termina despues de crear los cuatro supervisores independientes,
por lo que ninguna consola de instalacion permanece como propietaria del worker.

## Procesos administrativos

Ejecucion local recomendada en tres procesos:

```powershell
# Terminal 1
scripts/start-worker.ps1

# Terminal 2
scripts/start-admin-dashboard.ps1

# Terminal 3
scripts/start-telegram-control.ps1

# Terminal 4
scripts/start-captcha-shadow.ps1
```

Abrir `http://127.0.0.1:8766/`. El admin API sirve el build Angular y entrega
una sesion local `HttpOnly`/`SameSite=Strict` para autorizar `/api/v1` sin
guardar el token en el navegador. Este modo solo acepta loopback y no abre CORS.

## Rollback y desarrollo

Para volver al modo de tres terminales, ejecutar `appointment-bot-admin-api` y
`npm start` dentro de `dashboard/`. El proxy `dashboard/proxy.conf.cjs` conserva
la inyeccion del token fuera de Angular y apunta a `127.0.0.1:8766`.

## Compatibilidad con API embebida

El worker conserva su API embebida en `http://127.0.0.1:8765`. Si se necesita
rollback temporal del dashboard, cambiar `dashboard/proxy.conf.cjs` a `8765`.
Para validar la arquitectura objetivo, usar `8766`.

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
