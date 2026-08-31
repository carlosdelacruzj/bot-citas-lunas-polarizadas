# Plan integral de endurecimiento y escalabilidad del desarrollo

Fecha de la auditoria base: `2026-08-31`.

Este documento convierte la auditoria integral de codigo y arquitectura en una
secuencia ejecutable. Su objetivo es que el sistema pueda seguir creciendo sin
acumular codigo muerto, dependencias circulares, reglas duplicadas, estados
ambiguos ni cambios imposibles de validar.

La prioridad oficial permanece en [`README.md`](README.md). Este archivo
contiene el detalle tecnico y operativo. No reemplaza el estado actual de
[`../project-status.md`](../project-status.md), los contratos ni los runbooks.

## Decision de trabajo

Hasta cerrar las fases 0 a 4:

- no iniciar features comerciales nuevas;
- permitir solo correcciones, pruebas, observabilidad y refactors incluidos en
  este plan;
- terminar o estabilizar primero el cambio del esquema `v72` y paquete
  integral;
- no aprovechar un refactor para cambiar reglas de negocio no relacionadas;
- no desplegar una migracion, reiniciar procesos ni enviar mensajes como parte
  de una comprobacion ordinaria.

Cerrar la fase 4 habilita reevaluar el congelamiento. Las fases 5 a 8 pueden
continuar de forma incremental mientras se admiten features pequeñas, siempre
que no vuelvan a concentrar responsabilidades ni reduzcan las barreras creadas.

## Resultado esperado

Al terminar el plan:

1. los caminos de reserva, WhatsApp, sesiones manuales y pagos fallan de forma
   conservadora ante ambiguedad;
2. las reglas comerciales y etiquetas tienen una autoridad unica;
3. los casos de uso coordinan el negocio y `db/` se limita principalmente a
   persistencia;
4. `reservation_engine/` no conoce Telegram, reportes ni detalles de
   infraestructura innecesarios;
5. el dashboard posee estado y fachadas por dominio, no una aplicacion global
   accesible desde todas las vistas;
6. backend y frontend tienen pruebas proporcionales al riesgo y CI reproducible;
7. los ciclos, globals mutables, modulos gigantes y compatibilidades tienen una
   decision explicita;
8. el repositorio conserva un estandar permanente y este plan temporal puede
   eliminarse.

## Linea base que debe refrescarse antes de ejecutar

La auditoria del `2026-08-31` observo:

- `149` archivos Python bajo `src/`, aproximadamente `52,207` lineas;
- `57` archivos TypeScript, HTML y CSS, aproximadamente `20,581` lineas;
- `59` pruebas Python y ninguna prueba frontend;
- dos ciclos de importacion reales;
- once clones de codigo de al menos doce lineas, cerca de `0.33%` del total
  analizado;
- `telegram_control.py` con `5,908` lineas;
- `dashboard/src/app/app.ts` con `5,343` lineas;
- `migrations.py` con `3,821` lineas;
- build Angular correcto, con warnings de presupuesto para bundle inicial y
  `app.css`;
- cambios locales sin publicar del esquema `v71` y paquete integral.

Estas cifras son una fotografia, no limites permanentes. Antes de cada fase se
deben recalcular el estado Git, esquema, pruebas, consumidores y riesgos del
dominio afectado.

## Principios obligatorios durante el plan

1. Un cambio de comportamiento critico por bloque y por commit.
2. Agregar primero una prueba de caracterizacion cuando el comportamiento
   actual deba conservarse.
3. No convertir `timeout`, excepcion posterior a una interaccion o resultado
   incompleto en permiso de reintento.
4. No seleccionar una identidad, tramite, fecha, destinatario o actor por
   posicion, valor predeterminado o texto aproximado.
5. Mantener una sola transaccion para invariantes atomicas, aunque la
   coordinacion se extraiga fuera de `db/`.
6. Mantener compatibilidad externa hasta demostrar cero consumidores y conservar
   rollback.
7. Usar excepciones y codigos de dominio; no inferir HTTP o estados buscando
   palabras dentro de mensajes.
8. No aumentar presupuestos, limites o timeouts solo para ocultar crecimiento.
9. No declarar aceptacion funcional por pasar compilacion o pruebas aisladas.
10. No modificar `.env`, datos historicos ni trabajos reales salvo autorizacion
    explicita del paso correspondiente.

## Orden y dependencias

| Fase | Objetivo | Depende de | Habilita |
|---|---|---|---|
| 0 | Congelar alcance y crear linea base | ninguna | trabajo seguro |
| 1 | Corregir riesgos operativos P0 | fase 0 | reservas confiables |
| 2 | Estabilizar `v72` y paquete integral | fase 0; partes de 1 | finanzas coherentes |
| 3 | Cerrar filtraciones y estados sensibles | fase 0 | diagnostico seguro |
| 4 | Crear red automatica de seguridad | fases 1 a 3 | refactor controlado |
| 5 | Corregir fronteras del backend | fase 4 | crecimiento modular |
| 6 | Modularizar el dashboard | fase 4 | frontend escalable |
| 7 | Uniformar API, contratos y consultas | fases 4 a 6 | integraciones estables |
| 8 | Validar, documentar y cerrar | fases 1 a 7 | reabrir desarrollo normal |

Las fases 1, 2 y 3 pueden avanzar en paralelo solamente si trabajan archivos,
contratos y procesos distintos. Ningun bloque puede desplegar una migracion o
reiniciar un propietario mientras otro bloque mantiene cambios operativos sin
validar.

## Fase 0 - Congelar alcance y establecer una linea base

### Objetivo

Evitar que la correccion se haga sobre un arbol cambiante o que se confundan
fallos anteriores con regresiones del plan.

### 0.1 Inventario del trabajo actual

- [x] Registrar branch, `HEAD`, upstream y `git status --short`.
- [x] Separar los cambios locales del paquete integral de cualquier cambio
  posterior; no descartarlos ni mezclarlos silenciosamente.
- [x] Identificar esquema de codigo, esquema PostgreSQL aplicado y proceso que
  aun ejecuta la version anterior.
- [x] Enumerar compatibilidades dentro de la ventana de observacion vigente.
- [x] Confirmar que el congelamiento de features aparece en el roadmap.

