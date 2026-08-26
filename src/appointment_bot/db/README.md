# DB

Estructura futura para conexion, migraciones y repositorios PostgreSQL
compartidos por el worker y el admin API.

Desde el paso 9.3 contiene la implementacion PostgreSQL principal:

- `db.cleanup`
- `db.common`
- `db.connection`
- `db.migrations`
- `db.order_contacts`
- `db.order_credentials`
- `db.order_queue`
- `db.order_state`
- `db.orders`
- `db.pool`
- `db.reservations`
- `db.runs`
- `db.worker_commands`
- `db.remote_control_audit`
- `db.whatsapp_message_templates`
- `db.worker_state`

Desde el paso 9.7 se retiraron los wrappers historicos
`services/database_migrations.py` y `services/postgres_*.py`. Los consumidores
internos deben importar directamente desde `appointment_bot.db.*`.

Desde el P2 de backend, `db.orders` es una fachada de compatibilidad. La
implementacion se divide por responsabilidad entre `order_credentials`,
`order_contacts`, `order_state` y `order_queue`.
