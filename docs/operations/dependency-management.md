# Dependencias reproducibles y CI

Estado: vigente. Ultima verificacion: `2026-09-01`.

Este documento gobierna la instalacion de desarrollo, la actualizacion de
dependencias y el rollback. El runtime operativo conserva su entorno; una
actualizacion nunca se aplica implicitamente a `.venv` ni modifica `.env`.

## Autoridades

- `pyproject.toml`: dependencias directas y rangos soportados de Python.
- `requirements-dev.lock`: resolucion exacta, transitiva y con hashes para
  Python `3.12`; CI fija el parche `3.12.14`.
- `dashboard/package.json`: dependencias directas del frontend.
- `dashboard/package-lock.json`: resolucion exacta del frontend para Node
  `22.15.0` y npm `11`.
- `.github/workflows/ci.yml`: definicion reproducible de validacion en un clon
  limpio.

No editar manualmente los paquetes transitivos de los archivos lock.

## Instalacion de desarrollo

Crear y activar un entorno virtual Python `3.12`, y luego ejecutar:

```powershell
python -m pip install --require-hashes -r requirements-dev.lock
python -m pip install --no-deps --no-build-isolation -e .
```

Para el dashboard:

```powershell
Set-Location dashboard
npm ci
```

`pip install -e .[dev]` puede usarse para explorar una actualizacion, pero no
demuestra reproducibilidad y no sustituye la instalacion desde el lock.

## Actualizacion Python

1. Cambiar solamente los rangos directos necesarios en `pyproject.toml`.
2. Regenerar con Python `3.12` y la version de `pip-tools` declarada:

```powershell
python -m piptools compile --extra dev --generate-hashes --allow-unsafe `
  --strip-extras --resolver=backtracking `
  --output-file=requirements-dev.lock pyproject.toml
```

3. Instalar el lock en un entorno limpio.
4. Ejecutar `pip-audit`, `pip check` y las puertas backend.
5. Revisar el diff completo; una actualizacion transitiva inesperada exige
   justificacion o rollback.

Auditoria:

```powershell
python -m pip_audit --require-hashes -r requirements-dev.lock
python -m pip check
```

## Actualizacion frontend

1. Cambiar solamente la dependencia directa requerida.
2. Ejecutar `npm install` exclusivamente para regenerar
   `dashboard/package-lock.json`.
3. Borrar el entorno de prueba, ejecutar `npm ci`, typecheck, build y auditoria.
4. Revisar cambios directos y transitivos antes de integrar.

```powershell
Set-Location dashboard
npm ci
npm audit --audit-level=high
npm run typecheck
npm run build
```

## Politica de actualizacion y rollback

- Actualizar una familia de dependencias por cambio; no mezclarla con features.
- Vulnerabilidades altas o criticas bloquean CI. Una excepcion necesita alcance,
  mitigacion, responsable y fecha de retiro documentados.
- Cambios mayores requieren revisar notas de migracion y ejecutar un clon
  limpio antes de actualizar el lock.
- El rollback restaura juntos el manifiesto y su lock desde el ultimo commit
  verde; nunca se restaura solo uno.
- Tras el rollback se repiten instalacion, auditorias y todas las puertas.
- No actualizar dependencias directamente dentro del entorno del runtime como
  mecanismo de despliegue.

## CI y proteccion de rama

El workflow `CI` crea los checks `Backend` y `Frontend`. Usa PostgreSQL temporal,
password publico exclusivo de CI y `TARGET_URL=example.invalid`; los helpers
inyectan claves y destinos ficticios dentro de cada escenario. CI no carga
`.env`, no abre el portal y no se conecta a PostgreSQL, WhatsApp o Telegram
operativos.

`Backend` conserva JUnit y cobertura durante 14 dias. `Frontend` conserva el
build durante 7 dias. La rama `main` exige ambos checks con estado actualizado
respecto de su base; GitHub no permite integrar si alguno falta o falla.
