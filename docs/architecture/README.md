# Arquitectura

Documentos de arquitectura del proyecto.

Esta carpeta describe el runtime actual, la arquitectura alcanzada y el
historial de la migracion. No es una lista de tareas. El estado vigente esta en
[`../project-status.md`](../project-status.md) y el trabajo futuro en
[`../roadmap/README.md`](../roadmap/README.md).

| Documento | Estado | Autoridad |
| --- | --- | --- |
| [`current-runtime.md`](current-runtime.md) | Vigente, inventario orientativo | Entrypoints, procesos, leases, codigos de salida y separacion actual. Las rutas concretas se confirman en contratos/codigo. |
| [`target-architecture.md`](target-architecture.md) | Supersedido como objetivo | Reglas de separacion alcanzadas; no es trabajo pendiente. |
| [`migration-plan-worker-admin-api.md`](migration-plan-worker-admin-api.md) | Historico | Secuencia 1-9.7, decisiones de migracion y compatibilidad retirada. |

La topologia operativa y recuperacion se consultan en
[`../operations/README.md`](../operations/README.md).
