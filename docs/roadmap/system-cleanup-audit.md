# Plan integral de limpieza y alineacion del sistema

Fecha de la auditoria base: `2026-08-29`.

Este documento concentra los hallazgos de la revision completa de codigo,
dashboard, PostgreSQL, runtime, documentacion, artefactos y reportes. Su objetivo
es permitir ejecutar la limpieza mas adelante, en orden y sin volver a descubrir
todo desde cero.

La prioridad oficial sigue viviendo en [`README.md`](README.md). Este archivo es
el detalle operativo de la tarea de limpieza: no reemplaza el estado actual de
[`../project-status.md`](../project-status.md), los contratos ni los runbooks.

## Aceptacion pendiente despues del commit `ab91372`

Ventana de observacion: `2026-08-31` a `2026-09-06`, zona `America/Lima`.

Este es un checklist temporal para que el usuario valide la limpieza en uso
real. No crear reservas, citas ni mensajes artificiales para completarlo. Las
mediciones tecnicas y los umbrales exactos se encuentran en
[`../operations/current-only-observation.md`](../operations/current-only-observation.md).

### Lo que debe revisar el usuario

- [ ] **Uso diario general:** abrir Pendientes, Resumen, Ordenes, Actividad,
  Citas y recordatorios, Finanzas y Mensajes; confirmar que cargan sin errores
  nuevos ni datos evidentemente ausentes.
- [ ] **Ordenes:** buscar una orden, abrir su detalle y comprobar que filtros,
  acciones y paginacion siguen funcionando. No modificar una orden solo para
  probar.
- [ ] **Citas y recordatorios:** comprobar proximas citas, casos en revision e
  historial; cambiar busqueda, filtro, orden y tamaño de pagina. Confirmar que
  los controles de paginacion no desaparecen al cambiar de vista.
- [ ] **Finanzas:** abrir el mes actual y confirmar que resumen, movimientos y
  calidad cargan. La UI debe usar `conversion_complete` sin mostrar un error por
  la eliminacion de `is_complete`.
- [ ] **Telegram:** usarlo normalmente durante la semana y confirmar que
  responde, que el estado del worker es coherente con el dashboard y que no
  aparecen alertas falsas o duplicadas del monitor anterior.
- [ ] **Postpago natural:** cuando ocurra el siguiente caso real, comprobar que
  el texto no esta vacio, que conserva Reserva y Sede cuando corresponden y que
  los PDF mantienen el orden contractual. No reenviar si el resultado queda
  `uncertain`.
- [ ] **WhatsApp restante:** observar el siguiente album, aviso de registro,
  recordatorio y cierre diario que ocurran naturalmente. Distinguir preparado,
  `sent`, confirmacion tecnica y lectura del destinatario.
- [ ] **Reinicio real:** despues del proximo reinicio normal de Windows,
  comprobar que PostgreSQL, Admin API, worker, dashboard y Telegram se recuperan
  sin iniciar propietarios duplicados.
- [ ] **Diagnostico copiado:** usar una vez la opcion de copiar diagnostico y
  confirmar visualmente que el JSON no contiene identidad, contacto,
  credenciales, DOM, rutas locales ni datos sin enmascarar.
- [ ] **Ausencia de regresiones:** registrar hora, pantalla y accion exactas de
  cualquier error nuevo; no restaurar el backup ni reactivar n8n antes de
  demostrar que el fallo depende de este commit.

### Lo que debe comprobarse tecnicamente al cerrar la semana

- [ ] Admin API `8766`, PostgreSQL y worker permanecieron saludables.
- [ ] `AppointmentBotMonitor` de n8n siguio inactivo y no reaparecio su sondeo
  periodico a `8765`.
- [ ] `GET /api/v1/monthly-summary` no tuvo consumidores; su retiro puede
  ejecutarse desde el `2026-09-04`.
- [ ] No hubo consumidores reales de la lista de ordenes sin
  `projection=dashboard` ni de post-cita sin parametros. Si aparece alguno,
  debe migrarse y reiniciarse su ventana de observacion.
- [ ] `8765` no recibio accesos naturales durante siete dias; los chequeos
  manuales se separaron del trafico real.
- [ ] PostgreSQL sigue en `v70`, todos los paquetes postpago conservan
  `message_text` y no se crearon reintentos ambiguos como efecto de la limpieza.
- [ ] Pasan `compileall`, Ruff, las pruebas existentes, build Angular, validador
  documental y `git diff --check`.

### Cuando se considera valido todo el proceso

El cierre solo es valido cuando todas las casillas anteriores aplicables estan
marcadas, no existe una regresion atribuible a la limpieza y las superficies
antiguas cumplen sus umbrales de cero consumidores. Un flujo natural que no
ocurra durante la semana no debe marcarse como probado: permanece en
[`README.md`](README.md) como aceptacion pendiente, pero no bloquea retirar una
compatibilidad distinta cuya ausencia de consumidores si fue demostrada.

### Destino de este archivo

Si, este archivo debe eliminarse despues del cierre final; no debe convertirse
en otra bitacora permanente. La secuencia es:

1. retirar las compatibilidades externas que hayan cumplido el umbral;
2. actualizar `project-status.md` y los contratos con el estado resultante;
3. conservar en `roadmap/README.md` solamente flujos o riesgos aun pendientes;
4. ejecutar la validacion documental y tecnica final;
5. eliminar `system-cleanup-audit.md` y el runbook temporal
   `operations/current-only-observation.md`, corrigiendo sus enlaces.

Git conserva esta auditoria, sus resultados y su rollback. No se necesita crear
otro Markdown para archivarla ni copiar su cronologia a `docs/history/`.

## Como usar este documento

1. No ejecutar todos los pasos en un solo cambio.
2. Revalidar cada hallazgo antes de modificarlo: esta auditoria es una fotografia
   del `2026-08-29` y el runtime puede haber cambiado.
3. Completar los pasos en el orden indicado. Los primeros corrigen la fuente de
   verdad; los ultimos reducen deuda y espacio.
4. Hacer commits separados por dominio para conservar rollback sencillo.
5. No marcar un paso como cerrado solo porque compila: aplicar su criterio de
   cierre y su validacion especifica.
6. No modificar `.env`, reiniciar servicios, migrar PostgreSQL, enviar WhatsApp
   ni crear pruebas automatizadas sin la autorizacion que corresponda.

## Resultado general de la auditoria

El sistema no contiene un subsistema grande completamente abandonado. Las ocho
rutas canonicas del dashboard, los procesos principales, las tablas con mayor
volumen y los contratos centrales tienen consumidores reales. La deuda se
concentra en cinco grupos:

1. codigo publicado que aun no coincidia con el runtime observado;
2. funciones, aliases, señales, estilos y archivos pequeños sin consumidores;
3. superficies de compatibilidad que necesitan medir trafico antes de retirarse;
4. documentacion mayormente valida, pero con afirmaciones desactualizadas,
   duplicacion y contratos faltantes;
5. evidencia generada que sigue activa, pero crece sin rotacion eficiente.

## Evidencia y limites de la auditoria

Se contrastaron:

- `docs/project-status.md` y `docs/roadmap/README.md`;
- referencias estructurales con CodeGraph y busquedas de simbolos;
- imports y referencias en Python, TypeScript y templates Angular;
- rutas HTTP, entrypoints y configuracion;
- procesos de Windows y estado PostgreSQL en modo de solo lectura;
- volumen y referencias de tablas operativas;
- documentacion activa, reportes generados, enlaces y archivos grandes;
- historial Git necesario para entender compatibilidad y procedencia.

CodeGraph se uso como mapa de dependencias. No demuestra por si solo que una
funcion sea segura, que un endpoint no tenga consumidores externos o que el
runtime desplegado coincida con Git.

