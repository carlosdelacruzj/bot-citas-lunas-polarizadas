# Continuidad manual por WhatsApp del registro alojado — 01-08-2026

## Objetivo

Cerrar de forma segura el paso entre el registro privado y la conversación de
WhatsApp que ya existe con el cliente. Esta primera entrega prepara el mensaje y
obliga al operador a revisar el destinatario y el estado antes de copiarlo. No
abre WhatsApp Web, no pulsa `Enviar` y no registra una entrega que no ocurrió.

## Alcance implementado

La vista `Invitaciones` permite usar `Preparar seguimiento` en estos estados:

| Estado local                        | Mensaje preparado                        | Condición operativa                                            |
| ----------------------------------- | ---------------------------------------- | -------------------------------------------------------------- |
| `submitted`, `leased`, `retry_wait` | Recepción con validación pendiente       | No afirmar que la cuenta ya fue validada                       |
| `accepted`                          | Acceso validado y comienzo del monitoreo | Solo usar tras una validación real en modo de producción       |
| `awaiting_restrictions`             | Solicitud de fechas restringidas         | No activar el monitoreo antes de recibirlas y confirmarlas     |
| `credentials_invalid`               | Aviso de corrección                      | No pedir la contraseña en el chat; emitir una invitación nueva |

El cuadro de revisión muestra:

- nombre o referencia local;
- WhatsApp completo conservado en PostgreSQL local;
- estado que originó el texto;
- mensaje completo y seleccionable;
- aviso visible `No se ha enviado nada`;
- acción única `Copiar mensaje`.

El texto de la invitación inicial también aclara que, después de completar el
registro, la atención continuará en ese mismo WhatsApp.

## Procedimiento del operador

1. Abrir `Invitaciones` y actualizar la lista.
2. Identificar al cliente por nombre o referencia y WhatsApp.
3. Comprobar el estado antes de preparar cualquier mensaje.
4. Pulsar `Preparar seguimiento`.
5. Volver a comparar destinatario, estado y texto en el cuadro de revisión.
6. Copiar el mensaje.
7. Pegar y enviar manualmente una sola vez en la conversación donde se entregó
   la invitación.
8. Si existe cualquier duda sobre el chat o el envío, revisar manualmente y no
   repetirlo por suposición.

## Límites deliberados

- Copiar no significa enviar.
- No existe todavía un estado durable de entrega para este seguimiento manual.
- No se automatizó la apertura del chat ni el envío.
- No se ejecutó una prueba con un número real durante esta entrega.
- El modo `controlled` solo permite revisar textos ficticios; un estado
  `accepted` de ese modo no autoriza enviar a un cliente que la cuenta fue
  validada.
- Un futuro envío asistido o automático debe usar la cola durable, un único
  propietario del perfil de WhatsApp Web y los estados `queued`, `running`,
  `sent`, `failed` y `uncertain`.
- `uncertain` nunca vuelve automáticamente a la cola.

## Validación controlada pendiente

La primera prueba externa debe usar una cuenta y un número controlados y seguir
`preparar → revisar → confirmar → un envío`. Antes de pulsar `Enviar` se debe
verificar explícitamente:

- número de destino;
- conversación correcta;
- estado local que originó el mensaje;
- texto completo;
- ausencia de datos sensibles;
- inexistencia de un mensaje equivalente ya enviado.

La prueba debe conservar únicamente evidencia sanitizada. Capturas con nombres,
números o conversaciones permanecen fuera de Git.

## Validación local ejecutada

- `npm run build` en `dashboard/`: correcto; bundle inicial `501.24 kB`.
- `python -m compileall -q src`: correcto.
- `python -m ruff check src tests`: correcto.
- `python -m pytest -q`: `59 passed`.
- `git diff --check`: correcto.
- Auditoría estática de la interfaz nueva: controles semánticos, label del
  mensaje, foco visible, estado anunciado con `aria-live` y texto largo
  seleccionable.
- No se abrió WhatsApp Web ni se transmitió un mensaje.
- La revisión visual directa no se pudo ejecutar porque el navegador integrado
  no estuvo disponible.

## Criterio para evaluar automatización

No automatizar la confirmación hasta comprobar el recorrido manual sin
destinatarios incorrectos ni mensajes duplicados. Si se evalúa después, la
unidad inicial debe ser solo el acuse transaccional de recepción; las
restricciones y correcciones continúan bajo revisión humana.
