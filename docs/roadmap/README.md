# Trabajo pendiente

Última priorización: `2026-07-28`.

Esta es la única lista de tareas futuras y el orden vigente de ejecución. El
estado de lo construido, validado y observado vive en
[`../project-status.md`](../project-status.md).

## Prioridad 0 - Recuperar una validación confiable

Estado: completado el `2026-07-28`.

Objetivo: volver a tener una suite que distinga regresiones reales de contratos
de prueba desactualizados.

Resultado:

1. Los 11 fallos correspondían a contratos de prueba desactualizados.
2. Claim y creación por API conservan el preflight obligatorio; las pruebas
   directas que necesitan una orden reclamable lo desactivan explícitamente.
3. Las expectativas ahora incluyen `document_type`, el contrato completo de
   restricciones y la firma vigente del muestreo CAPTCHA sombra.
4. No se modificó código productivo ni se redujeron protecciones de identidad,
   lease, selección o confirmación.
5. Suite final: `59 passed`.

Criterio de cierre: cumplido.

## Prioridad 1 - Consolidar los cambios recientes

Estado: en observación.

### WhatsApp automático

- Medir trabajos `sent`, `failed`, `blocked` y `uncertain`.
- Confirmar que solo Admin API abre el perfil persistente.
- Verificar que evidencia y Yape permanezcan en un solo álbum y que sus rutas
  deduplicadas sigan resolviendo en los próximos envíos.
- Verificar que el postpago solo se cree después de confirmar `paid`.
- No habilitar reintentos automáticos para resultados ambiguos.

### Reglas y backoff

- Esperar una nueva aparición real de varias fechas fuera de rango.
- Confirmar `partial / blocked_by_order_rule`, sin CAPTCHA resuelto, submit ni
  backoff general.
- Confirmar que una opción compatible posterior todavía se selecciona.

### Observer

- Comparar al menos dos o tres días con `OBSERVER_MAX_ATTEMPTS=4`.
- Revisar lecturas por hora, sesiones, errores, `slot_lost`, CAPTCHA y señales
  `403`, `429` o `recovery_backoff`.
- Cambiar una sola variable por experimento.

## Prioridad 2 - Cerrar el corte documental

Estado: iniciado con el punto de partida del `2026-07-25`.

1. Mantener `project-status.md` como estado maestro.
2. Mantener este archivo como única cola futura.
3. Corregir documentos con texto o fechas obsoletas solo cuando afecten una
   decisión actual; los documentos históricos no se reescriben.
4. Añadir a `history/` un nuevo cierre cuando termine esta fase de
   consolidación.

## Prioridad 3 - Reducir riesgo operativo

Estado: iniciado.

1. Verificar backup durable cifrado y restauración fuera del volumen activo.
2. Documentar recuperación de la PC, Docker y perfiles de navegador.
3. Medir dependencia de intervención humana en WhatsApp y pagos.
4. Mantener Telegram como interfaz remota y Admin API como frontera de
   autorización.
5. Confirmar en el siguiente reinicio que Kaspersky conserva la tarea
   `AppointmentBotContinuousWorker` y el supervisor raíz PowerShell. La
   recuperación individual de los cuatro supervisores ya quedó implementada;
   falta observarla después de un reinicio real.

## Integración futura - Invitaciones y registro alojado

Estado: pendiente y bloqueada por el contrato del proyecto
`lunas-polarizadas-clientes`.

No adelantar esta integración a la estabilización actual ni implementarla
antes de que el servicio alojado de invitaciones y registro tenga un contrato
probado.

Cuando se libere esa dependencia:

1. añadir al dashboard local una sección de invitaciones;
2. permitir crear, copiar, consultar, revocar y reemitir enlaces;
3. seleccionar o registrar el WhatsApp antes de crear la invitación y enviarlo
   normalizado a la API alojada;
4. hacer que el navegador llame solo a la Admin API local;
5. implementar en la Admin API un cliente HTTPS autenticado hacia la API
   alojada, con secreto fuera del frontend y de los logs;
6. implementar un conector saliente que consulte y reclame solicitudes
   pendientes con lease e idempotencia;
7. entregar cada solicitud a las fronteras internas existentes para validar el
   portal y, cuando corresponda, crear una sola orden;
8. devolver a la nube solo estados mínimos y sanitizados;
9. conservar PostgreSQL local como registro operativo definitivo;
10. mantener WhatsApp, Telegram, evidencia y reservas exclusivamente en local;
11. informar por el WhatsApp existente cuando una validación diferida requiera
    corrección y permitir emitir una invitación nueva;
12. probar primero con una cuenta y un número controlados, manteniendo el alta
    manual como alternativa.

Condiciones obligatorias:

- no abrir puertos ni publicar la Admin API;
- no conectar la nube directamente a PostgreSQL;
- no generar en el navegador ni guardar localmente el token de invitación;
- no volver a pedir el WhatsApp dentro del registro alojado;
- no depender de una página persistente de estado del cliente;
- no exponer credenciales del portal o de servicio en logs;
- no crear órdenes por abrir un enlace;
- no comenzar este trabajo hasta que `lunas-polarizadas-clientes` complete y
  valide la parte alojada que consumirá este proyecto.

## Deuda técnica posterior

Estas tareas no deben adelantarse a la estabilización:

1. Romper el ciclo entre `appointments.py` y `appointment_selection.py`.
2. Sustituir mutaciones globales en módulos transicionales como
   `queue_runtime.py` por dependencias explícitas.
3. Dividir módulos grandes en cortes pequeños, sin mezclar refactor con cambios
   de comportamiento.
4. Revisar retención de `runs` para que las comparaciones históricas no dependan
   únicamente de snapshots manuales.

## Regla de ejecución

- Leer `docs/project-status.md` y este archivo antes de implementar un cambio.
- Trabajar una prioridad o experimento a la vez.
- No modificar `.env` sin autorización explícita.
- Mantener sesión, cookies, lease y confirmación independientes por orden.
- No usar CAPTCHA sombra como autoridad de reserva.
- Validar Python, Angular, runtime y documentación antes de cerrar una fase.
- Al terminar, actualizar el estado maestro y esta lista en el mismo cambio.
