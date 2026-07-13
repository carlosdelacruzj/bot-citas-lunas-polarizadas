# Plan de migracion: worker, admin API y dashboard Angular

Este documento guia la migracion hacia una arquitectura mas profesional sin
afectar el flujo actual de reservas. La regla principal es avanzar por fases
pequenas, validar despues de cada fase y mantener funcionando el worker actual
hasta que exista una alternativa equivalente.

Documento historico de fases completadas. Estado vigente:
`docs/project-status.md`. Mejoras futuras: `docs/roadmap/README.md`.
Este plan de migracion queda como historial tecnico de las fases ya ejecutadas y
como referencia si se abre una fase nueva.

## Arquitectura objetivo

El proyecto seguira como monorepo. Se separaran responsabilidades por modulos y
procesos:

- `core/`: modelos, estados y reglas compartidas.
- `db/`: conexion, migraciones y repositorios PostgreSQL.
- `reservation_engine/`: Playwright, login, lectura de cupos, CAPTCHA y reserva.
- `worker/`: proceso continuo, leases, ventanas, recovery y cola.
- `admin_api/`: CRUD administrativo, pagos, historial y comandos.
- `manual_session/`: sesiones manuales controladas, solo locales.
- `reports/`: reportes, evidencia y salidas operativas.
- `dashboard/`: frontend Angular separado del paquete Python.

## Principios de seguridad

- No mover codigo funcional sin una fase explicita.
- No duplicar reglas entre worker y admin API.
- No exponer passwords, tokens, Fernet keys, `owner_token` ni rutas absolutas.
- No permitir acceso directo de Angular a PostgreSQL.
- No reutilizar cookies ni contexto Playwright del worker.
- No cambiar `appointment-bot-worker`, `scripts/start-worker.ps1`, `.env` ni la
  API actual durante la fase de estructura.

## Estado actual documentado

Los cambios realizados hasta este punto estan contemplados por la migracion
porque son cambios de documentacion, contratos y limpieza interna compatible,
no una separacion real de procesos ni un cambio del flujo de reservas.

Ya queda documentado que:

- el worker actual sigue siendo `appointment-bot-worker`;
- la API local embebida sigue viva en `127.0.0.1:8765`;
- la API embebida conserva control directo de `pause`, `resume` y `restart`
  cuando tiene un `ContinuousWorker` en memoria;
- el admin API separado encola `pause`, `resume` y `restart` mediante
  `worker_commands`;
- Angular ya puede ejecutar acciones administrativas locales con confirmacion
  visible, pero todavia debe completar subordenes, restricciones, comandos
  persistidos y operacion contra el admin API separado;
- el futuro admin API no debe acceder a cookies, passwords, Fernet keys,
  `owner_token` ni PostgreSQL desde el frontend;
- cualquier separacion de worker/admin API debe pasar primero por contratos,
  DTOs publicos y un canal persistido de comandos.

Por lo tanto, estos cambios no bloquean la migracion. Al contrario, son la base
para hacerla sin romper el flujo actual. Lo que si queda prohibido por ahora es
mover control del worker, cambiar entrypoints, cambiar scripts de arranque,
cambiar `.env` o reemplazar la API local antes de tener una alternativa probada.

## Paso 1: estructura sin mover nada

Crear carpetas destino y documentarlas como estructura futura. No cambiar
imports, entrypoints, API, worker, scripts, `.env` ni logica de reserva.

Estado: completado como preparacion documental. La estructura objetivo quedo
descrita, pero no se movio codigo funcional ni se cambiaron entrypoints.

Validacion:

```powershell
python -m compileall src
python -m ruff check src tests
python -m pytest
git diff --check
```

Resultado esperado: todos los comandos pasan y no hay cambios funcionales.

## Paso 2: contratos y documentacion

Documentar el runtime actual antes de refactorizar:

- `docs/architecture/current-runtime.md`
- `docs/architecture/target-architecture.md`
- `docs/contracts/admin-api.md`
- `docs/contracts/worker-control.md`
- `docs/contracts/order-lifecycle.md`
- `docs/contracts/reservation-safety.md`
- `docs/operations/deployment-topology.md`