### 0.2 Linea base tecnica

- [x] Ejecutar compilacion, Ruff, pruebas, build, validador documental,
  `git diff --check`, `pip check` y auditoria de dependencias frontend.
- [x] Ejecutar el chequeo TypeScript con `noUnusedLocals` y
  `noUnusedParameters` sin convertir todavia los hallazgos en cambios masivos.
- [x] Recalcular archivos, lineas, ciclos, clones y modulos de mayor tamano.
- [x] Registrar warnings conocidos por separado de errores nuevos.

### 0.3 Barreras operativas

- [x] Antes de cualquier migracion o restart, comprobar leases, submissions,
  intentos activos, sesiones manuales, rafagas, lotes post-cita y jobs WhatsApp.
- [x] Definir rollback del primer bloque antes de editar codigo critico.
- [x] No liberar backoffs, claims o estados ambiguos para facilitar pruebas.

Criterio de cierre: existe una fotografia reproducible del arbol, esquema,
procesos y validaciones, y cada cambio local tiene propietario y destino.

### Registro de ejecucion de la Fase 0

Fecha de corte: `2026-08-31 00:20 -05:00`. Esta es una fotografia puntual y no
reemplaza la observacion natural que debe continuar hasta el `2026-09-06`.

#### Arbol y propiedad de cambios

- Branch: `codex/observer-multiclient-flow`.
- `HEAD` y upstream: `ab91372d661d434b2cddfb8881deb859d6cba104`;
  no hay commits locales sin publicar respecto del upstream.
- El arbol tiene 20 archivos tracked modificados y 2 untracked. No se hizo
  `stash`, descarte, commit ni mezcla automatica.
- Bloque ya existente **paquete integral / v71**: cambios de `dashboard/`,
  contratos de finanzas y ordenes, `project-status.md`,
  `system-cleanup-audit.md`, modelos, persistencia, migraciones, preflight,
  avisos, Telegram y el nuevo `core/service_packages.py`. Su destino es la
  Fase 2 y debe estabilizarse y publicarse como bloque funcional independiente.
- Bloque **gobierno del endurecimiento**: este documento y el congelamiento de
  features en `roadmap/README.md`. Su destino es la Fase 0. Ningun cambio
  posterior debe incorporarse silenciosamente al bloque v71.

#### Esquema y procesos cargados

- `SCHEMA_VERSION` del arbol: `71`; `schema_version` aplicado en PostgreSQL:
  `71`. No existe diferencia entre codigo en disco y base aplicada.
- Admin API fue iniciado el `2026-08-30 16:58:47` y Telegram a las `11:40:51`,
  antes de que los archivos v71 terminaran de editarse alrededor de las
  `18:48-18:54`. Esos procesos conservan modulos Python anteriores en memoria.
- El worker termino normalmente por corte diario a las `18:00:12`; no habia un
  worker activo durante la foto. Su proxima ejecucion normal cargara el arbol
  vigente. No se forzo restart ni se activo codigo durante esta fase.

#### Runtime y barreras operativas

- PostgreSQL y n8n estan `up`; Admin API `8766` responde `status=ok` y
  `reason=api_only`. El puerto `8765` no tiene listener. Este estado es esperado
  fuera de la ventana del worker `07:30-18:00`, no una falla demostrada.
- `AppointmentBotMonitor` existe en n8n pero permanece `active=false`.
- Telegram mantiene proceso vivo. La recepcion real y ausencia de alertas
  perdidas quedan pendientes de trafico natural; vida del proceso no prueba
  entrega funcional.
- Barreras en PostgreSQL/API: 0 leases de orden vigentes, 0 ordenes en
  `submission_intent` o `submission_pending`, 0 sesiones manuales, 0 comandos
  pendientes, 0 rafagas abiertas, 0 ejecuciones de rafaga sin terminar, 0 jobs
  WhatsApp activos y 0 revisiones post-cita activas.
- Existe 1 intento historico `unknown`, creado el `2026-07-03`, sin resolver.
  No corresponde a actividad actual, pero conserva su proteccion ambigua: no se
  libero, reclasifico ni reintento para facilitar esta auditoria.

#### Compatibilidades bajo observacion

Se mantienen, sin retirarlas durante esta fase:

1. `GET /api/v1/monthly-summary` hasta cumplir su umbral de cero accesos.
2. API embebida del worker en `8765` hasta siete dias sin trafico natural.
3. Lista de ordenes sin `projection=dashboard` hasta demostrar cero consumidores.
4. Consulta post-cita sin parametros hasta demostrar cero consumidores.

Desde las `00:00` hasta el corte, el log de Admin API contiene solo 2 requests,
ambos chequeos manuales de esta auditoria. Los contadores de las tres
compatibilidades HTTP fueron 0; el intento manual contra `8765` se registro
aparte y no cuenta como trafico natural. Esta muestra inicia la ventana, no
autoriza ningun retiro.

#### Linea base tecnica reproducible

| Control | Resultado |
|---|---|
| `python -m compileall -q src` | pasa |
| `python -m ruff check src tests` | pasa |
| `python -m pytest -q` | 59 pruebas pasan |
| `npm run build` | pasa con 2 warnings de budget |
| `scripts/check-documentation.ps1` | pasa |
| `git diff --check` | pasa; solo avisos LF/CRLF del working copy |
| `python -m pip check` | sin dependencias rotas |
| `npm audit --json` | 0 vulnerabilidades en 496 dependencias |
| TypeScript con ambos `noUnused*` | 1 hallazgo conocido; ver abajo |

Warnings conocidos, separados de regresiones:

- bundle inicial Angular: `546.59 kB`, excede el budget por `11.59 kB`;
- `app.css`: `30.04 kB`, excede el budget por 35 bytes;
- `followups-view.component.ts:440`: `needsPostAppointmentReview` esta declarado
  y no se usa; es el unico error del chequeo TypeScript estricto;
- Git avisa conversion futura LF a CRLF en archivos locales, sin whitespace
  invalido segun `git diff --check`.

#### Metricas estructurales de entrada

- Python bajo `src/`: 142 archivos y 49,826 lineas fisicas.
- Frontend bajo `dashboard/src/`: 57 archivos y 20,581 lineas fisicas.
- 66 funciones Python superan 100 lineas. Las mayores son
  `migrate_database` (1,068), `load_settings` (531),
  `_process_interface_callback` (452) y `_handle_post` (429).
