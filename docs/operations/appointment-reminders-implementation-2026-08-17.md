# Implementacion de recordatorios de cita

Fecha de inicio: `2026-08-17`.

## Objetivo

Generar diariamente recordatorios WhatsApp para las reservas confirmadas cuya
cita sea dentro de `1`, `2` o `3` dias, segun el control persistido, conservando
como prioridad absoluta el resumen diario de evidencias enviado al operador.

## Reglas acordadas

- La zona horaria operativa es `America/Lima`.
- El resumen diario de evidencias debe terminar antes de enviar recordatorios.
- Los recordatorios pueden persistirse antes, pero permanecen bloqueados por la
  barrera diaria.
- Solo una automatizacion WhatsApp puede ejecutarse a la vez.
- Un resultado `uncertain` es terminal y nunca se reintenta automaticamente.
- La seleccion usa reservas confirmadas y datos administrativos; nunca toma
  destinatarios de credenciales, campos del portal ni honeypots.
- Antes de enviar se revalida que la cita y el destinatario sigan vigentes.
- La anticipacion y el modo se administran desde el dashboard y PostgreSQL; no
  requieren modificar `.env` ni reiniciar procesos.

## Estado recuperable

### Paso 1 - Lectura y delimitacion

Estado: `completado`.

- Leidos completos `docs/project-status.md` y `docs/roadmap/README.md`.
- Revisado el worktree: existen cambios ajenos en archivos de evidencia y dos
  HTML sin seguimiento; se preservaran intactos.
- Confirmado que Admin API es el propietario unico del perfil WhatsApp.
- Confirmado que la cola durable ya serializa los trabajos y conserva
  `queued`, `blocked`, `running`, `sent`, `failed` y `uncertain`.
- Confirmado que el worker encola el resumen diario al cerrar a las `18:00`.
- Confirmado que `reservations.appointment_date` es texto y requiere una fecha
  normalizada para una consulta diaria segura.

### Paso 2 - Contrato y migracion

Estado: `completado`.

- Definido PostgreSQL `schema v56` de forma aditiva.
- `reservations` incorpora `appointment_day date` e indice parcial para
  reservas confirmadas.
- El backfill transaccional interpreto `125` fechas existentes y dejo `0`
  reservas confirmadas con fecha textual no interpretable.
- `whatsapp_automation_jobs` incorpora reserva, fecha de cita y prioridad.
- El nuevo tipo `appointment_reminder` exige orden, reserva, fecha, contacto y
  texto, sin adjuntos ni campos de otros flujos.
- Se agrego el estado terminal `skipped` para impedir un envio obsoleto despues
  de la revalidacion.
- `appointment_reminder_days` conserva el corte diario, conteos, barrera,
  alertas y ultima reconciliacion.
- Una creacion limpia del esquema `v56` paso `_validate_current_schema` dentro
  de una transaccion revertida.
- La migracion real `v55 -> v56` tambien se probo dentro de una transaccion y
  se revirtio antes de aplicarla de forma persistente.
- La base viva quedo en `v56`, con `125` reservas normalizadas y cero reservas
  confirmadas con fecha textual no interpretable.

### Paso 3 - Seleccion e idempotencia

Estado: `completado y validado sobre v56 vivo`.

- La seleccion usa la reserva confirmada mas reciente de cada orden para
  manana en hora Lima.
- Se excluyen retiros, cupos externos, duplicados, casos no gestionables y
  deudas cerradas como incobrables.
- Se aceptan ordenes reservadas con pago pendiente, pagadas y archivadas
  legitimamente.
- El destinatario procede solo del contacto primario administrativo; telefono
  tiene prioridad sobre `@usuario`.
- La clave `appointment_reminder:{reservation_id}:{appointment_day}` evita
  duplicados mediante `ON CONFLICT DO NOTHING`.
- Cada reconciliacion normaliza fechas nuevas que un worker antiguo pudiera
  haber escrito antes de su siguiente reinicio programado.
- El dry-run vivo para citas del `2026-08-18` encontro `8` elegibles, cero
  contactos faltantes, cero fechas invalidas y creo cero trabajos.