La documentacion debe congelar endpoints actuales, estados, leases, codigos de
salida, responsabilidades del worker y limites de seguridad.

Estado: completado como documentacion base.

Documentos creados:

- `docs/architecture/current-runtime.md`
- `docs/architecture/target-architecture.md`
- `docs/contracts/admin-api.md`
- `docs/contracts/worker-control.md`
- `docs/contracts/order-lifecycle.md`
- `docs/contracts/reservation-safety.md`
- `docs/operations/deployment-topology.md`

Tambien quedo registrado este estado de avance en el presente plan para que las
siguientes fases partan de una fuente unica y no de memoria informal.

## Paso 3: Angular read-only

Crear el proyecto Angular dentro de `dashboard/` y conectarlo en modo lectura
mediante proxy local hacia `http://127.0.0.1:8765`.

Primera pantalla permitida:

- health del worker
- estado/phase del worker
- orden actual
- lista de ordenes
- lista de runs
- filtros de lectura
- copiar solo datos no sensibles

No habilitar CRUD, pagos, restart ni sesion manual en esta fase.

Estado: completado como primera version local de solo lectura.

Implementacion:

- proyecto Angular creado en `dashboard/`;
- proxy de desarrollo `dashboard/proxy.conf.cjs` para `/api` y `/health`;
- pantalla unica con health, estado/phase del worker, orden actual, lista de
  ordenes, lista de runs y filtros locales;
- API token ingresado manualmente y mantenido solo en memoria del navegador;
- copiado de snapshot sanitizado sin `owner_token`, leases ni detalles crudos
  de runs;
- sin endpoints de escritura en el cliente Angular.

Validacion de la fase:

```powershell
cd dashboard
npm run build
```

## Paso 4: endurecer API

Antes de habilitar botones administrativos:

- Filtrar `owner_token` de respuestas publicas.
- Exigir autorizacion estricta para `pause` y `resume`.
- Definir DTOs publicos para worker, ordenes y runs.
- Evitar mostrar/copiar `details` crudos por defecto.
- Mantener tokens fuera del bundle Angular y fuera de `localStorage`.

Estado: completado como endurecimiento previo a acciones administrativas.

Implementacion:

- `GET /api/v1/worker` devuelve solo campos publicos por allowlist;
- `owner_token`, `lease_expires_at` y datos internos quedan fuera del DTO del
  worker;
- `worker/pause`, `worker/resume` y `worker/restart` requieren token estricto;
- ordenes y runs usan DTOs publicos por allowlist;
- `GET /api/v1/runs/{run_id}` no devuelve `details` crudos por defecto;
- detalles crudos solo salen con `?include_details=1` para diagnostico manual;
- el dashboard mantiene el API token solo en memoria del navegador.

Validacion de la fase:

```powershell
python -m compileall src
python -m ruff check src tests
python -m pytest
```

## Paso 5: admin API separado

Crear un proceso Python de admin API que reutilice los servicios actuales de DB.
El worker actual y su API embebida seguiran vivos por compatibilidad hasta que
el admin API separado tenga paridad suficiente.

No mover `pause`, `resume` ni `restart` fuera del proceso actual todavia.

Estado: completado como primer proceso separado compatible.

Implementacion:

- nuevo entrypoint `appointment-bot-admin-api`;
- escucha por defecto en `127.0.0.1:8766` mediante
  `APPOINTMENT_BOT_ADMIN_API_HOST` y `APPOINTMENT_BOT_ADMIN_API_PORT`;
- reutiliza los handlers publicos y servicios PostgreSQL existentes para
  health, worker status, ordenes y runs;
- usa el mismo `APPOINTMENT_BOT_API_TOKEN` administrativo;
- no aloja `ContinuousWorker` ni mueve `pause`, `resume` o `restart` fuera del
  proceso actual.

Validacion de la fase:

