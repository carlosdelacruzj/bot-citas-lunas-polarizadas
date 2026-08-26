# Plan de plantillas editables de WhatsApp

Estado: **en ejecución; Etapas 0-1 completadas, Etapa 2 implementada y pendiente
de revisión visual, Etapa 3 implementada como piloto y pendiente de observación
natural, Etapas 4-8 pendientes**.

Fecha: `2026-08-25`.

Este documento detalla una implementación incremental. No crea una cola de
trabajo paralela: la prioridad y el momento de ejecutar cada etapa permanecen
exclusivamente en [`../roadmap/README.md`](../roadmap/README.md).

## Objetivo

Permitir que el operador modifique desde el dashboard los mensajes comerciales
de WhatsApp sin editar código ni reiniciar servicios, reutilizando el patrón ya
probado por los recordatorios pre-cita:

- editor de plantilla;
- variables permitidas;
- vista previa;
- validación antes de guardar;
- restauración del texto recomendado;
- revisión y auditoría de cambios.

La configuración solo cambia el contenido. No modifica destinatarios,
disparadores, estados, adjuntos, reglas de reserva, pagos ni la política de un
solo intento automático.

## Situación actual

Los recordatorios pre-cita ya conservan en PostgreSQL la plantilla vigente, su
revisión y versiones anteriores. El dashboard permite editarla, previsualizarla
y restaurar el valor recomendado.

Los demás mensajes se encuentran repartidos entre:

- textos Python para avisos de registro;
- textos Python para reserva, cobro y pago confirmado;
- archivos locales para el destino y la imagen de pago;
- mensajes ya renderizados dentro de trabajos y paquetes durables.

Los avisos de registro y los paquetes de reserva/cobro guardan el texto
preparado. Postpago guarda sus cuatro pasos y deriva de ellos el texto compacto
justo antes de abrir WhatsApp. Los recordatorios pre-cita son una excepción
vigente: encolan un snapshot, pero lo refrescan con la plantilla y los datos
actuales justo antes de enviarlo. La unificación futura no debe cambiar esa
diferencia sin una decisión explícita.

## Resultado de la Etapa 0 - Contrato e inventario

Estado: **completada el 2026-08-25**.

Esta etapa fue documental y de solo lectura sobre el runtime. No creó tablas,
endpoints, plantillas productivas ni mensajes; tampoco modificó `.env`, la
configuración local de pago o los trabajos existentes.

### Constructores y momento del snapshot

| Plantilla futura | Constructor vigente | Consumidor | Momento en que queda congelado hoy |
| --- | --- | --- | --- |
| `registration_monitoring_started` | `services/registration_notices.py::registration_notice_text` | preflight -> `enqueue_registration_notice_job` | al insertar `whatsapp_automation_jobs.message_text` |
| `registration_no_pending_request` | mismo constructor | preflight -> job durable | al insertar `message_text` |
| `registration_invalid_credentials` | mismo constructor | preflight -> job durable | al insertar `message_text` |
| `reservation_confirmation` | `services/reservation_messages.py::format_confirmed_reservation_message` | `prepare_order_whatsapp_message` | al insertar `whatsapp_messages.greeting` |
| `reservation_payment` | `db/whatsapp_messages.py::_payment_message` | `prepare_order_whatsapp_message` | al insertar `whatsapp_messages.payment_message` |
| `post_payment_confirmation` | `db/whatsapp_followup_messages.py::_build_followup_steps` y `_combined_followup_text` | `prepare_post_payment_whatsapp_message` | los pasos quedan congelados en `steps`; el texto compacto se deriva al abrir el borrador |
| `appointment_reminder` | `services/appointment_reminders.py::appointment_reminder_message` | scheduler y revalidación previa al envío | se encola un snapshot, pero se reemplaza antes de enviar con plantilla/datos vigentes |

### Defaults comerciales congelados

Los siguientes textos son la representación parametrizada de los mensajes
vigentes. La Etapa 1 debe insertarlos como defaults sin cambiar redacción,
emojis, saltos de línea ni orden de datos.

#### Registro validado e inicio de monitoreo

```text
Hola, {nombre} 👋

Pudimos ingresar correctamente y verificar tu solicitud ✅

Tu solicitud quedó registrada y desde ahora comenzaremos con el monitoreo.

Servicio: {servicio}
Precio acordado: S/{monto}
Condiciones de búsqueda: {condiciones}
{fechas_excluidas}

Buscaremos únicamente citas que cumplan estas condiciones. No reservaremos una fecha fuera de ellas.

La disponibilidad depende de la PNP y no podemos garantizar que aparezca un cupo. Te escribiremos apenas consigamos la cita.
```

