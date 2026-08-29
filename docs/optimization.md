# Contrato de optimizacion observacional

Ultima verificacion: `2026-08-29`.

Este documento define como comparar cambios del monitor y la reserva. No
contiene métricas vivas ni crea una cola distinta del roadmap.

## Objetivo

Optimizar `registered / intentos compatibles`, no tiempo aislado. Los resultados
`blocked_by_order_rule` y `priority_deferred` no son intentos compatibles.

## Cambios aislados

- medir una hipotesis por vez;
- no mezclar intervalos, orden, proveedor CAPTCHA, leases y confirmacion;
- mantener maximo dos sesiones concurrentes;
- preservar fallback y breakers;
- no promover una mejora con muestras pequeñas o periodos incomparables.

## Evidencia minima

Cada rafaga o intento comparable debe permitir reconstruir:

- orden y restricciones;
- inicio, fin y rol detector/auxiliar;
- candidato anterior y siguiente;
- lease y claim;
- tiempos a lectura, CAPTCHA, submit y confirmacion;
- screenshot del cupo unico;
- resultado y causa de salida.

## Comparacion

Un reporte declara `generated_at`, cobertura, dias esperados/faltantes, muestra y
definicion del denominador. Comparar periodos equivalentes y separar cambio
tecnico de valor comercial.

Fuentes:

- baseline generado: `reports/optimization/latest.md`;
- observaciones fechadas: `reports/optimization/observation-*.md`;
- operación: `reports/operations/latest.md`;
- evidencia: `docs/evidence-summary.md` y `docs/evidence-index.csv`;
- verdad actual: PostgreSQL.

`latest` es un artefacto, no estado vivo. Refrescar datos antes de concluir.

## Aceptacion vigente

Los runbooks de seguridad viven en:

- [`operations/opportunity-bursts.md`](operations/opportunity-bursts.md);
- [`operations/reservation-critical-path.md`](operations/reservation-critical-path.md);
- [`roadmap/README.md`](roadmap/README.md).

La cronologia retirada puede recuperarse mediante
[`history/README.md`](history/README.md).