```powershell
python -m compileall src
python -m ruff check src tests
python -m pytest
git diff --check
```

## Paso 6: comandos persistidos del worker

Crear un canal persistido, por ejemplo `worker_commands`, para que el admin API
pueda pedir acciones y el worker las consuma en su propio ciclo.

Comandos iniciales:

- `pause`
- `resume`
- `restart`

El admin API no debe depender de tener un objeto `ContinuousWorker` en memoria.

Estado: completado como canal persistido inicial.

Implementacion:

- schema `worker_commands` agregado como version 23;
- comandos soportados: `pause`, `resume`, `restart`;
- `appointment-bot-admin-api` encola comandos cuando no tiene
  `ContinuousWorker` en memoria;
- la API embebida del worker conserva control directo por compatibilidad;
- el worker reclama comandos pendientes con su `owner_token`, los aplica y los
  marca como `applied` o `failed`;
- `restart` persistido detiene el ciclo actual para que el host salga con el
  flujo de reinicio controlado existente.

Validacion de la fase:

```powershell
python -m compileall src
python -m ruff check src tests
python -m pytest
git diff --check
```

## Paso 7: CRUD progresivo

Habilitar acciones desde Angular por orden de menor a mayor riesgo:

1. actualizar contacto
2. pausar/activar
3. marcar sin cobro
4. marcar pagado
5. archivar/completar
6. crear orden nueva
7. restart worker

Cada accion debe tener confirmacion visible y respuesta clara del backend.

Estado: completado como panel administrativo local.

Implementacion:

- panel de acciones administrativas en `dashboard/`;
- orden seleccionada para contacto, pausa/activacion, sin cobro, pago y
  completar;
- las ordenes con multiples tramites se modelan como subordenes de cola:
  `parent_order_id`, `program_expediente` y `program_plate` deben permanecer en
  el DTO publico, en la tabla de ordenes y en cualquier formulario de creacion
  avanzada;
- el dashboard debe tratar cada suborden como trabajo independiente para pausa,
  pago, reporte, sesion manual y cierre, aunque comparta credenciales con la
  orden padre;
- formulario de contacto para nombre, WhatsApp y fuente;
- formulario de pago para monto pagado y monto acordado;
- formulario minimo para crear orden nueva sin persistir password en storage;
- boton de `restart worker` usando el contrato persistido/control directo
  disponible segun proceso backend;
- confirmacion visible antes de cada accion y respuesta clara despues del POST;
- token administrativo inyectado por el proxy local del servidor de desarrollo,
  sin campo visible ni storage del navegador.

Validacion de la fase:

```powershell
cd dashboard
npm run build
cd ..
python -m compileall src
python -m ruff check src tests
python -m pytest
git diff --check
```

## Paso 8: sesion manual controlada

Agregar una accion local para abrir una sesion Playwright nueva, visible y
separada del worker. Debe estar deshabilitada por defecto hasta definir reglas
de auditoria y seguridad.

Restricciones:

- solo `127.0.0.1`
- sin exponer cookies
- sin devolver password
- sin reutilizar contexto del worker
- sin cambiar estado de reserva por si sola

Estado: completado como accion local deshabilitada por defecto.

Implementacion:

- endpoint `GET /api/v1/manual-sessions`;
- endpoint `POST /api/v1/manual-session/open`;
- endpoint `POST /api/v1/manual-session/close`;
- requiere `MANUAL_SESSION_ENABLED=true`;
- acepta solo host y cliente loopback;
- recibe `order_id`, resuelve credenciales en backend y no devuelve password;
- abre Playwright visible con contexto nuevo y sin reutilizar cookies del
  worker;
- hace login, selecciona el tramite, abre el modal de cita y selecciona la sede
  requerida configurada, por defecto `LIMA-LA VICTORIA`;
- deja la sesion en manos del usuario sin ejecutar reserva automatica ni
  cambiar estado de orden;
- no selecciona fecha/hora, no resuelve CAPTCHA y no pulsa el boton final de
  reserva;