- Mayores archivos: `telegram_control.py` (5,908), `app.ts` (5,343),
  `migrations.py` (3,821), `whatsapp_web.py` (2,475) y `app.css` (2,298).
- Ciclos internos detectados: `unique_slot_watermark <-> utils.screenshots` y
  el grupo `appointments / appointment_reader / appointment_fetch_probe /
  appointment_selection`.
- `jscpd` encontro 11 clones y 163 lineas duplicadas de 49,004 analizadas
  (`0.33%`), excluyendo migraciones y artefactos de build.

Estas cifras son baseline, no objetivos de borrado masivo. Cada extraccion debe
demostrar menor acoplamiento sin romper contratos ni evidencia.

#### Rollback predefinido para la Fase 1.1

La correccion de multiples tramites pendientes sera un commit aislado, sin
migracion ni reescritura historica. Antes de activarla se repetiran las barreras
anteriores y se validaran preflight y worker por separado. Si aparece una
regresion atribuible:

1. detener el rollout sin liberar claims, backoffs ni intentos ambiguos;
2. revertir exclusivamente el commit de Fase 1.1;
3. ejecutar sus pruebas de caracterizacion y la validacion base;
4. reiniciar solo los propietarios afectados, despues de volver a comprobar
   leases, submissions, sesiones y jobs activos;
5. conservar las ordenes ambiguas e intentos historicos sin reactivarlos ni
   cambiar su estado como parte del rollback.

Resultado: Fase 0 cerrada. Existe una foto reproducible, el feature freeze esta
activo, las deudas conocidas estan separadas de fallos nuevos y no se modifico
estado operativo para obtener resultados favorables.

## Fase 1 - Corregir riesgos operativos criticos

Cada subfase es un cambio independiente. No agruparlas en un mismo commit: sus
fallos, pruebas, rollout y rollback son distintos.

### 1.1 Fallar cerrado con multiples tramites pendientes

Objetivo: representar el alcance comercial acordado para los tramites de una
misma cuenta e impedir que el sistema elija, active, cobre o comunique uno por
posicion. Todos los expedientes pertenecen al titular; la ambiguedad es sobre
cual o cuales tramites se contrataron, no sobre la identidad de la persona.

#### 1.1.1 Clasificar el listado correctamente

- [x] Crear pruebas de caracterizacion para cero, uno y varios `PENDIENTE`,
  incluyendo una fila `CANCELADO` y otra `PENDIENTE` con los mismos datos.
- [x] Usar `pending_count`, no el total historico de filas, para decidir si se
  requiere intervencion. `CANCELADO`, `ATENDIDO` y otros estados no cuentan
  como tramites reservables.
- [x] Si existe un solo `PENDIENTE`, seleccionarlo sin presentar el caso como
  multiple y conservar el flujo normal sin regresion.
- [x] Registrar listado, estado, expediente y placa observados sin interpretar
  datos iguales como duplicidad ni como pertenencia a otra persona.

#### 1.1.2 Persistir lo acordado con el cliente

- [x] Cuando haya varios `PENDIENTE`, mantener la orden pausada y registrar una
  accion interna `multiple_pending_resolution_required`; no marcar
  `validated/ready` mientras falte la decision.
- [x] Permitir al operador elegir explicitamente `resolver_uno`,
  `resolver_todos` o `mantener_pausado`, conservando actor, fecha y revision del
  listado sobre el que decidio.
- [x] Para `resolver_uno`, exigir expediente exacto. Aceptar placa como clave
  unica solo cuando identifica una sola fila `PENDIENTE`; una placa repetida no
  puede seleccionar la primera coincidencia.
- [x] Para `resolver_todos`, crear una suborden por cada expediente pendiente y
  archivar siempre el padre para evitar monitoreo duplicado.
- [x] Hacer la division idempotente y atomica: una falla no puede dejar solo
  parte de los hijos creados ni duplicarlos al repetir la accion.
- [x] Rechazar con conflicto una decision basada en un listado que cambio;
  refrescarlo y pedir nueva confirmacion en lugar de aplicar datos obsoletos.

#### 1.1.3 Conservar condiciones comerciales por tramite

- [x] Antes de activar subordenes, confirmar por cada una servicio, reglas,
  precio y `charge_required`. Permitir aplicar los mismos valores a todas solo
  mediante una confirmacion explicita.
- [x] No clonar silenciosamente el monto del padre como deuda independiente de
  cada hijo. Distinguir precio por expediente, precio total compartido y
  tramite sin cobro adicional segun lo acordado.
- [x] Mantener reserva, evidencia y estado propios por suborden sin presentar la
  division como garantia de conseguir todas las citas.

#### 1.1.4 Controlar toda comunicacion al cliente

- [x] Detectar multiples pendientes, bloquear preflight o pedir una decision
  solo genera acciones internas en dashboard y Telegram. No encola WhatsApp ni
  una aclaracion automatica al cliente.
- [x] En el caso `CANCELADO + PENDIENTE`, no enviar explicaciones sobre
  multiples expedientes; el aviso normal de registro puede seguir su politica
  ordinaria una sola vez.
- [x] Despues de resolver varios pendientes, exigir una decision persistida:
  `cliente_ya_informado`, `previsualizar_confirmacion_unica` o
  `mantener_sin_envio`. Ninguna opcion envia por defecto.
- [x] Si se considera comunicar `resolver_todos`, mostrar primero un unico texto
  conjunto. Resolver solo guarda el preview y nunca envia ni encola; cualquier
  envio exige una accion posterior separada y autorizada.
- [x] Conservar trazabilidad de la decision de comunicacion. Un envio posterior
  sigue el contrato WhatsApp: `sent` no prueba lectura y `uncertain` nunca se
  reintenta solo.

#### 1.1.5 Defensa en profundidad y aceptacion

- [x] Hacer que preflight bloquee la ambiguedad antes de activar la orden y que
  el motor rechace igualmente una orden antigua que haya evadido esa barrera.
- [x] Mostrar en dashboard y Telegram las filas pendientes y la accion exacta,
  sin resolver implicitamente por el operador.