`{fechas_excluidas}` devuelve la línea completa `Fechas excluidas: ...` o se
retira completamente si no existen exclusiones.

#### Acceso correcto sin solicitud pendiente

```text
Hola, {nombre} 👋

Pudimos ingresar correctamente, pero no encontramos una solicitud pendiente para reservar.

Por favor, revisa si el trámite fue registrado y confírmanos cuando aparezca. Luego realizaremos una nueva validación.
```

#### Credenciales rechazadas

```text
Hola, {nombre} 👋

No pudimos validar el acceso con los datos registrados.

Por seguridad realizamos un solo intento para evitar el bloqueo temporal de tu cuenta.

Por favor, revisa el tipo y número de documento y la contraseña, y confírmanos los datos correctos para volver a validar.
```

#### Reserva confirmada

```text
Estimado/a {nombre}, su cita ha sido reservada con exito.

Fecha: {fecha}
Hora: {hora}
Sede: {sede}
```

Se conserva `exito` sin tilde porque ese es el texto productivo actual. Cambiar
el estilo será una edición comercial posterior, no parte de la migración.

#### Instrucciones de pago

```text
Ahora ya podemos proceder con el pago del servicio, el monto es de {monto} soles.
El número es {numero_pago} a nombre de *{titular_pago}*
```

#### Pago confirmado

```text
✅ *¡Pago confirmado!*
Cita reservada. Llegue 30 min antes y vaya con el vehículo ya polarizado.
Reserva: {fecha} {hora}
Sede: {sede}

📄 Lleve los PDFs adjuntos impresos, llenados y firmados. Revise requisitos y copias.

🔍 El peritaje dura aprox. 5 min. Después de pasarlo, en 2 días consulte su autorización virtual en la misma web de reserva.

Gracias por confiar en nosotros. Si puede dejarnos un comentario en TikTok nos ayuda muchísimo: {usuario_tiktok}
```

El default no usa `{nombre}` ni `{monto_pagado}` para permanecer idéntico al
texto compacto vigente, aunque ambas variables estarán disponibles para una
edición posterior del operador.

#### Recordatorio pre-cita vigente

PostgreSQL conserva actualmente la revisión `6`, distinta del fallback en
código. La futura pantalla unificada debe preservar esta plantilla como vigente:

```text
Hola, {nombre} 👋

Como parte de nuestro servicio, te enviamos un recordatorio de tu cita para el trámite de lunas polarizadas:

📅 *Fecha:* {fecha}
🕐 *Hora:* {hora}
📍 *Sede:* {sede}

Recuerda asistir con anticipación y llevar la documentación necesaria para tu trámite.

¡Éxitos en tu cita! 😊
```

El fallback recomendado que sigue versionado en código permanece disponible
para **Restaurar recomendado**, pero no debe reemplazar silenciosamente la
revisión `6` durante una migración.

### Variables y formato aprobados

| Variable | Formato contractual | Ausencia |
| --- | --- | --- |
| `{nombre}` | nombre de la persona solicitante, espacios normalizados | `cliente` solo en preview; una orden productiva debe tener solicitante |
| `{servicio}` | `Estándar`, `Día elegido` o `Personalizado` | no permitida en registro exitoso |
| `{monto}` | número decimal sin moneda, por ejemplo `70.00` | no permitida en cobro/registro exitoso |
| `{monto_pagado}` | número decimal sin moneda | variable opcional de postpago |
| `{fecha}` | `DD/MM/YYYY`; pre-cita conserva su fecha larga actual | no permitida en reserva/postpago |
| `{hora}` | `HH:mm` | no permitida en reserva/postpago |
| `{sede}` | texto confirmado de la reserva | no permitida en reserva/postpago |
| `{condiciones}` | frase sin prefijo, con punto final | no permitida en registro exitoso |
| `{fechas_excluidas}` | línea completa `Fechas excluidas: ...` | se elimina la línea completa |
| `{numero_pago}` | dígitos de la configuración local autorizada | bloquea la preparación |
| `{titular_pago}` | titular de la configuración local autorizada | bloquea la preparación |
| `{usuario_tiktok}` | alias comercial con `@` | usa el valor recomendado configurado |

