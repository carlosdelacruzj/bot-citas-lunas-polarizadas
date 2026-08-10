# Auditoria documental integral del 09-08-2026

Estado: corte historico de clasificacion.

Este archivo registra la revision de los `40` archivos que existian bajo
`docs/` al comenzar la consolidacion. No es una lista de trabajo y no reemplaza
[`../project-status.md`](../project-status.md) ni
[`../roadmap/README.md`](../roadmap/README.md).

## Criterios

- **Rector:** gobierna estado u orden futuro.
- **Vigente:** contrato, politica o runbook aplicable a la operacion actual.
- **Vigente con correccion:** conserva autoridad, pero tenia contenido
  incompleto o contradictorio.
- **Historico:** evidencia fechada; no describe configuracion actual.
- **Supersedido:** fue reemplazado; se conserva solo por trazabilidad.
- **Generado:** snapshot regenerable; no equivale a estado vivo.

## Documentos rectores y raiz

| Documento | Clasificacion | Decision del corte |
| --- | --- | --- |
| `docs/README.md` | Vigente con correccion | Mantener como mapa documental y explicitar autoridad/clasificacion. |
| `docs/project-status.md` | Rector | Mantener como unica verdad de capacidades, validaciones y riesgos. |
| `docs/roadmap/README.md` | Rector | Reescribir como unica cola futura, sin fases completadas extensas. |
| `docs/optimization.md` | Vigente con correccion | Mantener metodologia y baseline; corregir que OBS-006 ya introdujo concurrencia controlada. |
| `docs/evidence-summary.md` | Generado | Declarar corte, cobertura y que no representa totales comerciales vivos. |
| `docs/evidence-index.csv` | Generado | Mantener como indice logico; una ruta sanitizada no garantiza artefacto disponible. |
| `docs/business-investment-assessment-2026-07-12.md` | Historico | Conservar como fotografia economica; no actualizar sus cifras. |
| `docs/incidente-validacion-identidad-2026-07-15.md` | Historico | Conservar causa, correccion y guardas; enlazar desde el mapa. |
| `docs/incidente-backoff-reglas-fecha-2026-07-24.md` | Historico parcialmente supersedido | Conservar incidente; marcar retirada de la restriccion horaria. |

## Arquitectura

| Documento | Clasificacion | Decision del corte |
| --- | --- | --- |
| `docs/architecture/README.md` | Vigente con correccion | Convertir en indice con estado y autoridad de cada documento. |
| `docs/architecture/current-runtime.md` | Vigente con correccion | Mantener runtime tecnico; sus rutas son inventario orientativo, no exhaustivo. |
| `docs/architecture/target-architecture.md` | Supersedido | El objetivo fue alcanzado; conservar reglas unicas y tratarlo como resultado historico. |
| `docs/architecture/migration-plan-worker-admin-api.md` | Historico | Conservar secuencia 1-9.7 y razones de migracion; no usar como roadmap. |

## Contratos

| Documento | Clasificacion | Decision del corte |
| --- | --- | --- |
| `docs/contracts/README.md` | Vigente con correccion | Enlazar todos los contratos y declarar su estado. |
| `docs/contracts/admin-api.md` | Vigente con correccion | Mantener autenticacion y DTO; aclarar que el inventario de rutas no es exhaustivo. |
| `docs/contracts/worker-control.md` | Vigente con correccion | Actualizar entrypoint, fases y separacion entre liveness y estado operativo. |
| `docs/contracts/order-lifecycle.md` | Vigente con correccion | Alinear WhatsApp automatico, pagos parciales/incobrables y canario. |
| `docs/contracts/reservation-safety.md` | Vigente con correccion | Alinear jerarquia de confirmacion: exito explicito primario, `Programado` respaldo. |
| `docs/contracts/captcha-shadow-dashboard.md` | Vigente con correccion | Abrir con v3/v6 y gate `500/>99%`; tratar V1/V2/V4 como historia. |
| `docs/contracts/finance.md` | Vigente | Mantener como autoridad semantica financiera. |

## Operacion

