# Manual operativo

## Validacion de clientes nuevos

Toda orden nueva queda fuera de la cola hasta que una sesion independiente
ingresa al portal, obtiene el nombre del titular y confirma que existe al menos
un tramite pendiente. En el dashboard se muestra `Validacion pendiente`,
`Validando acceso`, `Acceso validado` o `Validacion fallida`.

Si falla, revisar el mensaje visible en la orden y la captura guardada en
`screenshots/preflight/`, corregir el tipo de documento o la contrasena y usar
`Volver a validar`. No activar manualmente la orden: el backend bloquea esa
accion hasta completar el control. El comando `appointment-bot-client
order-add` realiza la misma validacion de forma sincrona y termina con codigo 1
si la cuenta no pasa el control.

## Flujo rápido de cobranza

El dashboard permite registrar un pago desde la tabla, el resumen mensual o el
panel de la orden sin abrir el formulario general. La ventana compacta propone
el monto acordado, incluye accesos rápidos para S/40 y S/50, y conserva una sola
confirmación antes de modificar el estado financiero.

Después de registrar el pago, el operador puede preparar inmediatamente el
paquete post-pago. Esta transición nunca confirma el envío automáticamente: los
mensajes y archivos continúan sujetos a revisión manual.

El panel separa las acciones frecuentes de contacto, restricciones y pago. Los
indicadores de pagos pendientes funcionan también como filtros y el número
completo de WhatsApp puede copiarse o abrirse desde el detalle protegido.

## Arranque recomendado

En Windows, la tarea programada `AppointmentBotContinuousWorker` ejecuta
`scripts/start-worker-hidden.vbs` al iniciar sesion. El lanzador levanta en
segundo plano todo el entorno local:

- Docker y PostgreSQL;
- worker y API de salud en `127.0.0.1:8765`;
- build Angular, admin API y dashboard en `127.0.0.1:8766`.
- receptor independiente de control remoto por Telegram.

El admin/dashboard se reinicia si su proceso termina. No hace falta abrir
`npm start`: el admin API sirve directamente el build Angular.

Para un arranque manual sin la tarea programada, usar tres terminales:

Terminal 1:

```powershell
scripts/start-worker.ps1
```

Terminal 2:

```powershell
scripts/start-admin-dashboard.ps1
```

Terminal 3:

```powershell
scripts/start-telegram-control.ps1
```

Abrir `http://127.0.0.1:8766/`. El admin API sirve Angular y usa una sesión
local `HttpOnly`/`SameSite=Strict`; no exponer ni redirigir este puerto fuera de
loopback.

Los recursos del dashboard local se sirven con revalidación obligatoria para
evitar que una pestaña recargada conserve un build anterior durante cambios de
interfaz. Una pestaña que ya estaba abierta debe actualizarse una vez después de
publicar un build nuevo.

Rollback/desarrollo: ejecutar `appointment-bot-admin-api` y `npm start` dentro
de `dashboard/`. El proxy sigue apuntando a `127.0.0.1:8766`.

## Control remoto por Telegram

El proceso `appointment-bot-telegram-control` recibe comandos sin compartir
memoria con el worker. En la primera version admite:

- `/estado`;
- `/clientes [pagina]`;
- `/cliente ORDER_ID`;
- `/reglas ORDER_ID`;
- `/ultimos_errores`;
- `/pausar`;
- `/reanudar`;
- `/reiniciar`;
- `/ayuda`;
- `/cancelar`.

Solo responde al `TELEGRAM_CHAT_ID` configurado. Opcionalmente,
`TELEGRAM_CONTROL_CHAT_IDS` permite una lista separada por comas. Un chat fuera
de esa lista se ignora sin revelar informacion.

El receptor usa long polling y guarda el siguiente `update_id` en
`.runtime/telegram-control-offset.json`. Antes de iniciarlo se puede comprobar
Telegram y la Admin API sin consumir mensajes:

```powershell
appointment-bot-telegram-control --check
```

El bot no ejecuta PowerShell ni consulta PostgreSQL directamente. `/estado`
consulta el Admin API autenticado; `worker_running` se calcula con el lease
vigente del worker y `outside_hot_window` significa activo pero esperando.

Los tres comandos que cambian el worker muestran botones `Confirmar` y
`Cancelar`. La confirmacion vence en dos minutos y solo puede consumirse una
vez. Despues de confirmar, Telegram espera el estado terminal de
`worker_commands` y comprueba el efecto real antes de anunciar exito. Un HTTP
`202` por si solo nunca se presenta como accion completada.

Las consultas operativas separan indice y detalle deliberado:

- `/clientes` muestra ocho ordenes por pagina y acepta el numero de pagina;
- `/cliente` muestra cliente, documento y WhatsApp completos, ademas de estado,
  prioridad, reserva y pago;