No se realizaron durante la auditoria:

- borrados, migraciones, reinicios ni despliegues;
- envios o reintentos de WhatsApp;
- cambios en `.env`;
- cambios de datos de clientes;
- pruebas naturales que requieran una cita, reserva o mensaje real.

## Fotografia comprobada que debe refrescarse

### Git y despliegue

En el corte de la auditoria:

- rama: `codex/observer-multiclient-flow`;
- commit publicado: `177c70b Promote validated canaries to stable runtime`;
- el working tree estaba limpio;
- el codigo declaraba `SCHEMA_VERSION = 68`;
- PostgreSQL seguia en esquema `v67`;
- los procesos Worker, Admin API y Telegram habian arrancado antes del ultimo
  commit, por lo que el codigo publicado aun no estaba desplegado.
- el control de recordatorios seguia en modo `live` con
  `canary_order_ids = []`, columna que la migracion v68 elimina;
- los dos controles de oportunidad observados estaban en `inherit/inherit` y el
  circuit breaker estaba cerrado.

Consecuencia: `docs/project-status.md` describia correctamente el objetivo
publicado en Git, pero no el runtime que estaba ejecutandose. El siguiente
arranque con el codigo actual intentaria migrar de `v67` a `v68`.

Antes de reutilizar esta conclusion, volver a comprobar Git, procesos,
`schema_version`, trabajos WhatsApp, submissions, leases, sesiones y rafagas.

### Volumen de tablas observado

Estos conteos prueban uso historico; no prueban que cada API asociada siga
teniendo consumidores actuales.

| Tabla o dominio | Filas observadas |
|---|---:|
| `runs` | 9,509 |
| `order_checks` | 76,887 |
| `opportunity_bursts` | 43 |
| `opportunity_burst_candidates` | 170 |
| `opportunity_burst_executions` | 125 |
| `slot_lost_reobservation_events` | 323 |
| `post_appointment_reviews` | 260 |
| `post_appointment_stage_snapshots` | 1,440 |
| `whatsapp_automation_jobs` | 474 |
| `whatsapp_followup_messages` | 171 |
| `whatsapp_messages` | 184 |
| `reservations` | 218 |
| `reservation_attempts` | 383 |
| `service_orders` | 227 |

Tablas con cero filas que **no deben declararse huerfanas solo por el conteo**:

- `captcha_shadow_outbox`: capacidad opcional;
- `post_appointment_automatic_reviews`: scheduler aun sin uso natural esperado;
- `finance_month_closures`: depende del cierre mensual;
- `payment_amount_reconciliations`: depende de diferencias conciliables.

## Elementos que no se deben borrar por falso positivo

- `worker/queue_traversal.py`: se configura dinamicamente desde
  `queue_runtime.py`.
- `mark_burst_execution_started` y `mark_burst_execution_finished`: se invocan
  mediante `getattr`.
- entrypoints de `pyproject.toml`: son puntos de ejecucion aunque no tengan
  imports ordinarios.
- `_legacy_combined_followup_text`: permite leer filas historicas sin traza de
  plantilla.
- migraciones `14..68`: siguen siendo necesarias mientras no exista una politica
  formal de baseline y restauracion.
- `pdfs/Formato_Tramite_Ejemplo.pdf`: 68 mensajes historicos enviados aun lo
  referenciaban en el corte de la auditoria.
- PDFs originales bajo `pdfs/`: el paquete actual los referencia directamente y
  `ORIGINAL_DOCUMENT_ROOT` conserva ese contrato.
- `scripts/verify-postgres-backup.ps1`: no tiene backlinks suficientes, pero es
  util para la tarea pendiente de backup y restore; debe documentarse.
- las ocho rutas del dashboard y el alias `/post-cita`: las primeras son activas
  y el alias es compatibilidad deliberada.

## Orden de ejecucion

## Paso 0 - Crear una nueva linea base

Objetivo: evitar ejecutar una limpieza con evidencia vieja.

- [x] Confirmar rama, commit, upstream y working tree.
- [x] Leer completos `docs/project-status.md` y `docs/roadmap/README.md`.
- [x] Consultar la version real de PostgreSQL.
- [x] Registrar hora de inicio de Worker, Admin API y Telegram.
- [x] Comprobar salud de `8765`, `8766` y los servicios auxiliares aplicables.
- [x] Consultar trabajos WhatsApp activos o ambiguos.
- [x] Consultar submissions, leases, sesiones Playwright y rafagas activas.
- [x] Repetir conteos relevantes de tablas y tamaño de artefactos.
- [x] Repetir busquedas de referencias de cada candidato antes de borrarlo.

### Registro de ejecucion del Paso 0

Corte de la comprobacion: `2026-08-29 07:24-07:28 America/Lima`.

- Git estaba en `codex/observer-multiclient-flow`, commit `177c70b`, con
  upstream `0/0`. En ese corte, los unicos cambios locales eran este plan y su
  enlace desde el roadmap.
- El codigo declaraba esquema `v68`, pero PostgreSQL continuaba en `v67`.
- Runtime, Worker, Admin API y Telegram habian arrancado entre `00:55` y
  `00:57`; el commit se creo a las `06:30`, por lo que los procesos cargados
  eran anteriores al codigo publicado.
- PostgreSQL estaba saludable. `8765` respondia `200` con worker activo y
  `8766` respondia `200` en modo `api_only`. `8787` no escuchaba porque CAPTCHA
  shadow estaba deshabilitado.
- Telegram mantenia el proceso vivo y habia iniciado long polling.
- El worker estaba en monitoreo, con una orden actual, lease del worker, una
  orden reclamada y una sesion Playwright activa. No habia sesiones manuales.
- No habia submissions `intent` o `pending`; persistia un intento historico
  `unknown` del `2026-07-03` que requiere conciliacion independiente.
- No habia rafagas, comandos de worker ni lotes automaticos post-cita activos.
- WhatsApp tenia `0 running`, `0 queued` y `0 blocked`; conservaba `49 uncertain`,
  de los cuales `40` no tenian revision. Son historicos terminales y no deben
  reintentarse automaticamente.
- El control de recordatorios estaba `live`, con `lead_days=2`, revision `11` y
  lista canaria vacia. Oportunidades seguia `inherit/inherit` con breaker
  cerrado.
- Los conteos principales se refrescaron: `9,528 runs`, `77,174 order_checks`,
  `43 opportunity_bursts`, `474 whatsapp_automation_jobs`, `218 reservations`,
  `383 reservation_attempts` y `227 service_orders`.
- Los tamaños de los candidatos y de la evidencia coincidian con la fotografia
  documentada: `reports/` tenia `20` archivos y `1,711,329` bytes.
- Las busquedas repetidas confirmaron el mismo conjunto de candidatos backend,
  frontend, configuracion, compatibilidad y artefactos. No se borro ninguno.

Resultado: **Paso 0 completado**. El Paso 1 no era seguro en ese corte porque el
worker estaba monitoreando y el runtime seguia en `v67`; desplegar o reiniciar
requiere una ventana sin leases, sesiones ni trabajo activo.

Criterio de cierre: existe una nota fechada con Git, esquema, procesos y trabajo
activo; las diferencias frente a esta auditoria estan identificadas.

## Paso 1 - Alinear codigo publicado, esquema y runtime

Riesgo: alto. Este paso puede ejecutar la migracion `67 -> 68` y afectar procesos
persistentes. No mezclarlo con eliminacion de codigo.

- [x] Verificar que no haya envios, submissions, leases, sesiones, rafagas ni
  lotes de recordatorios/post-cita en ejecucion.
