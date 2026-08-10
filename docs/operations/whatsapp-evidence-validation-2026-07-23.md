# Validación manual de evidencias por WhatsApp — 23-07-2026

> Evidencia historica de validacion manual. El estado vigente esta en
> `docs/project-status.md`.

## Objetivo

Validar con el número personal del operador el mismo flujo Playwright que usa
una orden real para preparar el álbum de evidencia y cobro, sin modificar
órdenes ni enviar información a clientes.

## Resultado

Se realizaron varias pruebas manuales desde **Órdenes > Probar evidencias**.
Todas terminaron correctamente:

- WhatsApp Web abrió el chat esperado;
- aparecieron las dos imágenes del álbum;
- el operador realizó un único envío manual;
- las dos imágenes llegaron al número de prueba;
- los mensajes alcanzaron doble check azul;
- no se reportaron duplicados;
- el flujo continuó funcionando mientras el operador utilizaba otras
  aplicaciones.

La preparación puede demorar porque espera el chat, el menú de adjuntos, un
selector que acepte múltiples imágenes y las dos miniaturas antes de declarar
el álbum listo. Esa espera es preferible a avanzar sobre controles que todavía
no están visibles.

## Hallazgo menor

Los textos de ambas imágenes aparecen combinados como descripción de la primera
imagen. No impide preparar ni enviar el álbum y el operador considera aceptable
este formato.

El comportamiento proviene de la estrategia vigente que combina ambos textos
para evitar la selección y verificación frágil de cada miniatura. Separar las
descripciones no es requisito para automatizar el flujo y no debe cambiarse
mientras implique arriesgar la estabilidad ya comprobada.

## Paridad entre prueba y orden real

El simulacro y el botón de una orden real usan el mismo motor Playwright para
abrir WhatsApp, localizar **Adjuntar**, seleccionar **Fotos y videos**, cargar
dos imágenes y preparar el álbum.

Las diferencias están antes de Playwright:

- el simulacro crea datos ficticios y no modifica órdenes;
- una orden real exige reserva confirmada, evidencia PNG segura, WhatsApp
  internacional, cobro pendiente y monto acordado;
- una orden real registra el paquete preparado y su confirmación de envío.

Por ello, las pruebas personales validan la interacción con WhatsApp, pero se
debe realizar al menos una validación controlada desde una orden real antes de
habilitar cualquier envío automático.

## Flujo operativo acordado

La evidencia y el cobro forman un solo mensaje comercial y deben permanecer
juntos. El flujo objetivo es:

1. El bot confirma completamente la reserva.
2. Termina la revisión diferida, obtiene la evidencia definitiva y envía la
   información diferida por Telegram.
3. Envía automáticamente por WhatsApp un álbum con:
   - la evidencia de la cita y sus datos;
   - la imagen QR de Yape con las indicaciones para pagar;
   - el texto combinado vigente, aunque aparezca asociado a la primera imagen.
4. El cliente realiza el pago.
5. El operador verifica el ingreso del dinero y pulsa **Registrar pago** en el
   dashboard.
6. Solo después de que el backend confirme que el pago quedó registrado
   correctamente como `paid`, envía automáticamente el postpago con los PDF y
   las indicaciones.

El envío del álbum inicial no registra un pago. La validación del dinero siempre
es humana. Si **Registrar pago** falla o la orden no alcanza el estado `paid`,
el postpago no debe ejecutarse.

## Estado actual y cambios futuros

Actualmente:

- **Probar evidencias** permite revisar las dos imágenes y sus textos antes de
  autorizar un único intento automático;
- después de la confirmación, Playwright prepara el álbum, pulsa **Enviar**,
  espera que desaparezca la vista previa, comprueba el regreso al chat normal,
  registra el paquete como `sent` y cierra la sesión;
- si WhatsApp no confirma el texto o el regreso al chat, el paquete no se marca
  como enviado y no existe un reintento automático;
- el botón de una orden real permite la misma revisión y confirmación desde el
  dashboard; después ejecuta el mismo envío automático validado por el
  simulacro;
- el postpago funciona, pero el operador todavía inicia **Enviar post-pago**
  después de registrar el pago.

La automatización futura debe agregar los dos disparadores descritos sin
reescribir primero la interacción Playwright que ya superó las pruebas:

- disparador de álbum después de la revisión diferida y Telegram;
- disparador de postpago después de confirmar la transición del pago a `paid`.

Antes de conectar esos disparadores se debe:

- completar una serie estable del envío automático mediante
  **Probar evidencias** y órdenes reales controladas;
- verificar el disparador de postpago con una orden controlada cuyo pago haya
  sido confirmado por el operador;
- conservar estados independientes para el álbum inicial, el pago y el
  postpago;
- limitar cada disparador a un intento automático y dejar los fallos para
  revisión o reintento manual;
- marcar un paquete como `sent` solo cuando WhatsApp confirme que salió de la
  vista previa y regresó al chat normal;
- impedir duplicados cuando se reinicie el Admin API, Playwright o el equipo.

## Criterios para futuras pruebas

Cada prueba debe registrar:

- orden o simulacro utilizado;
- destinatario esperado;
- momento en que se creó el paquete;
- aparición de las dos imágenes y del texto;
- resultado del intento automático;
- estado HTTP y estado persistido;
- recepción y doble check azul;
- ausencia de duplicados;
- comportamiento después de cerrar WhatsApp o reiniciar el Admin API.

No se habilitará el disparador automático para clientes hasta completar una
serie estable con el número personal y una validación real controlada. Un fallo
de WhatsApp nunca debe retrasar la siguiente reserva ni impedir la notificación
diferida de Telegram.

El simulacro automático mantiene un margen de hasta tres minutos para que
WhatsApp complete las esperas visibles. Esto evita que el dashboard declare un
timeout mientras Playwright todavía está trabajando. Durante ese intervalo no
se debe iniciar otro envío ni cerrar la ventana.

## Primer intento automático y corrección

La primera validación automática reveló un falso positivo. WhatsApp cargó las
dos imágenes y el texto, pero Playwright no pulsó el botón negro de envío. Aun
así, la comprobación genérica interpretó el compositor visible detrás de la
vista previa como regreso al chat, cerró la sesión y registró `sent`.

Las capturas `whatsapp-album-before-send.png` y `whatsapp-album-sent.png`
quedaron idénticas: ambas conservaban las dos miniaturas y el botón Enviar. Por
lo tanto, ese paquete no constituye evidencia de envío exitoso.

La corrección deja de reutilizar el selector genérico de postpago:

- exige dos miniaturas inmediatamente antes del clic;
- selecciona el control visible situado en la esquina inferior derecha;
- realiza un solo clic;
- espera hasta 30 segundos a que desaparezcan las dos miniaturas;
- exige además que regrese el compositor normal;
- si las miniaturas continúan visibles, guarda
  `whatsapp-album-send-not-confirmed.png`, deja la ventana abierta para
  inspección, conserva el paquete sin confirmar y no reintenta automáticamente.

Esta corrección requiere una nueva prueba con el número personal antes de
considerar validado el envío automático.

## Validación automática correcta — 24-07-2026

La repetición posterior terminó correctamente:

- el paquete ficticio se creó a las 11:23:10;
- Playwright abrió el chat y preparó las dos imágenes;
- el álbum se envió automáticamente a las 11:23:36;
- `/web/prepare` respondió HTTP 200 y registró `sent`;
- no hubo una llamada manual posterior a `/sent`;
- la captura final mostró el chat normal, sin miniaturas, con el texto y las dos
  imágenes salientes;
- el operador confirmó que el envío llegó correctamente.

Con esta evidencia, el mismo modo automático quedó habilitado para el botón
controlado de una orden real. Esto todavía no activa envíos en segundo plano
después de una reserva: el operador revisa el paquete y confirma **Enviar ahora**
desde el dashboard.

## Activación de disparadores — 25-07-2026

La limitación anterior quedó superada con una bandeja persistente y dos
disparadores. El álbum se encola después de la revisión diferida y Telegram; el
postpago se encola únicamente después de registrar el pago como `paid`. El motor
Playwright validado no fue reescrito.

Cada orden y tipo de mensaje conserva una clave única y un solo intento
automático. Un resultado fallido o incierto no se reintenta solo, genera alerta
por Telegram y queda disponible para recuperación manual. El detalle técnico y
el motivo de la decisión están en
[`whatsapp-automatic-triggers-2026-07-25.md`](whatsapp-automatic-triggers-2026-07-25.md).