- [x] Probar expediente exacto, placa unica, placa repetida, listado obsoleto,
  division completa, rollback transaccional y repeticion idempotente.
- [x] Probar que deteccion, bloqueo, resolucion y preview no crean ningun job
  WhatsApp.

#### 1.1.6 Consolidar la implementacion sin ampliar comportamiento

- [x] Extraer listado, resolucion transaccional y guardias financieras a
  `db/program_resolution.py`; `order_credentials.py` conserva credenciales,
  creacion y lectura runtime.
- [x] Encapsular estado, validacion, plantilla y estilos del flujo visual en un
  componente de resolucion dedicado; el modal general y `App` quedan como glue.
- [x] Mantener el mismo contrato API, decisiones, errores estables y politica
  sin envio durante la extraccion.
- [x] Repetir pruebas backend, TypeScript y build para demostrar que el refactor
  no cambia comportamiento.

Criterio de cierre: ninguna ruta llega a seleccion, CAPTCHA o submit con varios
`PENDIENTE` sin alcance e identidad de tramite persistidos; resolver todos no
duplica padre, hijos ni cobros; y ninguna deteccion o decision ambigua comunica
al cliente sin contenido visible y autorizacion explicita.

Limite seguro: una orden integral, con historia financiera, lease o intento
activo no puede dividirse. Requiere cerrar primero esa condicion y, para datos
financieros, definir una asignacion contable explicita antes de reintentar.

### 1.2 Preservar la captura canonica de todo cupo seleccionable

Objetivo: conservar fecha y hora exactas antes de CAPTCHA o submit, tambien para
`partial / blocked_by_order_rule` y reobservaciones recuperadas.

- [x] Caracterizar `available`, `partial`, regla bloqueada y reobservacion.
- [x] Capturar el modal estabilizado inmediatamente despues de seleccionar.
- [x] Llamar a `archive_unique_slot_capture()` antes de entrar a CAPTCHA.
- [x] Mantener `reservation_attempted=false` y cero filas de intento para un
  cupo solo observado por regla.
- [x] Evitar que la captura CAPTCHA sustituya la captura del cupo.
- [x] Verificar nombres, indice, watermark y notificacion sin crear una reserva.

Criterio de cierre: cada fecha/hora seleccionable tiene screenshot canonico y
su resultado distingue deteccion, regla, CAPTCHA e intento.

Implementacion cerrada el `2026-08-31`: la autoridad compartida
`capture_canonical_selected_slot()` captura y archiva el modal estable antes de
entrar a CAPTCHA o submit tanto en seleccion inicial, bloqueo por regla y
reobservacion tras `slot_lost`. Si falta fecha/hora o falla la persistencia, el
flujo se detiene sin iniciar la reserva. La evidencia CAPTCHA queda como
secundaria y las pruebas verifican indice, watermark, orden de evidencia y cero
callbacks de intento para `blocked_by_order_rule`.

### 1.3 Exclusividad real de sesiones manuales

Objetivo: impedir que una sesion manual compita con worker, preflight, intentos
o con otra sesion de la misma cuenta.

- [x] Definir la clave de exclusividad: orden, cuenta y propietario global.
- [x] Crear una admision atomica persistida o coordinada por Admin API.
- [x] Rechazar con `409` lease, intento activo, preflight incompatible, job de
  navegador o sesion existente.
- [x] Conservar la sesion como `closing` hasta terminar realmente thread,
  contexto y Chromium.
- [x] Exponer `close_timeout` sin eliminar el handle del inventario.
- [x] Incluir sesiones `opening`, `active`, `closing` y `close_timeout` en la
  barrera previa a restart.
- [x] Probar aperturas concurrentes y cierre bloqueado.

Criterio de cierre: nunca existen dos propietarios compatibles del navegador y
un restart no puede observar cero sesiones mientras una siga viva.

Implementacion cerrada el `2026-08-31`: la admision bloquea atomicamente la
cuenta del portal en PostgreSQL y conserva un propietario renovable en el lease
de la orden. Worker, preflight, revision post-cita y sesion manual comparten la
misma frontera. Un cierre agotado queda visible como `close_timeout`; solo el
`finally` posterior al cierre del contexto libera el lease y retira el handle.
Admin API responde `409 manual_session_active` ante restart mientras permanezca
una sesion bloqueante.

### 1.3A Asignacion segura de oportunidades restringidas

Objetivo: evitar traspasos despues de una reserva confirmada y aumentar la
probabilidad de aprovechar fechas escasas para clientes que realmente las
necesitan.

- [x] Limitar el traspaso secuencial a `blocked_by_order_rule` de la orden
  observada.
- [x] Mantener la reserva inmediata del detector cuando su propia regla acepta
  el cupo; una confirmacion continua por la cola general, sin transferirla.
- [x] Ordenar candidatos compatibles por menor cantidad de oportunidades
  observadas aceptadas y mayor restriccion antes de prioridad y antiguedad,
  conservando prioridad exclusiva y continuidad de subordenes.
- [x] Evitar que la pertenencia al bloque activo adelante un candidato amplio y
  volver a revisar al originador restringido al final del traspaso.
- [x] Permitir rafaga inmediata desde una seleccion bloqueada sincronizada, con
  captura canonica y sin intento; conservar el traspaso secuencial como fallback.
- [x] Exponer el maximo configurado desde Admin API y eliminar el limite `2`
  duplicado en el dashboard.
- [x] Ampliar la rafaga a tres sesiones aisladas: detector y dos auxiliares.
- [x] Elevar a `v72` los limites persistidos de sesiones configuradas y activas.
- [x] Aplicar `v72` sin tocar el intento ambiguo existente; el worker permanecio
  detenido y no se forzo ningun reinicio.
- [ ] Validar en una ventana natural que tres sesiones no aumentan defensa,
  errores tecnicos, CAPTCHA ni resultados inciertos frente al baseline de dos.

Criterio de cierre: una orden amplia nunca crea un traspaso secuencial despues
de reservar; una incompatibilidad puede ceder el cupo a candidatos exactos; y
el primer auxiliar favorece al cliente con menos alternativas sin compartir
sesion, claim ni intento.

### 1.4 Clasificacion conservadora de excepciones WhatsApp

Objetivo: garantizar que un fallo posterior a una posible interaccion no quede
como `failed` reintentable.