- [x] Revisar el contenido exacto de la migracion `v68`.
- [x] Confirmar backup verificable antes de migrar o, si la migracion ya ocurrio,
  documentar la evidencia disponible y validar la recuperabilidad actual.
- [x] Desplegar o reiniciar mediante el runbook vigente.
- [x] Confirmar `schema_version = 68` despues del arranque.
- [x] Confirmar que `appointment_reminder_control.canary_order_ids` ya no exista.
- [x] Confirmar modos y breakers persistidos despues de la migracion.
- [x] Verificar salud de Worker, Admin API, Telegram y perfil WhatsApp.
- [x] Observar logs del primer ciclo sin provocar reservas ni mensajes de prueba.
- [x] Corregir `docs/project-status.md` para distinguir estado publicado y estado
  desplegado si aun no coinciden.

### Registro de ejecucion del Paso 1

Corte de la comprobacion: `2026-08-30 10:13-10:16 America/Lima`.

- Git permanecia en `codex/observer-multiclient-flow`, commit publicado
  `177c70b`. Los cambios locales previos se preservaron y no se mezclo ninguna
  eliminacion de codigo con esta comprobacion.
- El reinicio natural de Windows ya habia levantado la topologia mediante los
  supervisores del runbook entre `09:56` y `09:59`, antes de iniciar esta
  ejecucion. No se provoco un segundo reinicio innecesario.
- La migracion `67 -> 68` solo promueve `inherit` a `enabled` en los controles
  de rafagas y reobservacion, sustituye el modo de recordatorios `canary` por
  `live`, restringe los valores persistibles a los modos estables y elimina
  `appointment_reminder_control.canary_order_ids`. Todo ocurre dentro de la
  transaccion y lock de migracion existentes.
- La migracion ya habia ocurrido antes de esta comprobacion. No existe en el
  repositorio un dump conservado que permita demostrar retroactivamente un
  backup anterior a ella. Como control compensatorio, se ejecuto
  `scripts/verify-postgres-backup.ps1`: creo un dump temporal del estado `v68`,
  lo restauro en una base aislada, comparo `service_orders`, `runs`,
  `reservations`, `reservation_attempts` y `payments`, y termino sin conservar
  el dump.
- PostgreSQL confirmo `schema_version = 68` y cero columnas
  `canary_order_ids`. Oportunidades quedo en `enabled/enabled`, revision
  aplicada `0/0` y breaker `closed`; recordatorios quedo en `live`,
  `lead_days=2`, revision `11`.
- Antes de cualquier accion se comprobaron cero leases de orden, cero leases
  WhatsApp, cero sesiones manuales, cero rafagas o ejecuciones abiertas y cero
  lotes post-cita reclamados. El worker estaba `outside_hot_window`, sin orden
  actual. El intento historico `unknown` y los `49 uncertain` de WhatsApp se
  conservaron sin reintento ni conciliacion.
- Worker respondio como activo mediante Admin API, `8765` y `8766` respondieron
  salud `200`, Telegram valido el bot autorizado e inicio long polling, y el
  endpoint local de solo validacion de WhatsApp devolvio `session_ready`. No se
  selecciono destinatario ni se preparo o envio contenido.
- Los logs del primer ciclo muestran al worker esperando fuera de ventana, al
  dispatcher y schedulers iniciados y a Telegram conectado. Los errores
  transitorios de Telegram anteriores a `09:59` correspondieron a la espera de
  Admin API; el supervisor recupero el servicio sin intervencion.
- `docs/project-status.md` ya declaraba esquema `v68` y coincide con Git,
  procesos, API y PostgreSQL, por lo que no requirio edicion.

Resultado: **Paso 1 completado**. La recuperabilidad del estado actual quedo
verificada; la ausencia de evidencia previa a la migracion se conserva como
limite historico y no se presenta como un backup pre-migracion confirmado.

Rollback: seguir el runbook y la estrategia de backup; no improvisar una
migracion inversa ni restaurar mientras existan escrituras posteriores sin
conciliar.

Criterio de cierre: Git, procesos, API, PostgreSQL y documentacion declaran la
misma version; no hay trabajo ambiguo creado por el despliegue.

## Paso 2 - Corregir verdad documental inmediata

Riesgo: bajo. Realizar despues de conocer el runtime real.

- [x] `docs/project-status.md`: declarar solo el esquema realmente desplegado o
  mostrar explicitamente la diferencia temporal frente al codigo publicado.
- [x] `reports/optimization/latest.md`: cambiar “Decision actual” por “Decision
  al corte” y tratarlo como baseline fechado. El texto antiguo de “sin cambios
  funcionales” contradice la promocion estable posterior y su propio encabezado.
- [x] `reports/operations/latest.md`: retirar la afirmacion de que la mejora aun
  vive en roadmap y corregir “Sin alertas” cuando el mismo reporte registra dos
  defensas.
- [x] `docs/evidence-summary.md` y su generador: agregar `generated_at`, rango,
  cobertura y limites. El archivo generado no debe parecer estado vivo.
- [x] `docs/contracts/whatsapp.md`: identificar la autoridad exacta del paquete
  y orden de PDFs. En el corte, la autoridad efectiva era
  `.runtime/whatsapp-followup/followup-details.json`, no un contrato escrito.
- [x] `docs/README.md`: retirar “reportes de negocio” de `reports/` mientras no
  exista ese dominio o crear una ubicacion real si se decide conservarlo.
- [x] `docs/contracts/reservation-safety.md`: agregar estado, ultima verificacion
  y responsable.
- [x] `docs/contracts/finance.md`: agregar estado, ultima verificacion y
  responsable.

### Registro de ejecucion del Paso 2

Corte de la comprobacion: `2026-08-30 10:20-10:27 America/Lima`.

- `docs/project-status.md` ya declaraba el esquema desplegado `v68`, confirmado
  en el Paso 1, por lo que no requirio una segunda edicion.
- Los dos `latest.md` quedaron identificados como cortes historicos: optimizacion
  usa `Decision al corte` y operacion reconoce las dos defensas observadas sin
  afirmar que la correccion sigue pendiente en el roadmap.
- El generador de evidencia ahora escribe fecha de generacion, ventana solicitada
  cuando aplica, rango real, cobertura temporal y limites. El snapshot vigente
  se regenero desde el indice sanitizado: `2,699/2,699` eventos tienen hora de
  cierre y cubren del `2026-06-30 08:27:37` al `2026-08-29 12:00:24` en Lima.
- El contrato WhatsApp declara que `.runtime/whatsapp-followup/followup-details.json`
  gobierna seleccion y orden de paquetes futuros, exige originales bajo `pdfs/`
  y congela la lista preparada en PostgreSQL. El orden verificado es
  `Formato_Tramite.pdf`, `requisitos.pdf`, `Formato_Tramite_Ejemplo.pdf`.
- `docs/README.md` ya no atribuye un dominio de negocio inexistente a `reports/`.
  Los contratos de reserva y finanzas indican estado, ultima verificacion y
  responsable por codigo propietario.
- No se modifico runtime, PostgreSQL, `.env`, clientes, reservas ni trabajos
  WhatsApp. No se agregaron pruebas nuevas; se extendio la prueba existente del
  generador para cubrir los metadatos nuevos.
- Validaciones: `compileall`, Ruff, `59 passed`, validador documental y
  `git diff --check`.

Resultado: **Paso 2 completado**. Los snapshots activos declaran su corte y
limites, y los contratos afectados identifican autoridad y verificacion.

Validacion:

```powershell
powershell -ExecutionPolicy Bypass -File scripts/check-documentation.ps1
git diff --check
```

