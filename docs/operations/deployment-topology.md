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

## Dashboard Angular futuro

Primera version local:

```powershell
# Terminal 1
scripts/start-worker.ps1

# Terminal 2
cd dashboard
npm install
ng serve --proxy-config proxy.conf.json
```

El proxy de desarrollo debe apuntar `/api` y `/health` a
`http://127.0.0.1:8765`. No abrir CORS al inicio.

## Seguridad operativa

- Mantener API en loopback para la primera version.
- No exponer dashboard a Internet.
- No guardar secretos en Angular.
- No versionar `.env`, logs, screenshots, videos, dumps ni `node_modules`.
- Usar `GET /health` para liveness.
- Usar `GET /api/v1/worker` para fase real del worker.

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