- permite multiples sesiones manuales activas por proceso, cada una en un
  navegador/contexto Playwright separado, y registra auditoria minima en logs;
- limpia cada sesion cuando se cierra su ventana, termina su hilo o el
  dashboard pide cerrar por `session_id`;
- boton confirmado en `dashboard/` sobre la orden seleccionada.

Validacion de la fase:

```powershell
cd dashboard
npm run build
cd ..
python -m compileall src
python -m ruff check src tests
python -m pytest
git diff --check
```

## Paso 9: refactor interno gradual

Mover codigo solo despues de tener contratos, dashboard/admin API estable y
validaciones. Este paso no debe hacerse como un refactor unico. Debe dividirse
en fases pequenas para mantener rollback claro y evitar romper el flujo actual
de reservas.

Estado: completado hasta el retiro de compatibilidad vieja. Desde este punto no
queda un refactor estructural grande abierto en esta fase; los pendientes
recomendados pasan a ser operativos, de dashboard o de validacion manual.

### Paso 9.0: cierre previo de superficie Angular/admin

Antes de mover modulos internos, cerrar las brechas que afectan al panel:

- apuntar el proxy local de Angular al admin API separado
  `http://127.0.0.1:8766` cuando se quiera operar contra la topologia objetivo;
- mantener una opcion documentada para volver temporalmente a la API embebida
  `http://127.0.0.1:8765`;
- exponer en Angular los campos de suborden
  `parent_order_id`, `program_expediente` y `program_plate`;
- exponer en Angular las reglas de reserva
  `minimum_reservation_hour`, `minimum_reservation_date` y `allowed_weekdays`;
- agregar una vista simple del resultado de comandos persistidos
  `worker_commands`, al menos para confirmar `pending`, `applied` y `failed`;
- agregar endpoint y accion controlada para dividir una orden en subordenes por
  tramites pendientes, equivalente al CLI `order-split-programs`;
- validar worker y admin API corriendo como procesos separados.

Esta fase puede avanzar en paralelo con mejoras visuales del dashboard, pero no
debe mezclar cambios de Playwright ni de reserva.

Estado: completado como cierre de superficie Angular/admin previo al refactor
interno.

Implementacion:

- `dashboard/proxy.conf.cjs` apunta por defecto al admin API separado en
  `http://127.0.0.1:8766`;
- la opcion de volver temporalmente a `http://127.0.0.1:8765` queda
  documentada como compatibilidad con la API embebida;
- Angular muestra `parent_order_id`, `program_expediente` y `program_plate`;
- Angular permite crear ordenes con suborden y reglas de reserva:
  `minimum_reservation_hour`, `minimum_reservation_date` y `allowed_weekdays`;
- `GET /api/v1/worker/commands` devuelve comandos recientes sin
  `worker_owner_token`;
- Angular muestra comandos recientes del worker con estado `pending`,
  `processing`, `applied` o `failed`;
- `POST /api/v1/service-orders/{order_id}/split-programs` reutiliza
  `split_service_order_programs`;
- Angular agrega una accion confirmada para dividir tramites pendientes y una
  opcion para mantener la orden padre activa.

Validacion minima:

```powershell
cd dashboard
npm run build
cd ..
python -m compileall src
python -m ruff check src tests
python -m pytest
git diff --check
```

### Paso 9.1: wrappers publicos sin mover implementacion

Crear modulos de compatibilidad que reexporten funciones actuales sin cambiar
imports existentes:

- `core/`: tipos, estados y helpers puros que no abren browser ni DB;
- `db/`: fachada de conexion, migracion y repositorios;
- `worker/`: fachada del loop continuo y comandos;
- `reservation_engine/`: fachada de login, lectura, CAPTCHA y reserva;
- `reports/`: fachada de fichas, reportes y evidencia.

La implementacion real puede seguir en `services/` durante esta fase. El
objetivo es definir nombres publicos y preparar los imports nuevos sin mover
riesgo operativo.

Estado: completado como fachadas publicas de compatibilidad.

