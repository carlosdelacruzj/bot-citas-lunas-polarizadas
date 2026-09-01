# Direccion de dependencias y deuda estructural

Vigente desde: `2026-09-01`.

Este contrato evita que crezcan dependencias inversas y ciclos mientras la
fase 5 retira la deuda existente. El control obligatorio vive en
`scripts/check-architecture.py`; su baseline versionada enumera excepciones
exactas, no permisos generales.

## Direccion permitida

| Origen | Capas internas permitidas |
|---|---|
| `core` | `core` |
| `db` | `core`, `db` |
| `reservation_engine` | `core`, `reservation_engine` |
| `services` | `core`, `db`, `reservation_engine`, `services` |
| `worker` | `core`, `db`, `reservation_engine`, `services`, `worker` |

Las carpetas de infraestructura auxiliares no alteran estas reglas. El grafo
de ciclos si incluye todos los modulos de `appointment_bot`, para detectar un
ciclo que atraviese `utils`, `browser` u otra superficie neutral.

## Baseline temporal

La baseline conserva 19 imports inversos y dos componentes circulares ya
existentes. El check falla si aparece deuda nueva y tambien si una excepcion
desaparece sin retirar su entrada: cada mejora debe reducir la baseline en el
mismo commit. La fase 5.3 la lleva a cero; no se esconden ciclos nuevos mediante
imports locales.

Ejecutar desde la raiz:

```powershell
python scripts/check-architecture.py --report reports/ci/architecture.json
```

## Clones y codigo sin consumidor

CI genera reportes de `vulture` para Python y `jscpd` para el dashboard. Durante
la linea base son informativos y no bloquean por hallazgos. TypeScript si bloquea
con `noUnusedLocals` y `noUnusedParameters`.

Un reporte aislado nunca autoriza borrar codigo. Antes de retirar un simbolo se
deben revisar entry points de `pyproject.toml`, rutas, plantillas Angular,
callbacks, imports diferidos, compatibilidad medida y consumidores encontrados
por busqueda o Graph; despues se ejecutan las pruebas del dominio.