`{monto}` queda deliberadamente sin `S/`: así los defaults actuales pueden
seguir diciendo `S/{monto}` en registro y `{monto} soles` en cobro sin producir
duplicados como `S/S/70.00`.

### Bloques opcionales aprobados

La primera versión no incorporará condicionales, expresiones ni una sintaxis de
programación dentro de la plantilla. Solo se admite esta regla acotada:

- si una línea contiene exclusivamente una variable declarada como opcional y
  su valor está vacío, se elimina esa línea;
- los demás saltos de línea se preservan;
- una sustitución nunca vuelve a interpretar llaves contenidas en el valor.

En el primer alcance esta regla se usa únicamente para
`{fechas_excluidas}`. `{nombre}` y `{monto_pagado}` pueden estar disponibles en
postpago, pero una plantilla que decida utilizarlos los vuelve obligatorios para
esa revisión o debe proporcionar un valor seguro desde el contexto.

### Inmutabilidad aprobada

- registro: la revisión queda congelada al insertar el job;
- reserva/cobro: queda congelada al crear `whatsapp_messages`;
- postpago: la Etapa 6 debe persistir también el texto compacto final al crear
  el paquete; no debe volver a renderizar una plantilla editable al enviarlo;
- mensajes `queued`, `running`, `sent`, `failed` o `uncertain` nunca cambian por
  una edición comercial posterior;
- recordatorio pre-cita conserva por ahora su contrato
  `applies_from=next_reconciliation`; la Etapa 7 adaptará el editor común sin
  cambiar ese comportamiento ni perder su historial actual.

### Decisiones cerradas para la Etapa 1

1. El piloto inicial sigue siendo `registration_monitoring_started`.
2. Los defaults de la migración son exactamente los textos anteriores.
3. La configuración de pago continúa fuera de las plantillas.
4. Resumen diario y publicación TikTok continúan fuera del alcance.
5. No se incluye HTML, condicionales, filtros ni evaluación de expresiones.
6. El registro genérico deberá soportar revisiones optimistas y preview sin
   conectar todavía consumidores productivos.
7. Los mensajes actuales y la revisión `6` de pre-cita no se modifican durante
   la Etapa 1.

## Resultado de la Etapa 1 - Registro y versiones

Estado: **completada el 2026-08-25**.

La fuente de verdad genérica quedó disponible sin conectar todavía ningún
constructor ni consumidor productivo. La migración aditiva `v61` creó:

- `whatsapp_message_templates`, con texto vigente, revisión, estado reservado,
  fecha y actor;
- `whatsapp_message_template_versions`, append-only y única por clave/revisión;
- siete plantillas iniciales derivadas del contrato de la Etapa 0;
- revisión inicial independiente para la copia genérica de pre-cita, sin alterar
  `appointment_reminder_control` ni su revisión histórica `6`.

La API autenticada incorporó:

- `GET /api/v1/whatsapp-message-templates` para inventario, defaults,
  variables, revisión, preview y momento de aplicación;
- `POST /api/v1/whatsapp-message-templates/{template_key}/preview` para validar
  y renderizar solo con contexto ficticio del servidor;
- `PUT /api/v1/whatsapp-message-templates/{template_key}` para guardar con
  `expected_revision`, actor, nueva versión y auditoría en una transacción;
- `409 stale` con la plantilla vigente cuando la revisión esperada ya cambió.

El renderizador común rechaza texto vacío, más de `1500` caracteres, llaves
incompletas, variables desconocidas, variables requeridas ausentes, repeticiones
excesivas y caracteres de control. Solo `{fechas_excluidas}` puede retirar una
línea opcional vacía; los valores sustituidos no se reinterpretan como plantilla.

### Validación de cierre

- los siete defaults renderizados se compararon con los constructores vigentes;
- PostgreSQL migró de `v60` a `v61` con siete filas vigentes y siete versiones;
- la revisión `6`, el hash del texto y `updated_at` de pre-cita no cambiaron;
- un guardado controlado del mismo texto creó la revisión `2`, su versión y una
  auditoría; repetir la revisión anterior devolvió `409`;
- las cantidades de jobs, álbumes y postpagos permanecieron idénticas;
- la API reiniciada respondió `200` para inventario y preview, y `409` para el
  guardado obsoleto;
- ninguna ruta de registro, reserva, cobro, postpago o recordatorio consume aún
  estas tablas genéricas.

## Principios obligatorios