Criterio de cierre: ningun documento activo presenta un snapshot como runtime
actual y todos los contratos indican autoridad y fecha de verificacion.

## Paso 3 - Retirar codigo backend sin consumidores

Riesgo: medio. Confirmar con busqueda textual, CodeGraph y pruebas existentes.
Eliminar en grupos pequeños.

### Grupo A - Funciones y estado sin referencias

- [x] `src/appointment_bot/flows/__init__.py`: paquete vacio sin referencias;
  eliminar solo si el empaquetado no necesita conservar el paquete.
- [x] `browser/whatsapp_web.py::_outgoing_image_message_states`: estado antiguo
  reemplazado por el camino basado en registros.
- [x] `db/appointment_reminders.py::get_appointment_reminder_batch_day`: helper
  sin consumidor.
- [x] `services/appointment_reminders.py::validate_reminder_template`: wrapper
  sin consumidor; la validacion vigente esta centralizada.
- [x] `utils/screenshots.py::archive_unique_slot_screenshot`: wrapper singular;
  el camino plural es el activo.
- [x] `db/whatsapp_followup_messages.py::_configured_followup_documents`: helper
  sin consumidor.

#### Registro de ejecucion del Grupo A

Corte de la comprobacion: `2026-08-30 10:30-10:36 America/Lima`.

- Se retiraron los seis candidatos, sus imports sobrantes y las dos entradas
  publicadas solo mediante `__all__`. `flows/` no contenia modulos ni tenia
  consumidores o entrypoints, por lo que el paquete vacio no era necesario.
- WhatsApp conserva `_outgoing_image_message_records`, que identifica cada
  imagen y su estado. Recordatorios conserva el congelamiento atomico mediante
  `ensure_appointment_reminder_batch_day` y la validacion central de plantillas.
- Screenshots conserva `archive_unique_slot_screenshots`, llamado por
  `record_run_history`, y `archive_unique_slot_capture`, usado inmediatamente
  por monitor y observer. Una primera retirada demasiado amplia del camino
  plural fallo durante la coleccion de pruebas; se restauro antes del resultado
  final y no alcanzo runtime ni Git publicado.
- Postpago conserva la lista ordenada de `.runtime` y la validacion de originales
  bajo `pdfs/`; solo se retiro el helper basado en `set` que no tenia llamadas.
- Las busquedas finales confirmaron cero imports, `__all__`, mocks o accesos
  dinamicos a los simbolos eliminados.
- No se modificaron PostgreSQL, `.env`, PDF, reservas, trabajos WhatsApp ni
  procesos en ejecucion. No fue necesario ningun paso manual o reinicio.
- Validaciones finales: `compileall`, Ruff, `59 passed`, validador documental y
  `git diff --check`.

Resultado: **Grupo A completado**. El Paso 3 permanece abierto para los grupos B
y C.

### Grupo B - Aliases y utilidades de oportunidad

- [x] `db/opportunity_controls.py::mark_applied`.
- [x] `db/opportunity_controls.py::open_opportunity_circuit_breaker`.
- [x] `db/opportunity_bursts.py::mark_burst_execution_first_check`.
- [x] `db/opportunity_bursts.py::close_opportunity_burst`.
- [x] `db/opportunity_bursts.py::persist_obs007_events_from_report`.

#### Registro de ejecucion del Grupo B

Corte de la comprobacion: `2026-08-30 America/Lima`.

- Se retiraron los cuatro aliases o wrappers sin consumidores y el importador
  retrospectivo de eventos OBS-007. Tambien se eliminaron su import y dos
  auxiliares privados que quedaron sin uso.
- Se conservaron las funciones vigentes: `mark_opportunity_control_applied`,
  `trip_opportunity_circuit_breaker`, `update_burst_execution`,
  `finish_opportunity_burst` y `record_burst_event`.
- El worker sigue marcando directamente la primera lectura y finalizando cada
  rafaga. Worker y monitor mantienen el cortacircuitos, y el monitor conserva el
  registro en vivo de cada evento OBS-007.
- No se modificaron esquema ni datos de PostgreSQL, controles activos,
  configuracion, reservas, WhatsApp o procesos en ejecucion. No se requirieron
  migraciones, reinicios ni pasos manuales.
- Validaciones finales: `compileall`, Ruff, `59 passed`, validador documental y
  `git diff --check`.

Resultado: **Grupo B completado**. El Paso 3 permanece abierto para el Grupo C.

### Grupo C - Fallbacks imposibles

- [x] Simplificar en `worker/opportunity_burst.py` los fallbacks hacia los
  nombres inexistentes `mark_started`, `mark_finished` y `finish_burst`.

#### Registro de ejecucion del Grupo C

Corte de la comprobacion: `2026-08-30 11:00 America/Lima`.

- Los nombres canonicos y los supuestos aliases nacieron en el mismo cambio;
  los aliases nunca existieron en `db/opportunity_bursts.py`.
- Se sustituyeron los tres accesos dinamicos por imports locales directos de
  `mark_burst_execution_started`, `mark_burst_execution_finished` y
  `finish_opportunity_burst`.
- Se comprobaron los caminos de inicio del detector y auxiliares, cierre de
  ejecuciones y cierre del coordinador. La suite actual no contiene mocks ni
  dobles especificos para esos nombres.
- No cambiaron argumentos, estados persistidos, limites de concurrencia,
  cortacircuitos, reservas ni comportamiento ante resultados ambiguos.
- Validaciones finales: importacion directa de los modulos, `compileall`, Ruff,
  `59 passed`, validador documental y `git diff --check`.

Validacion minima por grupo:

```powershell
python -m compileall -q src
python -m ruff check src tests
python -m pytest -q
git diff --check
```

Criterio de cierre: no quedan imports, `__all__`, mocks ni accesos dinamicos a los
simbolos retirados; rafagas, recordatorios, screenshots y WhatsApp conservan su
comportamiento.

Resultado: **Paso 3 completado**. Los Grupos A, B y C quedaron cerrados.

## Paso 4 - Limpiar configuracion deprecada o engañosa

Riesgo: medio. Revisar despliegues externos y archivos de entorno antes de
retirar nombres publicos.

- [x] `appointment_reminders_enabled` / `APPOINTMENT_REMINDERS_ENABLED`: se
  cargan, pero no se leen; el control real vive en PostgreSQL.
- [x] `appointment_reminders_dry_run` / `APPOINTMENT_REMINDERS_DRY_RUN`: se
  cargan, pero no se leen; el modo real vive en PostgreSQL.
- [x] `session_rotation_seconds` / `SESSION_ROTATION_SECONDS`: se carga, pero no
  tiene consumidor.
- [x] `continuous_interval_min_seconds`: solo participa en validacion de
  configuracion; no controla esperas.
- [x] `continuous_interval_max_seconds`: se renombro como
  `worker_progress_grace_seconds`; su ENV canonico es ahora
  `WORKER_PROGRESS_GRACE_SECONDS`.
- [x] Campo `Settings.evidence_profile`: es redundante despues de construir los
  settings. Conservar el ENV `EVIDENCE_PROFILE`, porque si deriva configuracion
  funcional de video y screenshots.
- [x] Retirar el fallback `OBSERVER_SITE_TOGGLE_INTERVAL_SECONDS`: el despliegue
  local, el ejemplo y los consumidores usan las variantes `MIN` y `MAX`.

Del `.env` local se retiraron las claves ignoradas autorizadas:

- `ORDER_RULE_COOLDOWN_SECONDS`;
- `OPPORTUNITY_BURST_ENABLED`.

