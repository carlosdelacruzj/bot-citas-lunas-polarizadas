# Documentacion del proyecto

Esta es la entrada principal. Para operar o decidir el siguiente trabajo no es
necesario recorrer toda la carpeta. La clasificacion integral de los `40`
archivos revisados el `2026-08-09` vive en
[`history/documentation-audit-2026-08-09.md`](history/documentation-audit-2026-08-09.md).

## Lectura recomendada

1. [`project-status.md`](project-status.md): que existe, que se valido y que
   falta.
2. [`roadmap/README.md`](roadmap/README.md): unico orden de trabajo pendiente.
3. [`operations/README.md`](operations/README.md): arranque, salud, recuperacion
   y rollback.
4. [`optimization.md`](optimization.md): metodologia, mediciones y limites de
   optimizacion; el orden futuro siempre vuelve al roadmap.
5. [`finance/README.md`](finance/README.md): registro de costos, conciliacion de
   2Captcha y gastos de captacion.

Los dos primeros archivos gobiernan el trabajo:

- `project-status.md` responde **como vamos, que se realizo, que funciona y que
  riesgos existen**;
- `roadmap/README.md` responde **que toca hacer ahora y en que orden**.

Antes de implementar un cambio se deben leer ambos. Al cerrar una fase se
actualizan en el mismo cambio si el estado o la prioridad variaron.

## Mapa de autoridad

| Tipo | Autoridad | Uso |
| --- | --- | --- |
| Estado | [`project-status.md`](project-status.md) | Capacidades, validaciones, metricas y riesgos actuales. |
| Trabajo futuro | [`roadmap/README.md`](roadmap/README.md) | Unica cola y orden de implementacion. |
| Operacion | [`operations/README.md`](operations/README.md) | Arranque, salud, controles, recuperacion y rollback. |
| Arquitectura | [`architecture/README.md`](architecture/README.md) | Runtime vigente y migracion historica. |
| Contratos | [`contracts/README.md`](contracts/README.md) | Fronteras normativas de API, estados y seguridad. |
| Evidencia | [`operations/evidence-policy.md`](operations/evidence-policy.md) | Retencion, sanitizacion y limites de publicacion. |
| Historia | [`history/`](history/) | Hitos, planes cerrados y cortes que no gobiernan el runtime. |

## Referencias

- [`architecture/`](architecture/): runtime vigente e historia de la migracion.
- [`contracts/`](contracts/): contratos de API, estados y seguridad de reserva.
- [`incidente-backoff-reglas-fecha-2026-07-24.md`](incidente-backoff-reglas-fecha-2026-07-24.md):
  diagnostico, mejora acordada y limites de rollback para el backoff causado
  por varias fechas fuera de rango.
- [`operations/evidence-policy.md`](operations/evidence-policy.md): retencion y
  sanitizacion de evidencia.
- [`history/`](history/): hitos, fases terminadas y auditorias documentales.
- `reports/`: metricas y bitacoras generadas; no son listas de tareas.

Las cifras variables viven principalmente en `reports/`. `evidence-summary.md`
y `evidence-index.csv` son excepciones generadas dentro de `docs/`: deben
declarar su fecha y cobertura y nunca equivalen a los totales comerciales vivos
de PostgreSQL.

Los contratos, incidentes, runbooks y reportes son referencias. No deben crear
colas paralelas de tareas ni reemplazar el estado maestro.

## Estados documentales

Los documentos no rectores deben indicar cuando corresponda:

- `Vigente`: aplica a la operacion actual.
- `Historico`: conserva evidencia fechada, no configuracion actual.
- `Supersedido`: fue reemplazado y solo conserva trazabilidad.
- `Generado`: snapshot regenerable con rango y fecha de corte.

No se elimina un documento solo por estar desactualizado. Primero se migra su
contenido unico, se actualizan backlinks y se comprueba que no sea evidencia
necesaria. Una reescritura del historial Git para retirar datos antiguos es una
operacion destructiva separada y requiere autorizacion explicita.
