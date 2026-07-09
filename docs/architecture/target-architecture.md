# Arquitectura objetivo

La arquitectura objetivo mantiene un solo repositorio, pero separa
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

## Estrategia de migracion

La separacion sera incremental:

1. documentar contratos;
2. crear wrappers publicos sobre servicios actuales;
3. crear admin API separado para lectura y CRUD simple;
4. crear canal persistido de comandos para `pause`, `resume`, `restart`;
5. mover modulos internos por tandas pequenas con wrappers de compatibilidad;
6. retirar compatibilidad solo cuando tests y runtime lo prueben.
