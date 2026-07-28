# Documentacion del proyecto

Esta es la entrada principal. Para operar o decidir el siguiente trabajo no es
necesario recorrer toda la carpeta.

## Lectura recomendada

1. [`project-status.md`](project-status.md): que existe, que se valido y que
   falta.
2. [`roadmap/README.md`](roadmap/README.md): unico orden de trabajo pendiente.
3. [`operations/README.md`](operations/README.md): arranque, salud, recuperacion
   y rollback.
4. [`optimization.md`](optimization.md): mediciones, decisiones y limites de
   optimizacion.
5. [`finance/README.md`](finance/README.md): registro de costos, conciliacion de
   2Captcha y gastos de captacion.

Los dos primeros archivos gobiernan el trabajo:

- `project-status.md` responde **como vamos, que se realizo, que funciona y que
  riesgos existen**;
- `roadmap/README.md` responde **que toca hacer ahora y en que orden**.

Antes de implementar un cambio se deben leer ambos. Al cerrar una fase se
actualizan en el mismo cambio si el estado o la prioridad variaron.

## Referencias

- `architecture/`: runtime vigente e historia de la migracion.
- `contracts/`: contratos de API, estados y seguridad de reserva.
- [`incidente-backoff-reglas-fecha-2026-07-24.md`](incidente-backoff-reglas-fecha-2026-07-24.md):
  diagnostico, mejora acordada y limites de rollback para el backoff causado
  por varias fechas fuera de rango.
- `operations/evidence-policy.md`: retencion y sanitizacion de evidencia.
- `history/`: hitos y fases terminadas.
- `reports/`: metricas y bitacoras generadas; no son listas de tareas.

Las cifras variables viven en `reports/`; los documentos manuales solo enlazan
a ellas para evitar contradicciones.

Los contratos, incidentes, runbooks y reportes son referencias. No deben crear
colas paralelas de tareas ni reemplazar el estado maestro.