- Una simulacion transaccional creo los ocho trabajos una sola vez; una segunda
  reconciliacion creo cero duplicados y el rollback dejo cero trabajos reales.

### Paso 4 - Barrera, programador y envio

Estado: `completado y validado sin envio`.

- Admin API incorpora un programador residente con hora Lima y reconciliacion
  recuperable.
- Los recordatorios se insertan bloqueados con prioridad `100`; el resumen
  diario se inserta con prioridad `0`.
- Tanto la lectura como el claim de la cola exigen que exista un resumen del
  dia y que no quede ningun resumen `queued`, `blocked` o `running`.
- Justo despues del claim se revalidan fecha, vigencia, destinatario y texto.
- Un recordatorio que ya no corresponde a manana termina `skipped` antes de
  abrir el chat.
- El envio reutiliza el administrador Playwright serial y exige una burbuja
  saliente confirmada; `uncertain` permanece terminal.
- Se agrego una pausa configurable despues de cada intento de recordatorio.
- La simulacion transaccional confirmo: cero recordatorios reclamables sin
  resumen, resumen como unico trabajo elegible mientras estaba activo y ocho
  recordatorios elegibles solo despues de terminar el resumen.

### Paso 5 - API y visibilidad operativa

Estado: `completado y validado por HTTP`.

- Nuevo endpoint autenticado `GET /api/v1/appointment-reminders`.
- El resumen del dashboard muestra configuracion, fecha objetivo, elegibles,
  cola, enviados, contactos faltantes y estado de la barrera.
- El endpoint solo expone destinatarios enmascarados.
- El build Angular termino correctamente con bundle inicial de `529.99 kB`.
- Admin API se reinicio de forma aislada despues de comprobar cero sesiones
  manuales, cero submissions y cero trabajos WhatsApp `running`.
- `GET /api/v1/appointment-reminders` respondio con fecha objetivo
  `2026-08-18`, configuracion desactivada/dry-run y cero trabajos reales.
- El worker de reservas no se reinicio y continuo saludable.

### Paso 6 - Documentacion y validacion

Estado: `completado`.

- `python -m compileall -q src`: correcto.
- `python -m ruff check src tests`: correcto, sin observaciones.
- `python -m pytest -q`: `59 passed`.
- `npm run build`: correcto; paquete inicial `529.99 kB`, dentro del limite y
  sin advertencias.
- `git diff --check` sobre los archivos de esta implementacion: correcto. Los
  tres archivos de evidencia que ya tenian cambios ajenos se excluyeron del
  control para no alterarlos.
- Antes del reinicio final se verificaron esquema `56`, cero sesiones manuales,
  cero intentos `intent/pending`, cero trabajos WhatsApp `running`, cero
  recordatorios persistidos y `current_order_id=null`.
- Admin API cambio de PID `8576` a `21024` bajo su supervisor. El worker no se
  reinicio y continuo saludable.
- La consulta HTTP final devolvio ocho citas elegibles para `2026-08-18`, cero
  contactos faltantes, cero fechas invalidas y cero trabajos creados, con
  `enabled=false` y `dry_run=true`.

## Archivos ajenos preservados

- `docs/evidence-index.csv`
- `docs/evidence-summary.md`
- `reports/evidence/history/reservation-optimization-log.md`
- `html con cupo.html`
- `html sin cupo.html`

## Registro cronologico

1. Se inicio la implementacion sin reiniciar procesos ni enviar comunicaciones.
2. Se fijaron las reglas anteriores antes de modificar codigo o base de datos.
3. Ruff y `compileall` pasaron sobre el codigo Python modificado.
4. La migracion se valido primero en un schema temporal limpio y luego contra
   los datos vivos dentro de una transaccion revertida.
5. No hubo navegadores, mensajes, reinicios ni cambios persistentes de esquema
   durante estas validaciones.
6. Se aplico `v56` y despues se reinicio solo Admin API en una frontera segura;
   no se reiniciaron worker, Telegram ni CAPTCHA.
7. No se envio WhatsApp ni Telegram. El recordatorio productivo permanece
   desactivado y el siguiente paso operativo es aprobar el primer canario.
8. La validacion final cerro sin errores ni advertencias de build y dejo la API
   administrativa cargando el codigo nuevo.

