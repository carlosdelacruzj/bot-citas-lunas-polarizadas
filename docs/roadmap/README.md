# Trabajo pendiente

Esta es la única lista de tareas futuras. Las fases cerradas están resumidas en
[`../history/roadmap-completed-2026-07-12.md`](../history/roadmap-completed-2026-07-12.md).

## Prioridad 1 - Acumular evidencia observacional

Estado: completada y analizada el `2026-07-19`, sin cambios funcionales en la
reserva.

### Próximo checkpoint

- Periodo de recolección: lunes `2026-07-13` a sábado `2026-07-18`.
- No se realizarán búsquedas el domingo `2026-07-19`, pero ese día ya se
  puede analizar el periodo cerrado.
- Fecha recomendada de revisión: lunes `2026-07-20`.
- Acción del usuario: pedir **"realiza el análisis semanal"**. Codex debe
  regenerar los reportes, comparar el periodo con la línea base y explicar si
  existe evidencia suficiente para proponer una mejora.
- No aplicar optimizaciones automáticamente: cualquier cambio al flujo de
  reserva se decide con el usuario después de revisar los resultados.

Resultado del checkpoint:

- se generaron `reports/operations/weekly-20260713-20260718.md` y
  `reports/optimization/observation-20260713-20260718.md`;
- la conversión atribuible a submits quedó estable: 49.1% frente a 48.4%;
- selección estable y sin evidencia para retirar esperas;
- la cola lenta de CAPTCHA concentró 16 de 29 `slot_lost`;
- el único experimento recomendado es bajar el polling del SDK de 10 a 5
  segundos, previa aprobación del usuario.

1. Recoger runs reales con el nuevo desglose de selección.
2. Regenerar el reporte semanal y la observación por el mismo rango.
3. Comparar conversión, p50/p90, `slot_lost`, CAPTCHA y defensas.
4. Revisar la evidencia con el usuario antes de proponer un cambio.

Fuente: [`../optimization.md`](../optimization.md).

## Prioridad 2 - Elegir un único experimento

Estado: experimento aprobado y aplicado el `2026-07-19`.

La muestra ya es suficiente. Experimento recomendado:

- configurar `pollingInterval=5` en el cliente 2Captcha;
- mantener proveedor, timeout, reintentos, selección y concurrencia sin cambios;
- comparar al menos 30 nuevos submits o una semana completa contra este cierre;
- conservar solo si baja el p90 de CAPTCHA y `slot_lost` sin aumentar errores
  del proveedor ni señales de defensa.

No se modificaron proveedor, timeout, reintentos, selección, confirmación, cola
ni concurrencia.

Alternativas descartadas por ahora:

- candidato de bajo riesgo: una espera concreta de selección, si el DOM prueba
  que es redundante;
- no cambiar proveedor CAPTCHA sin comparación de costo, precisión y latencia;
- no habilitar concurrencia si aumentan defensas, `429` o errores de sesión;
- retirar `fetch_probe` si no anticipa horas útiles y solo agrega carga.

## Deuda técnica posterior

1. Romper el ciclo entre `appointments.py` y `appointment_selection.py`.
2. Sustituir la mutación de globals en la fachada `queue_runtime.py` por
   inyección explícita.
3. Dividir `continuous_worker.py`, `appointments.py`, `migrations.py` y
   `notifier.py` en cortes pequeños sin mezclar optimización funcional.

## Regla de ejecución

- Un cambio por vez.
- Mantener sesión, lease y confirmación independientes por orden.
- No buscar los domingos.
- Validar Python, Angular, runtime y documentación antes de guardar.
