# Manual operativo

Estado: **vigente**.

Ultima verificacion: `2026-08-11`.

Este documento contiene el camino diario de operacion y recuperacion. El estado
general vive en [`../project-status.md`](../project-status.md) y todo trabajo
futuro se prioriza exclusivamente en
[`../roadmap/README.md`](../roadmap/README.md).

## Componentes actuales

```text
AppointmentBotContinuousWorker (tarea programada)
  -> scripts/start-runtime.pyw
     -> scripts/start-runtime.ps1
        |-- scripts/start-worker.ps1
        |-- scripts/start-admin-dashboard.ps1
        |-- scripts/start-telegram-control.ps1
        `-- scripts/start-captcha-shadow.ps1

PostgreSQL 16 en Docker
  |-- worker de reservas: 127.0.0.1:8765
  |-- Admin API + dashboard: 127.0.0.1:8766
  |-- Telegram control -> Admin API
  `-- CAPTCHA local/sombra: 127.0.0.1:8787
```

Los pares `.venv/python.exe -> Python312/python.exe` son el redirector normal
del entorno virtual en Windows, no procesos funcionales duplicados.

n8n `2.22.4` permanece local, fuera del camino crítico y sobre el volumen
durable `n8n_data`. Su puerto debe publicarse exclusivamente como
`127.0.0.1:5678:5678`; un bind vacío o `0.0.0.0:5678` vuelve a exponerlo en la
red. Si se recrea el contenedor, conservar el volumen y comprobar `/healthz` y
la activación de `Appointment Bot - Monitor continuo` antes de retirar el
contenedor anterior.

## Arranque

El camino normal es la tarea programada instalada con:

```powershell
scripts/install-startup-task.ps1
```

Para una recuperacion manual controlada:

```powershell
scripts/start-runtime.ps1
```

Cada supervisor puede iniciarse por separado durante diagnostico:

```powershell
scripts/start-worker.ps1
scripts/start-admin-dashboard.ps1
scripts/start-telegram-control.ps1
scripts/start-captcha-shadow.ps1
```

No iniciar una segunda copia sin comprobar antes la tarea, supervisores,
procesos hijos y puertos.

## Salud y horario

| Superficie | Comprobacion | Lectura |
| --- | --- | --- |
| Worker | `http://127.0.0.1:8765/health` | Vida del proceso durante la ventana operativa. |
| Estado worker | Dashboard `/api/v1/worker` | Fase, orden, error, pausa y proxima revision. |
| Admin API | `http://127.0.0.1:8766/health` | `ok/api_only` significa API viva, no worker activo. |
| CAPTCHA | `http://127.0.0.1:8787/health` | CUDA, modelos residentes y hora de inicio. |
| PostgreSQL | `docker ps` / healthcheck | Contenedor y esquema operativo. |

El worker consulta de lunes a sabado y termina normalmente a las `18:00` con
codigo `0`. `start-worker.ps1` espera hasta las `07:30`. Fuera de ese horario,
un worker no escuchando en `8765` no es por si solo un incidente si el
supervisor sigue vivo, no hay lease/submission y el corte quedo registrado.

## Configuracion vigente del observer

- hasta `15` consultas de sede por sesion;
- espera aleatoria independiente de `1-2` segundos;
- un `reload_probe` despues del intento `8`;
- nueva sesion Playwright por cliente;
- `OBS-006`: maximo dos sesiones concurrentes;
- `OBS-007`: reobservacion unica despues de `slot_lost` explicito;
- V6 opera en canario de hasta `20` decisiones; 2Captcha es fallback automático.

El canario operativo OBS-006/007 y su rollback estan en
[`opportunity-burst-canary-2026-08-09.md`](opportunity-burst-canary-2026-08-09.md).
La seleccion event-driven, sus mediciones y los dos kill switches de rollback
estan en
[`reservation-critical-path-canary-2026-08-11.md`](reservation-critical-path-canary-2026-08-11.md).
Los planes de rendimiento de julio son historia y no describen configuracion
actual.

## Operacion desde dashboard

Abrir `http://127.0.0.1:8766/`.

Flujo normal:

1. **Resumen**: salud, resultado mensual y alertas.
2. **Pendientes**: cobros, contactos y comunicaciones que requieren decision.
3. **Ordenes**: alta, edicion, prioridad, reglas, pago y sesiones manuales.
4. **Post-cita**: lectura administrativa aislada; no reserva ni comunica.
5. **CAPTCHA**: revision humana de la cola sombra; no responde al portal.
6. **Finanzas**: costos PostgreSQL, anulacion auditable y conciliacion.

Una orden lista abre **Sesion manual** en el panel de citas. Una orden no lista
puede usar **Abrir portal** para consulta sin ejecutar automaticamente el flujo
de reserva. Cada navegador se cierra de forma independiente.

Toda fecha visible usa `DD-MM-YYYY`; horas `HH:mm`; timestamps en
`America/Lima`.

## Control remoto por Telegram

La frontera obligatoria es:

```text
Telegram -> Admin API 127.0.0.1:8766 -> PostgreSQL/worker_commands -> worker
```

Telegram no ejecuta SQL ni PowerShell y no accede a una segunda fuente de
datos. El menu permite buscar clientes, crear altas manuales, ajustar prioridad
y reglas, consultar estado y etiquetar CAPTCHA sombra. Conversaciones y botones
vencen; los guardados se vuelven a leer antes de anunciar exito.

La consulta de credenciales completas es una excepcion deliberada para el unico
operador autorizado. Nunca se registran valores en logs o auditoria y debe
minimizarse su permanencia en el chat.

## WhatsApp automatico

Admin API es el unico propietario del perfil persistente. Worker, Telegram y
n8n no deben abrir una segunda sesion WhatsApp.