Tambien se retiraron `SESSION_ROTATION_SECONDS` y
`CONTINUOUS_INTERVAL_MIN_SECONDS`, y se migro
`CONTINUOUS_INTERVAL_MAX_SECONDS=55` a `WORKER_PROGRESS_GRACE_SECONDS=55`.
`EVIDENCE_PROFILE` y los intervalos `MIN/MAX` del observer se conservaron.

#### Registro de ejecucion del Paso 4

Corte de la comprobacion: `2026-08-30 America/Lima`.

- El unico arranque externo local identificado es la tarea programada
  `AppointmentBotContinuousWorker`, que inicia `scripts/start-runtime.pyw` y los
  procesos del mismo repositorio. Los scripts no consumen los nombres retirados.
- Recordatorios y rafagas conservan sus controles persistidos en PostgreSQL;
  eliminar flags ignorados no cambia esos modos ni el cortacircuitos.
- El margen de salud conserva el valor efectivo `55` y el calculo de estancamiento
  permanece igual. No se modificaron esperas del observer ni reintentos de sesion.
- `.env.example` describe solamente opciones con efecto real. El `.env` local se
  limpio por autorizacion explicita y permanece fuera de Git.
- No se reiniciaron procesos ni se modificaron datos, reservas, trabajos
  WhatsApp o comandos operativos.
- Validaciones finales: carga aislada de configuracion y perfiles, consulta de
  controles persistidos, `compileall`, Ruff, `59 passed`, validador documental y
  `git diff --check`.

Criterio de cierre: cada variable documentada cambia comportamiento real; los
nombres conservados describen su uso y no existen flags que aparenten gobernar
controles persistidos.

Resultado: **Paso 4 completado**.

## Paso 5 - Auditar y retirar superficies de compatibilidad

Riesgo: alto porque las referencias externas no aparecen en el repositorio.

### API mensual v1

Hallazgo:

- el dashboard usa exclusivamente `GET /api/v2/monthly-summary`;
- `AppointmentApiService.getMonthlySummary()` y `MonthlySummary` v1 no tienen
  consumidores internos;
- backend aun sirve `GET /api/v1/monthly-summary` desde `local_api.py`, rutas y
  consultas asociadas;
- la documentacion aun declara v1 y v2.

Secuencia:

- [x] Medir logs de acceso durante una ventana representativa.
- [x] Revisar n8n, scripts, proxies y clientes externos.
- [x] Marcar v1 como deprecada con fecha y alternativa v2.
- [ ] Mantener una ventana de compatibilidad acordada.
- [x] Retirar metodo e interfaz frontend v1.
- [ ] Retirar ruta, payload y consulta backend v1.
- [x] Actualizar contrato Admin API y documentacion.

### API embebida del Worker en `8765`

Hallazgo: el servicio se inicia siempre, mientras la operacion normal usa Admin
API `8766`. La documentacion conserva `8765` como rollback.

- [x] Medir trafico y revisar n8n, proxy, scripts y monitores externos.
- [x] Confirmar si alguna recuperacion depende realmente de `8765`.
- [ ] Si no tiene consumidores, primero deshabilitarlo de forma reversible.
- [ ] Observar una ventana operativa completa.
- [ ] Retirar el servidor y actualizar topologia/runbooks solo al final.

### Registro de ejecucion parcial del Paso 5

Corte de la comprobacion: `2026-08-30 11:18-11:41 America/Lima`.

- Los logs del `2026-08-16` al `2026-08-30` registraron cero accesos al resumen
  mensual v1 y `619` al v2. No aparecieron consumidores v1 en dashboard,
  scripts, proxy ni los cuatro workflows n8n.
- Se retiro del frontend el metodo y la interfaz v1. El endpoint backend conserva
  por ahora el mismo JSON, registra cada acceso y emite `Deprecation`, `Sunset`
  y enlace a v2. La compatibilidad termina al cierre del `2026-09-03`; el retiro
  puede ejecutarse desde el `2026-09-04`.
- `8765` recibio `1,829` solicitudes en la misma ventana: `1,805` fueron
  revisiones `/health` del workflow n8n activo. Por tanto no estaba sin
  consumidores y no se apago.
- Telegram Control incorpora el reemplazo nativo: consulta autenticadamente
  `/api/v1/worker` cada cinco minutos entre `07:30` y `18:00`, alerta tras tres
  fallos y no reinicia. Se activo localmente, se reinicio solo ese proceso y su
  primera revision confirmo salud del worker.
- Los cuatro workflows se exportaron a
  `.runtime/n8n-backup-20260830T1140/`. El contenedor y el volumen permanecen
  intactos y el monitor anterior sigue activo durante la comparacion.
- Se agrego `WORKER_EMBEDDED_API_ENABLED` para que el apagado posterior sea
  reversible. Permanece `true` mientras n8n observa `8765`.
- Al corte no habia sesiones manuales ni rafagas activas; worker, `8765`, `8766`,
  Telegram y n8n permanecian operativos.

Resultado: **Paso 5 en observacion**. No borrar el backend v1 antes del
`2026-09-04`, ni detener n8n o `8765` antes de completar una jornada operativa
sin diferencias entre ambos monitores.

Actualizacion `2026-08-30 16:51-17:03 America/Lima`:

- el workflow `AppointmentBotMonitor` se exporto antes y despues del cambio en
  `.runtime/n8n-backup-current-only-20260830T165103/`, se desactivo y n8n
  reinicio saludable;
- el ultimo sondeo periodico de n8n a `8765` fue a las `16:50:15`; Telegram
  continuo validando el worker por Admin API cada cinco minutos;
- `8765` permanece habilitado solo como rollback durante la ventana semanal;
- el runtime retiro el alias financiero `is_complete`, un wrapper Python sin
  consumidores y la reconstruccion postpago; la migracion `v70` congelo el
  texto de `142` paquetes historicos y dejo cero textos vacios;
- las respuestas sin `projection` de ordenes y sin query de post-cita tuvieron
  uso reciente y permanecen bajo medicion, no se retiraron a ciegas.

Resultado actualizado: **Paso 5 sigue en observacion externa**. La deuda interna
ya fue retirada; quedan solo fronteras con posible consumidor externo y fecha
de corte documentada.

Criterio de cierre: existe evidencia de cero consumidores externos durante la
ventana acordada y hay rollback documentado.

## Paso 6 - Resolver persistencia legacy de recordatorios

Riesgo: alto por historia y trazabilidad.

- [x] Auditar las seis filas observadas en
  `appointment_reminder_template_versions`.
- [x] Comparar revisiones antiguas con `whatsapp_message_template_versions`.
- [x] Preservar contenido historico distinto, especialmente revision 1.
- [x] Diseñar archivo o migracion explicita; no borrar la tabla directamente.
- [x] Evaluar la columna duplicada
  `appointment_reminder_control.message_template`: el runtime usa la plantilla
  unificada y no se encontro consumidor funcional de esa copia.
- [x] Retirar columna y tabla legacy solo en una migracion nueva, con validacion
  de trazas historicas.
- [x] Confirmar que reportes y trabajos congelados siguen renderizando la
  revision que les corresponde.

### Registro de ejecucion del Paso 6

Corte de la comprobacion: `2026-08-30 11:43-12:03 America/Lima`.

- La tabla legacy contenia seis revisiones. Las revisiones 2 a 6 ya coincidian
  exactamente con la autoridad unificada; la revision 1 conservaba el unico
  texto historico que decia "manana" y no tenia trabajos que la referenciaran.
- La migracion `v69` sustituyo la revision 1 unificada por el texto, fecha y
  autor historicos, valido las seis revisiones dentro de la misma transaccion y
  solo entonces retiro la tabla legacy y la columna duplicada del control.
