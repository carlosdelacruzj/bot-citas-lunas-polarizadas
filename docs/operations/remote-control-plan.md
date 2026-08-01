# Plan de control remoto por Telegram

Estado general: Fase 4 completada y validada en operacion real.

Revisión vigente `2026-08-01`: la interfaz dejó de usar Telegram para etiquetar
CAPTCHA o recibir contraseñas durante el alta. El flujo principal crea una
invitación con nombre opcional y WhatsApp, muestra registros pendientes y cubre
las cinco restricciones. Para registros `awaiting_restrictions`, la confirmación
guarda reglas, ejecuta preflight y actualiza el estado alojado. Las secciones de
fases anteriores se conservan como historial y no describen la interfaz vigente.

Ultima actualizacion: `2026-07-18`.

Este es el documento principal para implementar, probar y registrar el control
remoto del sistema. Debe actualizarse al terminar cada fase y despues de cada
prueba operativa relevante.

## Meta

Poder administrar el sistema desde el celular cuando el operador no se
encuentre frente a la computadora, sin exponer el dashboard ni PostgreSQL a
Internet y sin crear una segunda logica de negocio paralela.

El operador debe poder:

- consultar si el sistema esta activo, detenido, pausado o esperando una
  ventana de trabajo;
- solicitar pausa, reanudacion y reinicio del worker;
- consultar la cola y el estado de los clientes;
- agregar clientes mediante un flujo guiado y validado;
- consultar y actualizar prioridad y restricciones de reserva;
- recibir confirmacion del resultado de cada accion;
- consultar errores operativos recientes sin acceder a la computadora.

## Fin esperado

Al cerrar el proyecto, el mismo bot de Telegram usado para alertas tambien
servira como interfaz de administracion remota. La recepcion de comandos vivira
en un proceso independiente del worker, pero reutilizara la Admin API y sus
validaciones.

```text
Celular del operador
  -> Telegram
  -> proceso telegram_control
  -> Admin API local
  -> PostgreSQL / worker_commands
  -> worker
```

n8n podra vigilar disponibilidad y escalar incidentes, pero no sera necesario
para ejecutar una reserva, modificar una orden o controlar el worker.

## Principios y limites

- Reutilizar la Admin API; Telegram no ejecutara PowerShell ni SQL arbitrario.
- Mantener la Admin API en loopback durante la primera version.
- Autorizar exclusivamente una lista explicita de `chat_id`.
- Exigir confirmacion para acciones que cambien estado.
- Registrar quien solicito cada accion, cuando, con que parametros y cual fue
  el resultado.
- No enviar contrasenas, tokens ni credenciales completas por Telegram.
- No modificar `.env` como parte de pruebas temporales.
- No cambiar el flujo de reserva para implementar el control remoto.
- No agregar tests automatizados salvo que el usuario lo solicite de forma
  explicita; las fases de este documento usan validaciones existentes y pruebas
  manuales controladas.
- Si la computadora esta apagada, suspendida o sin Internet, el bot local no
  podra responder. Resolver ese escenario exige infraestructura externa o una
  maquina siempre encendida.

## Base disponible

El proyecto ya cuenta con:

- Admin API separada en `127.0.0.1:8766`;
- autenticacion para las operaciones administrativas;
- endpoints para crear ordenes, editar prioridad y editar restricciones;
- comandos persistidos `pause`, `resume` y `restart` en `worker_commands`;
- estado del worker y endpoint de salud;
- bootstrap de Windows para iniciar y supervisar el worker;
- bootstrap separado para Admin API y dashboard;
- Telegram como canal de alertas y screenshots.

La implementacion debe ampliar estas capacidades, no reemplazarlas.

## Significado de reinicio

Se deben distinguir dos casos:

1. **Worker vivo:** `/reiniciar` solicita el reinicio mediante la Admin API y
   `worker_commands`. El worker consume y aplica el comando.
2. **Proceso del worker caido:** no existe un worker que pueda consumir el
   comando. El bootstrap/supervisor de Windows debe volver a levantarlo. El bot
   de control solo informa el diagnostico y verifica la recuperacion.

Un reinicio no se considerara exitoso solo porque la API acepte la solicitud.
Debe verificarse el cambio de estado, la aplicacion del comando y la nueva
actividad del proceso.

## Alcance de la primera version

Comandos previstos:

| Comando | Funcion | Cambia estado | Confirmacion |
|---|---|---:|---:|
| `/ayuda` | Mostrar comandos permitidos | No | No |
| `/estado` | Salud, fase, ultima y proxima revision | No | No |
| `/clientes` | Resumen de la cola | No | No |
| `/cliente ORDEN` | Detalle administrativo permitido | No | No |
| `/pausar` | Pausar el worker | Si | Si |
| `/reanudar` | Reanudar el worker | Si | Si |
| `/reiniciar` | Reiniciar el worker y verificar resultado | Si | Si |
| `/prioridad ORDEN VALOR` | Actualizar prioridad | Si | Si |
| `/reglas ORDEN` | Consultar restricciones | No | No |
| `/reglas_editar ORDEN` | Flujo guiado para restricciones | Si | Si |
| `/pendientes` | Registros que requieren atención | No | No |
| `/invitacion` | Crear un enlace privado con nombre y WhatsApp | Si | Si |
| `/cancelar` | Cancelar el flujo conversacional actual | No | No |
| `/ultimos_errores` | Resumen saneado de incidentes recientes | No | No |

Los nombres finales pueden ajustarse durante la prueba de uso, pero cada accion
debe conservar una correspondencia clara con la Admin API.

