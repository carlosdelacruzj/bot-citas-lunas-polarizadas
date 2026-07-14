# Reports

Estructura futura para reportes, evidencia resumida, fichas operativas y
salidas administrativas reutilizables.

Desde el paso 9.6 contiene la implementacion de reportes y evidencia:

- `reports.evidence`
- `reports.optimization`
- `reports.run_reporting`
- `reports.status`

Estas rutas generan o actualizan:

- historial final de corridas;
- indice y resumen compacto de evidencia;
- bitacoras de optimizacion y disponibilidad parcial;
- fichas de estado y reporte diario.

El indice compacto aplica un criterio operativo: una disponibilidad parcial
solo se conserva si incluye fecha y hora seleccionables o explica un bloqueo,
un intento final o una defensa. Las fechas sin hora quedan en PostgreSQL/logs,
pero no se presentan como evidencia util.

Desde el paso 9.7 se retiraron las rutas antiguas `services/run_reporting.py`,
`services/status_reports.py`, `services/evidence_summary.py` y
`services/optimization_log.py`. Los consumidores internos deben importar
directamente desde `appointment_bot.reports.*`.

No cambiar aqui los formatos ni rutas de salida historicas:

- `docs/evidence-index.csv`
- `docs/evidence-summary.md`
- `reports/evidence/history/reservation-optimization-log.md`
- `reports/evidence/history/partial-availability-log.md`
- `reports/status/`
- `reports/daily/`
