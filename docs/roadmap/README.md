# Trabajo pendiente

Última priorización: `2026-07-25`.

Esta es la única lista de tareas futuras y el orden vigente de ejecución. El
estado de lo construido, validado y observado vive en
[`../project-status.md`](../project-status.md).

## Prioridad 0 - Recuperar una validación confiable

Estado: pendiente.

Objetivo: volver a tener una suite que distinga regresiones reales de contratos
de prueba desactualizados.

1. Clasificar los 11 fallos actuales de pytest.
2. Actualizar expectativas antiguas de `document_type`, restricciones por orden
   y firma del muestreo CAPTCHA.
3. Investigar por separado los fallos de claim y creación de órdenes por API.
4. Confirmar que ningún ajuste reduzca las protecciones de identidad, lease,
   selección o confirmación final.
5. Registrar aquí el resultado final de la suite.

Criterio de cierre: suite existente en verde o cada fallo restante documentado
como excepción consciente con causa y alcance.

## Prioridad 1 - Consolidar los cambios recientes

Estado: en observación.

### WhatsApp automático

- Medir trabajos `sent`, `failed`, `blocked` y `uncertain`.
- Confirmar que solo Admin API abre el perfil persistente.
- Verificar que evidencia y Yape permanezcan en un solo álbum.
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
   `AppointmentBotContinuousWorker` y el lanzador PowerShell.

## Deuda técnica posterior

Estas tareas no deben adelantarse a la estabilización:

1. Romper el ciclo entre `appointments.py` y `appointment_selection.py`.
2. Sustituir mutaciones globales en fachadas como `queue_runtime.py` por
   dependencias explícitas.
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
