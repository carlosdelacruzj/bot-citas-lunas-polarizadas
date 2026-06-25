# Version que detecto cupos - 25/06/2026

Este checkpoint documenta la version del bot que por primera vez detecto cupos reales
en produccion y envio alerta por Telegram.

## Evidencia observada

- Fecha de operacion: 25/06/2026, hora de Lima.
- Sede: LIMA-LA VICTORIA.
- Fecha detectada por el portal: 13/07/2026.
- Ventana de deteccion: aproximadamente 09:43:54 a 09:44:32.
- Logs principales:
  - `logs/run-20260625-072612.log`
  - `logs/worker-bootstrap-20260625.log`
- Resultado: el bot detecto opciones seleccionables de fecha y hora y envio alertas
  `[AVAILABLE]` por Telegram.

Detecciones registradas:

| Hora | Orden | Fecha | Hora disponible |
| --- | --- | --- | --- |
| 09:43:59 | `order-70569448` | 13/07/2026 | 10:00 |
| 09:44:07 | `order-09329652` | 13/07/2026 | 11:00 |
| 09:44:16 | `order-42334486` | 13/07/2026 | 11:00 |
| 09:44:24 | `order-70569448` | 13/07/2026 | 12:00 |
| 09:44:32 | `order-09329652` | 13/07/2026 | 12:00 |

Despues de esa ventana, el portal volvio a responder `Sin Cupos`.

## Comportamiento confirmado

- El bot logra iniciar sesion, entrar al seguimiento y abrir el panel de citas.
- La deteccion ya no depende solo de texto visible; valida opciones reales de fecha y hora.
- Las alertas principales salen desde el bot Python hacia Telegram.
- La cola multi-cliente usa sesiones independientes por orden.
- El worker guarda metricas por ventana para comparar horarios con datos.
- El corte diario de las 18:00 genera reporte final y detiene consultas nuevas.

## Configuracion recomendada para repetir la observacion

Estos valores reducen el espacio entre consultas dentro de ventanas calientes sin cambiar
credenciales ni tokens:

```env
OBSERVER_SESSION_SECONDS=120
OBSERVER_MAX_ATTEMPTS=3
OBSERVER_INTERVAL_MIN_SECONDS=20
OBSERVER_INTERVAL_MAX_SECONDS=30
OBSERVER_HOT_WINDOWS=08:00-08:30,09:30-10:00,11:40-12:40,15:55-16:30
UNAVAILABLE_STREAK_LIMIT=0
```

La razon del ajuste es que la disponibilidad real observada duro menos de un minuto. Con
intervalos de 45 a 70 segundos era posible no verla aunque el portal abriera cupos.

## Hipotesis actual

Con la evidencia del 25/06/2026, no parece que el problema principal haya sido un baneo
por IP. El bot pudo navegar, leer el panel y detectar disponibilidad real. La explicacion
mas probable es que antes habia demasiado espacio entre consultas para cupos que aparecen
y desaparecen en segundos.

Senales que si apuntarian a defensa o bloqueo del portal:

- HTTP 403 o HTTP 429.
- CAPTCHA inesperado fuera del flujo normal de reserva.
- Sesion cerrada repetidamente.
- Acceso denegado.
- Fallos de carga consistentes antes de llegar al panel de citas.

Si esas senales aparecen, el worker debe entrar en modo de recuperacion y pausar consultas
para bajar la huella.

## No versionar

No guardar en Git:

- `.env`
- tokens de Telegram
- claves de 2captcha
- contrasenas de clientes
- dumps o backups reales de PostgreSQL
- logs completos con datos sensibles
- screenshots o videos reales de clientes
