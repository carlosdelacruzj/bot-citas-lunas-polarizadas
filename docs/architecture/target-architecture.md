# Arquitectura alcanzada

> Snapshot de la arquitectura alcanzada durante la migracion. Para operacion y
> riesgos actuales usar `docs/operations/deployment-topology.md` y
> `docs/project-status.md`.

La arquitectura alcanzada mantiene un solo repositorio, pero separa
responsabilidades por modulos y procesos. El objetivo es que el worker se
enfoque en reservar y que el dashboard/admin API se enfoque en administracion.

## Topologia

```text
PostgreSQL
  ^                 ^
  |                 |
worker Python      admin API Python
reservas           CRUD/dashboard/operaciones
  ^                 ^
  |                 |
portal web         Angular dashboard
```

## Modulos Python objetivo

```text
src/appointment_bot/
  core/
  db/
  reservation_engine/
  worker/
  admin_api/
  manual_session/
  reports/
```

- `core/`: modelos puros, estados, reglas compartidas y sanitizacion comun.
- `db/`: conexion, migraciones y repositorios PostgreSQL.
- `reservation_engine/`: Playwright, portal, CAPTCHA, reserva y confirmacion.
- `worker/`: loop continuo, leases, ventanas, cola, backoff y recovery.
- `admin_api/`: endpoints administrativos y DTOs publicos.
- `manual_session/`: sesiones visibles controladas, siempre separadas del
  worker.
- `reports/`: fichas, resumenes, evidencia y salidas operativas.

## Procesos objetivo

- `appointment-bot-worker`: solo motor continuo y reservas.
- `appointment-bot-admin-api`: CRUD, pagos, runs, estado, comandos y dashboard.
- `dashboard/`: Angular servido localmente o por el admin API.

El admin API no debe ejecutar logica de reserva ni descifrar credenciales para
mostrar datos. Solo el worker o una sesion manual controlada pueden usar
credenciales del portal.

## Reglas de separacion

- Angular nunca accede directo a PostgreSQL.
- Angular nunca recibe passwords, Fernet keys, API tokens, `owner_token` ni
  cookies Playwright.
- El worker no depende de Angular.
- El admin API no debe duplicar reglas de reserva; debe llamar servicios
  compartidos.
- Las transiciones criticas de reserva siguen protegidas por leases,
  `reservation_attempts` y confirmacion.

## Subordenes como unidad operativa

La unidad operativa del worker es una fila de `service_orders`, no una cuenta
del portal. Si una cuenta tiene varios tramites pendientes, el sistema debe
representarlos como subordenes con:

- `parent_order_id`
- `program_expediente`
- `program_plate`

Cada suborden comparte credenciales con la cuenta, pero tiene estado de cola,
reserva, pago, evidencia y cierre propios. El dashboard y el admin API no deben
colapsar subordenes como si fueran un solo trabajo.

## Angular en la arquitectura objetivo

Angular puede avanzar antes de terminar el refactor interno de Python. Sus
limites son:

- consumir el admin API por HTTP;
- mantener el token administrativo solo en memoria;
- no guardar passwords despues del POST de creacion;
- no recibir passwords, cookies, Fernet keys ni `owner_token`;
- no duplicar reglas de reserva; debe enviar datos y dejar que el backend los
  valide;
- no abrir CORS ni exponer el panel fuera de loopback durante esta migracion.

El target preferido del proxy de desarrollo en la arquitectura objetivo es
`http://127.0.0.1:8766`, donde corre `appointment-bot-admin-api`.

## Estrategia de migracion ejecutada

La separacion se ejecuto incrementalmente:

1. documentar contratos;
2. crear wrappers publicos sobre servicios actuales;
3. crear admin API separado para lectura y CRUD simple;
4. crear canal persistido de comandos para `pause`, `resume`, `restart`;
5. completar Angular contra el admin API separado;
6. mover modulos internos por tandas pequenas con wrappers de compatibilidad;
7. retirar compatibilidad solo cuando tests y runtime lo prueben.

Los siete puntos quedaron completados en el paso 9.7. Los siguientes trabajos
estan ordenados en `../roadmap/README.md`.