## Fases de implementacion

### Fase 0 - Congelar contratos y linea base

Estado: completada el `2026-07-18`.

1. Inventariar los endpoints exactos que usara cada comando.
2. Confirmar los campos admitidos al crear una orden y editar restricciones.
3. Confirmar como los bootstraps detectan y recuperan procesos caidos.
4. Registrar el estado inicial de worker, Admin API, Telegram y PostgreSQL.
5. Definir respuestas estandar de exito, rechazo, espera y error.

Criterio de cierre:

- existe un mapa comando -> endpoint -> respuesta -> verificacion;
- ninguna operacion requiere SQL directo ni ejecucion arbitraria de shell.

#### Mapa congelado de comandos

| Comando | Operacion interna | Respuesta esperada | Verificacion real |
|---|---|---|---|
| `/ayuda` | Local en `telegram_control` | Lista de comandos permitidos | No aplica |
| `/cancelar` | Local en `telegram_control` | Conversacion cancelada o ausencia de flujo activo | Estado conversacional eliminado |
| `/estado` | `GET /health` y `GET /api/v1/worker` | Salud de API, fase y tiempos operativos | Combinar heartbeat persistido con liveness del proceso; ver brecha 1 |
| `/clientes` | `GET /api/v1/service-orders` | Lista resumida y paginada | Conteos por estado coinciden con el DTO enmascarado |
| `/cliente ORDEN` | `GET /api/v1/service-orders/{order_id}` | Resumen saneado de la orden | Filtrar nuevamente documento y WhatsApp antes de enviarlos a Telegram |
| `/pausar` | `POST /api/v1/worker/pause` | HTTP `202`, `status=queued`, `command_id` | Consultar `GET /api/v1/worker/commands` hasta `applied` o `failed`; despues consultar worker |
| `/reanudar` | `POST /api/v1/worker/resume` | HTTP `202`, `status=queued`, `command_id` | Igual que pausa y confirmar `paused=false` |
| `/reiniciar` | `POST /api/v1/worker/restart` | HTTP `202`, `status=queued`, `command_id` | Confirmar `applied`, salida controlada y actividad posterior del worker |
| `/prioridad ORDEN VALOR` | `POST /api/v1/service-orders/{order_id}/priority` con `{"priority": N}` | HTTP `200`, prioridad y orden actualizadas | Volver a consultar el detalle de la orden |
| `/reglas ORDEN` | `GET /api/v1/service-orders/{order_id}` | Cinco restricciones actuales | Mostrar límites, días y rangos excluidos |
| `/reglas_editar ORDEN` | `POST /api/v1/service-orders/{order_id}/restrictions` | HTTP `200` y restricciones normalizadas | Verificar valores; si falta preflight, programarlo y esperar resultado |
| `/pendientes` | `GET /api/v1/hosted-invitations` | Estados sanitizados y órdenes vinculadas | Abrir cliente o editor de restricciones mediante botones |
| `/invitacion` | `POST /api/v1/hosted-invitations` | HTTP `201`, URL privada y referencia local | Confirmar una sola creación y devolver el enlace sin credenciales |
| `/ultimos_errores` | `GET /api/v1/runs?limit=N` y estado publico del worker | Resumen corto y saneado | No solicitar `include_details=1` ni enviar evidencia cruda |

Todos los endpoints bajo `/api/v1/` requieren
`Authorization: Bearer <APPOINTMENT_BOT_API_TOKEN>`. La comprobacion sin token
del `2026-07-18` devolvio HTTP `401` para worker y ordenes.

#### Contrato de alta congelado

Campos obligatorios actuales:

- `document_number`;
- `document_type`: `dni` o `foreign_resident_card`;
- `password`;
- `contact_name`;
- `contact_source`: `tiktok`, `facebook` o `whatsapp`.

`contact_whatsapp` es opcional. Prioridad, nombre del solicitante, cobro y
restricciones son campos administrativos opcionales. La orden nace pausada y
entra a preflight; no se debe anunciar como activa hasta comprobar el resultado
de esa validacion.

La contrasena obligatoria impide habilitar `/cliente_nuevo` de produccion hasta
definir un mecanismo de ingreso aceptable. Telegram no debe guardar la
contrasena en estado persistente, logs ni mensajes de confirmacion.

#### Contrato de restricciones congelado

El endpoint reemplaza en una sola operacion:

```json
{
  "minimum_reservation_hour": 11,
  "minimum_reservation_date": "2026-08-01",
  "maximum_reservation_date": "2026-08-31",
  "allowed_weekdays": [1, 3, 6]
}
```

Cada campo acepta `null`. Los dias son ISO `1=lunes` a `7=domingo`; la fecha
maxima es inclusiva y no puede preceder a la minima. La confirmacion de Telegram
debe mostrar los valores anteriores y nuevos antes de enviar el POST.

#### Respuestas estandar congeladas

El receptor traducira las respuestas de la API a estas categorias:

| Categoria | Condicion API | Respuesta al operador |
|---|---|---|
| Exito confirmado | HTTP `200/201` y verificacion posterior correcta | Accion completada con identificador y estado final |
| Aceptado y esperando | HTTP `202` o preflight en curso | Solicitud recibida; mostrar progreso hasta estado terminal |
| Entrada invalida | `bad_request` y posibles `field_errors` | Mostrar campos corregibles sin detalles internos |
| No encontrado | `not_found` | Informar que la orden o recurso no existe |
| Conflicto | `conflict` | Explicar el estado que impide la accion |
| No autorizado | HTTP `401` o chat fuera de allowlist | No mostrar informacion administrativa |
| Configuracion incompleta | `configuration_error` | Informar indisponibilidad administrativa sin revelar secretos |
| Fallo operativo | `failed`, timeout o API inaccesible | No confirmar el cambio; indicar verificacion pendiente o fallo |