- [x] Modelar fases `pre_interaction`, `interaction_started`,
  `confirmation_observed` y `confirmation_persisted`.
- [x] Marcar `uncertain` toda excepcion despues de iniciar una interaccion.
- [x] Preservar screenshot, componente, destinatario enmascarado y contexto.
- [x] Mantener `failed` solo para fallos demostrablemente anteriores a envio.
- [x] Probar excepcion de navegador, persistencia y callback despues del envio.
- [x] Confirmar que ningun scheduler o recuperador reintenta `uncertain`.

Criterio de cierre: no existe un camino donde un envio posible termine como
automaticamente reintentable.

### 1.5 Heartbeat independiente del lease global

Objetivo: impedir que otro host adquiera el worker mientras el propietario
original sigue dentro de CAPTCHA, submit o confirmacion.

- [ ] Crear heartbeat del lease global durante toda la vida del host.
- [ ] Separarlo del loop de chequeos y del heartbeat del claim de orden.
- [ ] Propagar perdida de lease como cancelacion conservadora.
- [ ] No transformar un submit iniciado en fallo reintentable.
- [ ] Probar solver bloqueado por mas de cinco minutos con reloj simulado.
- [ ] Probar caida de PostgreSQL y recuperacion sin dos hosts propietarios.

Criterio de cierre: una operacion lenta no deja vencer el lease global y una
perdida real detiene admision nueva sin duplicar submit.

## Fase 2 - Estabilizar esquema `v72`, pagos y paquete integral

La ampliacion tecnica `v71 -> v72` ya esta aplicada. No registrar un paquete
integral real hasta cerrar toda esta fase. El esquema, los resumenes y el
contrato deben avanzar juntos.

### 2.1 Catalogo comercial unico

Objetivo: eliminar precios, claves y etiquetas duplicadas entre core,
dashboard, Telegram y avisos.

- [ ] Convertir `core/service_packages.py` en autoridad de clave, etiqueta,
  precio total, abono, tasa, saldo y compatibilidades.
- [ ] Reemplazar literales de `50`, `70`, `160`, `80` y `71.40` donde
  representen la misma regla comercial.
- [ ] Corregir el detalle Telegram que presenta integral como estandar.
- [ ] Mantener `service_package` separado de reglas de busqueda, con
  combinaciones validas explicitas.
- [ ] Alinear previews, avisos, cobro y textos futuros.

Este conjunto si puede resolverse unido porque comparte una sola autoridad y
no toca migracion ni runtime del navegador.

### 2.2 Invariantes del paquete integral

Objetivo: impedir estados contables imposibles.

- [ ] Hacer que integral exija `charge_required=true`.
- [ ] Validar precio `S/160`, abono `S/80` y tasa `S/71.40` en dominio.
- [ ] Reforzar invariantes representables mediante constraints PostgreSQL.
- [ ] Preservar idempotencia de recibo y costo en reintentos de alta.
- [ ] Verificar que reserva cobre solo el saldo y pago completo acumule S/160.
- [ ] Definir comportamiento al corregir o cancelar una alta integral.

Criterio de cierre: API, dominio y PostgreSQL rechazan la misma combinacion
invalida y ninguna orden integral puede cerrarse dejando el saldo incoherente.

### 2.3 Integridad de `payment_receipts`

Objetivo: asegurar que cada recibo pertenece al pago y orden correctos.

- [ ] Eliminar `order_id` redundante o crear una FK compuesta consistente.
- [ ] Indexar claves foraneas y consultas por fecha/orden necesarias.
- [ ] Nombrar y validar constraints e indices en esquema fresco y migrado.
- [ ] Probar doble registro, reduccion invalida, pago parcial y pago completo.
- [ ] Mantener recibos inmutables; correcciones deben ser movimientos
  explicitos, no sobrescrituras silenciosas.

### 2.4 Semantica del backfill historico

Objetivo: no presentar una fecha inferida como fecha real de caja.

- [ ] Medir cuantos pagos historicos no permiten reconstruir cada abono.
- [ ] Conservar `source=historical_backfill` y exponer su calidad.
- [ ] Declarar fecha de corte desde la cual cada recibo es exacto.
- [ ] Evitar comparaciones mensuales concluyentes sobre periodos aproximados.
- [ ] Validar migracion `70 -> 71` en base nueva y restore aislado.

Criterio de cierre: reportes y contratos distinguen fecha exacta de fecha
inferida, sin inventar precision historica.

### 2.5 Una sola fuente para caja y resumenes

Objetivo: evitar que Finanzas y Resumen muestren ingresos distintos.

- [ ] Extraer consulta o CTE comun basada en `payment_receipts`.
- [ ] Migrar resumen financiero, mensual v2, serie diaria y conteos.
- [ ] Definir si `payments_received` cuenta recibos, ordenes o pagos cerrados.
- [ ] Probar un abono y cierre en meses diferentes.
- [ ] Comparar ambos endpoints para el mismo periodo y fixture.

Criterio de cierre: todos los indicadores de caja usan la misma semantica y
coinciden para una cohorte equivalente.

### 2.6 Activacion controlada

- [ ] Pasar pruebas nuevas, base tecnica y verificador documental.
- [ ] Revisar el diff completo del cambio local preexistente.
- [ ] Crear backup recuperable y probar restore aislado antes de migrar.
- [ ] Comprobar trabajo activo y aplicar la migracion una sola vez.
- [ ] Verificar esquema, conteos, constraints, indices y datos de control.
- [ ] Reiniciar solo el propietario necesario si la activacion lo requiere.
- [ ] Ejecutar un flujo natural futuro; no crear un cliente o cobro de prueba.

Criterio de cierre: codigo, esquema y runtime coinciden en `v72`, y el primer
caso natural conserva abono, tasa, saldo, mensaje y resumen correctos.

## Fase 3 - Privacidad, evidencia y secretos

### 3.1 Borrar secretos efimeros del dashboard

Objetivo: que cerrar o cancelar un modal elimine passwords y datos que no deben
quedar visibles.

- [ ] Limpiar siempre `newPassword` al cerrar alta.
- [ ] Conservar como borrador solo datos no sensibles si esa experiencia sigue
  siendo necesaria.
