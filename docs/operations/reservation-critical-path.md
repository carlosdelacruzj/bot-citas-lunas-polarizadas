# Runbook de ruta critica de reserva

Estado: vigente. La muestra pendiente vive solamente en el roadmap.

## Camino rapido

Puede reducir esperas antes del clic solo si dos snapshots atomicos, separados
por `150 ms`, conservan sede, fecha, hora, cupos e identidad estables. La
seleccion debe seguir siendo compatible con la orden.

## Fallback

Si falta un campo, cambia la identidad o falla una lectura, volver
automaticamente a esperas conservadoras de `500/750 ms`. Un fallback aislado es
comportamiento seguro, no motivo de rollback global.

## Invariantes

- screenshot unico antes de CAPTCHA o submit;
- restricciones y claims revalidados;
- CAPTCHA y submit mantienen autoridad separada;
- confirmacion estricta del portal;
- ningun reintento de submit ambiguo.

## Telemetria

`selection_observation` y `reservation_timing` deben permitir comparar estrategia,
fallback, estabilidad, tiempo pre-click y resultado final sin contar entrenamiento
como reserva.

## Desactivacion

Las dos optimizaciones pueden desactivarse de forma independiente. Hacerlo en
una frontera segura, sin matar una orden ni submission activo.

Aceptacion pendiente: [`../roadmap/README.md`](../roadmap/README.md).