#### Linea base operativa de 2026-07-18

Comprobacion realizada aproximadamente a las `00:25` en `America/Lima`:

- tarea programada `AppointmentBotContinuousWorker`: `Running`;
- bootstrap del worker: activo y propietario del arranque de PostgreSQL y del
  proceso `appointment_bot.worker.host`;
- bootstrap del dashboard: activo y supervisor de
  `appointment_bot.admin_api.server`;
- PostgreSQL `appointment-bot-postgres`: saludable;
- n8n local: activo, pero no forma parte del camino critico definido;
- API embebida `8765`: saludable, `worker_running=true`, fase
  `outside_hot_window`;
- Admin API `8766`: saludable en modo `api_only`;
- estado persistido: sin pausa, sin error reciente, fase
  `outside_hot_window`;
- comandos recientes consultados: tres reinicios, todos `applied`;
- Telegram habilitado, token y chat configurados, `getMe` correcto;
- Telegram sin webhook configurado y sin actualizaciones pendientes, compatible
  con la decision de usar long polling;
- no existe todavia un receptor permanente `getUpdates`; el unico lector
  encontrado es un script manual de benchmark CAPTCHA.

Los conteos de ordenes consultados se usaron solamente para comprobar el
contrato de listado y no se congelan como verdad de negocio, porque cambian con
la operacion diaria.

#### Brechas detectadas para las siguientes fases

1. **Liveness ambiguo en Admin API.** El proceso separado devuelve
   `worker_running=false` porque no contiene un `ContinuousWorker` en memoria,
   aunque el worker real este activo. `/estado` necesita una señal persistida de
   heartbeat con umbral de antiguedad o un liveness agregado antes de informar
   que el worker esta caido.
2. **Bind del API embebido.** La linea base encontro `8765` escuchando en
   `0.0.0.0`, mientras `8766` permanece en `127.0.0.1`. Las rutas
   administrativas de `8765` exigen token, pero antes del control remoto se debe
   confirmar si ese bind amplio es intencional y restringirlo si no lo es.
3. **Auditoria del actor.** El Admin API registra actualmente
   `requested_by=admin_api`. El control remoto necesita conservar un actor
   Telegram saneado sin aceptar texto arbitrario del cliente.
4. **Credenciales de altas.** El alta requiere password. Esta accion no se
   habilitara hasta decidir su tratamiento seguro.
5. **Resultado terminal.** Un HTTP `202` solo significa encolado. El receptor
   debe esperar `applied` o `failed` y verificar el estado posterior.

#### Evidencia de cierre

- contratos revisados: `docs/contracts/admin-api.md` y
  `docs/contracts/worker-control.md`;
- rutas verificadas en `services/api/worker_routes.py`,
  `services/api/service_order_routes.py` y `services/local_api.py`;
- supervision verificada en `scripts/start-worker.ps1`,
  `scripts/start-worker-hidden.vbs` y `scripts/start-admin-dashboard.ps1`;
- runtime consultado mediante endpoints locales, procesos de Windows, tarea
  programada, Docker y metodos de lectura de Telegram;
- no se escribieron ordenes, reglas, comandos ni configuracion durante la linea
  base.

### Fase 1 - Crear el receptor independiente de Telegram

Estado: completada el `2026-07-18`.

1. Crear un modulo separado para recibir actualizaciones de Telegram.
2. Usar el mismo bot de alertas, manteniendo separado el codigo de envio y el
   codigo de recepcion.
3. Empezar con long polling para no publicar un webhook en Internet.
4. Procesar correctamente el `update_id` para evitar comandos duplicados.
5. Implementar lista permitida de `chat_id` y rechazo silencioso o saneado para
   usuarios no autorizados.
6. Incorporar `/ayuda`, `/estado` y `/cancelar`.
7. Integrar el proceso al arranque supervisado de Windows sin afectar el
   bootstrap del worker.

Criterio de cierre:

- el receptor sigue respondiendo aunque el worker se cierre;
- un chat no autorizado no obtiene datos ni puede cambiar estado;
- reiniciar el receptor no vuelve a ejecutar actualizaciones confirmadas.

Avance realizado:

- creado `appointment_bot.services.telegram_control` como proceso separado;
- agregado entrypoint `appointment-bot-telegram-control`;
- long polling validado sin webhook configurado;
- autorizacion inicial mediante `TELEGRAM_CHAT_ID`, con soporte opcional para
  `TELEGRAM_CONTROL_CHAT_IDS` separado por comas;
- chats no autorizados ignorados sin respuesta ni datos;
- implementados `/ayuda`, `/estado` y `/cancelar`;
- comandos dirigidos al bot con sufijo `@nombre_bot` normalizados;
- offset guardado atomicamente en `.runtime/telegram-control-offset.json` tras
  procesar cada actualizacion valida;
- agregado modo `--check`, que valida Telegram y Admin API sin consumir
  actualizaciones;
- creado `scripts/start-telegram-control.ps1` con recuperacion ante salida;
- integrado el nuevo supervisor en `scripts/start-worker-hidden.vbs`;
- receptor iniciado y long polling activo desde las `00:34` de Lima;
- liveness corregido: el Admin API separado calcula `worker_running` usando el
  lease vigente de PostgreSQL en vez de asumir `false` por no compartir memoria.

