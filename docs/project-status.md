# Estado maestro del proyecto

Este es el documento principal para saber que se construyo, que se valido y
que falta. Los contratos, documentos de arquitectura y bitacoras de evidencia
se conservan como referencias; no deben usarse como listas paralelas de tareas.

Ultima revision integral: `2026-07-12`.

Baseline estable de reservas: tag `best-performing-2026-07-12`, commit
`a43c6a1`. Es el corte con mejor evidencia acumulada hasta esta fecha. El P0 de
seguridad administrativa posterior no modifica el motor Playwright, la cola de
reservas ni sus reglas.

## Estado ejecutivo

| Area | Estado | Conclusion |
| --- | --- | --- |
| Reserva automatica | Operativa | Hay reservas `registered` reales y confirmacion estricta del portal. |
| Cola multi-cliente | Operativa | Usa una sesion Playwright nueva por orden y conserva leases. |
| Reglas y prioridades | Operativas | Fecha, hora, dias, subordenes y prioridad de enfoque estan implementadas. |
| Migracion interna | Completada | Pasos 1 a 9.7 cerrados; wrappers historicos retirados. |
| Admin API separado | Operativo | Funciona en loopback y controla al worker mediante `worker_commands`. |
| Dashboard Angular | Operativo | CRUD, runs, flujo por tarea, accesibilidad y entrega local en dos procesos listos. |
| Evidencia y reportes | Operativos | Indice, resumen, logs, screenshots y reportes se generan y conservan. |
| Optimizacion | En mejora continua | Ruta rapida probada; siguen abiertos `slot_lost` y outliers de CAPTCHA. |

## Fuente unica para ejecutar trabajo

El orden obligatorio esta en [`roadmap/README.md`](roadmap/README.md). Cada
archivo de area contiene pasos verificables, pero el orden global solo se
cambia en ese indice.

1. Seguridad y contratos backend.
2. Frontend operativo.
3. Observabilidad y operacion.
4. Optimizacion de conversion y tiempos.
5. Pulcritud interna no urgente.

No se debe iniciar una fase posterior mientras queden criterios de cierre de la
fase anterior, salvo que una incidencia de produccion obligue a interrumpirla.

## Trabajo realizado y cumplido

### Reserva, seguridad y evidencia

- Reserva automatica con confirmacion estricta: click de envio mas resultado
  terminal `registered` o texto de exito del portal.
- Persistencia de `reservation_attempts`, estado pendiente de submission y
  reconciliacion posterior.
- Heartbeat del lease durante intentos para evitar ejecuciones duplicadas.
- Screenshots y diagnosticos sanitizados en fallos importantes.
- Reintento controlado ante `captcha_invalid` explicito.
- Evidencia compacta en `docs/evidence-index.csv` y
  `docs/evidence-summary.md`.
- Reportes regenerables con `appointment-bot-client evidence-summary`.
- Notificacion de reserva primero; datos operativos de contacto enviados de
  forma diferida para no retrasar la cola.

### Cola, reglas y portal

- Sesion Playwright independiente por orden, sin reutilizar login ni cookies.
- Cola rapida posterior a disponibilidad real y cambio rapido entre clientes.
- Restricciones por hora minima, fecha minima y dias permitidos.
- Diferimiento por prioridad y registro `blocked_by_order_rule`.
- Prioridad de enfoque desde `100`, sin promover automaticamente hasta ese
  umbral.
- Subordenes por expediente/placa para cuentas con varios tramites.
- Seleccion explicita del tramite objetivo antes de abrir citas.
- `fetch_probe` separado como diagnostico; no autoriza reservas por si solo.
- Recovery/backoff ante defensas, errores de red y rachas sin cupos.

### Migracion y backend

- Arquitectura modular bajo `core/`, `db/`, `reservation_engine/`, `worker/`,
  `admin_api/`, `manual_session/` y `reports/`.
- Implementacion PostgreSQL movida a `appointment_bot.db`.
- Worker continuo y motor Playwright movidos a sus paquetes definitivos.
- Reportes y evidencia movidos a `appointment_bot.reports`.
- Wrappers historicos retirados en el paso 9.7.
- Admin API separado en `127.0.0.1:8766`.
- Canal persistido `worker_commands` para pausa, reanudacion y restart.
- DTOs publicos y autenticacion administrativa local.
- Motivos de cierre, pagos, contactos, subordenes y sesiones manuales
  concurrentes implementados.

El detalle historico de las fases se conserva en
[`architecture/migration-plan-worker-admin-api.md`](architecture/migration-plan-worker-admin-api.md).

### Frontend

- Angular 20 conectado al admin API por proxy local.
- Token administrativo inyectado por el proxy, sin campo de token en la UI.
- Estado vivo, auto-refresh, seleccion de orden y filtros rapidos.
- Diseño responsive y controles seguros para movil.
- Alta simplificada de orden con contacto y fuente obligatorios.
- Edicion de contacto, pago, pausa, activacion, cierre y division de tramites.
- Confirmacion visible antes de acciones administrativas.
- Motivos y notas de cierre.
- Sesiones manuales visibles y concurrentes, deshabilitadas por defecto.
- Snapshot operativo sanitizado y copiable.
- Listado, filtros y snapshots con documento/WhatsApp enmascarados; detalle
  completo solicitado solo al abrir la edicion protegida de una orden.
