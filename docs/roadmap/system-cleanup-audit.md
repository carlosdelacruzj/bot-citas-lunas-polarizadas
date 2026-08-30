# Plan integral de limpieza y alineacion del sistema

Fecha de la auditoria base: `2026-08-29`.

Este documento concentra los hallazgos de la revision completa de codigo,
dashboard, PostgreSQL, runtime, documentacion, artefactos y reportes. Su objetivo
es permitir ejecutar la limpieza mas adelante, en orden y sin volver a descubrir
todo desde cero.

La prioridad oficial sigue viviendo en [`README.md`](README.md). Este archivo es
el detalle operativo de la tarea de limpieza: no reemplaza el estado actual de
[`../project-status.md`](../project-status.md), los contratos ni los runbooks.

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

- [ ] `src/appointment_bot/flows/__init__.py`: paquete vacio sin referencias;
  eliminar solo si el empaquetado no necesita conservar el paquete.
- [ ] `browser/whatsapp_web.py::_outgoing_image_message_states`: estado antiguo
  reemplazado por el camino basado en registros.
- [ ] `db/appointment_reminders.py::get_appointment_reminder_batch_day`: helper
  sin consumidor.
- [ ] `services/appointment_reminders.py::validate_reminder_template`: wrapper
  sin consumidor; la validacion vigente esta centralizada.
- [ ] `utils/screenshots.py::archive_unique_slot_screenshot`: wrapper singular;
  el camino plural es el activo.
- [ ] `db/whatsapp_followup_messages.py::_configured_followup_documents`: helper
  sin consumidor.

### Grupo B - Aliases y utilidades de oportunidad

- [ ] `db/opportunity_controls.py::mark_applied`.
- [ ] `db/opportunity_controls.py::open_opportunity_circuit_breaker`.
- [ ] `db/opportunity_bursts.py::mark_burst_execution_first_check`.
- [ ] `db/opportunity_bursts.py::close_opportunity_burst`.
- [ ] `db/opportunity_bursts.py::persist_obs007_events_from_report`.

### Grupo C - Fallbacks imposibles

`worker/opportunity_burst.py` intenta nombres alternativos inexistentes como
`mark_started`, `mark_finished` y `finish_burst`. Los metodos canonicos existen
siempre. Simplificar esos fallbacks solo despues de comprobar el camino completo
de rafagas y sus dobles de prueba existentes.

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

## Paso 4 - Limpiar configuracion deprecada o engañosa

Riesgo: medio. Revisar despliegues externos y archivos de entorno antes de
retirar nombres publicos.

- [ ] `appointment_reminders_enabled` / `APPOINTMENT_REMINDERS_ENABLED`: se
  cargan, pero no se leen; el control real vive en PostgreSQL.
- [ ] `appointment_reminders_dry_run` / `APPOINTMENT_REMINDERS_DRY_RUN`: se
  cargan, pero no se leen; el modo real vive en PostgreSQL.
- [ ] `session_rotation_seconds` / `SESSION_ROTATION_SECONDS`: se carga, pero no
  tiene consumidor.
- [ ] `continuous_interval_min_seconds`: solo participa en validacion de
  configuracion; no controla esperas.
- [ ] `continuous_interval_max_seconds`: se usa como umbral de salud, no como
  intervalo. Renombrar segun su funcion antes de eliminarlo.
- [ ] Campo `Settings.evidence_profile`: es redundante despues de construir los
  settings. Conservar el ENV `EVIDENCE_PROFILE`, porque si deriva configuracion
  funcional de video y screenshots.
- [ ] Mantener `OBSERVER_SITE_TOGGLE_INTERVAL_SECONDS` hasta decidir retirar su
  fallback de compatibilidad.

En el `.env` local se observaron claves ignoradas:

- `ORDER_RULE_COOLDOWN_SECONDS`;
- `OPPORTUNITY_BURST_ENABLED`.

No modificarlas como parte automatica de la limpieza. El usuario debe autorizar
explicitamente cambios en `.env` y primero se debe verificar que ningun script o
servicio externo dependa de ellas.

Criterio de cierre: cada variable documentada cambia comportamiento real; los
nombres conservados describen su uso y no existen flags que aparenten gobernar
controles persistidos.

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

- [ ] Medir logs de acceso durante una ventana representativa.
- [ ] Revisar n8n, scripts, proxies y clientes externos.
- [ ] Marcar v1 como deprecada con fecha y alternativa v2.
- [ ] Mantener una ventana de compatibilidad acordada.
- [ ] Retirar metodo e interfaz frontend v1.
- [ ] Retirar ruta, payload y consulta backend v1.
- [ ] Actualizar contrato Admin API y documentacion.