Pruebas completadas:

- `--check`: identidad de Telegram, ausencia de webhook y Admin API correctos;
- enrutamiento manual con dobles: `/estado`, `/ayuda` y `/cancelar` correctos;
- chat no autorizado: ignorado sin respuesta;
- persistencia y lectura del offset: correctas;
- Admin API reiniciada por su supervisor y nueva lectura autenticada con
  `worker_running=true`, `phase=outside_hot_window`;
- receptor levantado por su supervisor y long polling confirmado en logs.

Pruebas pendientes para cierre: ninguna.

Validacion conversacional y de recuperacion realizada:

- `/estado`: respondio correctamente en el celular autorizado;
- `/ayuda`: respondio correctamente en el celular autorizado;
- `/cancelar`: respondio `No hay una operacion guiada activa`, resultado
  esperado porque no existia una conversacion abierta;
- offset antes del reinicio del receptor: `89336802`;
- el supervisor recupero el receptor 15 segundos despues de terminar su
  proceso;
- offset despues del reinicio: `89336802`, sin repetir respuestas anteriores.

Prueba de caida abrupta del worker:

- realizada el `2026-07-18` fuera de una ventana activa;
- Telegram permanecio activo con los mismos procesos durante toda la prueba;
- el cierre forzado dejo correctamente el lease de PostgreSQL vigente durante
  cinco minutos para impedir un segundo propietario simultaneo;
- el primer intento del bootstrap salio con codigo `76` por lease vigente;
- se detecto que el reintento anterior de `300` segundos agregaba una espera
  innecesaria despues del primer intento;
- `LeaseUnavailableDelaySeconds` se redujo a `30` segundos para reintentar de
  forma prudente sin forzar ni borrar el lease;
- despues de expirar el lease se reinicio la tarea programada y el worker volvio
  saludable en `outside_hot_window`;
- la prueba final confirmo `worker_running=true` y receptor Telegram activo.
- despues de recuperar el worker, el operador envio `/estado` desde el celular
  autorizado y recibio correctamente la respuesta esperada;
- con esa comprobacion quedaron satisfechos los criterios de cierre de la Fase
  1: independencia del worker, autorizacion, deduplicacion y recuperacion.

### Fase 2 - Control seguro del worker

Estado: completada el `2026-07-18`.

1. Implementar `/pausar`, `/reanudar` y `/reiniciar` mediante la Admin API.
2. Agregar botones de confirmar y cancelar.
3. Usar un identificador de operacion para impedir doble ejecucion.
4. Consultar `worker_commands` hasta obtener `applied` o `failed`, con un tiempo
   maximo definido.
5. Distinguir `outside_hot_window` de un worker detenido.
6. Informar cuando la recuperacion depende del supervisor porque el proceso
   esta completamente caido.

Criterio de cierre:

- Telegram confirma el resultado real, no solamente un HTTP aceptado;
- las solicitudes repetidas no generan reinicios duplicados;
- pausa, reanudacion y reinicio quedan auditados.

Avance realizado:

- implementados `/pausar`, `/reanudar` y `/reiniciar`;
- cada comando genera una confirmacion unica con botones `Confirmar` y
  `Cancelar`;
- las confirmaciones vencen en dos minutos;
- una confirmacion consumida o vencida no puede volver a encolar el comando;
- `/cancelar` elimina la confirmacion pendiente del chat sin realizar cambios;
- la ejecucion ocurre en un hilo separado para mantener activo el long polling;
- Telegram muestra primero `encolada` y solo anuncia exito despues de observar
  `applied` y verificar el efecto real en el estado del worker;
- `failed`, timeout o API inaccesible no se presentan como exito;
- el actor se envia en `X-Appointment-Actor` como hash corto del `chat_id` y se
  persiste en `worker_commands.requested_by` sin guardar el chat completo;
- el Admin API normaliza actores ausentes o invalidos a `admin_api`.

Pruebas locales completadas:

- botones de confirmacion generados correctamente;
- cancelacion sin mutacion verificada;
- doble confirmacion verificada: una sola ejecucion;
- actor valido e invalido normalizados correctamente;
- Admin API y receptor reiniciados por sus supervisores con la nueva version;
- pausa real: comando `applied`, fase `paused`, `paused=true`;
- reanudacion real: comando `applied`, fase `outside_hot_window`,
  `paused=false`;
- reinicio real: comando `applied`, worker recuperado en
  `outside_hot_window`, `worker_running=true`;
- las tres acciones de validacion quedaron auditadas como
  `requested_by=phase2_validation`.

Pruebas pendientes para cierre: ninguna.

Validacion desde Telegram:

- el operador completo la secuencia desde el celular autorizado;
- se registro exactamente un comando `pause`, uno `resume` y uno `restart` con
  el mismo actor Telegram saneado;
- los tres comandos terminaron en `applied` y tienen timestamps de solicitud y
  procesamiento;
- no se encontraron comandos Telegram duplicados en la secuencia;
- estado final: `worker_running=true`, `paused=false`, fase
  `outside_hot_window`, `consecutive_errors=0` y sin `last_error`;
- receptor Telegram activo y offset persistido despues de la prueba;
- con esta evidencia se cumplen los criterios de cierre de la Fase 2.

### Fase 3 - Consultas operativas

Estado: completada el `2026-07-18`.

1. Implementar `/clientes` con una respuesta corta y paginada.
2. Separar ordenes activas, pausadas, reservadas pendientes de pago y cerradas.
3. Implementar `/cliente ORDEN` sin exponer credenciales.
4. Implementar `/reglas ORDEN`.
5. Implementar `/ultimos_errores` con mensajes saneados y limites de longitud.

