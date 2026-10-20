# Direccion de dependencias y deuda estructural

Vigente desde: `2026-09-02`.

Este contrato evita dependencias inversas y ciclos nuevos. El control obligatorio vive en
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

## Baseline vigente

La baseline conserva un unico import inverso conocido y ningun ciclo. El check
falla si aparece deuda nueva y tambien si una excepcion desaparece sin retirar
su entrada. CI ejecuta el control como paso obligatorio; los imports locales no
se usan para esconder relaciones entre modulos.

Los contratos, DTO y selectores de citas viven en `appointment_contracts.py`;
las lecturas DOM neutrales viven en `appointment_dom.py`. El marcado visual de
cupos se solicita desde `reports/run_reporting.py` despues de que `utils`
archiva la captura, sin dependencia inversa desde infraestructura compartida.
La cola y la ejecucion de ordenes exponen bundles inmutables de dependencias;
produccion usa sus defaults y las pruebas reemplazan funciones mediante fakes
explicitos, sin reasignar globals ni una fachada dinamica.

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
