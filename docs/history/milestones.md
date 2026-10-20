# Decisiones e hitos durables

Este resumen explica por qué existen las guardas actuales. No es estado vivo ni
roadmap.

## Reserva

- La primera deteccion real confirmó que los cupos pueden durar menos de un
  minuto y justificó monitoreo continuo.
- La primera reserva efectiva terminó inicialmente
  `reservation_unconfirmed`; desde entonces la confirmacion del portal es
  estricta y reconciliable.
- Cada cliente usa sesion Playwright aislada, claim y lease propios.
- Un cupo unico archiva screenshot inmediatamente antes de CAPTCHA o submit.
- Una fecha incompatible es `partial / blocked_by_order_rule`, sin backoff
  general.

## Arquitectura

- Worker y Admin API son procesos separados.
- Admin API es la frontera para dashboard, Telegram y n8n.
- Los controles viajan por `worker_commands`; Telegram no ejecuta SQL ni
  PowerShell.
- La API embebida del worker queda solo como compatibilidad local.

## CAPTCHA

- El servicio grafico evolucionó como experimento en sombra con fallback
  externo y nunca obtuvo autoridad ilimitada.
- Actualmente permanece en almacenamiento frio.
- El CAPTCHA HTML matematico es un mecanismo separado.

## WhatsApp

- El flujo pasó de trazas manuales a un dispatcher unico propiedad de Admin API.
- `sent`, `uncertain`, llegada y lectura son hechos separados.
- Un resultado ambiguo nunca se reintenta automaticamente.
- Plantillas futuras se versionan y cada job congela texto, clave y revision.

## Seguimiento

- Recordatorios y post-cita pertenecen a schedulers de Admin API.
- Recordatorios admiten anticipacion de `1..3` dias y barrera durable.
- Post-cita usa lectura serial, pausas conservadoras y cap diario.

## Finanzas y planes externos

- PostgreSQL gobierna cobros y costos; snapshots antiguos no representan
  utilidad ni estado vivo.
- Cloudinary, tres sesiones concurrentes y reescritura de historial nunca fueron
  autorizados como capacidad normal.

Los detalles fechados siguen recuperables desde Git cuando una investigacion los
necesite.