Criterio de cierre:

- la informacion coincide con Admin API/PostgreSQL;
- ningun mensaje contiene tokens, contrasenas o datos completos innecesarios.

Avance realizado:

- `/clientes [pagina]` implementado con ocho ordenes por pagina;
- el encabezado separa activos, pausados, reservas pendientes de pago y
  cerrados;
- `/cliente ORDER_ID` muestra un resumen operativo enmascarado;
- `/reglas ORDER_ID` muestra fecha minima, fecha maxima, hora minima y dias
  permitidos;
- `/ultimos_errores` revisa las ultimas 50 ejecuciones y devuelve como maximo
  cinco incidentes;
- mensajes de error saneados y limitados, sin URLs ni rutas locales;
- identificadores de orden validados antes de consultar;
- pagina y sintaxis invalidas devuelven ayuda corta sin consultar datos;
- ninguna de estas consultas usa `include_details=1`.

Decision operativa y de seguridad:

- `/clientes` usa `GET /api/v1/service-orders` como indice paginado y no vuelca
  documentos ni telefonos de toda la base;
- `/cliente ORDER_ID` usa deliberadamente el detalle administrativo protegido y
  muestra como cliente al titular identificado por el portal y, por separado,
  al contacto; tambien muestra documento y WhatsApp completos al chat
  autorizado;
- `/reglas` continua usando el DTO del listado porque no necesita datos
  personales completos;
- password, tokens, cookies, datos de cifrado, leases y detalles crudos de runs
  permanecen excluidos siempre;
- esta decision responde a la necesidad operativa confirmada por el usuario:
  cliente, documento y WhatsApp no deben ocultarse al consultar una orden
  especifica desde su chat autorizado.

Pruebas locales completadas con datos reales:

- listado consultado y paginado sobre 66 ordenes;
- respuesta de clientes: 597 caracteres;
- detalle enmascarado: 261 caracteres;
- reglas: 159 caracteres;
- errores recientes: 74 caracteres;
- todas las respuestas por debajo del limite de Telegram;
- indice confirmado sin volcado masivo de documento ni WhatsApp;
- detalle especifico confirmado con cliente, documento y WhatsApp completos,
  sin password ni datos internos;
- `applicant_name` es el cliente/titular y `contact_name` es quien contacto al
  negocio; nunca se asume que son la misma persona;
- si `applicant_name` contiene el documento o no fue obtenido, Telegram informa
  `Titular no identificado por el portal` en vez de presentar un numero como
  nombre;
- errores confirmados sin rutas de Windows ni URLs;
- compilacion, Ruff y `git diff --check` correctos;
- receptor reiniciado por su supervisor y validado contra Admin API.

Pruebas pendientes para cierre: ninguna.

Validacion desde Telegram:

- `/clientes` y paginacion respondieron correctamente;
- `/cliente ORDER_ID` fue probado con una orden sin nombre de titular obtenido y
  con otra orden que si conserva titular identificado;
- se confirmo que cliente/titular y contacto se muestran como personas
  independientes;
- documento y WhatsApp completos aparecen en el detalle deliberado;
- `/reglas ORDER_ID` y `/ultimos_errores` respondieron correctamente;
- no se reportaron contrasenas, rutas ni datos tecnicos innecesarios;
- worker y receptor permanecieron activos despues de las consultas;
- con esta validacion se cumplen los criterios de cierre de la Fase 3.

### Fase 4 - Actualizacion de reglas y prioridad

Estado: completada el `2026-07-18`.

1. Implementar `/prioridad` con validacion y confirmacion.
2. Implementar el flujo conversacional de `/reglas_editar`.
3. Mostrar valores actuales antes de solicitar cambios.
4. Permitir conservar campos que el operador no quiera modificar.
5. Presentar un resumen final y pedir confirmacion.
6. Volver a consultar la orden despues de guardar para verificar persistencia.

Criterio de cierre:

- las reglas aplicadas coinciden con el detalle de la orden;
- cancelar o dejar vencer la conversacion no realiza cambios parciales;
- el worker observa las reglas nuevas sin requerir una modificacion manual de
  la base de datos.

Avance realizado:

- `/prioridad ORDER_ID VALOR` implementado con entero no negativo;
- compara prioridad anterior y nueva antes de confirmar;
- evita confirmacion si el valor ya es el actual;
- `/reglas_editar ORDER_ID` implementado como conversacion de cuatro pasos;
- cada campo permite `igual` para conservarlo y `quitar` para llevarlo a
  `null`; dias tambien acepta `todos`;
- fechas visibles y de entrada usan `DD-MM-YYYY`, hora `0..23` y dias ISO
  `1..7`; la conversion a `YYYY-MM-DD` es solamente interna para API/BD;
- se rechaza una fecha maxima anterior a la minima;
- la conversacion vence despues de cinco minutos de inactividad;
- `/cancelar` elimina conversaciones y confirmaciones sin guardar;
- al completar los pasos se muestra anterior -> nuevo para los cuatro campos;
- solo el boton final `Confirmar` envia un POST atomico;
- botones consumidos o vencidos no pueden repetir la escritura;
- despues del POST se vuelve a consultar el detalle y solo se confirma si todos
  los valores coinciden.

Pruebas locales completadas:

- prioridad genera comparacion y confirmacion;
- editor guiado recoge los cuatro campos sin escrituras parciales;
- comparacion final y botones generados correctamente;
- persistencia real de prioridad verificada sobre una orden archivada;
- persistencia real de las cuatro restricciones verificada;
- prioridad y reglas originales restauradas al terminar la prueba;
- compilacion, Ruff y `git diff --check` correctos.