## Ampliacion de visibilidad en Seguimiento

Estado: `implementado el 2026-08-17; revision visual humana pendiente`.

1. El endpoint de recordatorios incorpora `candidates` con nombre, fecha, hora,
   sede, orden, destinatario enmascarado y estado. No devuelve telefono completo
   ni credenciales.
2. La tarjeta de Resumen se redujo a una senal compacta con el total elegible y
   el boton `Ver elegibles`.
3. La antigua navegacion `Post-cita` se renombro `Seguimiento`; la ruta visible
   es `/seguimiento` y `/post-cita` se conserva como redireccion compatible.
4. Seguimiento se dividio en `Proximas citas`, `Post-cita` e `Historial`. La
   pestana activa queda en `?tab=` para abrir directamente cada contexto.
5. Proximas citas permite buscar y ordenar por hora, cliente, sede o estado.
   Post-cita conserva filtros, busqueda, orden y revision manual; Historial
   separa completados y accesos perdidos sin acciones automaticas.
6. La consulta local devolvio `8` candidatos, todos `eligible`, con contactos
   enmascarados y cero trabajos reales.
7. `compileall`, Ruff y el build Angular fueron correctos. El bundle inicial
   quedo en `530.57 kB`; el umbral de advertencia se ajusto de `530 kB` a
   `535 kB`, manteniendo el limite de error en `1 MB`.
8. No habia navegador conectado para inspeccionar visualmente escritorio y
   movil. El build valida plantilla y tipos, pero no sustituye esa aprobacion.
9. Antes de publicar el backend se comprobaron esquema `56`, cero sesiones
   manuales, cero submissions, cero trabajos WhatsApp activos y ninguna orden
   reclamada por el worker. Admin API cambio de PID `21024` a `36596`; el
   worker no se reinicio.
10. La validacion HTTP final confirmo `/seguimiento?tab=upcoming` y la ruta
    compatible `/post-cita` con codigo `200`, bundle `main-64TD5UPN.js`, ocho
    candidatos enmascarados, modo desactivado/dry-run y cero trabajos reales.

## Editor, variables y activacion protegida

Estado: `implementado el 2026-08-17; activacion real pendiente`.

1. Se reemplazo la autoridad de activacion basada en `.env` por el singleton
   `appointment_reminder_control`; horario, pausa, limite diario y barrera del
   resumen permanecen configurables como antes.
2. El schema `v57` crea el control en `disabled`, con revision `1`, y guarda
   cada texto aceptado en `appointment_reminder_template_versions`.
3. La API acepta solo `{nombre}`, `{fecha}`, `{hora}` y `{sede}`, exige
   `{fecha}`, limita el texto a `1000` caracteres y rechaza llaves incompletas.
4. El modo `canary` exige 1 o 2 ordenes que sigan elegibles para manana; `live`
   admite todos dentro del limite diario. Ambos requieren confirmacion adicional
   en la interfaz.
5. El dispatcher consulta nuevamente el control antes de abrir WhatsApp. Una
   desactivacion impide reclamar trabajos bloqueados y una carrera posterior al
   claim termina antes de abrir el chat.
6. `Seguimiento > Proximas citas` incorpora composicion, chips de variables,
   vista previa con datos reales enmascarados, restauracion y los modos
   Desactivado, Solo revision, Canario y Activo.
7. Esta implementacion no modifica `.env`, no activa canario/productivo y no
   envia ni encola comunicaciones durante la migracion.
8. La creacion limpia `v57` y la migracion `v56 -> v57` pasaron primero dentro
   de transacciones revertidas. Luego se aplico la migracion viva con
   `mode=disabled`, revision `1`, cero canarios y cero trabajos.
9. Solo Admin API se reinicio (`36596 -> 38408`); worker, Telegram y CAPTCHA no
   se reiniciaron. El worker continuo en monitoreo y no habia submissions ni
   trabajos WhatsApp activos.
10. La verificacion HTTP sirvio `main-4TE6ORXA.js`, devolvio los cuatro campos
    permitidos, `8` candidatos y cero trabajos. Un POST canario invalido fue
    rechazado con `400` sin cambiar modo, revision ni cola.
