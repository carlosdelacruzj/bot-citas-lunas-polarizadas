# Operacion y observabilidad

## P0 - Reporte semanal comparable

Estado: pendiente.

1. Generar por rango exacto: `registered`, `Programado/completed`,
   `reservation_unconfirmed`, `slot_lost`, bloqueos por regla y defensas.
2. No sumar `completed` como `registered` sin explicarlo.
3. Calcular p50 y p90 de deteccion a fin, CAPTCHA, seleccion y cambio de usuario.
4. Etiquetar siempre fecha inicial, fecha final, zona horaria y cantidad de
   intentos medidos.
5. Separar acumulado historico del reporte semanal.

Criterio de cierre: dos semanas consecutivas pueden compararse sin releer logs
largos ni confundir ventanas distintas.

## P1 - Alertas y runbook

1. Alertar outliers de CAPTCHA y aumento sostenido de `slot_lost`.
2. Mantener `outside_hot_window` como espera saludable, no caida.
3. Documentar recuperacion de admin API, dashboard y worker por separado.
4. Agregar verificacion de backup/restore PostgreSQL sin versionar dumps.
5. Registrar toda validacion operativa importante en `project-status.md`.

## P1 - Higiene de evidencia

1. Mantener resumen e indice como primera lectura.
2. Evitar duplicados entre `docs/` y `reports/evidence/`; `reports/` debe ser la
   salida fechada y `docs/` el resumen vigente.
3. Conservar screenshots/HTML solo cuando la politica de evidencia los requiera.
4. Revisar que documentos, contactos y cuentas esten enmascarados en artefactos
   destinados a compartir.
