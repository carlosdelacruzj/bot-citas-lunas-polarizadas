# Core

Estructura futura para modelos puros, estados compartidos y reglas de negocio
que deban ser usadas por el worker, el admin API y el dashboard.

Contiene la implementacion real de modelos, estados y reglas puras:

- `core.models`
- `core.rules`
- `core.statuses`
- `core.contacts`
- `core.documents`
- `core.order_priority`

Los consumidores internos importan directamente desde el modulo propietario;
el paquete `core` no reexporta simbolos.
