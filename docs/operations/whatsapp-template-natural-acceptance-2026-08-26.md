# Aceptación natural de plantillas de WhatsApp

Estado: **en observación**.

Este runbook permite cerrar la validación real de las plantillas editables sin
crear clientes ficticios, reenviar casos ambiguos ni modificar trabajos
históricos. Cada caso se revisa cuando ocurra naturalmente.

## Evidencia mínima por flujo

Para aceptar un flujo deben coincidir:

- el contenido visible en el chat y sus adjuntos;
- el destinatario y los datos comerciales de la orden;
- el estado técnico final (`sent`, `failed` o `uncertain`);
- la captura conservada por el intento;
- la clave y revisión de plantilla mostradas en el detalle;
- la alerta de Telegram, sin informar error cuando WhatsApp quedó confirmado.

`sent` confirma el envío técnico observado, no la lectura del destinatario.
`uncertain` es terminal y nunca autoriza un reintento automático.

## Casos pendientes

| Flujo | Comprobación natural | Condición para retirar el respaldo |
| --- | --- | --- |
| Registro correcto | texto, destinatario, captura, clave/revisión y ausencia de duplicado | un caso confirmado |
| Solicitud inexistente | variante correcta y una sola notificación por ciclo | un caso confirmado |
| Credenciales incorrectas | variante correcta y una sola notificación por ciclo | un caso confirmado |
| Reserva y cobro | dos imágenes, caption combinado, monto y dos revisiones | un caso confirmado |
| Pago confirmado | PDF primero, texto después y resultado separado por componente | un caso confirmado o incertidumbre correctamente conservada |
| Recordatorio pre-cita | nombre de quien asistirá, fecha larga, revisión vigente y modo sin cambios | un caso confirmado |

La revisión visual del editor sigue pendiente en `360`, `768`, `1024` y
`1440 px`. Esa revisión no envía WhatsApp.

## Recuperación controlada del 2026-08-26

El primer lote natural de reserva/cobro no cerró la aceptación automática. Las
cinco reservas quedaron confirmadas, pero sus trabajos fallaron antes de abrir
WhatsApp por un desfase de placeholders en el `INSERT` de
`whatsapp_messages`. Después de corregirlo, el operador autorizó preparar y
enviar manualmente los cinco paquetes faltantes.

Los cinco paquetes nuevos terminaron técnicamente `sent`, conservaron
`reservation_confirmation` revisión `2` y `reservation_payment` revisión `1`,
y no produjeron un estado ambiguo. El operador confirmó que todos llegaron. Los
trabajos originales no tenían un paquete preparado, por lo que se conciliaron
como `dismissed` con una nota que conserva la recuperación separada `sent`; no
se reescribió su estado técnico `failed`. La confirmación del operador acredita
llegada, pero no reemplaza la próxima observación natural del dispatcher, que
sigue siendo necesaria para retirar el respaldo de este flujo.

## Consultas de trazabilidad

Avisos de registro y recordatorios recientes:

```sql
SELECT job_key, order_id, job_kind, registration_notice_type, status,
       template_key, template_revision, error_message, finished_at
FROM whatsapp_automation_jobs
WHERE template_key IS NOT NULL
ORDER BY created_at DESC
LIMIT 30;
```

Reserva y cobro:

```sql
SELECT jobs.job_key, jobs.order_id, jobs.status,
       messages.confirmation_template_key,
       messages.confirmation_template_revision,
       messages.payment_template_key,
       messages.payment_template_revision,
       jobs.error_message, jobs.finished_at
FROM whatsapp_automation_jobs AS jobs
JOIN whatsapp_messages AS messages ON messages.message_id = jobs.message_id
WHERE jobs.job_kind = 'reservation_album'
ORDER BY jobs.created_at DESC
LIMIT 20;
```

Postpago:

```sql
SELECT jobs.job_key, jobs.order_id, jobs.status,
       followups.template_key, followups.template_revision,
       followups.status AS package_status, jobs.error_message, jobs.finished_at
FROM whatsapp_automation_jobs AS jobs
JOIN whatsapp_followup_messages AS followups
  ON followups.message_id = jobs.message_id
WHERE jobs.job_kind = 'post_payment_followup'
ORDER BY jobs.created_at DESC
LIMIT 20;
```

Cambios y restauraciones de plantilla:

```sql
SELECT created_at, actor, target_id, status, detail
FROM remote_control_audit
WHERE action = 'update_whatsapp_message_template'
ORDER BY created_at DESC;
```

Desde la Etapa 8A, `detail` distingue `source=operator_edit` de
`source=restore_recommended`. Los fallos productivos de renderizado quedan
visibles como error del trabajo que no pudo prepararse o enviarse.

## Regla de limpieza

La limpieza se hace por flujo, no en bloque. Cuando un caso cumpla toda la
evidencia anterior, se puede retirar únicamente su constructor hardcodeado y
validar de nuevo el proyecto. Hasta entonces, los constructores permanecen como
rollback; no son una segunda fuente activa mientras el consumidor use la
plantilla de PostgreSQL.