- Detalle sanitizado de runs solicitado por `run_id`, con estado, tiempos,
  resultado y rutas publicas de evidencia, sin `details` crudos.
- Flujo de orden centrado en siguiente accion, secciones operativas y jerarquia
  de tramites; modales con foco restaurable, cierre por Escape y controles
  tactiles responsive.
- Build Angular servido por el admin API en loopback con sesion local segura;
  `scripts/start-admin-dashboard.ps1` reduce la operacion a worker mas
  admin-dashboard y conserva el proxy como rollback.

### Operacion

- Worker en `127.0.0.1:8765`, admin API en `127.0.0.1:8766` y dashboard por
  proxy local.
- Worker supervisado en Windows por `scripts/start-worker.ps1`.
- PostgreSQL como fuente compartida de estado, historial y comandos.
- n8n limitado a supervision externa.
- Primera validacion integral realizada el `2026-07-12 11:31:32 -05:00`:
  health, worker, ordenes, runs y comandos respondieron HTTP `200`; una
  actualizacion idempotente de contacto fue confirmada por CLI sin cambiar el
  estado `ready` de la orden.
- Validacion posterior: `compileall`, Ruff, 53 tests, build Angular y
  `git diff --check` correctos.

## Cambios actuales revisados

El corte de trabajo preparado el 12 de julio incluye:

- formulario de alta del dashboard mas simple y explicito;
- contacto y fuente obligatorios en dashboard, API y CLI;
- seleccion amigable de dias permitidos;
- prioridad de enfoque para el bloque de observadores;
- reserva inmediata en la propia sesion cuando un observador detecta un cupo
  compatible, sin transferirlo a otra cuenta enfocada;
- propagacion consistente de identidad/contacto al resultado diferido;
- evidencia operativa actualizada;
- tests de reglas corregidos para no depender de fechas fijas vencidas.
- P0 backend de seguridad: listado enmascarado y endpoint de detalle
  administrativo protegido por orden.
- P1 backend: fuentes de contacto centralizadas, normalizacion compartida,
  errores por campo y alta avanzada conservada sin recargar el formulario.

Validacion P0 por proxy local:

- health HTTP correcto;
- listado sin `document_number` ni `contact_whatsapp` completos;
- listado con `document_number_masked` y `contact_whatsapp_masked`;
- detalle protegido con los dos campos completos para edicion deliberada;
- orden inexistente respondio HTTP `404`;
- 53 tests, Ruff, compileall, build Angular y `git diff --check` correctos.

## Evidencia de rendimiento actual

- El resumen actual registra 95 eventos y 17 reservas `registered`.
- En intentos recientes, la ruta normal repitio reservas cercanas a 6.5-7.3
  segundos cuando 2captcha respondio alrededor de 1.3 segundos.
- Los cambios de usuario llegaron a 0-2 segundos.
- `reload_probe` no fue necesario para esas reservas rapidas.
- `slot_lost` sigue apareciendo incluso en intentos de 7-9 segundos.
- 2captcha tuvo outliers de 12 y 22.7 segundos.
- `fetch_probe` aun no demuestra mejora de conversion.

Los acumulados no deben presentarse como KPI semanal. Para analisis se lee, en
orden: `evidence-index.csv`, `evidence-summary.md`, bitacoras largas y finalmente
artefactos pesados del caso seleccionado.

## Documentos que se conservan y para que sirven

- `docs/project-status.md`: estado, cumplimiento y entrada principal.
- `docs/roadmap/`: unico trabajo futuro autorizado y ordenado.
- `docs/architecture/`: runtime, arquitectura alcanzada e historial de migracion.
- `docs/contracts/`: contratos que no deben romperse.
- `docs/operations/deployment-topology.md`: arranque y rollback.
- `docs/evidence-*.csv` y `docs/evidence-summary.md`: lectura compacta.
- `docs/reservation-optimization-log.md` y
  `docs/partial-availability-log.md`: bitacoras generadas; no son roadmaps.
- `docs/history/milestones.md`: hitos historicos consolidados.
- `reports/`: salidas fechadas regenerables, no fuentes de planificacion.

## Definicion de terminado

Una mejora solo cambia a completada cuando:

1. codigo y documentacion coinciden;
2. no expone credenciales ni datos innecesarios;
3. `python -m compileall -q src` pasa;
4. `python -m ruff check src tests` pasa;
5. `python -m pytest -q` pasa;
6. `npm run build` pasa si toca Angular;
7. `git diff --check` pasa;
8. la validacion manual proporcional al riesgo queda registrada;
9. el roadmap del area y este documento se actualizan en el mismo corte.
