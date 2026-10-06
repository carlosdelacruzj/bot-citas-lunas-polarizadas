# AGENTS.md

Instrucciones para Codex, agentes de IA y contribuidores.

## Lectura obligatoria

Antes de implementar cualquier cambio, leer completos:

1. `docs/project-status.md`: capacidad y limites actuales.
2. `docs/roadmap/README.md`: unica lista de trabajo pendiente.

No leer por defecto `docs/history/`, `reports/`, `docs/evidence-index.csv` ni
`docs/evidence-summary.md`. `.ignore` y `codegraph.json` los excluyen de
busquedas e indexacion ordinarias. Abrir una ruta explicita solo cuando la tarea
necesite evidencia fechada.

Despues, abrir solamente las referencias del dominio afectado:

| Tarea | Lectura adicional |
|---|---|
| Runtime, despliegue o reinicio | `docs/operations/README.md`, `docs/architecture/current-runtime.md` |
| API, Telegram o n8n | `docs/contracts/admin-api.md`, `docs/contracts/worker-control.md` |
| Ordenes, pagos o dashboard | `docs/contracts/order-lifecycle.md` y contrato del dominio |
| Reservas o CAPTCHA | `docs/contracts/reservation-safety.md`, `docs/contracts/captcha.md` |
| WhatsApp | `docs/contracts/whatsapp.md` |
| Finanzas | `docs/contracts/finance.md` |
| Evidencia | `docs/operations/evidence-policy.md` |

Usar busqueda o Graph para localizar simbolos y consumidores antes de recorrer
modulos completos. No quitar exclusiones para una consulta ordinaria.

## Mantenimiento documental

- `project-status.md` describe solo el presente y debe permanecer bajo `250`
  lineas.
- `roadmap/README.md` contiene solo trabajo futuro y debe permanecer bajo `180`
  lineas.
- No agregar bitacoras cronologicas: reemplazar el estado anterior. Git conserva
  el detalle; `docs/history/milestones.md` resume solo decisiones durables.
- Al cerrar un cambio relevante, actualizar estado o roadmap solo si vario una
  capacidad, validacion, riesgo, metrica, tarea o prioridad.
- Contratos describen invariantes; operaciones explica como actuar; historial
  no gobierna el runtime.
- Documentos generados deben declarar fecha de corte y nunca presentarse como
  estado vivo.

## Reglas del proyecto

- No guardar credenciales reales en el repositorio.
- No modificar `.env` salvo pedido explicito.
- No agregar tests automatizados salvo pedido explicito.
- Mantener el proyecto simple, modular y facil de leer.
- Codigo en ingles; documentacion del proyecto en espanol.
- Python `3.12`.
- Comentarios solo cuando aclaren una decision no obvia.
- Guardar screenshot cuando falle un paso importante.
- Preferir errores claros antes que silencios o reintentos infinitos.
- `MONITOR_WINDOW_SECONDS=0` conserva una sola revision por ejecucion.
- n8n es orquestador externo; alertas principales y screenshots salen del bot.
- La cola multi-cliente usa una sesion Playwright nueva por cliente.
- PostgreSQL guarda historial, estado y credenciales; no versionar dumps reales.

Separacion de responsabilidades vigente:

- `core/`: modelos y reglas puras.
- `db/`: persistencia y migraciones.
- `reservation_engine/`: portal, seleccion, CAPTCHA y submit.
- `worker/`: cola, leases, controles y supervision continua.
- `services/`: API, Telegram, WhatsApp, schedulers y notificaciones.
- `reports/`: artefactos generados y agregados.
- `browser/` y `utils/`: infraestructura compartida.

## Seguridad operativa

- No reintentar automaticamente un submit o envio WhatsApp ambiguo.
- Antes de reiniciar, comprobar submissions, leases, sesiones, rafagas y
  trabajos WhatsApp activos.
- Telegram y n8n pasan por Admin API; no ejecutan SQL ni PowerShell.
- Una restriccion de fecha produce `partial / blocked_by_order_rule`, no backoff
  general.
- Preservar el screenshot de cada cupo unico antes de CAPTCHA o submit.

## Comandos habituales

```powershell
python -m pip install -e .
python -m playwright install chromium
appointment-bot-worker
appointment-bot-client orders
```

Validacion base:

```powershell
python -m compileall -q src
python -m ruff check src tests
python -m pytest -q
powershell -ExecutionPolicy Bypass -File scripts/check-documentation.ps1
git diff --check
```

Dashboard:

```powershell
Set-Location dashboard
npm run build
```
