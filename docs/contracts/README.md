# Contratos vigentes

Ultima verificacion: `2026-08-30`.

Los contratos describen invariantes actuales. No contienen cronologias,
resultados de canarios ni listas de trabajo futuro.

| Contrato | Codigo propietario | Cubre |
|---|---|---|
| [`admin-api.md`](admin-api.md) | `services/local_api.py`, `services/api/` | Frontera HTTP, autenticacion, privacidad y errores. |
| [`order-lifecycle.md`](order-lifecycle.md) | `core/`, `db/orders.py` | Estados, precio, restricciones, pagos y cierre. |
| [`reservation-safety.md`](reservation-safety.md) | `reservation_engine/`, `worker/` | Leases, seleccion, submit y evidencia. |
| [`worker-control.md`](worker-control.md) | `worker/`, `db/worker_commands.py` | Comandos persistidos y operacion segura. |
| [`captcha.md`](captcha.md) | `reservation_captcha*`, `services/captcha_shadow.py` | CAPTCHA HTML y servicio grafico opcional. |
| [`whatsapp.md`](whatsapp.md) | `services/whatsapp*`, `db/whatsapp*` | Jobs, plantillas, evidencia y conciliacion. |
| [`finance.md`](finance.md) | `db/finance*`, `services/api/finance*` | Cobros, costos, cierres y calidad. |
| [`appointment-followups.md`](appointment-followups.md) | `services/appointment_reminders.py`, `services/post_appointment.py` | Recordatorios, lotes, revision post-cita y frescura. |
| [`optimization.md`](optimization.md) | `worker/`, `reservation_engine/` | Comparabilidad, evidencia y limites de optimizacion. |

Si un contrato contradice el codigo activo o PostgreSQL, verificar primero el
runtime y corregir el contrato en el mismo cambio. Los contratos supersedidos se
recuperan puntualmente mediante [`../history/README.md`](../history/README.md).