1. **Aplicación futura:** una plantilla comercial nueva se usa únicamente al
   preparar el siguiente mensaje. No reescribe mensajes ni trabajos existentes.
   Pre-cita conserva durante todo este plan su contrato de siguiente
   reconciliación, incluida la unificación de su editor en la Etapa 7.
2. **Snapshot durable:** cada mensaje comercial preparado conserva texto final,
   clave de plantilla y revisión utilizada. Pre-cita conserva además el snapshot
   encolado, pero puede reemplazarlo durante su revalidación previa al envío,
   como ocurre actualmente.
3. **Variables allowlisted:** solo se sustituyen variables declaradas para esa
   plantilla. Llaves incompletas o variables desconocidas bloquean el guardado.
4. **Datos sensibles fuera:** no se permiten contraseña, documento completo,
   cookies, tokens, CAPTCHA ni credenciales del portal.
5. **Envío independiente:** editar una plantilla no envía, encola, reintenta ni
   concilia WhatsApp.
6. **Un solo intento:** `failed` y `uncertain` continúan terminales y nunca se
   reintentan automáticamente.
7. **Auditoría:** cada guardado conserva revisión, fecha, actor, canal y texto
   anterior/nuevo.
8. **Concurrencia segura:** el guardado exige la revisión esperada y devuelve
   `409` si otro cambio ocurrió antes.
9. **Defaults versionados:** el texto recomendado vive en código como fallback
   y puede restaurarse desde el dashboard sin borrar historial.
10. **Configuración separada:** número, titular e imagen de pago no se mezclan
    inicialmente con el editor de texto.

## Plantillas propuestas

| Clave | Uso | Variables permitidas | Variables requeridas |
| --- | --- | --- | --- |
| `registration_monitoring_started` | Registro validado e inicio de monitoreo | `{nombre}`, `{servicio}`, `{monto}`, `{condiciones}`, `{fechas_excluidas}` | `{nombre}`, `{servicio}`, `{monto}`, `{condiciones}` |
| `registration_no_pending_request` | Acceso correcto sin solicitud pendiente | `{nombre}` | `{nombre}` |
| `registration_invalid_credentials` | Credenciales rechazadas | `{nombre}` | `{nombre}` |
| `reservation_confirmation` | Cita conseguida | `{nombre}`, `{fecha}`, `{hora}`, `{sede}` | `{nombre}`, `{fecha}`, `{hora}`, `{sede}` |
| `reservation_payment` | Instrucciones de cobro | `{monto}`, `{numero_pago}`, `{titular_pago}` | las tres |
| `post_payment_confirmation` | Confirmación del pago y pasos posteriores | `{nombre}`, `{fecha}`, `{hora}`, `{sede}`, `{monto_pagado}`, `{usuario_tiktok}` | `{fecha}`, `{hora}`, `{sede}`, `{usuario_tiktok}` |
| `appointment_reminder` | Aviso pre-cita existente | `{nombre}`, `{fecha}`, `{hora}`, `{sede}` | `{fecha}` |

El resumen diario y su publicación TikTok quedan fuera del primer alcance. Son
mensajes operativos con componentes secuenciales y deben abordarse después de
validar las plantillas dirigidas a clientes.

## Contrato de variables

- `{nombre}`: nombre de la persona solicitante, nunca el alias del contacto.
- `{servicio}`: `Estándar`, `Día elegido` o `Personalizado`.
- `{monto}` y `{monto_pagado}`: número decimal sin símbolo, por ejemplo
  `70.00`; la plantilla decide entre `S/{monto}` y `{monto} soles`.
- `{fecha}`: `DD/MM/YYYY` en mensajes de reserva; el recordatorio puede conservar
  su fecha larga actual mientras se documente la diferencia.
- `{hora}`: `HH:mm`.
- `{sede}`: sede confirmada de la reserva.
- `{condiciones}`: resumen generado por reglas vigentes, incluyendo día de la
  semana y límites mínimo/máximo.
- `{fechas_excluidas}`: línea completa solo cuando existan exclusiones. El
  renderizador debe retirar limpiamente el bloque opcional cuando esté vacío.
- `{numero_pago}` y `{titular_pago}`: valores leídos de la configuración de pago
  autorizada; el texto no puede redefinirlos.
- `{usuario_tiktok}`: identificador comercial configurado, sin URL externa
  arbitraria.