11. `compileall`, Ruff, `59` pruebas y build Angular pasaron; el bundle inicial
    quedo en `532.65 kB`. La revision visual humana sigue pendiente porque no
    habia navegador conectado.

## Primer lote real y correccion del nombre

Estado: `8/8 sent el 2026-08-17; correccion aplicada para lotes futuros`.

1. El control se guardo en `live`, revision `2`, a las `17:53:44`, con ocho
   candidatos para el `2026-08-18` y cero fechas o contactos invalidos.
2. El worker cerro normalmente a las `18:00:32` y encolo primero el resumen con
   `16` evidencias. Los ocho recordatorios se crearon `blocked` a las
   `18:00:56` y ninguno se reclamo mientras el resumen permanecio `running`.
3. El resumen termino `sent` a las `18:02:07`. El primer recordatorio inicio a
   las `18:02:24` y el octavo termino a las `18:04:53`; el corte quedo
   `complete` a las `18:04:57`, sin `failed`, `uncertain`, `skipped` ni
   duplicados.
4. La revision posterior detecto que `{nombre}` preferia `contact_name`. Los
   ocho mensajes ya enviados no se reenvian ni modifican, pero los siguientes
   usan exclusivamente `applicant_name`, la persona de la cita, con `cliente`
   como fallback seguro.
5. Se corrigio tambien el contrato nullable del nombre en Angular y la fecha de
   vista previa: ahora consume la misma etiqueta `18 de agosto de 2026` que el
   backend usa al renderizar WhatsApp.
6. Con cero trabajos WhatsApp, sesiones manuales y submissions activos se
   reinicio solo Admin API (`38408 -> 30048`). El runtime conservo `live`,
   revision `2`, los `8` trabajos `sent` y sirvio `main-5RIZKUNK.js` con la
   etiqueta de fecha nueva; no se reiniciaron worker, Telegram ni CAPTCHA.

## Anticipacion configurable y nueva superficie operativa

Fecha de ampliacion: `2026-08-28`.

Estado: `implementacion tecnica incorporada; las validaciones del corte y la
revision visual se registran por separado en project-status y roadmap`.

### Persistencia y API

1. PostgreSQL `schema v66` agrega
   `appointment_reminder_control.lead_days smallint NOT NULL DEFAULT 1`. La
   restriccion nombrada `ck_appointment_reminder_control_lead_days` admite solo
   `1`, `2` o `3`, preservando el comportamiento anterior al migrar.
2. `PUT /api/v1/appointment-reminders` exige `lead_days` como entero estricto
   junto con `mode`, `canary_order_ids` y `expected_revision`. Los booleanos y
   valores fuera del rango se rechazan. El guardado incrementa la misma revision
   optimista y deja la anticipacion en la auditoria del control.
3. `GET /api/v1/appointment-reminders` expone:
   - `control.lead_days`, el valor configurado;
   - `configuration.effective_lead_days`, la anticipacion efectiva del lote;
   - `control.lead_days_applies_from`, con
     `current_service_date` o `next_service_date`;
   - `control.applies_from`, la fecha Lima exacta desde la que se aplica;
   - `control.existing_jobs_policy=preserved`.
4. El cambio se toma desde PostgreSQL en cada reconciliacion. No requiere
   modificar `.env`, reiniciar Admin API ni reiniciar el worker.

### Lote diario congelado

1. La primera reconciliacion de un `service_date` crea la fila diaria y congela
   `appointment_day = service_date + lead_days`. La restriccion del lote admite
   diferencias de `1` a `3` dias.
2. Si esa fecha Lima ya tiene lote, nuevas reconciliaciones reutilizan su
   `appointment_day`. Un cambio de anticipacion queda guardado, pero comienza el
   siguiente dia Lima; no pisa la fecha objetivo ni mezcla elegibles, trabajos
   o conteos de dos configuraciones.
3. Si aun no existe lote para hoy, la proxima reconciliacion usa inmediatamente
   el valor guardado. La validacion de un canario sigue la misma regla: consulta
   el target congelado cuando existe y el target propuesto cuando todavia no.
