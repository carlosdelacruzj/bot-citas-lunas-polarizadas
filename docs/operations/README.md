# Runbook operativo

Ultima verificacion documental: `2026-08-29`.

Este archivo contiene controles seguros y rutas de diagnostico. El estado actual
vive en [`../project-status.md`](../project-status.md); el trabajo futuro, en
[`../roadmap/README.md`](../roadmap/README.md).

## Topologia

Procesos principales:

- Admin API en loopback: dashboard, comandos, schedulers y WhatsApp;
- worker continuo: monitoreo y reservas;
- control Telegram: interfaz movil sobre Admin API;
- supervisor CAPTCHA: opcional, solo si la feature está habilitada;
- PostgreSQL y dependencias externas.

Detalles: [`deployment-topology.md`](deployment-topology.md) y
[`../architecture/current-runtime.md`](../architecture/current-runtime.md).

## Inicio

```powershell
powershell -ExecutionPolicy Bypass -File scripts/start-runtime.ps1
```

Para desarrollo del dashboard:

```powershell
powershell -ExecutionPolicy Bypass -File scripts/start-admin-dashboard.ps1
```

No interpretar un PID o un HTTP `200` aislado como salud funcional.

## Verificacion minima

1. Confirmar PostgreSQL accesible y esquema esperado.
2. Consultar salud de Admin API.
3. Comprobar heartbeat y estado del worker.
4. Verificar Telegram con una actualizacion nueva, no solo proceso vivo.
5. Verificar WhatsApp `session_ready` y ausencia de jobs bloqueados.
6. Revisar submissions, leases, rafagas y sesiones manuales activas.
7. Confirmar frescura de la fuente relevante para la tarea.

Durante la ventana `2026-08-31` a `2026-09-06`, aplicar tambien
[`current-only-observation.md`](current-only-observation.md) antes de retirar
interfaces compatibles.

## Antes de reiniciar

No reiniciar si existe:

- submit o reserva en curso;
- lease activo que no puede drenarse;
- rafaga o reobservacion de cupo abierta;
- sesion manual en `opening`, `active`, `closing` o `close_timeout`;
- trabajo WhatsApp preparando, seleccionando o esperando confirmacion;
- lote de recordatorios o post-cita en ejecucion.

Si el reinicio es seguro, detener y levantar solo el proceso propietario. No
liberar backoffs ni reconciliar jobs como efecto lateral del restart.

## Dashboard

- **Pendientes** usa `/api/v1/operator-inbox`; CAPTCHA queda separado.
- **Ordenes** administra alta, preflight, reglas y detalle.
- **Citas y recordatorios** contiene agenda y post-cita.
- **Mensajes** edita plantillas futuras y muestra trazabilidad.
- **Finanzas** separa cobrado, pendiente, costo y calidad.
- **Actividad** contiene diagnostico, no decisiones comerciales principales.

Un error visual no autoriza alterar contratos del backend. Un build no reemplaza
revision real en navegador.

## Reservas

- una sesion Playwright por cliente;
- screenshot del cupo unico inmediatamente antes de CAPTCHA o submit;
- confirmar solo con evidencia estricta;
- `blocked_by_order_rule` no es fallo general;
- no reintentar submit ambiguo;
- videos locales se graban sin mascaras y son evidencia sensible.

Runbooks activos:

- [`opportunity-bursts.md`](opportunity-bursts.md);
- [`reservation-critical-path.md`](reservation-critical-path.md).

## WhatsApp

Admin API es el unico propietario del perfil. Antes de aislarlo o reiniciarlo,
comprobar jobs, dispatcher y sesiones. No reenviar `uncertain`; preservar
captura, componentes y contexto.

Contrato: [`../contracts/whatsapp.md`](../contracts/whatsapp.md).
Aceptacion natural:
[`whatsapp-natural-acceptance.md`](whatsapp-natural-acceptance.md).

## Recordatorios y post-cita

Los schedulers pertenecen a Admin API. Mantener una sola sesion de solo lectura,
pausas de `4-7` segundos, cap diario `20` y breaker ante ambiguedad. Preparacion,
envio, entrega y lectura permanecen separados.

Contrato: [`../contracts/appointment-followups.md`](../contracts/appointment-followups.md).

## CAPTCHA

El CAPTCHA HTML matematico y el servicio grafico en sombra son sistemas
distintos. El segundo es opcional y está en almacenamiento frio por defecto.
No activarlo, entrenarlo ni promoverlo desde una investigacion ordinaria.

Contrato: [`../contracts/captcha.md`](../contracts/captcha.md).

## Evidencia y reportes

Seguir [`evidence-policy.md`](evidence-policy.md). `evidence-summary.md` y
`evidence-index.csv` son snapshots; `reports/*/latest.md` son punteros o
baselines historicas. Verificar corte y fuente viva antes de concluir.

## Backup y restauracion

La verificacion local de dump y restore esta documentada en
[`postgres-backup-restore.md`](postgres-backup-restore.md). El script crea una
base temporal aislada, compara conteos y elimina sus artefactos; no conserva un
backup ni sustituye el backup externo pendiente.

## Desarrollo reproducible

Dependencias, locks, auditorias, actualizacion, rollback y CI se gobiernan en
[`dependency-management.md`](dependency-management.md). CI usa estado temporal
y nunca consume credenciales ni servicios operativos.

La matriz de riesgos y sus umbrales iniciales se gobiernan en
[`backend-test-policy.md`](backend-test-policy.md).

## Diagnostico por sintoma

| Sintoma | Primera comprobacion |
|---|---|
| Telegram no responde | Admin API, log de bootstrap, offset y una actualizacion nueva. |
| Dashboard carga pero no opera | auth local, Admin API, PostgreSQL y endpoint exacto. |
| Worker no toma orden | estado/preflight, pausa, lease, backoff y comando pendiente. |
| WhatsApp parece enviado | burbuja visible, reloj/check, componentes y resultado tecnico. |
| Reserva no confirma | intento, screenshot, submit y evidencia del portal. |
| Reporte discrepa | fecha de corte, cobertura y consulta PostgreSQL actual. |

## Documentos historicos

Planes cerrados y trazas anteriores se retiraron del working tree. El mecanismo
de recuperacion puntual está en [`../history/README.md`](../history/README.md).