Los valores renderizados pasan por la sanitización existente y nunca se
interpretan como una segunda plantilla. Si un nombre contiene llaves, se trata
como texto normal.

## Diseño de datos

### Tabla vigente

Crear una tabla genérica, por ejemplo `whatsapp_message_templates`, con:

- `template_key` como clave única;
- `message_template`;
- `revision`;
- `updated_at`;
- `updated_by`;
- `enabled` reservado para una necesidad futura, inicialmente siempre `true`.

No usar `enabled` para controlar disparadores. El modo de recordatorios y los
disparadores de registro, reserva y pago siguen bajo sus contratos actuales.

### Historial

Crear `whatsapp_message_template_versions` con:

- `template_key`;
- `revision`;
- `message_template`;
- `created_at`;
- `created_by`;
- índice único por clave y revisión.

Las versiones son append-only. Restaurar un default crea una revisión nueva; no
borra ni reactiva una fila antigua.

### Trazabilidad del mensaje

Añadir `template_key` y `template_revision` a los registros donde aporte
trazabilidad, sin reemplazar el texto final ya persistido:

- `whatsapp_automation_jobs` para avisos textuales;
- `whatsapp_messages` para reserva y cobro;
- `whatsapp_followup_messages` para postpago.

La migración debe ser aditiva. Los mensajes históricos permanecen con revisión
nula y continúan siendo válidos.

## Contrato de backend

### Lectura

`GET /api/v1/whatsapp-message-templates`

Debe devolver por plantilla:

- clave y nombre visible;
- texto vigente y recomendado;
- variables permitidas y requeridas;
- revisión, fecha y actor;
- ejemplo renderizado con datos ficticios;
- lugar donde se utiliza y momento de aplicación.

### Vista previa

`POST /api/v1/whatsapp-message-templates/{template_key}/preview`

- valida sin persistir;
- renderiza únicamente con un contexto ficticio del servidor;
- devuelve errores por campo y variables faltantes;
- no consulta credenciales, no crea mensajes y no abre WhatsApp.

### Guardado

`PUT /api/v1/whatsapp-message-templates/{template_key}`

Payload mínimo:

```json
{
  "message_template": "Hola, {nombre}...",
  "expected_revision": 3
}
```

El actor llega por `X-Appointment-Actor`. La operación valida, bloquea la fila,
comprueba revisión, crea una versión y actualiza la plantilla en una sola
transacción.

### Restauración

Puede reutilizar el mismo `PUT` enviando el default mostrado por la API. No se
necesita un endpoint que borre datos.

## Validaciones

- texto obligatorio y no compuesto solo por espacios;
- máximo inicial de `1500` caracteres por plantilla;
- llaves balanceadas;
- rechazo de variables desconocidas;
- presencia de todas las variables requeridas;
- máximo razonable de repeticiones por variable;
- rechazo de caracteres de control;
- preview y backend usando el mismo renderizador;
- mensaje final no vacío después de resolver bloques opcionales;
- límite final compatible con WhatsApp antes de persistir el trabajo.

Las validaciones no deben intentar evaluar Python, HTML, Markdown arbitrario ni
expresiones dentro de las llaves.

## Diseño del dashboard

Ubicación recomendada:

`Seguimiento -> Configuración de mensajes -> Plantillas de WhatsApp`

La pantalla tendrá tarjetas o pestañas por flujo, no un único textarea sin
contexto:

1. Registro.
2. Reserva y cobro.
3. Pago confirmado.
4. Recordatorio pre-cita.

Cada editor mostrará:

- nombre y explicación del disparador;
- textarea con contador;
- variables disponibles como botones para insertar;
- advertencia de variables obligatorias;
- vista previa lado a lado;
- revisión vigente y última actualización;
- **Restaurar recomendado**;
- **Guardar cambios**;
- confirmación final con resumen del cambio.

No incluir botones de prueba o envío en esta vista. Las pruebas de comunicación
permanecen separadas y requieren destinatario y alcance explícitos.

## Implementación por etapas

### Etapa 0 - Contrato e inventario

Estado: **completada el 2026-08-25**.

Objetivo: congelar nombres, variables, defaults y consumidores antes de migrar.

- identificar cada constructor de mensaje actual;
- copiar los defaults exactos sin modificar el contenido comercial;
- decidir bloques opcionales y variables obligatorias;
- documentar el formato monetario y de fechas;
- confirmar que editar no altera trabajos ya preparados.

Cierre: tabla de plantillas aprobada y ejemplos renderizados iguales a los
mensajes actuales.