Pruebas pendientes para cierre: ninguna.

Validacion desde Telegram y restauracion:

- el operador completo la prueba conversacional desde el celular autorizado;
- las fechas fueron solicitadas y mostradas en `DD-MM-YYYY`;
- una fecha minima ingresada como `14-05-1998` se persistio internamente como
  `1998-05-14`, confirmando la conversion correcta hacia API/BD;
- la prioridad termino restaurada en `0`;
- la fecha minima de prueba se restauro a `null`;
- fecha maxima, hora minima y dias permitidos quedaron en `null`;
- una lectura final confirmo prioridad `0` y las cuatro restricciones sin
  limite;
- el worker permanecio saludable en `outside_hot_window`;
- con esta evidencia se cumplen los criterios de cierre de la Fase 4.

### Fase 5 - Alta remota de clientes

Estado: implementada; pendiente de prueba final con un alta real desde Telegram.

1. Implementar `/cliente_nuevo` como conversacion con estado y vencimiento.
2. Solicitar solamente los campos definidos por el contrato vigente.
3. No inventar datos opcionales que el usuario no proporcione.
4. Validar cada campo mediante la Admin API.
5. Mostrar un resumen completo antes de crear la orden, incluida la contrasena,
   solamente en el chat autorizado del unico operador.
6. Pedir confirmacion explicita.
7. Mostrar el `order_id`, estado inicial y resultado del preflight.
8. Permitir `/credenciales ORDER_ID` como consulta individual y deliberada; no
   incluir contrasenas en `/clientes`, `/cliente`, logs ni respuestas masivas.

Decision operativa sobre credenciales:

- el sistema es operado exclusivamente por una persona y el operador solicito
  expresamente ver usuario/documento y contrasena completos cuando los necesite;
- `/cliente_nuevo` muestra esos valores completos en el resumen previo a la
  confirmacion y `/credenciales ORDER_ID` los muestra bajo demanda;
- ambos comandos solo procesan mensajes provenientes de `TELEGRAM_CHAT_ID` o
  `TELEGRAM_CONTROL_CHAT_IDS` autorizados;
- Telegram conserva historial: cada respuesta con credenciales debe tratarse
  como un mensaje sensible y el bot lo advierte expresamente;
- la contrasena sigue cifrada en PostgreSQL y solo se descifra para una consulta
  individual autenticada; no se agrega a los DTO de listado ni detalle general;
- ningun valor sensible se escribe en logs o en este documento.

Avance realizado:

- implementado `/cliente_nuevo` como conversacion de seis pasos con vencimiento
  de 60 segundos por paso y 60 segundos para la confirmacion final;
- se solicitan tipo y numero de documento, contrasena, nombre del contacto,
  fuente y WhatsApp opcional; escribir `OMITIR` no inventa un telefono;
- el titular no se confunde con el contacto: el nombre del titular continuara
  obteniendose del portal durante el preflight;
- el resumen previo muestra todos los valores y requiere el boton `Crear cliente`;
- una confirmacion consumida se elimina antes del POST, por lo que una segunda
  pulsacion del mismo boton no vuelve a crear la orden;
- despues del alta se informa `order_id`, estado inicial y resultado observado
  del preflight;
- implementado endpoint administrativo autenticado para credenciales de una
  sola orden y comando `/credenciales ORDER_ID`;
- `/cancelar` elimina conversaciones y confirmaciones pendientes sin persistir
  informacion parcial.
- cada alta y sesion de CAPTCHA usa un identificador propio, por lo que los
  botones antiguos quedan invalidados;
- solo existe un asistente activo por chat: iniciar alta, CAPTCHA o reglas
  cierra los otros flujos temporales;
- una imagen CAPTCHA vence a los 30 segundos sin respuesta valida y no se marca
  como resuelta.

Pruebas locales completadas sin crear ordenes reales:

- contrato protegido de credenciales consultado contra una orden existente;
- valores descifrados presentes pero no impresos en consola ni logs;
- conversacion completa validada con dobles;
- contrasena completa presente en el resumen de confirmacion;
- doble callback de confirmacion: exactamente una solicitud de creacion;
- sintaxis, lint y espacios pendientes validados.
- Admin API y receptor Telegram reiniciados por sus supervisores con esta
  version; endpoint protegido consultado en vivo sin imprimir sus valores;
- `--check` confirmo un chat autorizado, receptor valido y worker activo en
  `outside_hot_window`.

Prueba pendiente para cierre:

- ejecutar `/credenciales ORDER_ID` desde el celular autorizado;
- ejecutar `/cliente_nuevo` con un cliente real, confirmar el alta y comprobar
  el resultado del preflight. No se creo una orden ficticia para esta prueba.

Criterio de cierre:

- una orden valida queda creada una sola vez;
- una orden invalida muestra errores de campo comprensibles;
- reintentos y respuestas duplicadas no crean clientes duplicados.

### Fase 6 - Auditoria, recuperacion y endurecimiento

Estado: completada el `18-07-2026`.

1. Persistir auditoria de acciones remotas.
2. Definir vencimiento para confirmaciones y conversaciones abandonadas.
3. Aplicar limites de frecuencia por chat y por comando.
4. Sanear logs y respuestas de error.
5. Agregar aviso cuando el receptor de Telegram se reinicie.
6. Verificar la recuperacion independiente de worker, Admin API y receptor.
7. Documentar rotacion de token sin guardar secretos en el repositorio.

