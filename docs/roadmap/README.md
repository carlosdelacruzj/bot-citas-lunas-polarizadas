# Orden de mejoras pendientes

Esta es la unica lista maestra de trabajo futuro. El estado global esta en
[`../project-status.md`](../project-status.md).

## Orden obligatorio

### Fase 1 - Backend y seguridad administrativa

Ejecutar completo [`01-backend.md`](01-backend.md), bloque P0.

Motivo: antes de ampliar el dashboard hay que asegurar que los listados no
entreguen documento o WhatsApp completos innecesariamente y definir un endpoint
de detalle administrativo explicito.

### Fase 2 - Frontend operativo

Ejecutar completo [`02-frontend.md`](02-frontend.md).

Motivo: con el contrato seguro y estable se puede terminar el detalle de runs,
la edicion explicita de datos sensibles y la ergonomia sin rehacer componentes.

### Fase 3 - Operacion y observabilidad

Ejecutar completo [`03-operations.md`](03-operations.md).

Motivo: los KPI semanales y alertas deben medir el comportamiento de la
superficie ya estabilizada antes de cambiar tiempos o concurrencia.

### Fase 4 - Optimizacion de reservas

Ejecutar [`04-optimization.md`](04-optimization.md) por experimentos pequenos.

Motivo: primero se necesita una linea base p50/p90 y resultados exactos; despues
se optimizan seleccion, CAPTCHA y orden de clientes sin confundir percepcion con
conversion real.

### Fase 5 - Pulcritud interna

Ejecutar el bloque P2 de [`01-backend.md`](01-backend.md).

Motivo: dividir archivos grandes mejora mantenimiento, pero hoy tiene menor
impacto que seguridad, operacion y conversion.

## Regla de ejecucion

- Terminar una fase y sus criterios de cierre antes de iniciar la siguiente.
- Un incidente real de reserva puede interrumpir el orden; debe documentarse.
- No mezclar una optimizacion Playwright con un refactor estructural grande.
- Cada fase termina con validaciones, actualizacion de estado, commit y push.