- [ ] Hacer efectiva `containsSecret` o retirarla si se reemplaza por una
  politica mas clara.
- [ ] Enmascarar documento en confirmaciones y copias de diagnostico.
- [ ] Probar cierre, cancelacion, error HTTP y alta exitosa.

### 3.2 No persistir respuestas CAPTCHA en detalles generales

Objetivo: mantener la solucion solamente donde sea imprescindible y evitar que
termine en `runs.details_json`, endpoints o exportes.

- [ ] Retirar `captcha_solution_sent` antes de construir el reporte general.
- [ ] Mantener correlacion de autoridad en almacenamiento restringido si es
  necesaria para el sistema sombra.
- [ ] Agregar redaccion recursiva por clave y tipo de dato.
- [ ] Probar reportes, API, CSV, Markdown y diagnostico copiado.
- [ ] Revisar datos historicos sin modificarlos ni publicarlos automaticamente.

### 3.3 Trazabilidad de actor confiable

Objetivo: que auditoria y conciliacion identifiquen al principal autenticado,
no un texto enviado por el cliente o un literal fijo.

- [ ] Resolver actor una vez en la frontera HTTP/Telegram.
- [ ] Pasarlo a casos de uso y transacciones.
- [ ] No aceptar `reconciled_by` como identidad autoritativa desde el body.
- [ ] Eliminar el literal `dashboard-owner` del registro integral.
- [ ] Mantener actor enmascarado o hasheado cuando corresponda.

Criterio de cierre de fase: cerrar o fallar un flujo no deja secrets visibles,
las respuestas CAPTCHA no cruzan superficies generales y toda accion sensible
tiene actor derivado de autenticacion.

## Fase 4 - Red automatica de seguridad y estandar de empresa

### 4.1 Dependencias reproducibles

Objetivo: que otro equipo o CI pueda instalar exactamente el entorno soportado.

- [ ] Declarar `pytest` y herramientas de validacion usadas dentro del extra
  de desarrollo.
- [ ] Elegir y documentar una estrategia de lock Python reproducible.
- [ ] Mantener `package-lock.json` y usar `npm ci` en CI.
- [ ] Ejecutar auditoria de vulnerabilidades Python y frontend.
- [ ] Definir politica de actualizacion y rollback de dependencias.

### 4.2 CI obligatorio

Objetivo: impedir que una rama verde localmente falle al integrarse.

- [ ] Crear pipeline para Python `3.12` con compileall, Ruff y pytest.
- [ ] Agregar build Angular, typecheck estricto, validador documental y
  `git diff --check`.
- [ ] Ejecutar instalacion reproducible, no depender del entorno del operador.
- [ ] Guardar resultados y hacer obligatorios los checks antes de integrar.
- [ ] No incluir credenciales reales ni conectarse al runtime productivo.

### 4.3 Pruebas backend por riesgo

Objetivo: cubrir invariantes, no perseguir un porcentaje cosmetico.

Prioridad inicial:

- [ ] multiples tramites y preflight;
- [ ] screenshot bloqueado y reobservacion;
- [ ] lease global y claim de orden;
- [ ] sesiones manuales concurrentes;
- [ ] ambiguedad WhatsApp posterior a interaccion;
- [ ] migracion y contabilidad integral;
- [ ] submit `intent/pending/unknown` y confirmacion `Programado`.

Despues:

- [ ] medir cobertura por modulo critico;
- [ ] fijar umbrales iniciales realistas y elevarlos gradualmente;
- [ ] prohibir que una excepcion critica quede sin escenario de prueba.

### 4.4 Pruebas frontend minimas

Objetivo: proteger formularios, payloads y acciones sensibles antes de dividir
`app.ts`.

- [ ] Elegir runner compatible con Angular actual.
- [ ] Probar reglas y payloads puros.
- [ ] Probar servicio HTTP por verbo, URL, body y conflicto.
- [ ] Probar modales de alta, pago, credenciales y WhatsApp.
- [ ] Agregar smoke E2E local para navegacion y errores `409`, sin enviar ni
  reservar.

### 4.5 Guardas de arquitectura y codigo muerto

Objetivo: impedir que vuelvan dependencias inversas y simbolos sin consumidor.

- [ ] Activar `noUnusedLocals` y `noUnusedParameters` en el check, resolviendo
  primero `needsPostAppointmentReview()` y falsos positivos.
- [ ] Definir imports permitidos entre `core`, `db`, `services`,
  `reservation_engine` y `worker`.
- [ ] Detectar ciclos en CI.
- [ ] Ejecutar detector de clones y codigo muerto como reporte; hacerlo
  bloqueante solo despues de limpiar la linea base.
- [ ] No borrar compatibilidad o callbacks dinamicos por un reporte aislado.

Criterio de cierre de fase: un clon limpio puede instalar, compilar, probar y
construir todo sin estado local, y las regresiones P0 tienen pruebas obligatorias.

## Fase 5 - Corregir fronteras y estructura del backend

Ejecutar un limite por vez. Cada extraccion debe conservar comportamiento y
pasar las pruebas creadas en la fase 4.

### 5.1 Servicios de aplicacion transaccionales

Objetivo: separar coordinacion de negocio de SQL sin perder atomicidad.

- [ ] Extraer `CreateServiceOrder` de `db/order_credentials.py`.
- [ ] Extraer `RegisterPayment` de `db/order_contacts.py`.
- [ ] Extraer `ConfirmReservation` de `db/reservations.py`.
- [ ] Introducir una unidad de trabajo o transaccion explicita compartida.
- [ ] Mantener repositorios enfocados en leer y escribir agregados.
- [ ] Mover cifrado fuera de la dependencia `db -> services`.

No extraer los tres casos en un solo commit. Completar uno, validar y observar
antes de continuar.

### 5.2 Puertos del motor de reservas

Objetivo: que `reservation_engine/` reciba dependencias pequeñas y devuelva
resultados/eventos, sin administrar Telegram, reportes o DB directamente.

- [ ] Definir puertos como `RunSink`, `AlertSink`, `CaptchaAuthority` y
  `OpportunityControl` solo donde haya un consumidor real.