### API embebida del Worker en `8765`

Hallazgo: el servicio se inicia siempre, mientras la operacion normal usa Admin
API `8766`. La documentacion conserva `8765` como rollback.

- [ ] Medir trafico y revisar n8n, proxy, scripts y monitores externos.
- [ ] Confirmar si alguna recuperacion depende realmente de `8765`.
- [ ] Si no tiene consumidores, primero deshabilitarlo de forma reversible.
- [ ] Observar una ventana operativa completa.
- [ ] Retirar el servidor y actualizar topologia/runbooks solo al final.

Criterio de cierre: existe evidencia de cero consumidores externos durante la
ventana acordada y hay rollback documentado.

## Paso 6 - Resolver persistencia legacy de recordatorios

Riesgo: alto por historia y trazabilidad.

- [ ] Auditar las seis filas observadas en
  `appointment_reminder_template_versions`.
- [ ] Comparar revisiones antiguas con `whatsapp_message_template_versions`.
- [ ] Preservar contenido historico distinto, especialmente revision 1.
- [ ] Diseñar archivo o migracion explicita; no borrar la tabla directamente.
- [ ] Evaluar la columna duplicada
  `appointment_reminder_control.message_template`: el runtime usa la plantilla
  unificada y no se encontro consumidor funcional de esa copia.
- [ ] Retirar columna y tabla legacy solo en una migracion nueva, con validacion
  de trazas historicas.
- [ ] Confirmar que reportes y trabajos congelados siguen renderizando la
  revision que les corresponde.

Criterio de cierre: existe una sola autoridad para plantillas nuevas y toda
plantilla historica necesaria sigue siendo reconstruible.

## Paso 7 - Reducir deuda del dashboard

Riesgo: bajo a medio. Separar limpieza muerta, seguridad de payload y cambios de
contrato.

### Limpieza local de bajo riesgo

- [ ] Retirar `captchaSelectedStats` en `dashboard/src/app/app.ts` si la busqueda
  actual confirma cero lecturas.
- [ ] Retirar `selectedOrderRuns` en `dashboard/src/app/app.ts` si la busqueda
  actual confirma cero lecturas.
- [ ] Retirar selectores CSS sin markup consumidor:
  `.create-block`, `.followup-stage--warn` y `.inbox-empty`.
- [ ] Retirar `getMonthlySummary()` e interfaz `MonthlySummary` solo junto con la
  deprecacion completa de API v1 del paso anterior.

### Sanitizacion y exportacion

`sanitizeOrder()` y `sanitizeWorkerCommand()` solo clonan objetos. Sin embargo,
`copyDashboardSnapshot()` confia en esos nombres como si aplicaran una politica
de seguridad.

- [ ] Definir una allowlist explicita por objeto exportable.
- [ ] Excluir credenciales, datos personales y diagnostico sensible.
- [ ] Renombrar helpers si solo copian o hacer que realmente saniticen.
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

- [ ] Inventariar campos por vista y endpoint.
- [ ] Crear DTO de resumen, lista y detalle; no cortar campos del endpoint
  compartido sin revisar clientes externos.
- [ ] Medir tamaño y frecuencia de `/service-orders` y `/operator-inbox` antes y
  despues.
- [ ] Sustituir `DashboardViewFacade = any` por contratos tipados gradualmente.

### Paginacion real

La revision post-cita se presenta como paginada, pero el API entrega el conjunto
completo y el cliente corta localmente.

- [ ] Definir `limit`, cursor o `offset`, total y orden estable en el contrato.
- [ ] Paginar en PostgreSQL/API.
- [ ] Actualizar la UI para pedir solo la pagina necesaria.
- [ ] Corregir la documentacion para no llamar “paginado” al estado previo.

Nota: el dashboard no tiene una suite frontend automatizada. No crearla dentro
de esta limpieza salvo pedido explicito; cada cambio visual requiere build y
revision real en `360`, `768`, `1024` y `1440 px`.

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
| `assets/brand/citas-lunas-polarizadas-logo.jpeg` | 85,616 bytes | Eliminar si sigue sin consumidor. |
| `scripts/whatsapp-manual-trace.py` | 4,975 bytes | Archivar o eliminar; puede competir por el perfil persistente. |
| `scripts/verify-postgres-backup.ps1` | 2,394 bytes | Conservar y documentar. |

