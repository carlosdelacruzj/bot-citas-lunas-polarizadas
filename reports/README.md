# Reportes generados

Estos archivos son snapshots y logs derivados. No forman parte de la lectura
inicial del proyecto ni sustituyen consultas actuales a PostgreSQL.

- `operations/`: cortes semanales; `latest.md` es el ultimo artefacto escrito.
- `optimization/`: baselines y observaciones fechadas.
- `evidence/`: exportaciones historicas y logs append-only.

Antes de usar una cifra, comprobar fecha de corte, cobertura, dias faltantes y
fuente. Los dos logs bajo `evidence/history/` son append-only y deben rotarse por
periodo cuando se implemente la politica de retencion; no se leen completos para
una consulta ordinaria.
