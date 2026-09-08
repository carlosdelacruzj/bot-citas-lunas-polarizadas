# Despliegue y recuperacion local

Estado: vigente. Ultima verificacion: `2026-08-30`.

Este runbook contiene arranque, comprobacion, desarrollo y rollback. La
propiedad de procesos, dependencias y fronteras vive exclusivamente en
[`../architecture/current-runtime.md`](../architecture/current-runtime.md).

## Arranque recomendado en Windows

La tarea programada `AppointmentBotContinuousWorker` ejecuta
`scripts/start-runtime.pyw` con `pythonw.exe` al iniciar sesion. El lanzador
invoca `scripts/start-runtime.ps1`, mantiene un supervisor raiz y comprueba los
componentes cada 15 segundos.

La tarea se crea o recupera con:

```powershell
powershell -ExecutionPolicy Bypass -File scripts/install-startup-task.ps1
```

El arranque normal es:

```powershell
powershell -ExecutionPolicy Bypass -File scripts/start-runtime.ps1
```

Este camino levanta los supervisores de worker, Admin API/dashboard y Telegram.
CAPTCHA sombra solo se incluye cuando su feature esta habilitada. Si un
supervisor termina, el lanzador inicia solamente ese componente.

No interpretar una tarea `Running`, un PID o un HTTP `200` aislado como salud
funcional.

## Arranque manual por componente

Para diagnostico controlado:

```powershell
powershell -ExecutionPolicy Bypass -File scripts/start-worker.ps1
powershell -ExecutionPolicy Bypass -File scripts/start-admin-dashboard.ps1
powershell -ExecutionPolicy Bypass -File scripts/start-telegram-control.ps1
```

CAPTCHA sombra es opcional:

```powershell
powershell -ExecutionPolicy Bypass -File scripts/start-captcha-shadow.ps1
```

No iniciar un segundo propietario del mismo componente. Admin API es el unico
proceso autorizado para poseer el perfil persistente de WhatsApp.

## Verificacion despues del arranque

1. Confirmar PostgreSQL y `schema_version` esperado.
2. Consultar `http://127.0.0.1:8766/health`.
3. Consultar la fase y lease reales del worker mediante Admin API.
4. Verificar Telegram con una actualizacion nueva.
5. Verificar WhatsApp `session_ready`, no solo el proceso.
6. Revisar jobs, submissions, leases, rafagas y sesiones manuales activas.
7. Abrir `http://127.0.0.1:8766/` y comprobar la superficie afectada.

La API embebida del worker en `8765` es compatibilidad de rollback. Para validar
la topologia vigente usar `8766`.

## Desarrollo del dashboard

Ejecutar Admin API y, dentro de `dashboard/`:

```powershell
npm start
```

`dashboard/proxy.conf.cjs` apunta a `127.0.0.1:8766` e inyecta el token fuera de
Angular. No guardar secretos en el bundle ni cambiar `.env` para una prueba
temporal.

## Antes de reiniciar

No reiniciar mientras exista una reserva o submit en curso, lease no drenable,
rafaga abierta, sesion manual, trabajo WhatsApp activo o lote de
recordatorios/post-cita en ejecucion.

Si es seguro, reiniciar solo el proceso propietario. No liberar backoff,
conciliar trabajos ni reenviar como efecto lateral.

## Rollback

Ante un fallo:

1. detener solo el componente nuevo o afectado;
2. conservar worker y PostgreSQL si siguen saludables;
3. volver temporalmente al camino de compatibilidad documentado;
4. revertir el commit del dominio;
5. repetir salud, fase, leases y validacion tecnica.

No mezclar cambios de topologia con reserva o esquema en un mismo commit.

## Validacion tecnica

```powershell
python -m compileall -q src
python -m ruff check src tests
python -m pytest -q
Push-Location dashboard
npm run build
Pop-Location
git diff --check
```

El runbook general de diagnostico esta en [`README.md`](README.md).
