# Reports

Estructura futura para reportes, evidencia resumida, fichas operativas y
salidas administrativas reutilizables.

Desde el paso 9.1 contiene fachadas publicas de compatibilidad:

- `reports.evidence`
- `reports.optimization`
- `reports.status`

Estas rutas reexportan implementacion existente desde `services/status_reports.py`,
`services/evidence_summary.py` y `services/optimization_log.py`. No reemplazan
todavia a los imports actuales ni cambian formatos de reportes o rutas de
salida.