- `/reglas` muestra fechas, hora minima y dias permitidos;
- `/ultimos_errores` revisa las ultimas 50 ejecuciones y muestra como maximo
  cinco incidentes saneados.

El detalle completo se entrega solamente cuando el chat autorizado consulta un
`ORDER_ID` especifico. Nunca incluye password, tokens, cookies, datos de
cifrado, leases ni detalles crudos de runs.

## Salud y calendario

- `http://127.0.0.1:8765/health`: vida del worker.
- Dashboard `/api/v1/worker`: fase real del worker.
- `outside_hot_window` con `worker_running=true`: espera saludable.
- Las búsquedas automáticas funcionan de lunes a sábado; domingo no abre
  sesiones ni consulta el portal.

## Cambiar prioridad desde el dashboard

1. Abrir **Órdenes** y seleccionar la orden.
2. Pulsar **Editar**.
3. En **Prioridad de búsqueda**, ingresar un entero no negativo y confirmar.
4. Usar `0–99` para cola normal o `100` o más para enfoque.

Si dos órdenes deben ocupar los dos observadores, asignar `100` a cada una por
separado. El cambio entra en la siguiente selección y no requiere reiniciar el
worker.

## Consultar contacto operativo

Al seleccionar una orden se abre un panel lateral con el detalle administrativo:
nombre, WhatsApp completo, fuente, reglas, reserva, pago, trámite y acciones. El
panel no reduce ni desplaza la tabla y se cierra con **Cerrar**, `Esc` o pulsando
fuera. En móvil ocupa la pantalla completa. La tabla, los filtros, los snapshots
y las copias masivas continúan usando el número enmascarado para no exponer todos
los contactos a la vez.

## Flujo simplificado del operador

- La tabla muestra solo cliente, estado, reserva, pago y una acción
  contextual; prioridad, reglas, cierre y trámite permanecen en el panel lateral.
- El identificador técnico `order_id` no aparece en la tabla principal; se
  conserva en el panel lateral para diagnósticos. La tabla usa nombre, documento
  enmascarado y fuente para reconocer al cliente.
- La acción principal cambia según la orden: abrir sesión, activar, registrar
  pago o ver detalle.
- El panel ofrece accesos directos para editar, pausar/activar y gestionar otros
  cierres, además de presets **Cola normal** (`0`) y **Enfoque 100**.
- Las confirmaciones y resultados usan SweetAlert2 con mensajes claros; las
  acciones de lectura o navegación no solicitan confirmación innecesaria.
- La navegación por teclado conserva el foco al abrir y cerrar el panel.
- Al cerrar una sesión manual, la fila desaparece inmediatamente y el backend
  fuerza la limpieza del registro si Playwright no termina en ocho segundos.

## Resumen mensual

La vista **Resumen** permite elegir un mes y muestra ingresos realmente
cobrados, reservas, altas, ticket promedio, conversión, comparación con el mes
anterior, ingresos diarios y resultados por fuente. Los cobros pendientes y las
órdenes activas aparecen separados como trabajo por atender. Pulsar un pendiente
abre directamente su orden en el panel operativo.

Las fechas se agrupan en `America/Lima`: `paid_at` para ingresos, `reserved_at`
para reservas y `created_at` para órdenes nuevas. No sumar el importe pendiente
al ingreso cobrado.

## Formato de fecha y hora

Toda fecha visible del dashboard usa `DD-MM-YYYY`. Las horas usan formato de 24
horas `HH:mm` y los timestamps completos `DD-MM-YYYY HH:mm:ss`, siempre en la
zona `America/Lima`. Los controles HTML de captura pueden conservar internamente
`YYYY-MM-DD`, porque ese es el formato técnico exigido por el navegador.

## Recuperación

### Worker

1. Revisar health, fase, `next_check_at` y último error.
2. No reiniciar si está esperando fuera de ventana.
3. Si no responde, cerrar solo el worker y ejecutar `scripts/start-worker.ps1`.
4. Confirmar health y fase.

### Admin API y dashboard

1. Revisar `http://127.0.0.1:8766/health`.
2. Cerrar solo admin-dashboard.
3. Ejecutar `scripts/start-admin-dashboard.ps1 -SkipBuild`; reconstruir sin el
   flag si falta el build.
4. Comprobar órdenes y runs.

## Reportes

```powershell
appointment-bot-client weekly-report --start YYYY-MM-DD --end YYYY-MM-DD
appointment-bot-client optimization-observation --start YYYY-MM-DD --end YYYY-MM-DD
```

Las salidas vigentes están en `reports/operations/latest.md` y
`reports/optimization/latest.md`. Agregar `--notify` al reporte semanal solo
cuando se desee enviar sus alertas por Telegram.

## Prueba base y envio asistido por WhatsApp