- `AppointmentReminderControl` conserva modo, anticipacion, revision operativa,
  fecha y actor. El texto vigente se lee exclusivamente desde
  `whatsapp_message_templates`; no se mezclo la revision del control `11` con
  la revision de plantilla `6`.
- Los `44` trabajos de recordatorio enviados conservan texto congelado: `34`
  anteriores a la traza de plantilla y `10` con revision `6`. No existen textos
  vacios ni referencias a versiones ausentes.
- Antes del despliegue se guardo un respaldo local en
  `.runtime/step6-reminder-schema-v68-20260830.sql`. La migracion se valido
  primero sobre una copia temporal de PostgreSQL, eliminada despues de la
  comprobacion.
- No habia orden, lease de orden, sesion manual, rafaga, trabajo WhatsApp,
  recordatorio o revision post-cita activos. Admin API y worker se reiniciaron;
  el worker respeto el vencimiento natural de su lease anterior sin liberarlo
  manualmente.
- Estado final: PostgreSQL `v69`, worker activo, Admin API saludable, endpoint
  de recordatorios correcto y perfil WhatsApp `session_ready` sin envio.

Resultado: **Paso 6 completado**. Existe una sola autoridad de plantillas y
toda revision historica necesaria sigue siendo reconstruible.

Criterio de cierre: existe una sola autoridad para plantillas nuevas y toda
plantilla historica necesaria sigue siendo reconstruible.

## Paso 7 - Reducir deuda del dashboard

Riesgo: bajo a medio. Separar limpieza muerta, seguridad de payload y cambios de
contrato.

### Limpieza local de bajo riesgo

- [x] Retirar `captchaSelectedStats` en `dashboard/src/app/app.ts` si la busqueda
  actual confirma cero lecturas.
- [x] Retirar `selectedOrderRuns` en `dashboard/src/app/app.ts` si la busqueda
  actual confirma cero lecturas.
- [x] Retirar selectores CSS sin markup consumidor:
  `.create-block`, `.followup-stage--warn` y `.inbox-empty`.
- [x] Retirar `getMonthlySummary()` e interfaz `MonthlySummary` solo junto con la
  deprecacion completa de API v1 del paso anterior.

### Sanitizacion y exportacion

`sanitizeOrder()` y `sanitizeWorkerCommand()` solo clonan objetos. Sin embargo,
`copyDashboardSnapshot()` confia en esos nombres como si aplicaran una politica
de seguridad.

- [x] Definir una allowlist explicita por objeto exportable.
- [x] Excluir credenciales, datos personales y diagnostico sensible.
- [x] Renombrar helpers si solo copian o hacer que realmente saniticen.
- [ ] Revisar manualmente el JSON final antes de habilitar la copia.

### DTO y payloads

El contrato TypeScript contenia 106 propiedades nunca leidas por TS o HTML. Los
tipos no cuestan ejecucion por si solos, pero el backend puede seguir
transportando datos innecesarios. Ejemplos de `ServiceOrder` no usados por la UI:

- `whatsapp_followup_sent_at`;
- `minimum_reservation_hour`;
- `preflight_started_at`;
- `preflight_validated_at`;
- `preflight_cycle`;
- `registration_notice_updated_at`.

- [x] Inventariar campos por vista y endpoint.
- [x] Crear DTO de resumen, lista y detalle; no cortar campos del endpoint
  compartido sin revisar clientes externos.
- [x] Medir tamaño y frecuencia de `/service-orders` y `/operator-inbox` antes y
  despues.
- [x] Sustituir `DashboardViewFacade = any` por contratos tipados gradualmente.

### Paginacion real

La revision post-cita se presenta como paginada, pero el API entrega el conjunto
completo y el cliente corta localmente.

- [x] Definir `limit`, cursor o `offset`, total y orden estable en el contrato.
- [x] Paginar en PostgreSQL/API.
- [x] Actualizar la UI para pedir solo la pagina necesaria.
- [x] Corregir la documentacion para no llamar “paginado” al estado previo.

Nota: el dashboard no tiene una suite frontend automatizada. No crearla dentro
de esta limpieza salvo pedido explicito; cada cambio visual requiere build y
revision real en `360`, `768`, `1024` y `1440 px`.

### Registro de ejecucion parcial del Paso 7

Corte de la comprobacion: `2026-08-30 12:43 America/Lima`.

- Se retiraron las dos señales y los tres selectores CSS sin consumidores. El
  cliente mensual v1 ya habia sido retirado durante la deprecacion del paso 5.
- La copia de diagnostico usa allowlists tipadas y no incluye identidad,
  contacto, credenciales, DOM, screenshots, paths ni detalle de ejecucion. La
  inspeccion final del JSON desde el navegador sigue pendiente.
- `DashboardViewFacade` ahora referencia el tipo real de `App`; al retirar el
  `any`, el compilador detecto y se corrigio un mensaje nullable en CAPTCHA.
- La lista del dashboard solicita `projection=dashboard`. Sobre `240` ordenes,
  el JSON bajo de `523,423` a `368,635` bytes (`29.6%`); la bandeja canonica ya
  era proporcional: `3` tareas y `2,097` bytes al corte. Los logs disponibles
  del `2026-08-16` al `2026-08-30` contenian `3,707` cargas de la lista de
  ordenes y `89` de la bandeja; la frecuencia no se aumento.
- Post-cita filtra, busca, ordena y pagina en PostgreSQL. La pagina activa de
  diez casos bajo de `50,923` a `21,435` bytes despues de separar las `110`
  proximas citas, que solo se cargan al abrir o refrescar la vista.
- Una llamada sin query conserva los `225` elementos del contrato historico;
  dashboard usa parametros explicitos. Busqueda y cambios de pagina cancelan la
  solicitud anterior y el debounce se limpia al destruir el componente.
- Se corrigieron conteos globales, pie de pagina, integracion de proximas citas
  y orden por la fecha mostrada. Proximas citas reutiliza la paginacion visual
  del dashboard con tamanos de `5`, `10` o `20`, aplicada despues de buscar,
  filtrar y ordenar. No se agrego una suite frontend nueva.
- Validaciones funcionales contra PostgreSQL y Admin API: filtros, totales,
  pagina, proyeccion, compatibilidad y rechazo de booleanos invalidos.
- Antes de reiniciar solo Admin API se comprobaron `0` sesiones manuales, jobs
  WhatsApp, rafagas y revisiones post-cita activas; worker sin orden actual. El
  intento `unknown` historico del `2026-07-03` no se altero. Despues del reinicio,
  API saludable y WhatsApp `session_ready`, sin envio.
- `compileall`, Ruff, `59 passed`, build Angular, validador documental y
  `git diff --check` se ejecutan como cierre tecnico. El build mantiene dos
  warnings de presupuesto preexistentes.
- La sesion del agente no tuvo navegador conectado. El usuario aprobo
  visualmente la vista despues de corregir la paginacion de proximas citas; no
  quedo registrada una comprobacion individual de los cuatro anchos.

Resultado: **Paso 7 implementado y aprobado visualmente, pendiente solo de la
revision manual del JSON copiado en navegador**.

Validacion:

```powershell
Set-Location dashboard
npm run build
Set-Location ..
git diff --check
```

Criterio de cierre: no hay señales ni CSS sin consumidor, la exportacion usa
allowlists, los payloads son proporcionales a la vista y la paginacion ocurre en
servidor.

## Paso 8 - Eliminar o formalizar archivos raiz y assets

Riesgo: bajo, salvo scripts que puedan estar en uso manual.

