# Integración del servicio sombra de CAPTCHA

Fecha de inicio: 21 de julio de 2026.

Contrato fuente:
`C:\Users\CARLOS\Desktop\Codex\test-captcha\INTEGRACION_SERVICIO_SOMBRA.md`.

## Objetivo

Registrar en segundo plano las predicciones de los modelos locales y compararlas con la
respuesta de 2Captcha y la evidencia explícita del portal, sin cambiar la respuesta operativa ni
añadir espera de red al hilo de Playwright.

## Decisiones cerradas

- 2Captcha continúa siendo la única fuente operativa.
- La integración queda desactivada por defecto.
- El productor usa `put_nowait()` sobre una cola FIFO acotada.
- Un único consumidor realiza las llamadas HTTP con `urllib.request`.
- Una caída, un timeout o una cola llena solo descartan evidencia sombra.
- Cada reintento de CAPTCHA tiene un `event_id` diferente.
- `portal_accepted=true` requiere confirmación explícita o etapa `Programado`.
- `portal_accepted=false` se usa únicamente para `captcha_invalid`.
- Los demás resultados se conservan como `null`.
- La primera fase usa memoria; no incorpora outbox durable ni reintentos tras reiniciar.

## Plan y avance

| Paso | Estado | Entrega |
| --- | --- | --- |
| 1. Auditar y fijar el contrato | Completado | Alcance, riesgos y secuencia documentados. |
| 2. Configuración y dispatcher | Completado | Cliente fail-open, cola acotada y configuración apagada. |
| 3. Correlación y predicción | Completado | Propagación de contexto y `/v1/predict`. |
| 4. Resultado externo | Completado | Respuesta 2Captcha y clasificación del portal. |
| 5. Ciclo de vida | Completado | Inicio/cierre junto con el worker continuo. |
| 6. Validación final | Completado | Pruebas manuales, sintaxis, lint y cierre documental. |

## Archivos existentes preservados

Al iniciar había cambios locales ajenos a esta integración. Cada commit incluirá únicamente los
archivos del paso correspondiente para no mezclar ni sobrescribir ese trabajo.

## Criterio de reversión

Con `CAPTCHA_SHADOW_ENABLED=false`, el bot debe conservar el comportamiento anterior. Ningún
error del dispatcher puede propagarse al flujo de reserva.

## Paso 2: configuración y dispatcher

Se añadieron a `Settings` los valores `CAPTCHA_SHADOW_ENABLED`, `CAPTCHA_SHADOW_URL`,
`CAPTCHA_SHADOW_QUEUE_SIZE` y `CAPTCHA_SHADOW_TIMEOUT_SECONDS`. Sus valores predeterminados son
apagado, `http://127.0.0.1:8787`, 100 eventos y 2 segundos.

`services/captcha_shadow.py` contiene una cola FIFO acotada y un consumidor único. Encolar no
realiza red ni espera espacio; una cola llena devuelve inmediatamente y registra el descarte.
Los errores HTTP, de conexión y timeout se absorben dentro del consumidor.

## Paso 3: correlación y predicción

`run_id` y `order_id` se propagan explícitamente desde `runner.py` hasta
`reservation_submit.py`. Después de comprobar que el intento realmente continuará hacia
2Captcha, el flujo construye `{run_id}:{order_id_o_observer}:captcha-{attempt_number}` y encola
la ruta canónica `captcha_path_for_solver`.

El `captcha_audit` conserva el identificador y si el productor pudo encolarlo. Los flujos que
solo capturan evidencia por una regla bloqueada no producen eventos sombra.

## Paso 4: respuesta externa y resultado del portal

Al recibir la solución de 2Captcha se encola `/v1/results/external` con
`portal_accepted=null`; la normalización a mayúsculas ocurre solo en la copia sombra. La cadena
operativa enviada al portal permanece intacta.

