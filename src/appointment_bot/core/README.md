# Core

Estructura futura para modelos puros, estados compartidos y reglas de negocio
que deban ser usadas por el worker, el admin API y el dashboard.

Desde el paso 9.2 contiene la implementacion real de modelos, estados y reglas
puras:

- `core.models`
- `core.rules`
- `core.statuses`

Los modulos historicos `domain.py`, `services/database_models.py` y
`services/order_selection.py` permanecen como wrappers de compatibilidad. La
adopcion de imports directos desde `core/` debe hacerse por tandas posteriores.