| Candidato | Tamaño observado | Accion propuesta |
|---|---:|---|
| `html con cupo.html` | 141,100 bytes | Eliminar o convertir en fixture real. |
| `html sin cupo.html` | 140,827 bytes | Eliminar o convertir en fixture real. |
| `src/appointment_bot/assets/brand/citas-lunas-polarizadas-logo.jpeg` | 85,616 bytes | Eliminar si sigue sin consumidor. |
| `scripts/whatsapp-manual-trace.py` | 4,975 bytes | Archivar o eliminar; puede competir por el perfil persistente. |
| `scripts/verify-postgres-backup.ps1` | 2,394 bytes | Conservar y documentar. |

Los dos HTML y el JPEG liberarian aproximadamente `367 KB`; el script manual
otros `5 KB`. El ahorro es pequeño: el beneficio principal es reducir ambiguedad
para humanos y agentes.

- [x] Buscar referencias exactas y usos manuales recientes.
- [x] Decidir si los HTML son fixtures reproducibles; si lo son, moverlos a una
  ubicacion de fixtures y documentar su objetivo.
- [x] Confirmar que las otras tres imagenes de marca activas siguen sirviendo al
  watermark antes de retirar solo el JPEG huerfano.
- [x] Confirmar que nadie ejecuta `whatsapp-manual-trace.py`.
- [x] Nunca ejecutar el script manual en paralelo con Admin API y su perfil
  persistente.
- [x] Agregar el verificador de backup al runbook antes de conservarlo como
  herramienta oficial.

### Registro de ejecucion del Paso 8

Corte de la comprobacion: `2026-08-30 America/Lima`.

- Las busquedas de codigo, runtime, logs, procesos y tareas programadas no
  encontraron consumidores de los dos HTML raiz, del JPEG ni del trazador
  manual. Las coincidencias de proceso observadas pertenecian a la propia
  auditoria.
- Los HTML eran capturas completas del portal con recursos relativos ausentes;
  no eran fixtures reproducibles ni participaban en tests. Se retiraron y Git
  conserva su recuperacion.
- El watermark referencia por nombre `Logo transparente.png`,
  `logo con numero.png` y `Nombre canal.png`. Solo se retiro
  `citas-lunas-polarizadas-logo.jpeg`, sin consumidor.
- `whatsapp-manual-trace.py` pertenecia a un diagnostico manual de julio, abria
  el mismo perfil persistente y no tenia integracion vigente. Se retiro sin
  ejecutarlo ni abrir WhatsApp.
- `verify-postgres-backup.ps1` se conservo y se formalizo en
  `docs/operations/postgres-backup-restore.md`, declarando que su dump y base
  temporal se eliminan y que no sustituye un backup externo durable.
- La prueba actual creo y restauro una base temporal, verifico `240`
  `service_orders`, `9,174` runs, `225` reservas, `392` intentos, `221` pagos y
  `schema_version = 69`; termino sin conservar el dump.
- `compileall`, Ruff, `59 passed`, build Angular, validador documental y
  `git diff --check` pasaron. La busqueda final confirmo cero referencias
  operativas a los cuatro archivos retirados. El build conserva los dos avisos
  de presupuesto preexistentes.

Resultado: **Paso 8 implementado; restauracion temporal comprobada y candidatos
resueltos sin afectar los assets activos**.

Criterio de cierre: todo archivo raiz o asset tiene consumidor, proposito
documentado o decision explicita de eliminacion.

## Paso 9 - Consolidar documentacion sin perder autoridad

Riesgo: bajo, pero una fusion incorrecta puede mezclar contrato, operacion e
historia.

### Fusionar o recortar

- [x] `docs/finance/README.md`: conserva checklist operativo de TikTok/CAC y
  mueve reglas duplicadas al contrato `docs/contracts/finance.md`.
- [x] `docs/operations/deployment-topology.md`: conserva arranque, verificacion y
  rollback; recorta arquitectura repetida de `current-runtime.md`.
- [x] `docs/optimization.md`: clasificar formalmente como contrato o mover su
  contenido normativo a `docs/contracts/`.

### Agregar contratos o runbooks faltantes

- [x] Contrato breve de recordatorios y post-cita: autoridad, deduplicacion,
  modos, dia congelado, limite 20, estados y conciliacion.
- [x] Runbook de backup y restore que referencie
  `scripts/verify-postgres-backup.ps1`.
- [x] Autoridad y orden exactos del paquete PDF postpago.

### Conservar

- [x] `README.md`, `docs/README.md`, `docs/project-status.md` y roadmap.
- [x] arquitectura actual y su README de redireccion.
- [x] contratos Admin API, ciclo de orden, reserva, worker, CAPTCHA, WhatsApp y
  finanzas.
- [x] runbooks operativos vigentes.
- [x] `docs/resumen-del-negocio.md`.
- [x] indice y milestones historicos.
- [x] README cortos de paquetes y dashboard.

### Registro de ejecucion del Paso 9

Corte de la comprobacion: `2026-08-30 America/Lima`.

- Finanzas separa la semantica contable en `contracts/finance.md` del checklist
  de registro y cierre en `finance/README.md`.
- `operations/deployment-topology.md` conserva solamente arranque,
  comprobacion, desarrollo y rollback; `architecture/current-runtime.md` sigue
  siendo la autoridad de procesos y fronteras.
- El contrato observacional se movio a `contracts/optimization.md` y se agrego
  al mapa de lectura.
- `contracts/appointment-followups.md` consolida autoridad, modos,
  deduplicacion, dia congelado, barrera del resumen, estados y frescura. Aclara
  que el limite fijo `20` es de post-cita; recordatorios usa un limite
  configurable con valor predeterminado `100`.
- El runbook de backup ya se habia formalizado en el Paso 8. El contrato
  WhatsApp y la configuracion local coinciden en los tres PDF originales y su
  orden; no se modificaron paquetes historicos.
- Se preservaron documentos de entrada, contratos vigentes, runbooks, resumen
  de negocio, indice, milestones y README de paquetes.
- `compileall`, Ruff, `59 passed`, build Angular, validador documental y
  `git diff --check` pasaron. El build conserva los dos avisos de presupuesto
  preexistentes.

Resultado: **Paso 9 implementado sin cambios de runtime, esquema ni datos**.

No se encontro un documento activo completo que fuera basura pura. El problema
documental era deriva puntual, tres snapshots engañosos y duplicacion parcial,
no la existencia de toda la documentacion actual.

Criterio de cierre: cada dato tiene una sola autoridad; estado, contrato,
runbook, historial y generado no se contradicen ni duplican su proposito.

## Paso 10 - Rotar evidencia y reportes generados

Riesgo: medio. Los archivos grandes tienen escritores activos y no son
huerfanos.

Tamaños observados:

| Archivo | Tamaño aproximado |
|---|---:|
| `docs/evidence-index.csv` | 925 KB |
| `reservation-optimization-log.md` | 842 KB |
| `partial-availability-log.md` | 740 KB |

Los dos logs append-only sumaban cerca de `1.58 MB`, aproximadamente `92.5%` de
`reports/`. El arbol de reportes observado ocupaba cerca de `1.71 MB`: nueve
archivos versionados sumaban aproximadamente `1.64 MB` y once ignorados unos
`71 KB`. Cada append relee el archivo completo, por lo que el problema es de
crecimiento y costo de escritura, no solo espacio en disco.

- [x] Identificar todos los escritores y lectores de las rutas canonicas.
- [x] Diseñar rotacion mensual conservando un indice o puntero estable.
- [x] Crear agregados diarios antes de archivar o purgar crudos.
- [x] Mantener fecha, rango, cobertura y limites en cada snapshot.
- [x] Archivar por mes los snapshots fechados de operaciones/optimizacion.
- [x] Hacer que `latest.md` sea puntero o baseline honesto, no afirmacion de
  runtime actual.
