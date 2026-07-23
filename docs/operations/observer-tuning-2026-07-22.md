# Ajuste controlado del observer - 22-07-2026

## Objetivo

Aumentar las consultas realizadas dentro de una misma sesión autenticada sin
abrir navegadores paralelos, sin aumentar la cantidad de órdenes activas y sin
reducir todavía la espera entre consultas.

## Línea base

La revisión operativa del periodo del 13 al 22 de julio registró:

- `8,038` corridas.
- `37` reservas confirmadas directamente por corridas automáticas.
- `39` cupos perdidos antes de confirmar.
- `16` errores, equivalentes aproximadamente al `0.2%`.
- ningún `HTTP 403`, `HTTP 429` ni recovery backoff en los logs revisados.
- CAPTCHA p90 de `12.05 s` entre el 13 y el 18 de julio y `7.16 s` entre el
  20 y el 22 de julio.
- tiempo p90 desde disponibilidad hasta resultado de `18.56 s` entre el 13 y
  el 18 de julio y `13.94 s` entre el 20 y el 22 de julio.

Durante el enfoque exclusivo de Juan José, entre las 14:04 y las 18:00:

- se completaron `351` sesiones.
- se realizaron `2,106` lecturas de disponibilidad.
- cada sesión realizó tres intentos normales y tres `reload_probe`.
- el inicio de sesiones tuvo una separación media de `40.39 s`.
- no se registraron errores, warnings ni señales de defensa del portal.

## Paso 1 aplicado

Configuración operativa:

```dotenv
OBSERVER_SESSION_SECONDS=120
OBSERVER_MAX_ATTEMPTS=4
OBSERVER_INTERVAL_MIN_SECONDS=8
OBSERVER_INTERVAL_MAX_SECONDS=13
```

El único valor modificado es `OBSERVER_MAX_ATTEMPTS`, que pasa de `3` a `4`.
Los intervalos permanecen en `8–13 s` para poder atribuir cualquier cambio de
rendimiento a una sola variable.

Una sesión completa puede realizar ahora hasta cuatro intentos normales y
cuatro `reload_probe`. Esto no significa ocho navegadores ni ocho sesiones
paralelas: es una sola sesión Playwright que reutiliza el login del cliente
durante más tiempo.

La plantilla `.env.example` y el valor por defecto de `config.py` ya utilizaban
cuatro intentos, por lo que no necesitaron cambios.

## Resultado esperado

- reducir aperturas de navegador e inicios de sesión por cada cien lecturas.
- mantener o aumentar ligeramente las lecturas por hora.
- conservar sesiones separadas entre clientes.
- no aumentar la tasa de errores ni activar defensas del portal.
- aprovechar mejor el límite de `120 s` de cada sesión.

El cambio no busca duplicar la presión sobre el portal. La frecuencia interna
sigue limitada por el intervalo aleatorio de `8–13 s`.

## Métricas a vigilar

Comparar los próximos dos o tres días con esta línea base:

1. lecturas de disponibilidad por hora.
2. sesiones y logins por hora.
3. duración p50 y p90 de las sesiones.
4. reservas confirmadas y `slot_lost`.
5. errores de red y timeouts.
6. apariciones de `HTTP 403`, `HTTP 429`, CAPTCHA inesperado o
   `recovery_backoff`.
7. duración p50 y p90 de CAPTCHA.
8. tiempo desde disponibilidad hasta el clic de reserva.

## Criterio de continuidad

Mantener cuatro intentos si:

- no aparecen respuestas `403` o `429`.
- la tasa de error se mantiene por debajo de `0.5%`.
- no aumenta el `slot_lost` por sesiones vencidas o inestables.
- las lecturas por hora se mantienen o mejoran.

## Criterio de reversión

Volver temporalmente a `OBSERVER_MAX_ATTEMPTS=3` si aparece cualquiera de estas
condiciones:

- respuestas `403` o `429` repetidas.
- recovery backoff causado por señales del portal.
- crecimiento sostenido de errores por encima de `0.5%`.
- sesiones que alcanzan `120 s` sin finalizar correctamente.
- degradación clara de la conversión durante una muestra suficiente.

No se debe reducir simultáneamente `OBSERVER_INTERVAL_MIN_SECONDS` ni
`OBSERVER_INTERVAL_MAX_SECONDS`. Ese sería un segundo experimento y solo debe
evaluarse después de observar este cambio de forma aislada.

La secuencia completa, las fechas más tempranas y las condiciones para avanzar
están definidas en
[`performance-roadmap-2026-07-22.md`](performance-roadmap-2026-07-22.md).