- [ ] Inyectarlos desde `worker`.
- [ ] Retirar imports directos del motor hacia servicios y reportes.
- [ ] Mantener Playwright, reglas y modelos dentro del camino critico.
- [ ] Verificar que observer y reserva normal sigan compartiendo solo lo
  necesario.

### 5.3 Romper ciclos de importacion

Objetivo: hacer explicita la direccion de dependencias.

- [ ] Ampliar el ciclo documentado a `appointments`, `appointment_reader`,
  `appointment_fetch_probe` y `appointment_selection`.
- [ ] Extraer selectores, excepciones, DTO y lectura DOM a modulos neutros.
- [ ] Romper `utils.screenshots <-> services.unique_slot_watermark` mediante
  evento, callback o infraestructura compartida.
- [ ] Eliminar imports locales usados solamente para esconder ciclos.
- [ ] Activar el chequeo de ciclos como obligatorio.

### 5.4 Retirar mutaciones globales de `queue_runtime.py`

Objetivo: sustituir monkey patching por dependencias inyectables y pruebas que
usen fakes explicitos.

- [ ] Inventariar todos los imports productivos y de tests de la fachada.
- [ ] Parametrizar repositorios y ejecutores en cola y ejecucion.
- [ ] Migrar tests sin reasignar globals de otros modulos.
- [ ] Migrar consumidores productivos.
- [ ] Eliminar la fachada solo cuando tenga cero consumidores.

### 5.5 Dividir modulos grandes

Objetivo: reducir conflictos y hacer visible el ownership.

Orden recomendado:

1. `telegram_control.py`: cliente API, Bot API, router, conversaciones de alta,
   pagos, CAPTCHA y presentacion;
2. `local_api.py`: registro declarativo por metodo y patron;
3. `migrations.py`: funciones `vNN_to_vNN` registradas en secuencia;
4. `config.py`: settings agrupados por dominio con fachada temporal;
5. `whatsapp_web.py`: navegacion, destinatario, adjuntos y confirmacion.

- [ ] Fijar pruebas de caracterizacion antes de cada division.
- [ ] No modificar migraciones historicas aplicadas; extraerlas conservando su
  texto y orden.
- [ ] Definir un limite orientativo de tamano/ramificacion, no una regla ciega
  de lineas.
- [ ] Retirar la fachada temporal al migrar el ultimo consumidor.

Criterio de cierre de fase: core y motor no dependen de adaptadores, los casos
de uso no viven dentro de repositorios y no existen ciclos ni monkey patches
productivos.

## Fase 6 - Modularizar y asegurar el dashboard

### 6.1 Extraer estado y fachadas por dominio

Objetivo: dejar `App` como shell de navegacion y composicion.

Orden recomendado:

1. ordenes y alta;
2. finanzas y pagos;
3. WhatsApp y mensajes;
4. seguimiento;
5. CAPTCHA;
6. resumen, actividad y salud global.

Para cada dominio:

- [ ] crear fachada estrecha y estado propio;
- [ ] mover carga, comandos, confirmaciones y formato del dominio;
- [ ] limitar lo que la vista puede leer;
- [ ] migrar tests y templates;
- [ ] eliminar miembros equivalentes de `App`;
- [ ] medir bundle y comportamiento antes de continuar.

No crear un store global nuevo que reproduzca el mismo problema con otro
nombre.

### 6.2 Dividir contratos y clientes HTTP

Objetivo: evitar un archivo de API con todos los DTO y endpoints.

- [ ] Separar contratos por dominio.
- [ ] Compartir unions de estados desde una autoridad consistente.
- [ ] Validar en runtime respuestas criticas o mantener fixtures contractuales.
- [ ] Conservar detalle sensible separado de listas resumidas.
- [ ] Codificar siempre identificadores de ruta.

### 6.3 Cargas parciales y cancelacion

Objetivo: que un widget auxiliar caido no invalide una vista completa.

- [ ] Separar datos esenciales y secundarios.
- [ ] Reemplazar `Promise.all` monoliticos por resultados parciales donde
  corresponda.
- [ ] Mostrar error y frescura por tarjeta.
- [ ] Cancelar tambien detalle de orden en exito, error y `finally`.
- [ ] Probar navegacion rapida y respuestas fuera de orden.

### 6.4 Encapsulacion visual y accesibilidad

Objetivo: reducir CSS global y hacer que los modales cumplan su semantica.

- [ ] Mover estilos por dominio al extraer cada vista.
- [ ] Reducir `ViewEncapsulation.None` sin redisenar simultaneamente.
- [ ] Implementar focus trap e `inert` mediante CDK o solucion probada.
- [ ] Mantener Escape y restauracion de foco.
- [ ] Verificar teclado, contraste y reduced motion.
- [ ] Revisar `360`, `768`, `1024` y `1440 px`.
- [ ] Reducir bundle y CSS; no elevar presupuestos como cierre.

Criterio de cierre de fase: ninguna vista depende de toda la clase `App`, los
formularios sensibles tienen pruebas y los modales confinan correctamente el
foco.

## Fase 7 - Uniformar API, contratos y escalabilidad de datos

### 7.1 Errores de dominio y `request_id`

Objetivo: dejar de clasificar errores por palabras en el mensaje.

- [ ] Definir excepciones con `code`, HTTP sugerido y mensaje sanitizado.
- [ ] Traducirlas una sola vez en la frontera HTTP.
- [ ] Agregar `request_id` a respuesta, logs y auditoria pertinente.
- [ ] Mantener `409` para conflicto real y `422` para regla de dominio.
- [ ] Probar que cambiar un texto no cambia el codigo HTTP.

### 7.2 Router declarativo

Objetivo: reducir los grandes switches GET/POST sin introducir un framework
innecesario.

- [ ] Registrar metodo, patron, auth, parser y handler por ruta.
- [ ] Reutilizar los modulos `services/api/*` existentes.
- [ ] Centralizar limite JSON, cache, errores y headers.
- [ ] Conservar compatibilidad medida hasta su retiro autorizado.

### 7.3 Bandeja y consultas proporcionales

Objetivo: que costo de consulta y respuesta crezcan con tareas accionables, no
con todo el historial.

- [ ] Mover filtros y precedencia de Pendientes a SQL.
- [ ] Excluir estados no accionables desde origen.
- [ ] Paginar y medir plan de ejecucion.
- [ ] Sustituir cargas completas para existencia por `SELECT EXISTS`.
- [ ] Resolver la autoridad del contador CAPTCHA sin reconstrucciones
  contradictorias en frontend.

