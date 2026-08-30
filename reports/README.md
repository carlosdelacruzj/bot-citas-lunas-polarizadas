# Reportes generados

Estos archivos son snapshots y logs derivados. No forman parte de la lectura
inicial del proyecto ni sustituyen consultas actuales a PostgreSQL.

- `operations/archive/YYYY-MM/`: cortes semanales; `latest.md` apunta al ultimo
  corte publicado.
- `optimization/archive/YYYY-MM/`: baselines y observaciones; `latest.md` apunta
  solo a la referencia promovida.
- `evidence/monthly/`: indices compactos mensuales; `evidence/daily/` contiene
  agregados y `evidence/index.md` resuelve la historia.
- `evidence/history/`: bitacoras mensuales; las rutas antiguas son indices
  estables hacia cada mes.

Antes de usar una cifra, comprobar fecha de corte, cobertura, dias faltantes y
fuente. Los escritores solo leen el archivo del mes destino; PostgreSQL sigue
siendo la autoridad del runtime.
