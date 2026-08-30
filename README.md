# Appointment Bot

Sistema multi-cliente para buscar y reservar citas de lunas polarizadas, operar
ordenes y pagos, y acompañar comunicaciones antes y despues de la cita.

## Antes de trabajar

1. Leer [`docs/project-status.md`](docs/project-status.md).
2. Leer [`docs/roadmap/README.md`](docs/roadmap/README.md).
3. Abrir solo el contrato del dominio desde
   [`docs/README.md`](docs/README.md).

## Arquitectura

- **Admin API**: dashboard, autenticacion local, comandos, schedulers y perfil
  persistente de WhatsApp.
- **Worker**: cola continua y una sesion Playwright aislada por cliente.
- **PostgreSQL**: fuente de verdad de ordenes, reservas, pagos, comandos y
  comunicaciones.
- **Telegram**: cliente operativo de Admin API.
- **n8n**: orquestador externo, sin SQL ni navegador.
- **CAPTCHA sombra**: proceso opcional, inactivo por defecto.

Topologia completa:
[`docs/architecture/current-runtime.md`](docs/architecture/current-runtime.md).

## Requisitos

- Python `3.12`;
- PostgreSQL;
- Playwright Chromium;
- Node.js/npm para el dashboard;
- variables locales basadas en `.env.example`.

No versionar `.env`, credenciales, dumps ni evidencia sensible.

## Instalacion

```powershell
python -m pip install -e .
python -m playwright install chromium

Set-Location dashboard
npm install
```

## Inicio

Runtime supervisado:

```powershell
powershell -ExecutionPolicy Bypass -File scripts/start-runtime.ps1
```

Admin API y dashboard de desarrollo:

```powershell
powershell -ExecutionPolicy Bypass -File scripts/start-admin-dashboard.ps1
```

Entrypoints individuales:

```powershell
appointment-bot-worker
appointment-bot-admin-api
appointment-bot-telegram-control
appointment-bot-client orders
```

Antes de reiniciar procesos persistentes, comprobar submissions, leases,
sesiones, rafagas y trabajos WhatsApp activos. Ver
[`docs/operations/README.md`](docs/operations/README.md).

## Dashboard

```powershell
Set-Location dashboard
npm start
npm run build
```

El proxy de desarrollo usa Admin API. Rutas y convenciones:
[`dashboard/README.md`](dashboard/README.md).

## Configuracion

`.env.example` documenta nombres y valores de referencia. El runtime local puede
diferir; verificar la configuracion activa antes de afirmar horarios, limites o
modos. No modificar `.env` sin autorizacion explicita.

Reglas importantes:

- `MONITOR_WINDOW_SECONDS=0` realiza una sola revision por ejecucion;
- cada cliente usa un contexto Playwright nuevo;
- una restriccion de orden no produce backoff general;
- un submit o envio ambiguo nunca se reintenta automaticamente;
- el precio y tipo de servicio se conservan por orden.

## Validacion

```powershell
python -m compileall -q src
python -m ruff check src tests
python -m pytest -q
powershell -ExecutionPolicy Bypass -File scripts/check-documentation.ps1
git diff --check

Set-Location dashboard
npm run build
```

No agregar tests automatizados salvo pedido explicito. Un build correcto no
sustituye validacion visual o una observacion natural requerida.

## Evidencia y reportes

- Política: [`docs/operations/evidence-policy.md`](docs/operations/evidence-policy.md).
- Resumen generado: [`docs/evidence-summary.md`](docs/evidence-summary.md).
- Indice filtrable: `docs/evidence-index.csv`.
- Historia mensual: [`reports/evidence/index.md`](reports/evidence/index.md).
- Reportes: [`reports/README.md`](reports/README.md).

Los artefactos generados son snapshots; confirmar fecha, cobertura y estado vivo
antes de usarlos para una conclusion actual.
