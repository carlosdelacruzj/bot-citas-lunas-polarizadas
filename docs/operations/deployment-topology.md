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
  |-- appointment-bot-admin-api
  |-- dashboard Angular local
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

## Dashboard Angular

Ejecucion local contra el admin API separado:

```powershell
# Terminal 1
scripts/start-worker.ps1

# Terminal 2
appointment-bot-admin-api

# Terminal 3
cd dashboard
npm install
ng serve --proxy-config proxy.conf.json
```

El proxy de desarrollo apunta `/api` y `/health` a
`http://127.0.0.1:8766`, que es el admin API separado. No abrir CORS al inicio.

## Compatibilidad con API embebida

El worker conserva su API embebida en `http://127.0.0.1:8765`. Si se necesita
rollback temporal del dashboard, cambiar `dashboard/proxy.conf.json` a `8765`.
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

Para una lista completa de preparacion, validacion manual, pendientes y
rollback, usar `docs/operations/readiness-checklist.md`.

## Seguridad operativa

- Mantener API en loopback para la primera version.
- No exponer dashboard a Internet.
- No guardar secretos en Angular.
- No versionar `.env`, logs, screenshots, videos, dumps ni `node_modules`.
- Usar `GET /health` para liveness.
- Usar `GET /api/v1/worker` para fase real del worker.
- Usar `worker_commands` para controlar el worker desde procesos que no tienen
  `ContinuousWorker` en memoria.

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
