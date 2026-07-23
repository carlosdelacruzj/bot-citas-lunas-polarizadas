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
imagen. No impide preparar ni enviar el álbum, pero debe corregirse antes de
considerar terminado el formato para clientes reales.

El comportamiento proviene de la estrategia vigente que combina ambos textos
para evitar la selección y verificación frágil de cada miniatura. La corrección
posterior debe mantener las esperas y verificaciones actuales y asignar cada
texto a su imagen sin reintroducir fallos intermitentes.

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

## Automatización acordada

La automatización debe respetar tres momentos distintos:

1. **Evidencia de reserva**: automática después de confirmar la reserva,
   completar la revisión diferida y enviar la información diferida por
   Telegram. Un fallo de WhatsApp no debe bloquear la cola ni Telegram.
2. **Cobro**: iniciado manualmente por el operador. No se envía ni se registra
   un cobro sin una acción explícita.
3. **Postpago**: automático únicamente después de que el operador valide el
   pago y ejecute la acción que registra la orden como pagada.

Antes de conectar esos disparadores se debe:

- separar la evidencia de reserva del mensaje de cobro;
- corregir la distribución del texto entre las dos imágenes;
- verificar el envío automático con el número personal;
- registrar estados independientes para evidencia, cobro y postpago;
- limitar cada disparador a un intento y dejar los fallos para revisión o
  reintento manual;
- impedir duplicados cuando se reinicie el Admin API, Playwright o el equipo.
