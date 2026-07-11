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

Las rutas antiguas `services/run_reporting.py`, `services/status_reports.py`,
`services/evidence_summary.py` y `services/optimization_log.py` son wrappers
explicitos durante la transicion.

No cambiar aqui los formatos ni rutas de salida historicas:

- `docs/evidence-index.csv`
- `docs/evidence-summary.md`
- `docs/reservation-optimization-log.md`
- `docs/partial-availability-log.md`
- `reports/status/`
- `reports/daily/`
