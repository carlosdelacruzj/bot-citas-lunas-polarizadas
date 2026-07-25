# Disparadores automáticos de WhatsApp — 25-07-2026

## Problema que resuelve

El motor Playwright ya enviaba correctamente el álbum de evidencia y cobro y el
paquete postpago, pero ambos dependían de una acción posterior del operador en
el dashboard. Esto dejaba una reserva confirmada o un pago registrado sin
mensaje si el operador no ejecutaba el botón correspondiente.

## Decisión

Se conectaron dos disparadores independientes:

1. `reservation_album`: se encola después de completar la revisión diferida,
   actualizar la evidencia definitiva e intentar la notificación por Telegram.
2. `post_payment_followup`: se encola en la misma transacción de PostgreSQL que
   cambia el pago y la orden a `paid`.

El primer envío contiene la evidencia y el QR de Yape en un solo álbum. Registrar
o enviar ese álbum no confirma el pago. La verificación del dinero sigue siendo
humana. El segundo envío solo puede comenzar después de la transición real a
`paid`.

## Seguridad e idempotencia

La tabla `whatsapp_automation_jobs` conserva un trabajo único por orden y tipo.
Sus estados son:

- `queued`: todavía no comenzó y puede recuperarse después de un reinicio;
- `running`: el único intento automático ya comenzó;
- `sent`: WhatsApp confirmó la salida;
- `failed`: el intento terminó sin envío confirmado;
- `uncertain`: el resultado puede ser ambiguo y requiere revisión.

Cada trabajo admite como máximo un intento. Si el proceso termina mientras un
trabajo está `running`, el lease vence y el trabajo pasa a `uncertain`; nunca
regresa automáticamente a `queued`. Un índice parcial permite un solo trabajo
`running` entre procesos, protegiendo el perfil persistente de WhatsApp Web.

Mientras un trabajo está `queued` o `running`, los botones manuales no pueden
preparar otro paquete para la misma orden. Después de `failed` o `uncertain`, el
dashboard permanece disponible para revisar y realizar un reintento humano.

## Aislamiento operativo

El dispatcher usa un hilo daemon separado del worker de citas. Los disparadores
solo escriben en PostgreSQL y regresan; no esperan a que WhatsApp abra, adjunte o
envíe. Por ello, un WhatsApp lento o desconectado no bloquea la siguiente reserva
ni revierte el registro del pago.

Ante un fallo o resultado incierto:

- se guarda el estado y el detalle en PostgreSQL;
- se conserva el paquete preparado cuando exista;
- se envía una alerta operativa por Telegram;
- no se hace un segundo intento automático.

## Motivo para conservar este registro

Si la automatización causa demoras, duplicados o mensajes fuera de orden, la
unidad de reversión es el disparador/dispatcher y la tabla de trabajos. El motor
Playwright validado, la composición del álbum y el flujo manual no deben
reescribirse para desactivar los disparadores.

## Primer resultado real y problema observado

La primera serie automática procesó tres álbumes el 25-07-2026:

| Orden | Inicio (Lima) | Resultado | Detalle |
| --- | --- | --- | --- |
| `order-43052362` | 08:27:18 | `failed` | El chat no quedó listo y se informó que la sesión necesitaba vincularse. |
| `order-002394293` | 08:27:45 | `sent` | Álbum de dos imágenes confirmado a las 08:27:57. |
| `order-44836574` | 08:27:57 | `sent` | Álbum de dos imágenes confirmado a las 08:28:14. |

El primer paquete quedó `prepared`, sin `sent_at`. El flujo retornó antes de
adjuntar las imágenes, por lo que no hubo clic de envío ni evidencia de entrega
parcial.

La serie reveló una limitación que la exclusión por trabajo no cubría: el worker
y el Admin API iniciaban dispatchers independientes. PostgreSQL impedía dos
trabajos `running` al mismo tiempo, pero cada proceso podía conservar su propio
contexto Playwright sobre el mismo perfil persistente. El primer trabajo fue
tomado por el worker y no obtuvo el compositor del chat; los dos siguientes
fueron tomados por el Admin API y utilizaron su sesión ya validada.

También se detectó una limitación de observabilidad. `_wait_for_chat(...)`
devolvía el mismo resultado `login_required` cuando el compositor no aparecía,
sin distinguir entre:

- una sesión realmente desvinculada;
- un destinatario inválido o no disponible en WhatsApp;
- un timeout de carga del chat.

Por esta razón, el error persistido describe con certeza que el chat no quedó
listo, pero no prueba por sí solo que se hubiera mostrado un QR.

## Corrección planteada después de esta versión

La siguiente versión debe:

- conservar un único proceso emisor y dejar al worker únicamente como productor
  de trabajos;
- validar la sesión antes de consumir el intento automático;
- mantener recuperable un trabajo que no comenzó por falta de sesión;
- diferenciar sesión desvinculada, destinatario inválido y timeout;
- guardar una captura cuando el chat no llegue al compositor.
