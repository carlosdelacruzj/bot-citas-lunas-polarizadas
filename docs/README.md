# Mapa de documentacion

Ultima clasificacion: `2026-08-29`.

La documentacion se organiza por autoridad. Una fecha reciente no convierte un
reporte en contrato y un documento historico nunca crea trabajo pendiente.

## Punto de entrada

Leer siempre, en este orden:

1. [`project-status.md`](project-status.md): como funciona el sistema hoy.
2. [`roadmap/README.md`](roadmap/README.md): que sigue y en que prioridad.

Para el resto, abrir solo el dominio de la tarea.

## Documentos vigentes

| Tipo | Ubicacion | Proposito |
|---|---|---|
| Arquitectura | [`architecture/current-runtime.md`](architecture/current-runtime.md) | Procesos, fronteras y dependencias actuales. |
| Contratos | [`contracts/README.md`](contracts/README.md) | Invariantes que el codigo no debe romper. |
| Operacion | [`operations/README.md`](operations/README.md) | Arranque, diagnostico, reinicio y recuperacion. |
| Finanzas | [`finance/README.md`](finance/README.md) | Registro cotidiano y checklist de cierre mensual. |
| Negocio | [`resumen-del-negocio.md`](resumen-del-negocio.md) | Oferta y lectura comercial estable. |
| Evidencia | [`operations/evidence-policy.md`](operations/evidence-policy.md) | Privacidad, cobertura y uso de artefactos. |

## Lectura por tarea

| Si vas a cambiar | Lee tambien |
|---|---|
| API, Telegram o n8n | `contracts/admin-api.md`, `contracts/worker-control.md` |
| Ordenes o pagos | `contracts/order-lifecycle.md`, `contracts/finance.md` |
| Reservas | `contracts/reservation-safety.md` |
| Recordatorios o post-cita | `contracts/appointment-followups.md` |
| CAPTCHA | `contracts/captcha.md` |
| WhatsApp | `contracts/whatsapp.md` |
| Optimizacion del monitor | `contracts/optimization.md` |
| Runtime o reinicios | `operations/README.md`, `architecture/current-runtime.md` |
| Evidencia o reportes | `operations/evidence-policy.md` |

## Historico

[`history/`](history/) conserva un resumen de decisiones durables y explica cómo
recuperar desde Git migraciones, planes, incidentes y auditorias retirados. No
gobierna operacion ni prioridad. Su indice está en
[`history/README.md`](history/README.md).

El detalle completo se conserva en Git. No leer el historial salvo que una
investigacion necesite cronologia o evidencia de una decision antigua.

## Documentos generados

- `evidence-summary.md` y `evidence-index.csv` son snapshots del mes activo y
  permanecen en `docs/` porque esa ruta es contrato del generador.
- `reports/evidence/index.md` resuelve indices y agregados mensuales antiguos.
- `reports/` contiene cortes operativos, de optimizacion y salidas de evidencia.
- Un archivo llamado `latest.md` es un puntero a un corte publicado, no prueba
  de estado vivo.

Los generados no forman parte de la lectura inicial y sus cifras deben
refrescarse antes de una conclusion actual. `.ignore` y `codegraph.json` los
excluyen de busquedas e indexacion ordinarias.

## Reglas editoriales

- Estado: presente, sin cronologia, maximo `250` lineas.
- Roadmap: futuro accionable, sin tareas cerradas, maximo `180` lineas.
- Contrato: reglas vigentes y fuente de verdad en codigo o datos.
- Runbook: pasos operativos seguros y reversibles.
- Historial: resultado cerrado con fecha y sin autoridad operativa.
- Generado: fecha de corte, cobertura y limites visibles.

Al actualizar una capacidad, reemplazar la descripcion anterior. El detalle de
implementacion se mueve a historial en vez de acumularse al final.

Validacion local:

```powershell
powershell -ExecutionPolicy Bypass -File scripts/check-documentation.ps1
```
