# Manual Session

Estructura futura para sesiones manuales controladas por el backend, usando una
sesion Playwright nueva y separada de las sesiones del worker.

Por ahora no contiene logica funcional. No debe exponer cookies, passwords,
tokens ni reutilizar contexto del worker. La migracion real se hara por fases
documentadas antes de mover codigo.