Tipos vigentes:

- album de reserva + Yape;
- postpago despues de `paid`;
- aviso de preflight;
- resumen diario + imagenes unicas + publicacion TikTok.

Cada trabajo es durable, idempotente y permite un solo intento automatico. Solo
termina `sent` cuando se observa la evidencia saliente exigida para todos sus
componentes. `failed` y `uncertain` nunca se reintentan automaticamente.

Un `uncertain` se revisa con evidencia. No convertirlo en `sent` ni reenviar
solo porque desaparecio una miniatura o regreso la vista del chat. Las
decisiones y trazas actuales estan en:

- [`whatsapp-automatic-triggers-2026-07-25.md`](whatsapp-automatic-triggers-2026-07-25.md);
- [`whatsapp-daily-slot-summary-2026-07-30.md`](whatsapp-daily-slot-summary-2026-07-30.md).

## CAPTCHA local y sombra

Runtime residente actual:

- autoridad canaria: `v6_sequence_candidate`, hasta `20` decisiones reales;
- control en sombra: `v3_selected`;
- fallback del portal: 2Captcha.

V6 solo responde al portal si `min_char_confidence >= 0.60` y
`sequence_confidence_product >= 0.60`, con timeout de `500 ms`. Formato
invalido, baja confianza, timeout, servicio no saludable, circuito abierto o
limite agotado fuerzan 2Captcha. El primer `captcha_invalid`, un resultado
ambiguo o un fallo local abre el circuito; el rollback persistente cambia a
`mode=2captcha` sin editar `.env`. V3 sigue generando evidencia de sombra y no
responde al portal.

V1, V2, V4 y V5 se conservan solo como historia y no consumen GPU. El corte
prospectivo de `500` muestras sigue siendo una revision para decidir si el
canario se amplia o se cierra; no es el estado de autoridad actual ni elimina
el fallback.

El muestreo adicional esta desactivado por defecto y puede agregar cerca de
`0.4 s` por muestra. La integracion completa vive en
[`captcha-shadow-integration.md`](captcha-shadow-integration.md).

## Post-cita

Post-cita abre una sesion Playwright nueva y de solo lectura por orden. Guarda
expediente, placa, etapas y mensajes dentro de la frontera administrativa. No
modifica cola, reserva, CAPTCHA, pago ni comunicaciones.

Los accesos perdidos se conservan como historia y no se reintentan desde la
vista inicial. Antes de recordatorios u ofertas debe definirse consentimiento,
finalidad, retencion y acceso.

Contrato:
[`post-appointment-followup-2026-08-09.md`](post-appointment-followup-2026-08-09.md).

## Recuperacion segura

### Worker

1. Revisar horario, supervisor, health, fase, `current_order_id`, lease y
   submission pendiente.
2. No reiniciar por estar fuera de ventana o en corte diario normal.
3. Si existe submission, detener la intervencion y preservar la sesion.
4. Si el proceso esta realmente caido, reiniciar solo `start-worker.ps1`.
5. Confirmar fase, heartbeat y liberacion de claims.

### Admin API y dashboard

1. Comprobar `8766/health`.
2. Antes de reiniciar, verificar que no haya trabajos WhatsApp `running`.
3. Reiniciar solo `scripts/start-admin-dashboard.ps1`.
4. Validar health, ordenes, Post-cita y endpoints a traves del proxy Angular.

### Telegram

1. Confirmar Admin API disponible.
2. Revisar el ultimo polling/log sin enviar un mensaje de prueba a clientes.
3. Reiniciar solo `scripts/start-telegram-control.ps1`.
4. Ejecutar el check local del modulo si corresponde.

### CAPTCHA

1. Comprobar `8787/health` y modelos.
2. Reiniciar solo `scripts/start-captcha-shadow.ps1`.
3. Confirmar CUDA, `v3_selected`, `v6_sequence_candidate` y outbox.

### PC, Docker y datos

El simulacro disponible:

```powershell
scripts/verify-postgres-backup.ps1
```

prueba restaurabilidad temporal dentro del entorno local; no es una politica
de backup durable. La recuperacion externa cifrada sigue pendiente en el
roadmap.

## Validacion de codigo

Desde la raiz:

```powershell
python -m compileall -q src
python -m ruff check src tests
python -m pytest -q
git diff --check
```

Desde `dashboard/`:

```powershell
npm run build
npm audit --omit=dev
```

El build no sustituye una revision visual real.

## Reportes y evidencia

```powershell
appointment-bot-client weekly-report --start YYYY-MM-DD --end YYYY-MM-DD
appointment-bot-client optimization-observation --start YYYY-MM-DD --end YYYY-MM-DD
```

`latest` significa ultimo artefacto escrito, no necesariamente estado vivo ni
cobertura completa. Antes de comparar, revisar rango, fecha de generacion y
dias faltantes.

La politica de publicacion y retencion esta en
[`evidence-policy.md`](evidence-policy.md). La lectura compacta vive en
[`../evidence-summary.md`](../evidence-summary.md) y
[`../evidence-index.csv`](../evidence-index.csv), ambos snapshots generados que
no equivalen a PostgreSQL vivo.

## Documentos historicos

Los siguientes archivos conservan evidencia, pero no gobiernan la operacion:

- `performance-roadmap-2026-07-22.md`;
- `observer-tuning-2026-07-22.md`;
- `remote-control-plan.md`;
- `whatsapp-manual-trace-2026-07-22.md`;
- `whatsapp-dashboard-trace-2026-07-22.md`;
- `whatsapp-evidence-validation-2026-07-23.md`.

Su clasificacion completa se encuentra en
[`../history/documentation-audit-2026-08-09.md`](../history/documentation-audit-2026-08-09.md).