Los dos HTML y el JPEG liberarian aproximadamente `367 KB`; el script manual
otros `5 KB`. El ahorro es pequeño: el beneficio principal es reducir ambiguedad
para humanos y agentes.

- [ ] Buscar referencias exactas y usos manuales recientes.
- [ ] Decidir si los HTML son fixtures reproducibles; si lo son, moverlos a una
  ubicacion de fixtures y documentar su objetivo.
- [ ] Confirmar que las otras tres imagenes de marca activas siguen sirviendo al
  watermark antes de retirar solo el JPEG huerfano.
- [ ] Confirmar que nadie ejecuta `whatsapp-manual-trace.py`.
- [ ] Nunca ejecutar el script manual en paralelo con Admin API y su perfil
  persistente.
- [ ] Agregar el verificador de backup al runbook antes de conservarlo como
  herramienta oficial.

Criterio de cierre: todo archivo raiz o asset tiene consumidor, proposito
documentado o decision explicita de eliminacion.

## Paso 9 - Consolidar documentacion sin perder autoridad

Riesgo: bajo, pero una fusion incorrecta puede mezclar contrato, operacion e
historia.

### Fusionar o recortar

- [ ] `docs/finance/README.md`: conserva checklist operativo de TikTok/CAC y
  mueve reglas duplicadas al contrato `docs/contracts/finance.md`.
- [ ] `docs/operations/deployment-topology.md`: conserva arranque, verificacion y
  rollback; recorta arquitectura repetida de `current-runtime.md`.
- [ ] `docs/optimization.md`: clasificar formalmente como contrato o mover su
  contenido normativo a `docs/contracts/`.

### Agregar contratos o runbooks faltantes

- [ ] Contrato breve de recordatorios y post-cita: autoridad, deduplicacion,
  modos, dia congelado, limite 20, estados y conciliacion.
- [ ] Runbook de backup y restore que referencie
  `scripts/verify-postgres-backup.ps1`.
- [ ] Autoridad y orden exactos del paquete PDF postpago.

### Conservar

- [ ] `README.md`, `docs/README.md`, `docs/project-status.md` y roadmap.
- [ ] arquitectura actual y su README de redireccion.
- [ ] contratos Admin API, ciclo de orden, reserva, worker, CAPTCHA, WhatsApp y
  finanzas.
- [ ] runbooks operativos vigentes.
- [ ] `docs/resumen-del-negocio.md`.
- [ ] indice y milestones historicos.
- [ ] README cortos de paquetes y dashboard.

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

- [ ] Identificar todos los escritores y lectores de las rutas canonicas.
- [ ] Diseñar rotacion mensual conservando un indice o puntero estable.
- [ ] Crear agregados diarios antes de archivar o purgar crudos.
- [ ] Mantener fecha, rango, cobertura y limites en cada snapshot.
- [ ] Archivar por mes los snapshots fechados de operaciones/optimizacion.
- [ ] Hacer que `latest.md` sea puntero o baseline honesto, no afirmacion de
  runtime actual.
- [ ] Verificar los CSV ignorados antes de borrarlos:
  `evidence-events-20260713.csv` estaba completamente duplicado en el indice
  actual; `evidence-events-20260712.csv` conservaba 13 eventos ausentes y debe
  archivarse, no borrarse a ciegas.
- [ ] Regenerar indices y validar que ningun resumen apunte a rutas retiradas.
- [ ] Aplicar politica de privacidad antes de conservar reportes compartibles.

Criterio de cierre: los escritores no releen historicos ilimitados, los indices
siguen resolviendo evidencia antigua y una purga no elimina comparabilidad.

## Paso 11 - Validacion integral y cierre

- [ ] Ejecutar validacion Python existente.
- [ ] Ejecutar build del dashboard si hubo cambios frontend.
- [ ] Ejecutar el validador documental.
- [ ] Ejecutar `git diff --check`.
- [ ] Revisar visualmente pantallas afectadas.
- [ ] Revisar rutas API afectadas con datos no sensibles.
- [ ] Confirmar que no se crearon envios, reservas ni reintentos ambiguos.
- [ ] Actualizar `docs/project-status.md` si cambio una capacidad vigente.
- [ ] Actualizar `docs/roadmap/README.md` si cambio prioridad o trabajo futuro.
- [ ] Hacer commits separados por dominio y revisar cada diff antes de publicar.

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