Criterio de cierre:

- cada cambio remoto puede reconstruirse desde la auditoria;
- la caida de un componente no provoca acciones duplicadas;
- no existe una ruta de ejecucion arbitraria desde Telegram.

Avance realizado:

- esquema PostgreSQL elevado a version `33` con `remote_control_audit`;
- cada evento conserva actor Telegram hasheado, accion, orden opcional, estado,
  identificador de operacion y fecha;
- la auditoria no recibe mensajes escritos por el usuario, documentos,
  telefonos, contrasenas, tokens ni respuestas completas;
- resultados `accepted`, `applied`, `failed`, `cancelled`, `denied`,
  `rate_limited` y `started` permiten reconstruir el ciclo de una accion;
- limite por chat de 30 consultas o 15 acciones/conversaciones por minuto;
- una solicitud limitada no ejecuta Admin API ni consume una confirmacion;
- conversaciones y confirmaciones vencidas se eliminan tambien durante el
  long polling, sin esperar un nuevo mensaje del operador;
- cada inicio o recuperacion del receptor envia `CONTROL REMOTO DISPONIBLE` al
  chat autorizado con la fase observada del worker;
- chats no autorizados siguen sin recibir respuesta y ahora dejan solamente un
  actor hasheado con estado `denied`;
- Telegram continua limitado a rutas concretas de Admin API: no existe comando
  para PowerShell, SQL, archivos ni texto arbitrario.

Validacion realizada:

- migracion real a esquema `33` aplicada correctamente;
- escritura y lectura de auditoria persistente verificadas;
- barrera de frecuencia y recuperacion despues de 60 segundos verificadas;
- escaneo de los eventos persistidos sin campos sensibles;
- Admin API y receptor terminados de forma controlada y recuperados por sus
  supervisores independientes;
- primer intento de Telegram fallo mientras Admin API reiniciaba y el siguiente
  intento se recupero automaticamente;
- receptor recuperado con `authorized_chats=1`, worker activo en
  `outside_hot_window` y evento `receiver/started` persistido;
- aviso de recuperacion aceptado por Telegram para el chat autorizado.

Rotacion de secretos, sin versionarlos:

1. Token de Telegram: revocarlo y generar otro mediante BotFather.
2. Sustituir `TELEGRAM_BOT_TOKEN` solamente en la configuracion local ignorada
   por Git; nunca pegarlo en documentos, commits, capturas o chats de soporte.
3. Token de Admin API: generar un valor aleatorio nuevo y sustituir
   `APPOINTMENT_BOT_API_TOKEN` en la misma configuracion local.
4. Reiniciar Admin API y receptor mediante sus supervisores; no reiniciar el
   worker si solo cambio el token de Telegram.
5. Ejecutar `appointment-bot-telegram-control --check` y confirmar el nuevo
   aviso en el chat autorizado.
6. Revisar `git diff` antes de cualquier commit para comprobar que ningun valor
   secreto entro al repositorio.

### Fase 7 - Monitoreo externo con n8n

Estado: opcional y pendiente.

1. Ejecutar n8n fuera de la computadora operativa si se pretende detectar la
   caida completa de esa computadora.
2. Consultar salud con una frecuencia prudente.
3. Alertar solo por incidentes accionables y evitar mensajes repetidos.
4. Escalar cuando la maquina, Admin API o receptor permanezcan inaccesibles.
5. Mantener altas, reglas y control del worker en la Admin API.

Criterio de cierre:

- n8n detecta una indisponibilidad que el sistema local no puede reportar;
- una caida de n8n no impide la operacion normal del bot.

### Mejora transversal - Interfaz operativa con botones

Estado: implementada el `18-07-2026`.

Objetivo: reducir al minimo la escritura de comandos y `ORDER_ID` desde el
celular sin eliminar la compatibilidad con los comandos existentes.

Funciones implementadas:

- `/menu` abre un menu principal con Estado, Clientes, Nuevo cliente, Buscar,
  Resumen de hoy, Recientes, Worker y Errores;
- `/clientes` conserva ocho registros por pagina y agrega botones por cliente,
  Anterior, Siguiente, Actualizar y Menu;
- seleccionar un cliente abre su panel con datos completos autorizados y
  accesos a Credenciales, Reglas, Prioridad y Actualizar;
- el mensaje de credenciales incluye `Eliminar este mensaje` para retirarlo
  inmediatamente del historial y `Volver al cliente`;
- las prioridades ofrecen valores rapidos: Baja `0`, Normal `10`, Alta `50` y
  Urgente `100`, siempre con confirmacion antes de guardar;
- el editor de reglas ofrece Mantener, Quitar limite, horas comunes, Lunes a
  sabado, Solo sabado y Todos; las fechas especiales se escriben en
  `DD-MM-YYYY`;
- el alta permite elegir DNI/CE, fuente y omision de WhatsApp mediante botones;
  documento, contrasena, nombres y telefono permanecen como entrada escrita;
- `/buscar TEXTO` usa un endpoint administrativo protegido y encuentra por
  titular, contacto, documento completo, WhatsApp completo u `ORDER_ID` sin
  agregar esos datos al listado general; la consulta usa `POST` para que el
  valor buscado no aparezca en la URL registrada por Admin API;
- `/recientes` conserva hasta ocho clientes consultados mientras el receptor
  permanece activo;
- `/resumen` muestra fecha peruana, worker, fase, clientes activos, pausados,
  reservas del dia, pendientes de pago y errores consecutivos;
- el panel del worker muestra solo Pausar o Reanudar segun su estado, ademas de
  Reiniciar, Actualizar y Menu;