### Etapa 1 - Registro y versiones en PostgreSQL

Estado: **completada el 2026-08-25**.

Objetivo: crear la fuente de verdad sin cambiar todavía ningún mensaje real.

- migración aditiva;
- defaults insertados idempotentemente;
- lectura, validación, preview, guardado y conflicto `409`;
- auditoría y versiones;
- ninguna ruta productiva consume todavía las plantillas nuevas.

Cierre: API y migración validadas; cero cambios en mensajes emitidos.

### Etapa 2 - Editor de dashboard

Estado: **implementada técnicamente el 2026-08-25; pendiente de revisión visual**.

Objetivo: administrar y previsualizar sin conectar aún todos los disparadores.

- sección y navegación;
- editor, variables, preview y restauración;
- estados de carga, error y conflicto;
- confirmación de guardado;
- revisión visual en `360`, `768`, `1024` y `1440 px`.

Cierre: guardado y relectura correctos; ninguna acción envía WhatsApp.

Resultado técnico del `2026-08-25`:

- se añadió la sección **Mensajes** en Administración, con catálogo de las siete
  plantillas, editor, inserción de variables permitidas, restauración del texto
  recomendado y vista previa con datos ficticios;
- el guardado incluye una revisión explícita que aclara que no prepara, encola
  ni envía WhatsApp, y maneja carga, error y conflicto de revisión `409`;
- una escritura controlada de `registration_monitoring_started` reutilizó el
  texto vigente, avanzó de revisión `2` a `3` y la relectura devolvió el mismo
  contenido;
- antes y después de esa escritura se conservaron exactamente `370` filas en
  `whatsapp_automation_jobs`, `151` en `whatsapp_messages` y `145` en
  `whatsapp_followup_messages`; los siete consumidores siguen desconectados;
- PostgreSQL conserva `9` versiones: siete iniciales y una validación controlada
  por cada una de las Etapas 1 y 2;
- `npm run build` terminó correctamente. Queda una advertencia no bloqueante: el
  paquete inicial supera por `10.71 kB` el presupuesto de `535 kB`;
- no fue posible ejecutar la revisión visual en `360`, `768`, `1024` y `1440 px`
  porque esta sesión no tiene un navegador integrado conectado. Por eso la
  etapa no se considera completamente cerrada todavía.

### Etapa 3 - Piloto de registro exitoso

Estado: **implementada como piloto el 2026-08-25; pendiente de observación natural**.

Objetivo: conectar únicamente `registration_monitoring_started`.

- renderizar la plantilla al encolar;
- persistir texto final, clave y revisión;
- mantener `no_pending_request` e `invalid_credentials` en código como rollback;
- comprobar un próximo aviso natural, sin crear un cliente de prueba;
- verificar WhatsApp, job, captura y ausencia de alerta Telegram falsa.

Cierre: primer aviso natural confirmado y reconstruible por revisión.

Resultado técnico del `2026-08-25`:

- únicamente `registration_monitoring_started` lee la plantilla vigente al
  preparar el siguiente aviso; `no_pending_request` e `invalid_credentials`
  continúan usando sus constructores Python anteriores;
- el contexto productivo usa nombre verificado por el portal, servicio, monto,
  condiciones de búsqueda y exclusiones de la orden; el renderizado de la
  revisión vigente `3` resultó idéntico al constructor anterior para el caso
  **Día elegido** con rango y fecha excluida;
- PostgreSQL `v62` añadió `template_key` y `template_revision` como campos
  opcionales de `whatsapp_automation_jobs`. Los `370` trabajos históricos
  permanecieron con ambos valores nulos;
- una inserción controlada dentro de una transacción confirmó texto, clave y
  revisión, y luego fue revertida antes de quedar visible al dispatcher;
- el Admin API fue reiniciado de forma aislada con cero trabajos WhatsApp
  `running`, cero intentos de reserva activos y el worker detenido. Regresó
  saludable y publica exactamente un consumidor conectado;
- `compileall`, Ruff, `59` pruebas, `git diff --check` y el build Angular
  terminaron correctamente. Se conserva la advertencia no bloqueante de
  `10.71 kB` sobre el presupuesto inicial del dashboard;
- no se creó un cliente, no se encoló un trabajo persistente y no se envió
  WhatsApp. El cierre permanece pendiente hasta observar el siguiente aviso
  natural y comprobar job, captura y ausencia de una alerta Telegram falsa.