El dashboard no usa la API de Meta. En `Ordenes`, usar `Probar post-pago`, ingresar
el numero propio con codigo de pais (por ejemplo, `+51987654321`) y crear el
paquete ficticio. La prueba usa una cita de demostracion y los PDFs configurados en
`.runtime/whatsapp-followup/followup-details.json`, sin tocar ordenes reales.

En una orden real, `Enviar por WhatsApp` crea el paquete y prepara inmediatamente el
album: carga constancia e imagen de pago, selecciona cada miniatura y coloca su texto
individual. Comprobar destinatario, ambas imagenes y sus textos; despues pulsar una
sola vez `Enviar 2 seleccionados`. No hay un segundo paso en el dashboard. Si la
ventana local fue cerrada durante la preparacion, se vuelve a abrir y se reintenta
una vez. En el primer uso se debe escanear el QR y repetir la preparacion.
El perfil queda solo en `.runtime/whatsapp-web-profile/` y no se versiona.

La configuracion privada del cobro se guarda en
`.runtime/whatsapp-payment/payment-details.json` junto a la imagen indicada por el
campo `image`. Nunca versionar ese directorio. El monto real se toma de PostgreSQL;
el simulacro usa S/ 40.00. La alternativa copiar/pegar permanece cerrada y solo se
muestra como respaldo cuando la preparacion automatica falla; incluye las dos
imagenes y sus respectivos textos.

Esta automatizacion local no es una integracion oficial de Meta. Usarla solo para
mensajes transaccionales esperados, uno por uno, sin campanas ni reintentos
agresivos. Un borrador nunca se considera enviado: cerrar la ventana o el asistente
mantiene el paquete en `prepared`; solo `Confirmar envio realizado` lo cambia a
`sent`.

Para clientes reales, `Preparar WhatsApp` se habilita en una reserva confirmada con
cobro pendiente. El sistema no agrega `51`: el contacto debe guardarse previamente
en formato internacional. En el detalle de una orden pendiente aparecen juntas las
acciones `Registrar pago` y `Enviar por WhatsApp`; esta ultima deja el album listo
para el envio humano final. El texto de confirmacion usa el mismo formateador que
Telegram. Preparar o confirmar el mensaje no registra el pago.

Despues de confirmar la transferencia y registrar el pago, una orden pagada muestra
`Enviar post-pago` como accion directa en la fila y en el detalle. Esta accion es
independiente del album de cobro: abre WhatsApp Web, adjunta los PDFs configurados en
`.runtime/whatsapp-followup/followup-details.json`, envia primero los PDFs y luego
envia el texto post-pago como segundo mensaje. Si WhatsApp confirma el envio, el
paquete queda registrado como enviado automaticamente y la accion pasa a
`Reenviar post-pago`. Usar `Confirmar envio post-pago` solo como respaldo si el
operador tuvo que enviarlo manualmente.

La automatizacion espera a que el menu de adjuntos muestre una opcion real antes
de seleccionar archivos. Para el album normal exige un control con capacidad
multiple cuando hay dos imagenes; para post-pago limita `Documento` al menu de
adjuntos y no reutiliza coincidencias encontradas en mensajes antiguos del chat.

## Revision diferida de reservas confirmadas

Cuando una cola rapida termina normalmente porque ya no quedan ordenes con cupo, el
worker vuelve a abrir, en una sesion Playwright nueva por cliente, cada orden que
confirmo durante ese ciclo. Esta revision ocurre despues del ultimo intento y antes
de enviar la evidencia diferida de confirmacion: no agrega espera entre reservas ni
retrasa el siguiente cliente de la cola.

La revision exige encontrar exactamente `Separa Cita Peritaje` en estado
`Programado`. Entonces guarda un PNG nitido desde `Paterno`, `Materno` y `Nombres`
hasta esa fila, y reemplaza la evidencia principal de la reserva por una copia
estable apta para WhatsApp y por la imagen enviada en la secuencia de Telegram. Si
la revision falla, Telegram conserva como respaldo la captura original del momento
de confirmacion. No se pulsa ninguna accion de reserva.

El repaso no se ejecuta si la cola termino por pausa, limite de reservas, resultado
incierto o error tecnico. Un fallo individual de revision queda registrado con una
captura de error y no cambia la reserva ya confirmada ni detiene las demas revisiones.

## Simulacro de backup/restore

```powershell
scripts/verify-postgres-backup.ps1
```

El script restaura en una base temporal, compara tablas esenciales y elimina la
base y el dump al finalizar. Es una verificación de restaurabilidad, no una
política de backup durable. No versionar `.dump`, `.sql` ni `backups/`.

## Evidencia

Seguir [`evidence-policy.md`](evidence-policy.md). La primera lectura es
`docs/evidence-summary.md`, luego `docs/evidence-index.csv`; las bitácoras
extensas viven en `reports/evidence/history/`.