- avisos de inicio, cambios aplicados y altas completadas incluyen botones para
  continuar la operacion;
- todos los callbacks respetan autorizacion, limites de frecuencia, vencimiento
  y confirmaciones de una sola ejecucion.

Validacion sin mutaciones reales:

- menu y callbacks comprobados con dobles locales;
- limites de 64 bytes de Telegram comprobados para todos los botones;
- navegacion, recientes, resumen, alta guiada y eliminacion de mensajes
  sensibles comprobados;
- listado con botones validado contra las `66` ordenes reales sin enviar
  mensajes ni modificar datos;
- busqueda protegida validada sin imprimir documentos ni telefonos.

### Fase 8 - Acceso privado al dashboard

Estado: opcional y pendiente.

Evaluar una red privada para abrir el dashboard desde el celular o una laptop
sin publicar el puerto `8766` en Internet. Esta fase se ejecutara solamente
despues de cerrar autenticacion, autorizacion y pruebas del control por
Telegram.

## Matriz minima de pruebas operativas

| Escenario | Resultado esperado | Estado |
|---|---|---|
| Worker activo | `/estado` informa fase y siguiente accion reales | Completado |
| Fuera de ventana | Se informa activo pero esperando, no apagado | Completado |
| Worker pausado | Estado y motivo coherentes | Completado |
| Reinicio normal | Comando aplicado y nueva actividad verificada | Completado |
| Worker completamente caido | Supervisor lo recupera y Telegram lo verifica | Completado |
| Admin API caida | Error claro, sin ejecutar una ruta alternativa insegura | Completado |
| PostgreSQL no disponible | No se confirma ninguna escritura | Pendiente |
| Telegram sin Internet | Al recuperar conexion no duplica comandos | Pendiente |
| `update_id` repetido | La accion se procesa una sola vez | Completado |
| Chat no autorizado | No obtiene datos ni ejecuta acciones | Completado |
| Confirmacion vencida | No se realiza el cambio | Completado |
| Conversacion cancelada | No queda informacion parcial aplicada | Completado |
| Regla invalida | Se muestran errores y se conserva la regla anterior | Completado |
| Alta repetida | No se crean ordenes duplicadas | Validacion local; alta real diferida |
| Mensaje de error | No revela tokens, credenciales ni datos sensibles | Completado |

## Validacion al cerrar cada fase

Como minimo:

```powershell
python -m compileall src
python -m ruff check src
git diff --check
```

Ademas se debe ejecutar la prueba manual propia de la fase contra los procesos
locales y registrar el resultado en este documento. Las validaciones no deben
alterar ordenes reales salvo que la prueba lo indique y el usuario lo autorice.

## Registro de avance

| Fecha | Fase | Cambio o prueba | Resultado | Evidencia | Proximo paso |
|---|---|---|---|---|---|
| 2026-07-18 | Plan | Creacion del documento principal | Completado | `docs/operations/remote-control-plan.md` | Ejecutar Fase 0 |
| 2026-07-18 | 0 | Contratos, bootstraps y linea base de runtime | Completado con cinco brechas documentadas | Seccion Fase 0 de este documento | Resolver liveness y disenar receptor de Fase 1 |
| 2026-07-18 | 1 | Receptor Telegram, liveness por lease y supervisor | Completado y validado desde celular despues de recuperar el worker | Logs de bootstrap y seccion Fase 1 | Iniciar Fase 2: control seguro del worker |
| 2026-07-18 | 2 | Confirmaciones y control persistido del worker | Completado; pause, resume y restart aplicados una vez desde Telegram | `worker_commands` y seccion Fase 2 | Iniciar Fase 3: consultas operativas |
| 2026-07-18 | 3 | Consultas operativas y detalle deliberado | Completado y validado desde Telegram | Admin API y seccion Fase 3 | Iniciar Fase 4: prioridad y reglas remotas |
| 2026-07-18 | 4 | Prioridad y restricciones remotas | Completado desde Telegram; formato peruano y restauracion verificados | Admin API y seccion Fase 4 | Iniciar Fase 5: alta remota de clientes |
| 2026-07-18 | 5 | Alta remota y credenciales individuales | Implementado y desplegado; falta prueba con cliente real | Admin API, Telegram y seccion Fase 5 | Probar `/credenciales` y `/cliente_nuevo` desde el celular |
| 18-07-2026 | 6 | Auditoria, limites y recuperacion | Completado; esquema 33 y aviso de reinicio desplegados | PostgreSQL, supervisores y seccion Fase 6 | Priorizar mejoras de interfaz Telegram |
| 18-07-2026 | UX | Menu y operacion mediante botones | Implementado y validado sin mutar ordenes | Telegram, Admin API y mejora transversal | Validar navegacion desde el celular |

## Decisiones pendientes

- Decidir si n8n se desplegara fuera de la computadora operativa.
- Decidir si se necesita acceso privado al dashboard despues de validar
  Telegram.

Estas decisiones no bloquean la Fase 0 ni los comandos de solo lectura de la
Fase 1.

## Regla de actualizacion del documento

Al terminar una fase:

1. cambiar su estado;
2. marcar las pruebas ejecutadas;
3. agregar una fila al registro de avance;
4. enlazar logs, capturas o reportes que sirvan como evidencia;
5. anotar problemas encontrados y decisiones tomadas;
6. dejar escrito el siguiente paso exacto.

No se marcara una fase como completada solo porque el codigo compile. Debe
cumplir su criterio de cierre y superar sus pruebas operativas.