Implementacion:

- `core/__init__.py`, `core/models.py`, `core/rules.py` y `core/statuses.py`
  reexportan modelos, estados y reglas puras actuales;
- `db/connection.py`, `db/migrations.py`, `db/orders.py`,
  `db/reservations.py`, `db/runs.py` y `db/worker_state.py` reexportan los
  repositorios PostgreSQL actuales;
- `worker/control.py`, `worker/queue.py` y `worker/windows.py` reexportan el
  host continuo, cola y ventanas;
- `reservation_engine/flow.py`, `reservation_engine/portal.py` y
  `reservation_engine/submit.py` reexportan las piezas actuales del motor de
  reserva;
- `reports/evidence.py`, `reports/optimization.py` y `reports/status.py`
  reexportan reportes, evidencia y bitacoras;
- no se cambiaron imports existentes, entrypoints, scripts, `.env` ni logica de
  reserva.

Validacion minima:

```powershell
python -m compileall src
python -m ruff check src tests
python -m pytest
git diff --check
```

### Paso 9.2: mover modelos y reglas puras

Mover primero lo que no toca IO:

- dataclasses y DTOs puros;
- estados de orden, worker y resultado;
- sanitizacion y helpers de fechas/detalles que no leen DB;
- reglas de elegibilidad de cola y restricciones de reserva cuando no dependen
  de conexion.

No mover Playwright, PostgreSQL ni notificaciones en esta fase.

Estado: completado como primer movimiento real hacia `core/`.

Implementacion:

- `core/statuses.py` contiene `ResultStatus`, `OrderStateStatus`,
  `SENSITIVE_DETAIL_KEYS` y `sanitize_details`;
- `core/models.py` contiene `AvailabilityResult`, `RunReport`,
  `ServiceOrderCandidate`, `ServiceOrderRuntime`, `ServiceOrderSummary`,
  `ServiceOrderCreateResult`, `RunRecord`, `RunSummary`, `RunDetail`,
  `WorkerState` y `WorkerCommand`;
- `core/rules.py` contiene `ReservationConstraints`, parseo de fecha/hora y
  reglas puras de compatibilidad de citas;
- `domain.py`, `services/database_models.py` y `services/order_selection.py`
  quedaron como wrappers de compatibilidad para no romper imports existentes;
- no se movio codigo de PostgreSQL, Playwright, notificaciones, entrypoints,
  scripts ni `.env`.

Validacion minima:

```powershell
python -m compileall src
python -m ruff check src tests
python -m pytest
git diff --check
```

### Paso 9.3: separar capa DB por subdominio

Dividir gradualmente `db/orders.py` y modulos cercanos en
repositorios mas pequenos dentro de `db/`:

- ordenes y contactos;
- pagos;
- reservas;
- estado/backoff de orden;
- leases;
- runs/evidencia;
- worker state y `worker_commands`.

Cada subfase debe mantener compatibilidad con los imports viejos hasta que todos
los consumidores usen el modulo nuevo. Los cambios de schema deben quedar en una
fase separada y avanzar versiones de forma secuencial.

Estado: completado como traslado de implementacion PostgreSQL a `db/` con
wrappers de compatibilidad.

Implementacion:

- `db/common.py`, `db/pool.py` y `db/migrations.py` contienen conexion, pool y
  migraciones;
- `db/orders.py` contiene el repositorio actual de ordenes, contactos, pagos,
  reglas, leases de orden y estado/backoff de orden;
- `db/reservations.py` contiene reservas e intentos de reserva;
- `db/runs.py` contiene runs, checks y metricas de ventanas;
- `db/worker_state.py` contiene estado y lease del worker;
- `db/worker_commands.py` contiene el puente persistido de comandos;
- `db/cleanup.py` contiene limpieza de historial;
- los modulos antiguos `services/database_migrations.py` y
  `services/postgres_*.py` quedaron como wrappers transicionales hasta 9.7;
