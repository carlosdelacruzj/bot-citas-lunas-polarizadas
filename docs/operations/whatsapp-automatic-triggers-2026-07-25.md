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

La misma condición volvió a aparecer a las 09:09 con el postpago de
`order-44836574`: el worker tomó el trabajo y solicitó vinculación, aunque el
Admin API conservaba una sesión válida. Este segundo resultado confirmó que el
problema pertenecía a la propiedad del perfil entre procesos y no solamente al
destinatario del primer álbum.

## Corrección aplicada después del primer resultado

La corrección posterior conserva al Admin API como único proceso emisor. El
worker continúa creando trabajos después de las reservas, pero ya no inicia un
dispatcher ni abre el perfil persistente de WhatsApp.

Antes de cambiar un trabajo a `running`, el emisor valida la sesión desde el
mismo contexto Playwright que realizará el envío. Si la sesión no está lista:

- el trabajo pasa a `blocked`;
- `attempt_count` permanece en `0`;
- se programa otra prevalidación un minuto después;
- se alerta una sola vez por cada error distinto;
- no se adjuntan archivos ni se pulsa Enviar.

Una sesión que se pierde entre la prevalidación y la apertura del chat también
devuelve el trabajo a `blocked` sin consumir el intento.

La apertura del chat ya no interpreta cualquier `canvas` visible como un QR.
Ahora espera el compositor y clasifica por separado:

- `login_required`: existe un QR real;
- `invalid_recipient`: WhatsApp rechaza o no reconoce el número;
- `chat_unavailable`: la sesión está vinculada, pero el chat no termina de
  cargar.

Los tres casos guardan una captura identificada por `message_id`. Solo
`login_required` queda recuperable automáticamente; los otros dos terminan como
fallo para revisión humana y no se reintentan solos.

La validación controlada usó un número deliberadamente imposible y
`auto_send=false`. WhatsApp dejó una página vacía sin compositor ni mensaje
explícito de número inválido, por lo que el resultado correcto fue
`chat_unavailable`, `sent=false`, sin adjuntos ni clic de envío. Después del
simulacro, la validación del perfil continuó en `session_ready`.
