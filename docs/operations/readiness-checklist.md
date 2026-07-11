# Plan para terminar y operar

Este es el documento principal que debes leer si quieres saber que falta, como
validarlo y cual es el paso a paso para dejar todo listo. Los demas documentos
quedan como referencia tecnica de arquitectura, contratos o historial.

Si solo vas a leer un documento, lee este.

## Objetivo

El sistema queda listo cuando se puede correr esta topologia local:

```text
PostgreSQL
  |-- appointment-bot-worker en 127.0.0.1:8765
  |-- appointment-bot-admin-api en 127.0.0.1:8766
  |-- dashboard Angular por proxy local hacia 8766
```

El camino operativo principal sigue siendo `scripts/start-worker.ps1`. El admin
API separado y el dashboard son la superficie administrativa local. Si algo
falla, el rollback inmediato es operar por el worker y su API embebida en
`127.0.0.1:8765`.

## No tocar antes de validar

- No modificar `.env` para pruebas temporales.
- No exponer el admin API fuera de loopback.
- No guardar tokens, passwords, cookies, Fernet keys ni `owner_token` en el
  dashboard.
- No cambiar `appointment-bot-worker`, codigos de salida ni
  `scripts/start-worker.ps1` sin una fase dedicada.
- No mezclar cambios de reserva Playwright con cambios de dashboard o
  documentacion.

## Preparacion local

1. Instalar paquete y dependencias del navegador:

```powershell
python -m pip install -e .
python -m playwright install chromium
```

2. Instalar dependencias del dashboard:

```powershell
cd dashboard
npm install
cd ..
```

3. Confirmar que `dashboard/proxy.conf.cjs` apunta a
   `http://127.0.0.1:8766` para validar la topologia objetivo. Para rollback
   temporal, puede apuntar a `http://127.0.0.1:8765`.

## Arranque operativo

Usar tres terminales.

Terminal 1:

```powershell
scripts/start-worker.ps1
```

Terminal 2:

```powershell
appointment-bot-admin-api
```

Terminal 3:

```powershell
cd dashboard
npm start
```

La sesion manual debe seguir apagada salvo prueba explicita. Para una prueba
local controlada:

```powershell
$env:MANUAL_SESSION_ENABLED='true'
appointment-bot-admin-api
```

Si se requiere operar sesiones manuales desde el dashboard durante una jornada,
usar `MANUAL_SESSION_ENABLED=true` en el entorno local del admin API. El
dashboard puede abrir multiples sesiones visibles, cada una con navegador
separado. Cerrar la ventana del navegador o refrescar/cerrar el dashboard debe
solicitar el cierre de las sesiones abiertas por esa pagina.

La cola rapida debe mantenerse con una espera corta cuando los cupos duran pocos
segundos. Los valores operativos recomendados para ese caso son:

```powershell
QUEUE_DELAY_MIN_SECONDS=1
QUEUE_DELAY_MAX_SECONDS=1
```

Estos valores no cambian la cadencia del observer normal; solo afectan la pausa
entre ordenes de la cola rapida.

## Verificacion rapida

1. Confirmar liveness del admin API:

```powershell
Invoke-WebRequest http://127.0.0.1:8766/health
```

2. Confirmar estado real del worker:

```powershell
appointment-bot-client orders
Invoke-WebRequest http://127.0.0.1:4200/api/v1/worker
```

Interpretacion:

- `GET /health` solo confirma que la API responde.
- `GET /api/v1/worker` confirma fase, pausa, ventana, orden actual y estado
  persistido.
- `outside_hot_window` significa worker vivo pero esperando ventana.
- `worker_running=false` o errores de lease requieren revisar logs antes de
  reiniciar a ciegas.

3. Confirmar que el dashboard carga sin pedir token. El proxy local
   `dashboard/proxy.conf.cjs` lee `APPOINTMENT_BOT_API_TOKEN` desde `.env` o
   desde la variable de entorno y agrega el header administrativo del lado del
   servidor de desarrollo.

4. Confirmar que las acciones administrativas muestran confirmacion antes del
   POST y respuesta clara despues del backend.

5. Confirmar que, despues de una reserva exitosa, Telegram envia primero el
   mensaje limpio para copiar al cliente y luego un mensaje operativo con
   nombre, orden, origen y WhatsApp/contacto. Ese segundo mensaje debe tratarse
   como notificacion diferida y no como requisito para considerar tomada la
   reserva.

## Validacion antes de cerrar cambios

Ejecutar desde la raiz del repo:

```powershell
python -m compileall src
python -m ruff check src tests
python -m pytest
git diff --check
```

Ejecutar para Angular:

```powershell
cd dashboard
npm run build
cd ..
```

Si una validacion falla, no cerrar la fase. Corregir el problema o documentar
el bloqueo con el comando exacto que fallo.

## Prueba manual recomendada

Esta prueba valida la convivencia de worker, admin API y dashboard sin tocar el
flujo de reserva:

1. Levantar worker con `scripts/start-worker.ps1`.
2. Levantar `appointment-bot-admin-api`.
3. Abrir dashboard con `npm start`.
4. Revisar health, fase del worker, orden actual, ordenes, runs y comandos
   recientes.
5. Ejecutar una accion de bajo riesgo, por ejemplo actualizar contacto de una
   orden de prueba o pausar/reactivar una orden controlada.
6. Confirmar en `appointment-bot-client orders` que el estado coincide.
7. No ejecutar sesion manual ni restart en produccion salvo necesidad real.

## Pendientes necesarios

Estos pendientes deben hacerse en pasos pequenos:

1. Agregar vista de detalle de runs en Angular sin mostrar ni copiar `details`
   crudos por defecto.
2. Mejorar ergonomia visual del dashboard sin cambiar contratos ni endpoints.
3. Ejecutar una validacion manual completa contra `appointment-bot-admin-api`
   vivo, token real y worker activo.
4. Registrar en este documento la fecha, comandos ejecutados y resultado de la
   primera sesion operativa completa.

No hay un refactor estructural grande pendiente en el plan actual. La migracion
interna documentada llego hasta el paso 9.7; los siguientes cambios deben ser
operativos, de UI o de validacion, salvo que se abra una fase nueva.

## Rollback

Si el admin API o dashboard fallan:

1. detener `appointment-bot-admin-api`;
2. detener `npm start`;
3. dejar `scripts/start-worker.ps1` como unico camino operativo;
4. si se necesita dashboard temporal, apuntar `dashboard/proxy.conf.cjs` a
   `http://127.0.0.1:8765`;
5. validar `appointment-bot-client orders` y `GET /health` del worker embebido.

Si el worker falla, no reiniciar sin mirar primero:

- estado de `appointment-bot-client orders`;
- `GET /api/v1/worker`;
- ultimo log en `logs/`;
- si la fase es `outside_hot_window`, no es una caida.
