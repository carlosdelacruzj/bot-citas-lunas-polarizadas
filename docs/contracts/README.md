# Contratos

Documentos de contratos internos y externos.

Esta carpeta documenta endpoints, estados de orden, control del worker,
seguridad de reservas y superficies que no deben romperse. No contiene el
roadmap; usar `../roadmap/README.md` para trabajo futuro.

| Contrato | Estado | Alcance |
| --- | --- | --- |
| [`admin-api.md`](admin-api.md) | Vigente; rutas orientativas | Autenticacion, DTO, mutaciones y frontera local. |
| [`worker-control.md`](worker-control.md) | Vigente con correcciones de runtime | Estado publico, comandos persistidos y controles. |
| [`order-lifecycle.md`](order-lifecycle.md) | Vigente | Estados, prioridad, subordenes, pagos y comunicaciones. |
| [`reservation-safety.md`](reservation-safety.md) | Vigente | Leases, confirmacion estricta y resultados ambiguos. |
| [`captcha-shadow-dashboard.md`](captcha-shadow-dashboard.md) | Vigente con apendice historico | Integridad, revision humana, calidad y autoridad 2Captcha. |
| [`finance.md`](finance.md) | Vigente | Caja, costo, prepago, consumo, anulacion y moneda. |

Cuando un inventario de endpoints no coincida con el runtime, mandan el codigo
activo, la autenticacion definida por Admin API y `project-status.md`; el
desfase debe corregirse documentalmente antes de usarlo para implementar.
