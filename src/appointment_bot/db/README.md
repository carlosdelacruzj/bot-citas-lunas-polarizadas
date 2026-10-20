# Persistencia

Repositorios PostgreSQL, esquema y migraciones del dominio. Este paquete
conserva ordenes, pagos, reservas, intentos, comandos, finanzas, recordatorios,
post-cita, oportunidades y comunicaciones.

La API y el worker consumen funciones de dominio; no deben duplicar SQL ni
inferir el esquema desde reportes. Revisar la version de esquema activa antes de
una correccion dependiente de columnas.

No guardar dumps ni credenciales reales en el repositorio.
