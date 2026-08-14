# Resumen diario de cupos por WhatsApp — 30-07-2026

## Objetivo

Al finalizar la operación diaria, enviar al número personal configurado:

1. un mensaje con el texto
   `Resumen de cupos únicos hoy <día> de <mes> de <año>`;
2. todas las imágenes archivadas ese día en
   `screenshots/DD-MM-YYYY/cupos-unicos/`;
3. una publicación variable para TikTok lista para copiar.

Si no existen imágenes, se omite el álbum pero se conservan el mensaje de
cierre y la publicación.

## Disparador y propiedad

El worker encola el resumen después de la revisión final del corte de las
18:00, hora de Lima. El Admin API continúa como único propietario del perfil
persistente de WhatsApp Web y realiza el envío en segundo plano.

El destinatario vive fuera del repositorio en
`.runtime/whatsapp-daily-summary/config.json`. No se añadió el número a `.env`
ni a archivos versionados.

## Durabilidad y seguridad

El trabajo usa la clave `daily_slot_summary:YYYY-MM-DD`, por lo que solo puede
existir un resumen por fecha aunque el worker se reinicie después del corte.
PostgreSQL conserva destinatario, mensaje, rutas de imágenes y estado.

La publicación no utiliza IA ni consume tokens. Combina de forma determinista
12 títulos, 8 aperturas, 6 explicaciones, 8 llamados a la acción, 5
advertencias y 6 grupos de hashtags. El ciclo contiene 138,240 combinaciones.
Precio, condición de pago, WhatsApp público y límites de disponibilidad
permanecen fijos. La combinación se deriva de la fecha y el texto completo se
guarda dentro del trabajo durable antes del envío.

Desde el `2026-08-01`, el precio fijo usado por las nuevas publicaciones es
`S/50 por trámite`.

El texto debe quedar confirmado como mensaje saliente antes de adjuntar las
imágenes. Desde el `2026-08-13`, las imágenes se dividen en paquetes
secuenciales de hasta cuatro y cada paquete debe quedar confirmado antes de
abrir el siguiente; el último puede contener menos de cuatro. La publicación
se intenta únicamente después de confirmar todos los paquetes. Un resultado
ambiguo informa el paquete y el total previamente confirmado, queda
`uncertain` y no se reintenta automáticamente, porque el texto o las imágenes
podrían haber salido parcialmente.

## Primera validación real

El `30-07-2026` se envió al número personal configurado:

- el texto exacto `Resumen de cupos únicos hoy 30 de julio de 2026`;
- cuatro imágenes únicas;
- un único intento durable.

La primera confirmación técnica fue incorrecta: PostgreSQL terminó inicialmente
en `sent` porque la vista previa desapareció, pero el usuario recibió una sola
imagen. La captura posterior al clic mostró las cuatro burbujas con reloj,
todavía en carga, y Chromium se cerró antes de que tres terminaran.

El trabajo se reconcilió a `uncertain`, sin reenvío automático. La confirmación
vigente espera que aparezcan las cuatro imágenes salientes y que todas cambien
del estado pendiente a enviado o entregado antes de cerrar el navegador.

Después de la autorización expresa del usuario se creó un trabajo separado
`retry-1`. El reintento envió nuevamente el texto y las cuatro imágenes; todas
cambiaron a estado confirmado antes de cerrar y el trabajo terminó `sent`.
La publicación variable se incorporó después de esa validación y comenzará en
el siguiente cierre diario. Una prueba controlada posterior detectó dos
diferencias de representación en WhatsApp Web:

- el compositor transforma internamente los dígitos con emoji y no coincidía
  byte por byte con el texto original;
- la burbuja saliente transforma también algunos emojis, aunque el contenido
  visible permanezca completo.

La validación ahora compara el contenido alfanumérico normalizado tanto antes
como después del clic. La prueba final envió únicamente la publicación, mostró
el texto completo con doble check azul y se reconcilió a `sent` sin reenviar.

Una prueba completa adicional reveló que WhatsApp virtualiza mensajes antiguos:
la cantidad de imágenes o textos idénticos visibles en el DOM puede no aumentar
aunque exista un envío nuevo confirmado. Para imágenes se validan las últimas
`N` burbujas del lote cuando el historial fue reciclado. Para textos se compara
la identidad de la nueva burbuja confirmada, no solo el número de coincidencias.
Las evidencias con doble check se reconciliaron sin repetir contenido.

## Falso incierto del 07-08-2026

El cierre del 7 de agosto envió el texto, las imágenes y la publicación. El
operador confirmó la recepción del resumen y la captura
`.runtime/whatsapp-followup-text-send-uncertain.png` muestra la publicación
completa como burbuja saliente con doble check azul. Sin embargo, el trabajo
terminó `uncertain` porque el detector abandonaba la búsqueda al encontrar la
primera familia de selectores DOM, aunque la nueva burbuja estuviera disponible
mediante otra estructura compatible.

