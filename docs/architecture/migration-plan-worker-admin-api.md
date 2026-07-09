# Plan de migracion: worker, admin API y dashboard Angular

Este documento guia la migracion hacia una arquitectura mas profesional sin
afectar el flujo actual de reservas. La regla principal es avanzar por fases
pequenas, validar despues de cada fase y mantener funcionando el worker actual
hasta que exista una alternativa equivalente.

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
- `pause`, `resume` y `restart` siguen dependiendo del objeto `ContinuousWorker`
  en memoria;
- Angular todavia no debe hacer CRUD ni ejecutar acciones de control;
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
- proxy de desarrollo `dashboard/proxy.conf.json` para `/api` y `/health`;
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
- formulario de contacto para nombre, WhatsApp y fuente;
- formulario de pago para monto pagado y monto acordado;
- formulario minimo para crear orden nueva sin persistir password en storage;
- boton de `restart worker` usando el contrato persistido/control directo
  disponible segun proceso backend;
- confirmacion visible antes de cada accion y respuesta clara despues del POST;
- token administrativo mantenido solo en memoria del navegador.

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

## Paso 9: refactor interno gradual

Mover codigo solo despues de tener contratos y validaciones:

1. crear wrappers publicos en `core/` y `db/`
2. mover modelos puros
3. dividir `postgres_orders.py` por subdominio
4. mover worker modules a `worker/`
5. mover flujo Playwright a `reservation_engine/`
6. actualizar imports por tandas pequenas
7. validar despues de cada tanda

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