- el codigo de aplicacion ahora importa `appointment_bot.db.*` directamente;
- los tests y consumidores externos pueden seguir usando imports viejos durante
  la transicion;
- no hubo cambios de schema, Playwright, reserva, notificaciones, entrypoints,
  scripts ni `.env`.

Nota tecnica: `db/orders.py` todavia concentra varias responsabilidades
historicas. Queda como repositorio de ordenes para preservar riesgo bajo. Si se
necesita seguir reduciendo ese archivo, hacerlo como subfase posterior de 9.3,
separando pagos, leases y estado de orden con pruebas antes de cada corte.

Validacion minima:

```powershell
python -m compileall src
python -m ruff check src tests
python -m pytest
git diff --check
```

### Paso 9.4: mover worker continuo

Estado: completado como corte transicional con wrappers de compatibilidad.

Se movio el loop y sus piezas internas a `worker/` por tandas:

- ventanas, cutoff diario y hot windows;
- lease del worker;
- aplicacion de comandos persistidos;
- seleccion de cola y control de rapid queue;
- politicas de error, recovery y reportes diferidos.

Resultado:

- `appointment-bot-worker` apunta a `appointment_bot.worker.host:main`;
- `worker/continuous_worker.py` contiene el loop continuo;
- `worker/queue_runtime.py` contiene cola rapida y ejecucion transicional de
  ordenes;
- `worker/windows_runtime.py`, `worker/lease.py`, `worker/recovery.py`,
  `worker/error_policy.py`, `worker/deferred_reports.py`, `worker/execution.py`,
  `worker/state_callbacks.py`, `worker/order_results.py` y
  `worker/observer_results.py` contienen las piezas internas del worker;
- `services/continuous_*`, `services/order_execution.py` y
  `services/worker_*.py` quedaron como wrappers transicionales hasta 9.7;
- `scripts/start-worker.ps1` no cambia y sigue ejecutando el comando instalado;
- el motor Playwright detallado queda para Paso 9.5 bajo `reservation_engine/`.

Validacion minima:

```powershell
python -m compileall src
python -m ruff check src tests
python -m pytest
git diff --check
```

### Paso 9.5: mover motor Playwright

Estado: completado como corte transicional con wrappers de compatibilidad.

Se movio a `reservation_engine/` el flujo que interactua con el portal:

- login;
- seleccion de tramite;
- lectura de fechas/horas;
- fetch/reload probes;
- CAPTCHA;
- submit de reserva;
- confirmacion post-submit.

Resultado:

- `reservation_engine/runner.py` orquesta la sesion Playwright, video y reporte;
- `reservation_engine/session_flow.py` contiene login, seleccion de tramite y
  apertura del panel de citas;
- `reservation_engine/monitor.py` contiene lectura de disponibilidad,
  reload probe y decision de reserva;
- `reservation_engine/appointment_*.py`, `appointments.py`, `login.py`,
  `programs.py` y `stages.py` contienen navegacion, lectura y seleccion del
  portal;
- `reservation_engine/reservation_captcha_*`,
  `reservation_engine/reservation_submit.py`,
  `reservation_engine/reservation_portal.py` y
  `reservation_engine/reservation_flow.py` contienen CAPTCHA, submit y
  confirmacion post-submit;
- `reservation_engine/observer.py` contiene el observer Playwright;
- `flows/*`, `services/session_*`, `services/reservation_flow.py`,
  `services/reservation_timings.py` y `services/observer.py` quedaron como
  wrappers transicionales hasta 9.7;
- no hubo cambios de schema, dashboard, `.env`, notificaciones ni contratos de
  entrypoint.

Validacion minima:

```powershell
python -m compileall src
python -m ruff check src tests
python -m pytest
git diff --check
```

### Paso 9.6: mover reportes y evidencia

Estado: completado como corte transicional con wrappers de compatibilidad.

Se movio a `reports/` la generacion de fichas, resumenes, evidencia compacta y
salidas operativas.

Resultado:

- `reports/run_reporting.py` contiene finalizacion de corridas, conversion de
  resultados y registro historico;