| Documento | Clasificacion | Decision del corte |
| --- | --- | --- |
| `docs/operations/README.md` | Vigente con correccion | Reducir a runbook actual: cuatro supervisores, `15/1-2/8`, salud y recuperacion. |
| `docs/operations/deployment-topology.md` | Vigente con correccion | Sustituir topologia embebida por runtime separado; mantener legado solo como rollback. |
| `docs/operations/evidence-policy.md` | Vigente con correccion | Ampliar datos prohibidos y distinguir snapshot de evidencia viva. |
| `docs/operations/opportunity-burst-canary-2026-08-09.md` | Vigente | Conservar como contrato del experimento activo y su rollback. |
| `docs/operations/post-appointment-followup-2026-08-09.md` | Vigente | Conservar limites read-only y privacidad; sanear casos identificables. |
| `docs/operations/captcha-shadow-integration.md` | Vigente con historia acumulada | Poner v3/v6 y autoridad 2Captcha al inicio; marcar benchmarks viejos como historia. |
| `docs/operations/whatsapp-automatic-triggers-2026-07-25.md` | Vigente con historia acumulada | Conservar emisor unico, idempotencia y `uncertain`; sanear identificadores. |
| `docs/operations/whatsapp-daily-slot-summary-2026-07-30.md` | Vigente con historia acumulada | Conservar contrato actual y reconciliaciones como evidencia fechada. |
| `docs/operations/public-slot-evidence-cloudinary-plan-2026-08-01.md` | Plan condicional | Mantener como diseño no autorizado para esta fase. |
| `docs/operations/remote-control-plan.md` | Supersedido como plan | Conservar implementacion historica; la operacion actual vive en el runbook. |
| `docs/operations/performance-roadmap-2026-07-22.md` | Supersedido | Conservar baseline; calendario, gate `200/98%` e intervalos no gobiernan. |
| `docs/operations/observer-tuning-2026-07-22.md` | Historico | Conservar experimento `3->4` y `8-13 s`; no usar como configuracion. |
| `docs/operations/whatsapp-manual-trace-2026-07-22.md` | Historico | Conservar linea base manual. |
| `docs/operations/whatsapp-dashboard-trace-2026-07-22.md` | Historico | Conservar trazado de validacion cerrado. |
| `docs/operations/whatsapp-evidence-validation-2026-07-23.md` | Historico | Conservar transicion manual a automatica; no usar como runbook. |

## Finanzas e historia

| Documento | Clasificacion | Decision del corte |
| --- | --- | --- |
| `docs/finance/README.md` | Vigente con correccion | Alinear categoria `captcha` y tipos `prepaid_topup/prepaid_consumption`. |
| `docs/finance/cost-register.csv` | Historico | Mantener solo como antecedente/importacion; PostgreSQL gobierna. |
| `docs/finance/ai-analysis-handoff-2026-07-16.md` | Supersedido | Conservar como snapshot historico; precio y cifras no son vigentes. |
| `docs/history/milestones.md` | Historico | Conservar secuencia de hitos; sanear identificadores. |
| `docs/history/roadmap-completed-2026-07-12.md` | Historico | Conservar fases cerradas fuera del roadmap activo. |

## Hallazgos transversales

1. No habia enlaces Markdown rotos entre los documentos revisados, pero varios
   indices no enlazaban referencias vigentes.
2. Los planes de rendimiento y observer de julio conservaban decisiones futuras
   ya supersedidas por `15/1-2/8`, OBS-006/007 y el gate CAPTCHA `500/>99%`.
3. El manual operativo mezclaba WhatsApp asistido con automatizacion durable.
4. Contratos de worker, reserva, lifecycle y CAPTCHA habian quedado atras del
   runtime actual.
5. `latest` no garantiza vigencia: cada reporte debe declarar rango y cobertura.
6. Las bitacoras historicas versionadas todavia exponian nombres, `order_id` y
   respuestas CAPTCHA. El arbol actual se sanea en este corte; el historial Git
   anterior solo puede reescribirse mediante una operacion separada y autorizada.

## Politica de retiro

No se elimino ningun documento en este corte porque todos conservaban contexto,
contratos o evidencia unica. Un archivo solo puede retirarse cuando su contenido
unico fue migrado, sus enlaces fueron actualizados, no conserva evidencia
necesaria y el cambio supera la validacion documental. Hasta entonces se marca
historico o supersedido y Git conserva la trazabilidad.
