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
| 4. Resultado externo | Pendiente | Respuesta 2Captcha y clasificación del portal. |
| 5. Ciclo de vida | Pendiente | Inicio/cierre junto con el worker continuo. |
| 6. Validación final | Pendiente | Pruebas manuales, sintaxis, lint y cierre documental. |

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