- `reports/evidence.py` contiene indice/resumen compacto de evidencia;
- `reports/optimization.py` contiene bitacoras de optimizacion y disponibilidad
  parcial;
- `reports/status.py` contiene fichas de estado y reporte diario;
- `services/run_reporting.py`, `services/status_reports.py`,
  `services/evidence_summary.py` y `services/optimization_log.py` quedaron como
  wrappers transicionales hasta 9.7;
- no hubo cambios de schema, dashboard, `.env`, formatos historicos ni rutas de
  salida.

Rutas de salida preservadas:

- `docs/evidence-index.csv`;
- `docs/evidence-summary.md`;
- `reports/evidence/history/reservation-optimization-log.md`;
- `reports/evidence/history/partial-availability-log.md`;
- `reports/status/`;
- `reports/daily/`.

Validacion minima:

```powershell
python -m compileall src
python -m ruff check src tests
python -m pytest
git diff --check
```

### Paso 9.7: retirar compatibilidad vieja

Solo cuando los imports nuevos ya esten usados por worker, admin API, CLI y
tests:

- eliminar wrappers viejos no usados;
- actualizar documentacion de runtime;
- revisar `.env.example` si aparecieron variables nuevas;
- dejar evidencia de validacion completa.

No retirar compatibilidad si todavia hay scripts, n8n o CLI dependiendo de la
ruta anterior.

Estado: completado.

Resultado:

- tests y scripts internos usan rutas nuevas directas;
- `scripts/start-worker.ps1` detecta y ejecuta `appointment_bot.worker.host`;
- se retiraron wrappers viejos de `flows/*`, `services/postgres_*`,
  `services/database_migrations.py`, `services/continuous_*`,
  `services/order_execution.py`, `services/worker_*`, `services/session_*`,
  `services/reservation_flow.py`, `services/reservation_timings.py`,
  `services/observer.py`, `services/run_reporting.py`,
  `services/status_reports.py`, `services/evidence_summary.py` y
  `services/optimization_log.py`;
- no se agregaron variables de entorno nuevas, por lo que `.env.example` no
  requirio cambios;
- no se tocaron `.env`, schema, dashboard ni formatos de salida.

Validacion minima:

```powershell
python -m compileall src
python -m ruff check src tests
python -m pytest
git diff --check
```

## Cierre historico del trabajo Angular

Angular avanzo en paralelo al Paso 9 respetando estos limites:

- consumir solamente el admin API o la API embebida por proxy local;
- no hablar directo con PostgreSQL;
- no guardar tokens ni passwords en storage;
- tratar cada suborden como una orden operativa independiente;
- pedir confirmacion visible antes de acciones de escritura;
- mostrar errores del backend sin ocultarlos.

Estado actual de Angular:

- proxy/documentacion contra `appointment-bot-admin-api` en `127.0.0.1:8766`:
  completado;
- tipos y UI de subordenes: completado;
- tipos y UI de restricciones de reserva: completado;
- accion confirmada de dividir tramites pendientes: completado;
- lectura de comandos persistidos: completado;
- acciones administrativas locales con confirmacion visible: completado;
- snapshot copiable sanitizado: completado;
- build Angular: validado con `npm run build`.

La validacion manual contra el admin API vivo se completo el 12 de julio de
2026. El detalle de runs y la ergonomia dejaron de pertenecer al plan de
migracion y se consolidaron en `docs/history/roadmap-completed-2026-07-12.md`.

Estado y validacion operativa: `docs/project-status.md`.

## Criterios de avance

Una fase solo queda cerrada si:

- pasan `compileall`, `ruff`, `pytest` y `git diff --check`
- el worker/API actual siguen intactos o con compatibilidad documentada
- no se exponen secretos nuevos
- hay rollback claro
- la documentacion de la fase queda actualizada

## Rollback

Si una fase afecta el flujo actual, revertir solo los cambios de esa fase. No
mezclar refactors de estructura con cambios de runtime, schema o reservas en un
mismo commit.