Después se registra `true` para `confirmed` o una confirmación posterior en `Programado`,
`false` exclusivamente para `captcha_invalid`, y `null` para los demás resultados. Como ambos
tipos de trabajo comparten el mismo consumidor FIFO, la actualización externa no se adelanta a
la creación del evento.

## Paso 5: ciclo de vida

`worker/host.py` configura e inicia el consumidor antes de arrancar el hilo del worker y lo
detiene en las salidas de inicio y en el cierre normal. El dispatcher intenta vaciar brevemente
la cola durante el apagado, pero su espera está limitada y su hilo es daemon.

No se consulta `/health` como requisito de arranque. Si el servicio de `127.0.0.1:8787` está
apagado, el worker arranca normalmente y cada fallo queda aislado en el consumidor.

## Paso 6: validación final

Validaciones realizadas:

- `python -m compileall -q src`: correcto;
- `python -m ruff check src`: correcto;
- pruebas existentes de reserva/CAPTCHA: 6 aprobadas;
- servicio sombra: 21 pruebas aprobadas;
- `/health`: `status=ok`, CUDA y tres modelos cargados;
- cola FIFO: orden `predict` -> respuesta externa -> resultado del portal confirmado;
- servicio apagado: error absorbido y contabilizado sin propagarse al productor;
- URL no local: integración desactivada de forma segura sin impedir el arranque;
- cola llena: descarte inmediato con advertencia;
- benchmark local de 500 inserciones: máximo observado de 0.711 ms por `enqueue`, por debajo
  del objetivo de 10 ms.

La suite completa existente ejecutó 53 pruebas y mantuvo 3 fallos y 5 errores en contratos
ajenos a esta integración: `document_type`, acciones/leases de órdenes y captura de muestras del
observador. No se modificaron esos módulos ni sus pruebas como parte de este alcance.

## Activación controlada

Activada el 21 de julio de 2026. `.env` contiene localmente:

```text
CAPTCHA_SHADOW_ENABLED=true
CAPTCHA_SHADOW_URL=http://127.0.0.1:8787
CAPTCHA_SHADOW_QUEUE_SIZE=100
CAPTCHA_SHADOW_TIMEOUT_SECONDS=2
```

Se realizó un reinicio controlado mediante `/api/v1/worker/restart`. Después del reinicio:

- `/health` del bot respondió `status=ok` y `worker_running=true`;
- el worker quedó activo y no pausado;
- el log `run-20260721-134456.log` confirmó el inicio del dispatcher en
  `http://127.0.0.1:8787`;
- `/health` del servicio sombra continuó saludable con CUDA y tres modelos;
- `/v1/stats` permaneció en cero porque todavía no ocurrió un CAPTCHA real posterior a la
  activación.

La siguiente verificación operacional ocurrirá con el próximo intento real que llegue a
2Captcha: `/v1/stats` deberá acumular un evento y tres predicciones por CAPTCHA. La reversión
consiste en volver a `CAPTCHA_SHADOW_ENABLED=false` y reiniciar el worker.

`.env` no se versiona ni se publica porque puede contener credenciales reales.

## Corrección posterior a los primeros intentos reales

Los primeros dos intentos posteriores a la activación revelaron que el productor enviaba la
ruta relativa de la imagen. Como el servicio sombra se ejecuta desde otro directorio, ambos
`/v1/predict` respondieron HTTP 400 y no ejecutaron inferencia.

El productor ahora resuelve `captcha_path_for_solver` a una ruta absoluta antes de encolarla.
Esto conserva la misma imagen canónica y permite que el servicio la encuentre dentro de la raíz
autorizada del proyecto del bot.

## Historial de entregas publicadas

- `9f0f30c`: contrato y registro de implementación;
- `b0af482`: configuración y dispatcher;
- `c99d621`: correlación y predicción;
- `c01a315`: respuesta externa y resultado del portal;
- `388e86e`: ciclo de vida del worker.
