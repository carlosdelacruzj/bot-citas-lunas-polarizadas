# Dashboard

Aqui vivira el frontend Angular del dashboard administrativo.

En este paso no se ejecuta `ng new`, no se agregan dependencias Node y no se
conecta todavia con la API. Esta carpeta solo reserva la ubicacion futura para
mantener el frontend separado del paquete Python.

Reglas para fases futuras:

- No guardar tokens, passwords ni secretos en el frontend.
- No versionar `node_modules`, `dist` ni caches de Angular.
- Usar la API local mediante proxy de desarrollo cuando se implemente Angular.
- No acceder directo a PostgreSQL desde Angular.
- No reutilizar cookies ni sesiones Playwright del worker.
