# Validación manual de evidencias por WhatsApp — 23-07-2026

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

- el álbum de evidencia y cobro queda listo, pero el operador todavía pulsa
  **Enviar 2 seleccionados** en WhatsApp;
- el postpago funciona, pero el operador todavía inicia **Enviar post-pago**
  después de registrar el pago.

La automatización futura debe agregar los dos disparadores descritos sin
reescribir primero la interacción Playwright que ya superó las pruebas:

- disparador de álbum después de la revisión diferida y Telegram;
- disparador de postpago después de confirmar la transición del pago a `paid`.

Antes de conectar esos disparadores se debe:

- probar el botón de una orden real controlada, todavía con envío humano final;
- verificar el clic y la confirmación automáticos del álbum con el número
  personal;
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