4. Los trabajos existentes conservan `report_date`, `appointment_day`, texto,
   plantilla y la clave
   `appointment_reminder:{reservation_id}:{appointment_day}`. Cambiar
   `lead_days` no los cancela, reescribe, mueve ni duplica.
5. Candidatos, estado y conteos del dia se calculan contra el target congelado.
   Una cita ya cubierta por esa clave durable no vuelve a producir otro envio
   al reaparecer bajo una anticipacion distinta.

### Revalidacion antes de WhatsApp

1. El dispatcher no compara un trabajo preparado contra el `lead_days` que
   pueda estar vigente despues. Usa el snapshot del propio trabajo y exige que
   `appointment_day - report_date` sea `1`, `2` o `3`.
2. `report_date` debe seguir siendo hoy en `America/Lima`. Un lote atrasado
   termina `skipped` antes de abrir WhatsApp.
3. Tambien se vuelven a leer la reserva confirmada vigente, su fecha, el
   contacto y el texto. Una cita o un destinatario obsoleto termina `skipped`.
4. La desactivacion del modo conserva autoridad sobre trabajos bloqueados. Si
   un intento llega al envio, `sent` sigue exigiendo evidencia confirmada y
   `uncertain` permanece terminal, sin reintento automatico.
5. El texto recomendado deja de afirmar `mañana` y usa la fecha explicita. Los
   textos de estado y error hablan de `fecha objetivo`, por lo que sirven para
   cualquiera de las tres anticipaciones. Si una plantilla personalizada aun
   contiene `mañana`, la API rechaza guardar `2` o `3` dias y la conciliacion
   conserva una segunda barrera defensiva. El operador la corrige en
   **Mensajes**; el sistema nunca sobrescribe texto personalizado en silencio.

### Citas y recordatorios

La antigua superficie **Seguimiento** pasa a presentarse como **Citas y
recordatorios**, con tres espacios de trabajo:

- **Proximas citas** reúne todas las citas futuras devueltas por Post-cita y
  superpone el estado del recordatorio cuando la cita pertenece a la fecha
  objetivo. Las demas permanecen visibles como `Cita programada`.
- **Necesitan revision** contiene los seguimientos accionables y conserva
  **Revisar ahora** como accion manual.
- **Historial** contiene completados y accesos perdidos, sin acciones
  automaticas.

En **Proximas citas**, la busqueda aparece antes de metricas y listado. Busca
por nombre, orden, documento enmascarado, placa, expediente, sede, contacto
enmascarado, fecha, hora, estado y mensajes de etapa disponibles. Los filtros
rapidos son **Todas**, **Pendientes**, **Sin contacto** y **Enviados**; un unico
selector ordena por cita mas proxima, cita mas lejana, nombre o estado.

En **Necesitan revision** e **Historial**, la busqueda conserva nombre, orden,
documento enmascarado, placa, expediente, sede, resultado y mensajes. El orden
se presenta como una sola eleccion comprensible: mas urgente, cita mas proxima,
actualizado recientemente o nombre. Los filtros tecnicos, IDs y recorrido
completo quedan secundarios respecto de fecha, persona, estado y siguiente
accion. **Necesitan revision** presenta como filtros rapidos **Todos**,
**Requieren atencion**, **Con observacion** y **Con avance**.

### Configuracion visual separada

El boton **Configurar recordatorios** abre un dialogo independiente del listado:

1. **Anticipacion** usa tres radios visibles: 1, 2 o 3 dias antes.
2. **Modo de operacion** ofrece Desactivado, Solo revisar, Prueba controlada y
   Activo. Prueba controlada limita la seleccion a una o dos citas elegibles de
   la fecha objetivo.
3. El dialogo muestra con fechas concretas que citas se prepararan, enlaza a
   **Mensajes** para editar el texto y exige confirmacion adicional al activar
   Prueba controlada o Activo.
4. El pie informa la revision vigente y que los trabajos ya creados conservan
   su programacion. Un conflicto `409` mantiene el contrato de relectura antes
   de volver a guardar.
5. La navegacion mantiene tabs reales con `aria-selected`, filtros con
   `aria-pressed`, radios nativos y un `dialog` modal. El build no sustituye la
   revision visual humana en `360`, `768`, `1024` y `1440 px`.