### 7.4 Contratos backend/frontend

Objetivo: detectar drift antes del runtime.

- [ ] Definir una fuente verificable para DTO criticos.
- [ ] Agregar fixtures contractuales o generacion controlada si no se adopta
  OpenAPI.
- [ ] Probar lista resumida, detalle sensible, inbox, finanzas y comandos.
- [ ] Mantener compatibilidad externa solo durante su ventana medida.

Criterio de cierre de fase: errores, actores, DTO y consultas tienen una
semantica unica y el costo de las vistas principales es proporcional.

## Fase 8 - Estandar permanente, validacion y cierre

### 8.1 Formalizar el estandar de desarrollo

Objetivo: conservar las reglas despues de eliminar este plan temporal.

- [ ] Crear o actualizar un documento breve de arquitectura con direcciones de
  dependencia, ownership, transacciones, errores y politica de pruebas.
- [ ] Mantener comandos y reglas de contribucion en `AGENTS.md`.
- [ ] Definir checklist de PR: alcance, riesgo, pruebas, migracion,
  observabilidad, rollout y rollback.
- [ ] Definir responsables o dominio propietario para cada carpeta.
- [ ] Mantener presupuesto de deuda visible sin convertir el roadmap en
  bitacora.

### 8.2 Auditoria final independiente

- [ ] Repetir inventario de ciclos, clones, codigo muerto y modulos grandes.
- [ ] Ejecutar todas las puertas locales y CI desde un clon limpio.
- [ ] Probar migracion desde la version minima soportada y base nueva.
- [ ] Verificar restore, health, lease y readiness.
- [ ] Confirmar cero regresiones en reservas, WhatsApp, pagos y post-cita.
- [ ] Completar aceptacion visual y flujos naturales pendientes.
- [ ] Confirmar que no se crearon reintentos, mensajes o reservas ambiguas.

### 8.3 Cerrar documentacion temporal

- [ ] Mover capacidades vigentes a `project-status.md`.
- [ ] Mover invariantes a contratos y procedimientos a operaciones.
- [ ] Dejar en `roadmap/README.md` solo pendientes reales.
- [ ] Eliminar este archivo cuando todos sus pasos aplicables esten cerrados.
- [ ] Eliminar el audit de system cleanup cuando termine su ventana propia.
- [ ] Corregir enlaces y ejecutar el validador documental.

Criterio de cierre global: el sistema puede aceptar una feature nueva mediante
un caso de uso y dominio claros, pruebas automatizadas, contrato estable,
observabilidad, rollout y rollback, sin agregar dependencias inversas ni estado
global compartido.

## Agrupaciones permitidas

Pueden resolverse juntas cuando el diff siga siendo revisable:

1. catalogo integral, etiquetas, previews y pruebas puras;
2. limpieza de password, uso de `containsSecret` y sus pruebas frontend;
3. activacion de flags TypeScript y retiro de simbolos realmente muertos;
4. errores tipados, `request_id` y pruebas de traduccion HTTP por un solo
   dominio a la vez;
5. estilos encapsulados junto con la extraccion de su propia vista;
6. constraint, indice y validador del mismo objeto de esquema.

## Agrupaciones prohibidas

No resolver en el mismo bloque:

- seleccion de tramite y cambios de submit;
- evidencia de cupo y refactor general del motor;
- lease global y sesiones manuales;
- clasificacion WhatsApp y cambios de selectores/envio;
- migracion financiera y retiro de compatibilidad API;
- modularizacion de dashboard y redisenio visual;
- extraccion de repositorios y cambio de reglas comerciales;
- varios modulos gigantes en un solo commit.

## Flujo obligatorio para ejecutar cada subtarea

1. Releer contrato y consumidores exactos.
2. Confirmar estado Git y cambios locales solapados.
3. Escribir escenario de fallo y criterio de cierre.
4. Agregar caracterizacion o fixture sin tocar datos reales.
5. Implementar el cambio minimo.
6. Ejecutar validacion focalizada.
7. Ejecutar la base completa proporcional al riesgo.
8. Revisar diff, seguridad, migracion y rollback.
9. Comprobar trabajo activo antes de migrar o reiniciar.
10. Observar el flujo natural cuando el contrato lo exija.
11. Actualizar estado o roadmap solo si cambio una capacidad o pendiente.
12. Crear un commit por dominio y publicar solamente con autorizacion.

## Puertas tecnicas

Base Python:

```powershell
python -m compileall -q src
python -m ruff check src tests
python -m pytest -q
python -m pip check
```

Dashboard:

```powershell
Push-Location dashboard
npm ci
npm run build
Pop-Location
```

Repositorio y documentacion:

```powershell
powershell -ExecutionPolicy Bypass -File scripts/check-documentation.ps1
git diff --check
git status --short --branch
```

Agregar a estas puertas, durante la fase 4, pruebas frontend, typecheck con
simbolos no usados, auditoria Python, ciclos, cobertura y CI.

## Condiciones para detener un bloque

Detener y no desplegar si ocurre cualquiera de estas condiciones:

- el cambio toca una orden, mensaje, pago o migracion fuera de su alcance;
- aparece un submit, WhatsApp o reserva `unknown/uncertain` sin conciliacion;
- no se puede demostrar que el propietario anterior dejo de operar;
- un constraint exige modificar datos historicos no auditados;
- una compatibilidad tiene consumidores no identificados;
- las pruebas requieren compartir cookies, credenciales o perfiles reales;
- el rollback depende de borrar evidencia o reescribir historia;
- frontend y backend discrepan sobre el contrato que se esta desplegando.

## Plantilla de ejecucion

```markdown
### Ejecucion: <fase.subtarea y titulo>

- Objetivo:
- Riesgo que elimina:
- Fecha, branch y commit base:
- Contratos y consumidores revisados:
- Trabajo activo comprobado:
- Pruebas de caracterizacion:
- Cambio realizado:
- Migracion o activacion:
- Validaciones ejecutadas:
- Resultado funcional/visual/natural:
- Pendientes y limites:
- Rollback:
- Commit:
- Publicado: si/no
```
