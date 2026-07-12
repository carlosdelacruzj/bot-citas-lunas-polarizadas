# Operacion y observabilidad

## P0 - Reporte semanal comparable

Estado: completado el 12 de julio de 2026.

Implementado:

1. `appointment-bot-client weekly-report --start YYYY-MM-DD --end YYYY-MM-DD`
   genera Markdown y CSV por rango exacto y compara el periodo anterior de la
   misma duracion.
2. `registered`, `Programado/completed`, no confirmadas, `slot_lost`, reglas y
   defensas se muestran por separado.
3. Deteccion a fin, CAPTCHA, seleccion y cambio de usuario incluyen n, p50 y
   p90; CAPTCHA tambien cuenta respuestas mayores a 3, 5, 10 y 20 segundos.
4. El reporte etiqueta fechas inclusivas, zona `America/Lima`, runs e intentos.
5. El acumulado historico queda explicitamente fuera de la tabla semanal.

Criterio de cierre cumplido: el reporte `2026-07-06` a `2026-07-12` se genero
contra `2026-06-29` a `2026-07-05` sin releer logs largos.

## P1 - Alertas y runbook

Estado: completado el 12 de julio de 2026.

1. El reporte alerta CAPTCHA mayor a 10 segundos y aumento sostenido de
   `slot_lost`; `--notify` envia las alertas por Telegram.
2. `docs/operations/runbook.md` define `outside_hot_window` como espera sana.
3. El runbook separa recuperacion de worker y admin-dashboard.
4. `scripts/verify-postgres-backup.ps1` restaura en una base temporal, compara
   tablas esenciales y elimina dump/base al finalizar.
5. Resultados y conteos verificados quedaron registrados en
   `docs/project-status.md`.

## P1 - Higiene de evidencia

Estado: completado el 12 de julio de 2026.

1. Resumen e indice vigentes se regeneran junto con cada exportacion.
2. `docs/` mantiene la lectura vigente y `reports/evidence/` la salida fechada;
   se retiraron salidas fechadas duplicadas anteriores.
3. `docs/operations/evidence-policy.md` define retencion de screenshots y HTML.
4. La sanitizacion cubre identificadores numericos de 8 a 16 digitos y los
   artefactos vigentes fueron regenerados sin documento/contacto/cuenta crudos.