### Etapa 4 - Completar avisos de registro

Objetivo: conectar las otras dos variantes después de aceptar el piloto.

- solicitud no encontrada;
- credenciales incorrectas;
- previews específicos por variante;
- defaults y variables mínimas.

Cierre: cada variante conserva el texto actual como default y no duplica avisos
por ciclo de preflight.

### Etapa 5 - Reserva y cobro

Objetivo: separar confirmación de cita e instrucciones de pago.

- plantilla de reserva;
- plantilla de cobro;
- destino de pago leído desde configuración separada;
- persistencia de revisión en `whatsapp_messages`;
- conservar imágenes y álbum sin cambios.

Cierre: dos imágenes, captions y monto correcto en el siguiente caso natural;
un cambio de plantilla no altera un paquete `prepared`.

### Etapa 6 - Pago confirmado

Objetivo: hacer editable el texto posterior a los PDF.

- plantilla única de postpago;
- variables de reserva y monto pagado;
- conservar PDF, orden de pasos y confirmación por componentes;
- registrar revisión en `whatsapp_followup_messages`;
- no repetir documentos si el texto queda ambiguo.

Cierre: siguiente postpago natural con PDF y texto confirmados, o incertidumbre
correctamente separada por componente.

### Etapa 7 - Unificación del recordatorio existente

Objetivo: mostrar todas las plantillas en una experiencia coherente sin romper
el control `disabled/dry_run/canary/live` de recordatorios.

- reutilizar el renderizador y las validaciones genéricas;
- migrar o adaptar el historial actual sin perder revisiones;
- mantener `{fecha}` obligatoria;
- conservar modos, canarios y scheduler fuera del registro de plantillas.

Cierre: editor unificado y comportamiento pre-cita idéntico al vigente.

### Etapa 8 - Operación y limpieza

Objetivo: retirar duplicación solo después de la validación real.

- eliminar constructores hardcodeados ya sin consumidores;
- actualizar contratos y runbooks;
- mostrar clave/revisión en detalle técnico y conciliación;
- medir errores de renderizado y uso de restauración;
- evaluar después, como trabajo separado, resumen diario y TikTok.

Cierre: no existen dos fuentes activas para la misma plantilla.

## Validación por etapa

Validaciones base:

```powershell
python -m compileall -q src
python -m ruff check src tests
python -m pytest -q
git diff --check
```

Cuando cambie dashboard:

```powershell
Set-Location dashboard
npm run build
npm audit --omit=dev
```

Además:

- migración limpia y migración sobre el esquema vigente;
- guardado válido, variable desconocida, llave incompleta y `409`;
- preview idéntico al renderizador productivo;
- ningún envío durante pruebas de configuración;
- cero trabajos WhatsApp `running` antes de reiniciar Admin API;
- canario natural por tipo antes de ampliar al siguiente.

No se agregarán tests automatizados nuevos salvo autorización explícita. Las
pruebas existentes se ejecutarán en cada etapa.

## Despliegue y rollback

Cada etapa debe poder desplegarse por separado.

Rollback funcional:

1. conservar tablas y revisiones;
2. hacer que el consumidor vuelva temporalmente al default versionado en código;
3. no borrar plantillas ni textos renderizados;
4. no reenviar trabajos ya terminales;
5. reiniciar únicamente Admin API después de comprobar la frontera segura.

Si una plantilla guardada resulta comercialmente incorrecta, restaurar el
default crea una revisión nueva y se aplica solo a trabajos futuros.

## Orden recomendado de ejecución

1. Etapas 0 y 1: base sin impacto en mensajes.
2. Etapa 2: editor sin consumidores productivos.
3. Etapa 3: piloto de registro exitoso.
4. Detenerse y observar un caso natural.
5. Etapas 4 y 5: registro completo, reserva y cobro.
6. Detenerse y observar una reserva natural.
7. Etapa 6: postpago.
8. Detenerse y observar un pago natural.
9. Etapas 7 y 8: unificación y limpieza.

## Criterio de aceptación global

El operador puede editar, previsualizar, restaurar y guardar cada plantilla
desde el dashboard; todo guardado queda versionado y auditado; los trabajos ya
preparados permanecen inmutables; las variables sensibles son imposibles; y los
mensajes naturales de registro, reserva/cobro, postpago y pre-cita usan la
revisión esperada sin modificar disparadores ni reintentar estados ambiguos.
