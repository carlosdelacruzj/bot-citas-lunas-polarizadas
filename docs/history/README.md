# Historial recuperable

El working tree conserva solo decisiones durables. Los planes, auditorias,
incidentes y rollouts detallados se eliminaron porque duplicaban contratos o
contenian estados supersedidos, datos sensibles y configuracion fechada.

Git conserva los originales en el commit base previo a la depuracion:
`5f49d464640764814346b3724f6e0a7a1315ab68`.

## Recuperacion puntual

Buscar una ruta antigua:

```powershell
git log --all --oneline -- docs/operations/remote-control-plan.md
```

Leerla sin restaurarla:

```powershell
git show 5f49d464:docs/operations/remote-control-plan.md
```

No restaurar historial completo para una tarea ordinaria. Extraer solo la
evidencia necesaria y contrastarla con codigo, PostgreSQL y contratos actuales.

Resumen durable: [`milestones.md`](milestones.md).

Este directorio está excluido de ripgrep y CodeGraph por defecto.
