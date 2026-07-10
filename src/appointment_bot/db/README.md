# DB

Estructura futura para conexion, migraciones y repositorios PostgreSQL
compartidos por el worker y el admin API.

Desde el paso 9.1 contiene fachadas publicas de compatibilidad:

- `db.connection`
- `db.migrations`
- `db.orders`
- `db.reservations`
- `db.runs`
- `db.worker_state`

Estas rutas reexportan implementacion existente desde `services/postgres_*` y
`services/database_migrations.py`. No reemplazan todavia a los imports actuales
ni cambian schema, conexion o migraciones.