- [x] Verificar los CSV ignorados antes de borrarlos:
  `evidence-events-20260713.csv` estaba completamente duplicado en el indice
  actual; `evidence-events-20260712.csv` conservaba 13 eventos ausentes y debe
  archivarse, no borrarse a ciegas.
- [x] Regenerar indices y validar que ningun resumen apunte a rutas retiradas.
- [x] Aplicar politica de privacidad antes de conservar reportes compartibles.

### Registro de ejecucion del Paso 10

Corte de la migracion: `2026-08-30 15:58-16:08 America/Lima`.

- Se auditaron escritores y lectores antes de migrar. El worker estaba fuera de
  ventana caliente, sin orden, sesion ni rafaga activa.
- El indice monolitico tenia `2,699` runs unicos. El snapshot `20260712`
  aportaba `13` ausentes: se preservo el error util del `2026-06-29` y las `12`
  filas `Sin Cupos` quedaron solo en el snapshot legacy, conforme a la politica.
- La historia compacta quedo en `2,700` eventos unicos: junio `4`, julio `643`
  y agosto `2,053`. Los agregados diarios suman exactamente esos conteos.
- `docs/evidence-index.csv` conserva agosto como mes activo. El manifiesto
  `reports/evidence/index.md` resuelve junio, julio y agosto y declara que la
  retencion de artefactos no fue verificada por una ruta sanitizada.
- Las bitacoras se dividieron en `411` casos de optimizacion y `579` parciales;
  se retiro un Run duplicado y las rutas monoliticas quedaron como indices.
- Los cortes semanales y observacionales se archivaron por mes. Las versiones
  corregidas de ambos `latest.md` se conservaron como canonicas y `latest.md`
  paso a ser un puntero pequeño.
- El export ignorado `20260713` fue confirmado como `95/95` duplicado y movido
  a `.runtime/retired-step10/`, recuperable localmente. Sus SHA-256 son
  `C1B2D0D30EA40D3AAE01AA8236E3AD9C9E9B77D5AA0E05C845E2F31AA6DFBCBE`
  y `EDE8CE9A42E3B874FED2BC3277A852B37667E2BE3EC1083C75336C19A7BF3651`.
- La migracion remascaro todo identificador de orden residual y corrigio enlaces
  a `docs/contracts/optimization.md`. No se modificaron PostgreSQL, `.env`,
  reservas, clientes ni trabajos WhatsApp.
- Tras comprobar cero leases, submissions ambiguos, rafagas, sesiones manuales
  y jobs WhatsApp activos, se reinicio solo el worker mediante Admin API. El
  comando quedo `applied` sin liberar backoffs y el worker volvio saludable.
- Validaciones: `compileall`, Ruff, `59 passed`, build Angular, validador
  documental y `git diff --check`. El build conserva sus dos avisos de
  presupuesto preexistentes.

Resultado: **Paso 10 implementado**. Los escritores leen solo el mes destino,
la historia conserva comparabilidad y una purga futura puede partir de
agregados y manifiestos verificables.

Criterio de cierre: los escritores no releen historicos ilimitados, los indices
siguen resolviendo evidencia antigua y una purga no elimina comparabilidad.

## Paso 11 - Validacion integral y cierre

- [x] Ejecutar validacion Python existente.
- [x] Ejecutar build del dashboard si hubo cambios frontend.
- [x] Ejecutar el validador documental.
- [x] Ejecutar `git diff --check`.
- [x] Revisar visualmente pantallas afectadas.
- [x] Revisar rutas API afectadas con datos no sensibles.
- [x] Confirmar que no se crearon envios, reservas ni reintentos ambiguos.
- [x] Actualizar `docs/project-status.md` si cambio una capacidad vigente.
- [x] Actualizar `docs/roadmap/README.md` si cambio prioridad o trabajo futuro.
- [x] Hacer commits separados por dominio y revisar cada diff antes de publicar.

### Registro de ejecucion del Paso 11

Corte final: `2026-08-30 16:19 America/Lima`.

- `compileall`, Ruff, las `59` pruebas existentes, el build Angular, el
  validador documental y `git diff --check` terminaron correctamente. El build
  conserva los dos avisos de presupuesto preexistentes.
- No se modificaron archivos del dashboard ni superficies visuales. Se revisaron
  directamente manifiesto, punteros y destinos archivados; no habia una pantalla
  afectada que justificara una aceptacion visual adicional.
- Admin API respondio, el endpoint autenticado del worker confirmo proceso vivo
  y el ultimo reinicio coordinado quedo `applied`. El worker regreso a
  `outside_hot_window`, sin orden ni error activo.
- PostgreSQL confirmo cero leases o submissions activos, cero rafagas, cero jobs
  WhatsApp en ejecucion y cero runs, intentos, reservas o jobs creados durante
  esta intervencion. No se libero ningun backoff ni se creo un reintento.
- Una auditoria independiente encontro dos bloqueos antes de publicar: cobertura
  incompleta de sanitizacion futura y un glob contractual antiguo. Ambos se
  corrigieron y se verificaron con datos sinteticos sin escribir evidencia real.
  Tambien se validaron enlaces cuando el puntero usa una ruta personalizada.
- La equivalencia final conserva `2,700` eventos utiles unicos, `12` exclusiones
  `Sin Cupos` en el snapshot legacy, `411` casos de optimizacion y `579`
  parciales. Agregados, manifiesto, privacidad y enlaces coinciden.
- `docs/project-status.md` declara la rotacion vigente. El roadmap retiro los
  agregados y esta limpieza integral de la cola futura; backup externo,
  retencion de artefactos y observaciones naturales permanecen pendientes.
- Commit de implementacion revisado: `74f33d9` (`chore: rotate evidence history
  and refresh indexes`). Este cierre documental se conserva por separado.

Resultado: **Pasos 1 a 4 y 6 a 11 cerrados; Paso 5 en observacion externa**.
Codigo, runtime, PostgreSQL, reportes y documentacion coinciden en el alcance
implementado. El retiro final de contratos externos se gobierna unicamente
desde `docs/roadmap/README.md`.

Comandos base:

```powershell
python -m compileall -q src
python -m ruff check src tests
python -m pytest -q
Push-Location dashboard
npm run build
Pop-Location
powershell -ExecutionPolicy Bypass -File scripts/check-documentation.ps1
git diff --check
git status --short --branch
```

Criterio de cierre global: codigo, PostgreSQL, procesos, APIs y documentos
coinciden; cada elemento conservado tiene consumidor o proposito; cada elemento
retirado tiene evidencia de ausencia de consumidores y rollback proporcional.

## Division recomendada en commits

1. `docs: align runtime truth and generated report labels`
2. `refactor: remove unreferenced backend helpers`
3. `refactor: retire deprecated runtime settings`
4. `refactor: deprecate and remove monthly summary v1`
5. `refactor: remove dead dashboard state and styles`
6. `security: narrow dashboard export and view payloads`
7. `chore: remove or formalize orphan repository artifacts`
8. `docs: consolidate contracts and add missing runbooks`
9. `chore: rotate evidence history and refresh indexes`

No combinar el despliegue/migracion del paso 1 con estos commits de limpieza.
La migracion debe tener su propia evidencia operativa y posibilidad de rollback.

## Plantilla de registro por paso

Copiar este bloque al trabajar cada paso:

```markdown
### Ejecucion: <paso y titulo>

- Fecha y commit base:
- Estado de PostgreSQL y procesos:
- Trabajo activo comprobado:
- Referencias encontradas:
- Cambio realizado:
- Validaciones ejecutadas:
- Resultado funcional/visual:
- Riesgos o pendientes:
- Commit:
- Publicado: si/no
- Rollback:
```
