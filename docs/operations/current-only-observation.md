# Observacion para retirar compatibilidad anterior

Vigencia: `2026-08-31` a `2026-09-06`, zona `America/Lima`.

Objetivo: demostrar que la operacion actual no depende de contratos anteriores
antes de retirar definitivamente codigo, puerto y respuestas compatibles. No
crear reservas ni envios de prueba para completar esta lista.

## Revision diaria

1. Confirmar Admin API `8766`, PostgreSQL y worker saludables.
2. Confirmar una revision saludable de Telegram dentro de los ultimos diez
   minutos y ninguna alerta perdida.
3. Confirmar que `AppointmentBotMonitor` de n8n sigue inactivo y que no reaparece
   el sondeo de cinco minutos a `8765`.
4. Contar accesos a `GET /api/v1/monthly-summary`; se espera cero.
5. Contar listas de ordenes sin `projection=dashboard` y consultas post-cita sin
   parametros; identificar el consumidor antes de cualquier retiro.
6. Abrir Resumen, Ordenes, Citas y recordatorios y Finanzas. Verificar carga,
   filtros, paginacion y que Finanzas interpreta `conversion_complete`.
7. En el proximo postpago natural, comprobar texto no vacio, orden de adjuntos y
   trazabilidad. `sent` no prueba lectura y un resultado ambiguo no se reintenta.

## Umbrales para retirar

- Resumen mensual v1: cero accesos hasta el cierre del `2026-09-03`; puede
  retirarse desde el `2026-09-04`.
- API embebida `8765`: cero accesos naturales durante siete dias, con Telegram
  y Admin API saludables. Los chequeos manuales deben anotarse aparte.
- Ordenes sin proyeccion y post-cita sin query: cero consumidores identificados
  durante siete dias. Si aparece uno, migrarlo primero y reiniciar la ventana.

## Cierre y rollback

Conservar hasta el cierre el dump PostgreSQL previo a `v70` y los exports n8n
bajo `.runtime/`. Si falla un flujo actual, registrar hora, endpoint, pantalla y
error; no reactivar n8n ni restaurar datos sin comprobar primero trabajo activo
y determinar si el fallo depende realmente de la compatibilidad retirada.