Desde el `2026-08-08`, la confirmación acumula las firmas encontradas en todas
las estructuras soportadas antes de comparar el estado anterior y posterior al
clic. Las capturas de texto usan nombres únicos por `message_id` y etapa para no
sobrescribir evidencia entre trabajos. El trabajo
`daily_slot_summary:2026-08-07` se reconcilió a `sent`, sin reenviar contenido;
los días anteriores conservan su estado porque no recibieron confirmación
externa equivalente.

## Falso incierto del 09-08-2026

El domingo 9 de agosto no existían capturas de cupos y el trabajo omitió el
álbum correctamente. El mensaje de cierre fue confirmado a las `18:00:31` y la
publicación de TikTok se envió inmediatamente después. El detector agotó sus
15 segundos sin reconocer la segunda burbuja y marcó todo el trabajo
`uncertain`; Telegram informó el estado global aunque el problema correspondía
únicamente a la confirmación automática del segundo texto.

La captura durable
`.runtime/whatsapp-daily-summary-daily_slot_summary-2026-08-09-publication-text-send-uncertain.png`
muestra ambos textos completos como burbujas salientes con doble check azul. El
operador confirmó la recepción. Por esa evidencia, el trabajo se reconcilió de
`uncertain` a `sent`, conservó `attempt_count=1` y su hora original de
finalización; no se creó ni envió un reintento.

La confirmación genérica de `[data-testid='msg-container']` ahora reconoce como
saliente un contenedor que posee una marca propia de enviado, entregado o leído.
El resultado del resumen también conserva por separado `summary`, `images` y
`publication`. Ante una ambigüedad futura, Telegram podrá indicar, por ejemplo,
**Resumen: confirmado**, **Imágenes: omitidas porque no había archivos** y
**Publicación TikTok: no confirmado automáticamente**, sin afirmar que falló el
paquete completo. La política de seguridad no cambió: un resultado ambiguo no
se reintenta automáticamente.

## Falso incierto del 13-08-2026 y validación de paquetes

El cierre del 13 de agosto confirmó el resumen y envió las `10` imágenes en
tres paquetes secuenciales de `4 + 4 + 2`. Cada paquete quedó confirmado antes
de abrir el siguiente y la publicación de TikTok se envió después del tercero.

La captura
`.runtime/whatsapp-daily-summary-daily_slot_summary-2026-08-13-publication-text-send-uncertain.png`
muestra la publicación completa como burbuja saliente con doble check azul a
las `18:02:07`. Esa confirmación apareció en el límite de la espera anterior de
`15` segundos, por lo que Telegram informó correctamente el estado automático
`uncertain` aunque el contenido sí llegó.

Desde ese caso, los textos esperan hasta `30` segundos, conceden `3` segundos
adicionales y vuelven a inspeccionar el DOM después de guardar la captura de
control final. Solo una burbuja saliente nueva con el texto esperado y marca de
enviado, entregado o leído permite terminar como `sent`. Sin esa evidencia se
mantiene `uncertain` y no se reintenta automáticamente.

La primera prueba deliberada, `retry-5`, copió el trabajo parcial `retry-4`.
Ese origen conservaba `message_text=''` para no repetir el resumen, de modo que
envió las `21` imágenes y TikTok pero omitió el encabezado. Tras la confirmación
del operador, su estado se corrigió de `sent` a `uncertain`.

La segunda prueba, `retry-6`, partió del trabajo original. La captura
`...retry-6-summary-text-sent.png` muestra **Resumen de cupos únicos hoy 12 de
agosto de 2026** como mensaje nuevo con doble check azul a las `21:48`. Después
se confirmaron seis paquetes `4 + 4 + 4 + 4 + 4 + 1`, y
`...retry-6-publication-text-send-uncertain.png` muestra TikTok completo con
doble check azul a las `21:49`.

El detector mantuvo un falso `uncertain` para TikTok incluso después de
`30 + 3` segundos. La inspección DOM posterior mostró que el check `Leído` sí
era reconocido, pero `text_content()` omitía los `17` emojis representados por
WhatsApp como elementos `<img alt="...">`; sin esos caracteres, la comparación
del texto completo fallaba.

La confirmación quedó simplificada: antes del clic se mantiene la validación
completa del compositor; después se toma la firma de las burbujas salientes ya
existentes y se espera compositor vacío más una burbuja nueva con estado
enviado, entregado o leído. No se vuelve a comparar el contenido ni los emojis.
Sin esas dos señales se conserva `uncertain` y no se reintenta. `retry-6` se
reconcilió a `sent` por las capturas, sin enviar una tercera vez.

## Uso futuro en la landing

Las capturas originales de `cupos-unicos` quedaron aprobadas como fuente de la
futura sección pública `Cupos encontrados recientemente`. Se mostrarán como
detecciones históricas, no como reservas ni disponibilidad vigente. El plan de
Cloudinary, idempotencia y aislamiento se documenta en
[`public-slot-evidence-cloudinary-plan-2026-08-01.md`](public-slot-evidence-cloudinary-plan-2026-08-01.md).
