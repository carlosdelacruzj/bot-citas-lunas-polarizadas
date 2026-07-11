# DB

Estructura futura para conexion, migraciones y repositorios PostgreSQL
compartidos por el worker y el admin API.

Desde el paso 9.3 contiene la implementacion PostgreSQL principal:

- `db.cleanup`
- `db.common`
- `db.connection`
- `db.migrations`
- `db.orders`
- `db.pool`
- `db.reservations`
- `db.runs`
- `db.worker_commands`
- `db.worker_state`

Desde el paso 9.7 se retiraron los wrappers historicos
`services/database_migrations.py` y `services/postgres_*.py`. Los consumidores
internos deben importar directamente desde `appointment_bot.db.*`.

`db/orders.py` todavia concentra ordenes, contactos, pagos, leases y estado de
orden para reducir riesgo operativo. Si se divide mas, hacerlo por subfases
pequenas con validacion completa.
