# Trabajo pendiente

Ultima priorizacion: `2026-08-17`.

Esta es la unica lista de trabajo futuro y su orden de ejecucion. El estado de
lo construido, validado y activo vive en
[`../project-status.md`](../project-status.md). Los contratos, runbooks,
incidentes, reportes y bitacoras aportan detalle o evidencia, pero no pueden
crear colas paralelas.

## Reglas de ejecucion

1. Trabajar una sola fase o experimento de comportamiento a la vez.
2. No mezclar refactor, cambios visuales y cambios del motor de reservas.
3. No modificar `.env` sin autorizacion explicita.
4. El CAPTCHA gráfico local solo puede tener autoridad dentro del canario V6
   persistido: maximo `20`, umbrales `0.60/0.60`, timeout `500 ms`, breaker y
   fallback a 2Captcha. La suma HTML del portal usa un resolutor local estricto
   independiente y no alimenta V3/V6. No ampliar ni retirar el fallback del
   CAPTCHA gráfico sin una nueva decision explicita.
5. No reintentar automaticamente un submit o envio de WhatsApp ambiguo.
6. Antes de reiniciar, comprobar submissions, leases, sesiones y trabajos
   WhatsApp activos.
7. Una fase solo termina cuando cumple sus criterios de aceptacion, actualiza
   `project-status.md` y deja este archivo alineado.

## Orden inmediato

1. Reunir la muestra productiva de cierre de la **Fase 1** sin cambiar sus
   parametros: `10` rafagas y `30` auxiliares reconstruibles.
2. Revisar las primeras `10` selecciones del canario de ruta critica: estrategia,
   fallback, seleccion preservada y tiempos pre-click, sin contar entrenamiento.
3. Cerrar en la **Fase 2** la conciliacion manual del pago historico con
   diferencia de `S/10` y reunir saldos/costos suficientes para cierres reales.
4. Completar la revision visual humana de `Seguimiento` en escritorio y movil;
   el primer lote real ya cerro `8/8 sent` despues del resumen diario.
5. Incorporar controles seguros y salud compuesta en la **Fase 3**.
6. Cerrar backup externo, watchdogs, rotacion y retencion en la **Fase 4**.
7. Reorganizar flujos y datos del dashboard antes del rediseño visual.
8. Ejecutar deuda tecnica solo despues de estabilizar las fases funcionales.

## Fase 0 - Consolidacion documental

Estado: **completada documentalmente el 2026-08-09**.

Objetivo: dejar una sola cola futura, distinguir instrucciones vigentes de
historia y eliminar contradicciones que puedan provocar una operacion insegura.

Resultado esperado del corte:

- inventario y clasificacion de toda la documentacion versionada;
- `project-status.md` como verdad de estado y este archivo como unica cola;
- planes de julio marcados como historicos o supersedidos;
- contratos vigentes enlazados desde sus indices;
- evidencia versionada actual sin nombres, `order_id` completos ni respuestas
  CAPTCHA;
- ninguna eliminacion de evidencia unica ni reescritura del historial Git.

Criterio de cierre: documentacion clasificada, enlaces locales validos,
contradicciones operativas criticas corregidas y `git diff --check` correcto.

## Fase 1 - Seguridad y medicion de OBS-006/OBS-007

Prioridad: **P0**.

Estado: **implementacion tecnica completada el 2026-08-10; pendiente muestra
productiva de aceptacion**.

Objetivo: hacer que cada rafaga real sea reconstruible y reversible antes de
usar sus resultados para decidir continuidad o escalamiento.

### Alcance

1. Persistir una entidad o evento durable por rafaga con `burst_id`, inicio,
   fin, motivo de cierre, candidatos y concurrencia maxima.
2. Propagar a cada ejecucion detectora y auxiliar:
   - `burst_id` y posicion;
   - rol detector/auxiliar;
   - candidato anterior y siguiente;
   - tiempo a primera lectura, CAPTCHA, submit y confirmacion;
   - resultado, lease y causa de salida.
3. Persistir la reobservacion `OBS-007`, el intento anterior `slot_lost`, el
   segundo intento y su resultado final.
4. Crear controles persistidos y auditados para activar, desactivar o drenar
   `OBS-006` y `OBS-007`, disponibles desde Admin API, dashboard y Telegram.
5. Implementar circuit breaker ante `403`, `429`, defensa, claim perdido,
   navegador huerfano, `reservation_unconfirmed` o fallo de coordinacion.
6. Mantener maximo dos sesiones concurrentes; tres sesiones no estan
   autorizadas.

### Fuera de alcance

- cambiar intervalos `15/1-2/8`;
- modificar seleccion de sede o confirmacion;
- promover modelos locales;
- rediseñar el dashboard.

### Validacion

- simulaciones de agotamiento, reemplazo, pausa, expiracion y rollback;
- validaciones Python y Angular aplicables;
- autorizacion explicita antes de agregar tests automatizados nuevos;
- luego, muestra real minima de `10` rafagas y `30` auxiliares;
- comparar contra el baseline del 1 al 8 de agosto.

### Implementado el 2026-08-10

- esquema PostgreSQL `v50` aditivo, con cabecera de rafaga, foto de candidatos,
  ejecuciones y eventos OBS-007 fuera de la retencion corta de `runs`;
- propagacion durable de rol, posicion, IDs de intento, lease, resultado,
  tiempos allowlisted y causa de cierre;
- control singleton con revision optimista, estado efectivo, drenaje y circuit
  breaker, manteniendo `inherit` como compatibilidad con las banderas vigentes;
- endpoints autenticados, panel operativo en Resumen y controles Telegram que
  pasan exclusivamente por Admin API;
- reconciliacion de rafagas incompletas al tomar un nuevo lease y limite duro de
  dos sesiones;
- primera muestra productiva: `2/10` rafagas y `4/30` auxiliares, con cuatro
  reservas confirmadas, cinco submits `slot_lost`, cero `captcha_invalid`, cero
  perdida de lease y cero defensas `403/429`;
- correlacion CAPTCHA corregida para que el segundo intento OBS-007 use su
  `reobservation_id`; doce colisiones sombra previas quedaron cerradas como
  descartes terminales, sin borrar imagenes, etiquetas ni eventos;
- archivo `cupos-unicos` corregido para conservar por separado todos los cupos
  del intento inicial y de la reobservación, cada uno con su propia fecha y
  hora; dos evidencias históricas del 10 de agosto fueron reparadas desde sus
  capturas originales;
- panel CAPTCHA alineado con la autoridad real: ruta muestras -> reglas ->
  resolutor final, estado `V6/20`, circuito, fallback y rollback confirmado;
- adaptador V6 corregido despues de dos oportunidades del `2026-08-11` que
  fallaron antes del submit por leer `request_ms` e `inference_ms` en lugar de
  `local_request_ms` y `local_inference_ms`; V6 conserva autoridad en modo
  `canary`, las decisiones se cerraron como `not_submitted_internal_error`, el
  worker fue reiniciado y la tercera decision V6 llego al submit productivo con
  resultado `slot_lost`, sin fallback, rechazo CAPTCHA ni breaker. La cuarta
  decision resolvio en `0.141 s`, fue aceptada por el portal y termino en la
  primera reserva confirmada bajo autoridad V6. El canario queda en `4/20`, con
  una confirmacion, un `slot_lost`, dos errores internos previos al submit y
  cero fallbacks; la efectividad sigue abierta hasta completar el corte;
- ruta crítica V6 corregida el `2026-08-13`: una sola llamada síncrona ejecuta
  únicamente V6 mediante `/v1/predict/authority`; V3 se completa después por el
  outbox durable, sin repetir V6. El servicio deduplica por `event_id`, separa
  telemetría de cola/preproceso/inferencia/persistencia/total y retiró el cálculo
  global de estadísticas de la respuesta crítica. El timeout permanece en
  `500 ms`; un fallo técnico aislado cae a 2Captcha y el circuito abre tras tres
  fallos técnicos consecutivos, mientras una respuesta inválida o un resultado
  ambiguo conserva el breaker inmediato;
- rollback operativo aplicado el `2026-08-14`: `mode=2captcha` vuelve a ser la
  autoridad desde el siguiente CAPTCHA, sin reinicio ni reinicio de contadores.
  El canario queda pausado con `5` decisiones locales, `2` confirmaciones, cero
  rechazos y `5` fallbacks preservados. Los dos fallos inmediatamente anteriores
  ocurrieron antes de invocar V6 o 2Captcha porque la imagen CAPTCHA del portal
  no cargó ni pudo capturarse; por tanto, una recurrencia bajo 2Captcha exige
  diagnosticar ese paso anterior al resolutor y no atribuirla al modelo local;
- compatibilidad con el nuevo CAPTCHA HTML implementada el `2026-08-14`: parser
  estricto de suma, cálculo local, firma de expresión, guarda de honeypot,
  evidencia visual y refresco por cambio de firma. La ruta gráfica anterior
  conserva 2Captcha y la suma queda excluida de muestreo, modelos y eventos
  shadow. Las validaciones locales pasan, pero la aceptación productiva queda
  pendiente porque los cupos desaparecieron durante la sesión aislada sin
  submit. La captura de disponibilidad también quedó desacoplada del CAPTCHA y
  se archiva en `cupos-unicos` inmediatamente después de estabilizar fecha y
  hora, con fallback a página completa; revisar ambas evidencias en el próximo
  cupo real antes de declarar aceptado el cambio;
- revisión humana CAPTCHA dirigida desde el `2026-08-13`: etiquetar primero
  todas las decisiones del canario V6, anomalías, baja confianza y desacuerdos
  V3/V6; usar una muestra SHA-256 determinista del `6.25%` de acuerdos como
  control. El resto permanece consultable sin formar parte de la cola diaria y
  no autoriza reentrenamiento automático;
- reserva fría aplicada el `2026-08-20`: preservar modelos, eventos y etiquetas,
  pero no cargar CUDA, producir sombra ni mostrar CAPTCHA en el dashboard
  mientras el portal use la suma HTML. La reactivación queda condicionada al
  regreso comprobado del CAPTCHA gráfico y mantiene 2Captcha como autoridad;
- migracion viva `v49 -> v51`, `compileall`, Ruff, `59 passed`, build Angular y
  `git diff --check` correctos.

El canario CAPTCHA V6 autorizado despues de esta primera muestra cambia la
latencia del submit. Las `2` rafagas y `4` auxiliares anteriores se conservan
como evidencia pre-canario, pero no deben mezclarse con la cohorte comparable
posterior al calcular rendimiento de la Fase 1.
Las observaciones anteriores al despliegue de la ruta V6 única tampoco deben
mezclarse con las posteriores al comparar latencia del resolutor. La siguiente
muestra debe revisar `local_request_ms`, `queue_wait_ms`, `preprocess_ms`,
`inference_ms`, `persist_ms`, `service_total_ms`, `cached` y `coalesced`.

No se marca la fase como cerrada porque todavia faltan `10` rafagas reales y
`30` auxiliares. Durante esa muestra no se deben cambiar intervalos, orden,
CAPTCHA ni concurrencia; cualquier breaker abierto detiene admisiones hasta la
revision manual.

### Criterio de aceptacion

Cada rafaga puede reconstruirse desde PostgreSQL sin depender de logs, no
existen submissions duplicados, las guardas detienen admisiones nuevas y el
rollback vuelve al flujo secuencial sin migracion destructiva.

### Rollback

Desactivar admisiones nuevas, dejar terminar submissions confirmables, cerrar
auxiliares y conservar la cadena secuencial. Nunca matar una sesion durante un
submit pendiente.

Detalle vigente:
[`../operations/opportunity-burst-canary-2026-08-09.md`](../operations/opportunity-burst-canary-2026-08-09.md).

## Fase 2 - Semantica de datos y calidad comercial

Prioridad: **P0/P1**.

Estado: **implementacion tecnica completada el 2026-08-10 en paralelo con la
muestra pasiva de Fase 1; cierre operativo pendiente de conciliacion de datos**.

Objetivo: impedir que el dashboard muestre cifras correctas individualmente
pero engañosas al mezclarlas en un mismo periodo o denominador.

### Alcance

1. Corregir `missing_contact_count` y Pendientes para aceptar telefono o
   `@usuario` como contacto operativo valido.
2. Separar el contrato mensual en:
   - `period_metrics`: eventos ocurridos dentro del mes;
   - `cohort_metrics`: ordenes creadas en el mes y su conversion posterior;
   - `current_attention_snapshot`: estado vivo con `as_of`.
3. Comparar MTD contra los mismos dias del mes anterior; mostrar por separado
   mes cerrado contra mes cerrado.
4. Congelar o conservar la fuente de captacion correspondiente al alta y
   explicar el universo de cada tabla.
5. Crear un centro de calidad de datos con contactos realmente inalcanzables,
   fuente ausente, `paid != agreed`, costos estimados y movimientos sin
   conversion.
6. Aclarar que `is_complete` financiero significa conversion monetaria
   completa, no captura total de costos ni utilidad neta.
7. Conciliar el pago `paid` con diferencia de `S/10` mediante una semantica
   explicita de descuento, condonacion o correccion; no asumir la causa.
8. Incorporar, solo con universos reconciliados, funnel
   `preflight -> reserva -> pago`, margen operativo porcentual, costo por
   reserva y costo CAPTCHA por reserva. CAC/ROAS queda oculto hasta contar con
   atribucion de fuente confiable.
9. Crear cierre financiero mensual con saldo inicial, recargas, consumo,
   reembolsos, saldo final, movimientos `actual/estimated/pending`, fecha de
   conciliacion y responsable del cierre.

### Criterio de aceptacion

Cada KPI muestra periodo, fecha de corte, numerador y denominador; cambiar de
mes no arrastra pendientes actuales como si fueran historicos; un contacto por
username no aparece como faltante.

### Implementado el 2026-08-10

- contrato autenticado `/api/v2/monthly-summary`, conservando v1 como rollback;
- separación de eventos del periodo, cohorte de altas y atención viva con
  `as_of`, cobertura, numeradores y denominadores;
- comparación MTD contra los mismos días del mes anterior y mes cerrado contra
  mes cerrado;
- contacto operativo válido por teléfono o `@usuario`;
- fuente de captación preservada en la orden para altas nuevas y backfill
  histórico marcado sin presentarlo como evidencia original;
- funnel de cohorte separado entre preflight validado y legado
  `not_required`;
- centro financiero de calidad, reconciliación explícita de diferencias de
  pago y cierre mensual durable con balance obligatorio;
- presentación operativa simplificada: resultado, reservas, altas, pendiente y
  gráfico diario visibles; comparaciones, cohortes, fuentes, calidad y cierre
  quedan fuera de la lectura normal; configuración CAPTCHA, ráfagas, soporte,
  movimientos y revisión financiera se abren solo cuando hace falta;
- CAC/ROAS, margen porcentual y costos unitarios bloqueados mientras la captura
  de costos o atribución no esté conciliada.

Permanece pendiente clasificar manualmente la diferencia histórica de `S/10` y
registrar saldos/costos suficientes para cerrar meses reales; no se inferirá la
causa ni se presentará margen neto antes de contar con esa evidencia.

### Rollback

Mantener temporalmente el endpoint anterior y la presentacion nueva detras de
un contrato versionado hasta reconciliar ambos resultados.

## Fase 3 - Controles y salud operativa

Prioridad: **P1**.

Objetivo: que el operador pueda distinguir una espera normal de una caida y
controlar el runtime sin arriesgar una reserva activa.

### Alcance

1. Separar:
   - `/health`: proceso vivo;
   - `/readiness`: PostgreSQL, schema y almacenamiento;
   - `/operations/status`: worker esperado, Telegram, WhatsApp, CAPTCHA,
     backup, disco, leases, sesiones y submissions.
2. Persistir `stop_reason=daily_cutoff` y `scheduled_resume_at` para mostrar
   `Corte diario normal - reanuda 07:30`.
3. Exponer Pausar, Reanudar, Drenar y reiniciar, con `can_restart`, fase,
   orden activa, sesiones y submissions.
4. Devolver `409 Conflict` ante un reinicio inseguro.
5. Registrar heartbeat funcional de Admin API, Telegram y dispatcher WhatsApp;
   los supervisores no deben depender solo de la existencia del PID.
6. Centralizar auditoria de mutaciones con actor, canal, entidad, request id,
   valores anteriores/nuevos sanitizados y resultado.
7. Clasificar credenciales rechazadas en sesiones manuales como resultado
   operativo, no como traceback tecnico inesperado.

### Criterio de aceptacion

El estado nocturno no genera falsa alarma; un proceso vivo pero bloqueado se
detecta; reinicio y drenaje son auditables y no interrumpen submissions.

### Implementado el 2026-08-11 y ampliado el 2026-08-14

- pausa, reanudacion y reinicio quedan auditados tanto por comando persistido
  como por el API embebido;
- el reinicio comparte una unica transicion con `paused=false`, cancelacion y
  detencion explicitas, evitando que el proceso nuevo herede una pausa;
- el dashboard mantiene el reinicio normal como opcion predeterminada y permite
  solicitar **Reiniciar y reintentar** de forma explicita. Esa variante libera
  unicamente el `next_allowed_at` de ordenes `ready` cuyo ultimo error no llego
  a intentar una reserva, sin submission activo, resultado de submit ni señal
  de defensa. El comando de reinicio sigue siendo persistido, la respuesta
  informa liberados/protegidos y la operacion queda auditada. No se liberan
  `reservation_unconfirmed`, `captcha_invalid`, `403/429` ni estados ambiguos;
- la alerta urgente de disponibilidad sale de la ruta critica: PostgreSQL
  `v55` la deduplica y conserva, mientras un dispatcher Telegram separado la
  envia con hasta tres intentos. Queda pendiente incorporar sus contadores y
  frescura a la salud compuesta;
- se retiro de la ruta critica la captura `preenvio` de pagina completa. El
  checkpoint durable anterior al clic conserva seleccion, resolutor,
  `decision_id`, validacion y hora, mientras `cupo`, CAPTCHA y respuesta del
  portal mantienen la cadena visual. Los archivos historicos permanecen
  intactos;
- la seleccion de hora incorpora un canario event-driven con dos snapshots DOM
  estables y fallback automatico al algoritmo `500/750 ms`. Las validaciones
  atomicas conservan la relectura independiente de identidad y tambien vuelven
  a las lecturas anteriores ante fallo. Dos kill switches permiten rollback
  separado; faltan `10` selecciones reales para aceptar el cambio.
- el alta manual de Telegram distingue desde el `2026-08-22` un rechazo real de
  una respuesta ambigua: amplía únicamente el timeout del POST de creación,
  verifica la persistencia y los valores por Admin API antes de recuperar el
  resultado, y audita por separado creación aplicada y seguimiento incompleto.
- el control Telegram separa desde el `2026-08-22` la cola operativa de los
  cobros pendientes. Cada cobro puede pasar a `paid` solo después de mostrar
  montos y recibir confirmación explícita; una relectura previa evita aplicar
  botones obsoletos y la respuesta distingue postpago encolado de envío.
- desde el `2026-08-23`, el contrato financiero de Admin API separa abono de
  cierre, impide que un parcial encole postpago y registra mutación y auditoría
  en una sola transacción. La fotografía esperada permite rechazar un cobro
  obsoleto con `409`; dashboard y Telegram ya presentan el total acumulado y
  eligen explícitamente entre abono y cierre completo;
- el control Telegram del `2026-08-23` agrega bandeja canónica de pendientes,
  contadores diarios, citas próximas, separación de pausados, prioridades
  `0/100/200`, navegación contextual y herramientas secundarias. Las mutaciones
  exigen identidad de usuario en chat privado, la revalidación requiere
  confirmación y los textos/credenciales sensibles se distinguen y eliminan;
- las credenciales rechazadas ya se corrigen directamente desde la fila de
  **Pendientes** o desde el panel contextual de la orden en Telegram: la nueva
  contraseña se borra del chat, requiere confirmación,
  aplica una guarda contra cambios concurrentes y dispara el preflight automático.
  El reintento simple queda reservado para fallos que no son
  `invalid_credentials`.
- desde el `2026-08-25`, el alta guiada registra el tipo de servicio y el precio
  antes del monitoreo: Estándar S/50, Día elegido S/70 con un único día de la
  semana permitido —combinable con fecha mínima, máxima y exclusiones—, o un
  monto personalizado. El aviso de registro validado usa una plantilla única y
  explicita servicio, precio, condiciones y exclusiones. El pago y los mensajes consumen ese
  valor persistido; falta medir el piloto comercial sin cambiar automáticamente
  precios de órdenes existentes.

Permanecen pendientes la salud compuesta, readiness, drenaje seguro, `409` ante
reinicio inseguro y heartbeats funcionales de los servicios.

## Fase 4 - Resiliencia y seguridad

Prioridad: **P1**.

Objetivo: recuperar la operacion ante perdida de PC, volumen, proceso o perfil,
y reducir riesgos de dependencias y exposicion local.

### Alcance

1. Backup automatico cifrado fuera de la PC con retencion diaria/semanal,
   checksum y alarma por antiguedad.
2. Restauracion mensual probada de PostgreSQL y metadatos necesarios; documentar
   recuperacion de Docker, perfiles y configuracion operativa.
3. Monitor externo real; n8n local ya queda limitado a loopback y dashboard y
   Admin API deben permanecer sin publicar.
4. Rotar logs por fecha y tamaño; mostrar espacio libre y crecimiento.
5. Definir retencion por finalidad para mensajes, jobs WhatsApp, Post-cita,
   capturas y telemetria detallada.

### Criterio de aceptacion

Existe un backup externo reciente, una restauracion completa documentada y una
alerta que sobrevive a la caida de la PC operativa; npm no reporta la
vulnerabilidad Angular identificada en este corte.

### Implementado el 2026-08-11

- n8n fue recreado sobre el mismo volumen durable con bind exclusivo
  `127.0.0.1:5678`; el health y el workflow activo regresaron correctamente;
- Angular `20.3.27` y herramientas `20.3.33` reemplazaron el corte vulnerable
  `20.3.26`; build y `npm audit --omit=dev` quedaron correctos. Tres alertas
  moderadas de herramientas de desarrollo requieren evaluar Angular CLI 21 en
  un cambio mayor separado, no afectan el bundle productivo actual.

## Fase 5 - Flujos funcionales del dashboard

Prioridad: **P1/P2**.

Objetivo: priorizar decisiones de clientes y dinero, y retirar diagnosticos de
la superficie principal.

Avance del `2026-08-26`: el alta del dashboard ya permite elegir y persistir
**Servicio regular - S/50**, **Disponibilidad restringida - S/70** o un monto
personalizado antes del preflight. La disponibilidad restringida requiere una
ventana cerrada y reglas de días o exclusiones, y la ficha muestra el servicio
y precio acordados. Esta capacidad queda completada; no agrega una tarea futura
independiente.

### Alcance

1. Separar Pendientes comerciales del backlog de entrenamiento CAPTCHA.
2. Mostrar antiguedad, vencimiento, responsable y siguiente accion.
3. Mover pruebas de WhatsApp a `Diagnostico de comunicaciones`, con destinatario
   y alcance visibles.
4. Implementar de forma incremental las plantillas editables de WhatsApp desde
   el dashboard: registro, reserva/cobro y postpago antes de unificar el editor
   pre-cita existente. Cada revisión aplica solo a trabajos futuros, usa
   variables allowlisted y conserva historial. El detalle y los puntos de pausa
   viven en
   [`../operations/whatsapp-editable-templates-plan-2026-08-25.md`](../operations/whatsapp-editable-templates-plan-2026-08-25.md).
   Las Etapas 0 y 1 quedaron completadas el `2026-08-25`: constructores,
   defaults, variables, bloques opcionales y momentos de snapshot están
   congelados; PostgreSQL `v61` conserva siete plantillas con historial y la API
   permite inventario, preview y guardado con revisión optimista y auditoría.
   La Etapa 2 quedó implementada técnicamente el `2026-08-25`: el dashboard ya
   permite seleccionar, editar, restaurar, previsualizar y guardar las siete
   plantillas, con confirmación y conflicto de revisión. El guardado y la
   relectura controlados no alteraron ninguna cola de WhatsApp. Falta la revisión
   visual en `360`, `768`, `1024` y `1440 px` para cerrarla. La Etapa 3 quedó
   implementada como piloto el `2026-08-25`: únicamente
   `registration_monitoring_started` consume la revisión vigente al preparar un
   aviso futuro y PostgreSQL `v62` conserva texto, clave y revisión en el job.
   Los `370` trabajos históricos no fueron alterados. Por instrucción explícita
   del operador, la Etapa 4 se implementó técnicamente el `2026-08-25` antes de
   aceptar el piloto natural: las tres variantes de registro consumen ahora su
   plantilla vigente, conservan texto, clave y revisión, y mantienen la
   deduplicación por orden, ciclo y tipo. La Etapa 5 quedó implementada
   técnicamente el `2026-08-26`: confirmación de reserva y cobro consumen ahora
   sus plantillas vigentes, y PostgreSQL `v63` congela ambos textos con pares de
   clave/revisión independientes en `whatsapp_messages`. Los `151` paquetes
   históricos permanecieron intactos; número, titular e imagen de pago siguen
   en configuración separada y el envío conserva dos imágenes dentro de un solo
   álbum. El primer lote natural del `2026-08-26` expuso un `INSERT` con `19`
   placeholders y `18` parámetros: cinco reservas quedaron confirmadas y sus
   cinco trabajos de álbum fallaron antes de abrir WhatsApp. La corrección se
   validó contra PostgreSQL y los cinco paquetes fueron recuperados uno por uno
   con autorización del operador; todos terminaron `sent` con revisiones
   `reservation_confirmation:2` y `reservation_payment:1`. El operador confirmó
   que los cinco llegaron correctamente; los trabajos originales, que no tenían
   `message_id`, se conciliaron como `dismissed` con una nota que conserva el
   enlace lógico al envío de recuperación y dejaron de aparecer en Pendientes.
   La aceptación automática continúa pendiente hasta que el próximo
   trabajo natural complete preparación y envío mediante el dispatcher. Un
   caso natural posterior congeló correctamente ambas revisiones, pero terminó
   `uncertain / non_multiple_input` antes de adjuntar las imágenes y no se
   reintentó. El `2026-08-26` esa fase incorporó una sola reapertura en página
   nueva, permitida únicamente mientras ningún selector de archivos haya sido
   invocado; después de cualquier riesgo de selección o envío continúa
   prohibido reintentar. La frontera se validó de forma aislada y Admin API
   regresó con WhatsApp `session_ready`, sin reenviar el histórico ni crear una
   prueba. La aceptación automática sigue abierta hasta observar esta guarda en
   el próximo álbum natural. Un reenvío posterior autorizado creó un solo
   paquete separado y terminó técnicamente `sent` con ambas imágenes y monto
   `S/70`; el intento automático original continúa técnicamente `uncertain` y
   quedó conciliado `dismissed` con una nota que enlaza el reenvío separado.
   Como WhatsApp mostró el selector correcto en el primer recorrido, esa
   recuperación no ejercitó la nueva reapertura ni cierra la aceptación
   automática. Falta
   observar naturalmente las tres variantes de registro y esa próxima
   reserva/cobro automática. La
   Etapa 6 quedó implementada técnicamente el `2026-08-26`:
   `post_payment_confirmation` controla el texto compacto posterior a los PDFs
   y PostgreSQL `v64` congela texto, clave y revisión en cada paquete nuevo. Los
   `145` paquetes históricos conservaron sus cuatro pasos y siguen legibles; la
   secuencia de PDFs y texto, la confirmación por componentes y la prohibición
   de reintentar ambigüedades no cambiaron. No se registró un pago, no se copió
   ningún PDF y no se envió WhatsApp. Falta observar también el próximo
   postpago natural. La Etapa 7 quedó implementada técnicamente el `2026-08-26`:
   el recordatorio consume la plantilla común tanto al conciliar como antes de
   enviar, y PostgreSQL `v65` conserva revisión vigente `6`, versiones genéricas
   `1-6` y las seis versiones legadas. Modos, canarios, scheduler y barrera del
   resumen siguen separados; **Seguimiento** controla activación y **Mensajes**
   edita el texto. No se cambió el modo `live`, no se encoló ni envió un
   recordatorio. Falta la revisión visual por ausencia de navegador conectado y
   observar el próximo caso natural. La Etapa 8 quedó separada: 8A ya aporta
   trazabilidad visible, auditoría de edición/restauración y un runbook de
   aceptación. 8C quedó cerrada sin implementación por decisión del operador:
   el resumen diario no requiere edición y TikTok conserva el generador actual
   de variantes, sin nuevas plantillas ni cambios de disparadores. La
   Etapa 8B quedó implementada técnicamente el `2026-08-26`
   por autorización explícita del operador: retiró el constructor de registro
   que ya era una rama muerta, eliminó el default hardcodeado del recordatorio y
   limitó el derivador postpago anterior a históricos sin trazabilidad. Los
   paquetes nuevos trazados deben conservar su `message_text`; Telegram y los
   `145` postpagos históricos mantienen sus contratos independientes. La matriz
   de observación natural sigue abierta por variante y para el próximo álbum
   enviado completamente por el dispatcher.
5. Extender la conciliacion guiada ya implementada para álbum y postpago a los
   demás tipos de WhatsApp. Desde el `2026-08-20`, los casos comerciales
   `failed/uncertain` permiten registrar `ya estaba completo`, `complete lo
   faltante` o `cerrar sin envio`; la revisión nunca reintenta y conserva el
   resultado técnico original. Falta cubrir resúmenes diarios, avisos de
   registro y recordatorios con la misma superficie.
6. Sacar configuracion CAPTCHA avanzada de Resumen; dejar una franja cuando el
   muestreo este activo.
7. Mantener IDs, `details_json`, estados crudos y copiar snapshot dentro de
   detalle tecnico.
8. Añadir frescura: ultima reserva, cupo, defensa, WhatsApp confirmado, backup y
   actualizacion de cada fuente.
9. Cargar Post-cita y textos sensibles de manera progresiva y paginada; evitar
   transportar las 108 historias completas cuando solo se necesita el resumen.
10. Completar la revision visual humana de `Seguimiento` en `360`, `768`,
    `1024` y `1440 px`. La separacion funcional entre Proximas citas,
    Post-cita e Historial ya esta implementada; queda pendiente aprobar su
    presentacion real en escritorio y movil.

### Criterio de aceptacion

El badge principal contiene solo trabajo accionable; no se confunde entrenamiento
con urgencias comerciales; un resultado WhatsApp ambiguo nunca reintenta por
si solo.

## Fase 6 - Diseño visual y accesibilidad

Prioridad: **P2**.

Objetivo: convertir el dashboard en una herramienta operativa reconocible,
coherente y accesible sin alterar contratos ni comportamiento del motor.

### Direccion

Sujeto: consola interna de un operador que reserva, cobra y acompana tramites
de lunas polarizadas. Audiencia: una persona que alterna supervision rapida y
resolucion de excepciones. Trabajo principal: saber que requiere accion ahora
y ejecutar el siguiente paso sin poner en riesgo una reserva.

Usar como estructura principal:

`Solicitud -> Validacion -> Cupo -> Reserva -> Pago -> Post-cita`

Orden de la portada:

1. tareas accionables;
2. salud y frescura;
3. resultado comercial;
4. riesgos y canarios;
5. configuracion avanzada.

Explorar antes de implementar un sistema visual propio del taller operativo:

- fondo `#F4F7F8`, superficies `#FFFFFF`, tinta `#13262D`, azul petroleo
  `#176B73`, ambar de atencion `#C87918` y rojo reservado a bloqueo
  `#B42318`;
- una sans humanista para lectura, una familia tabular/monoespaciada solo para
  horas, montos e IDs, y una escala compacta que no convierta cada KPI en hero;
- firma visual: una unica linea de tramite continua que conecte solicitud,
  validacion, cupo, reserva, pago y post-cita, con la etapa accionable marcada;
  es un mapa de estado real, no ornamentacion ni seis tarjetas repetidas;
- movimiento concentrado en transiciones de estado y refresco, con reduced
  motion; eliminar animaciones decorativas dispersas.

Antes de escribir CSS, comparar esta direccion contra la interfaz actual,
probar un wireframe de Resumen y uno de detalle, y descartar cualquier variante
que parezca un dashboard administrativo generico.

### Alcance

- tipografia diferenciada para texto, cifras e IDs;
- juego unico de iconos SVG;
- menos tarjetas KPI equivalentes y menos gradientes decorativos;
- focus trap o dialogo nativo en modales;
- `aria-pressed`, radio o tabs reales en filtros;
- foco, contraste y reduced motion conservados;
- validacion visual real en `360`, `768`, `1024` y `1440 px`.

### Criterio de aceptacion

No hay escape de foco en modales, todos los filtros comunican seleccion y una
revision visual humana aprueba escritorio y movil. Build no sustituye esta
aprobacion.

## Fase 7 - Reportes, retencion y evidencia

Prioridad: **P2**.

Objetivo: conservar comparabilidad sin retener indefinidamente datos crudos o
presentar snapshots incompletos como estado vivo.

### Alcance

1. Crear agregados diarios permanentes antes de purgar `runs` y `order_checks`.
2. Añadir `generated_at`, `coverage_start`, `coverage_end`, dias esperados y
   faltantes a reportes.
3. Alertar ante cualquier defensa, `403/429`, `reservation_unconfirmed`, claim
   perdido o navegador huerfano.
4. Mostrar politica de retencion: tabla, fecha minima/maxima, filas, tamaño,
   proxima purga, ultimo agregado, backup y restore.
5. Presentar CAPTCHA por cohortes comparables y destacar v6 prospectivo
   `N/500`, no el mejor resultado historico global.
6. Mantener bitacoras versionadas sanitizadas; una reescritura del historial
   Git es una operacion separada que requiere autorizacion explicita.
7. Incorporar un gate previo a publicar reportes que falle ante nombres,
   identificadores completos, placas, expedientes o respuestas CAPTCHA.

### Criterio de aceptacion

Un reporte no puede llamarse comparable si carece de dias; la purga de datos
crudos no elimina los agregados necesarios; la evidencia versionada no contiene
identificadores personales ni respuestas CAPTCHA.

## Fase 8 - Deuda tecnica posterior

Prioridad: **P3**.

No iniciar antes de estabilizar las fases funcionales.

1. Romper el ciclo entre `appointments.py` y `appointment_selection.py`.
2. Sustituir mutaciones globales de `queue_runtime.py` por dependencias
   explicitas.
3. Dividir `dashboard/src/app/app.ts` por dominio y reducir
   `ViewEncapsulation.None` gradualmente.
4. Uniformar errores HTTP inesperados con `request_id` y respuesta sanitizada.
5. Dividir modulos grandes en cambios pequeños sin modificar comportamiento.

## Observaciones reales que siguen abiertas

Estas validaciones no justifican cambios de variable y pueden cerrarse cuando
aparezca el evento natural:

- siguiente cupo real: modal CSS, orden de candidatos, `OBS-006/007`, reglas y
  claims;
- siguiente `captcha_invalid`: cooldown solo por orden y continuidad de cola;
- siguiente cupo incompatible: `partial / blocked_by_order_rule` sin backoff
  general ni ruido CAPTCHA por Telegram;
- siguientes trabajos WhatsApp: album, postpago y aviso de registro,
  revisar las guardas acotadas del `2026-08-20`: una segunda apertura del menú
  solo antes de seleccionar archivos, una segunda búsqueda por `@usuario` solo
  antes de escribir. Desde el `2026-08-26`, un `non_multiple_input` puede además
  recrear una sola vez la página del álbum únicamente si ningún selector de
  archivo fue invocado; validar esa recuperación con el próximo caso natural.
  En postpago, un único clic de documentos debe cerrar la
  vista previa antes del texto: si todas las burbujas PDF se confirman, continúa
  normalmente; si la vista previa cerró y volvió el compositor pero los checks
  no se reconocen, continúa únicamente con el texto, conserva los PDF como
  `uncertain` y nunca repite su clic. Preservar `uncertain` sin reintento después
  de un posible envío. La segunda apertura del menú ya no usa
  `Escape` y debe conservar visible el compositor del chat; el resumen real
  del `2026-08-13` ya validó
  paquetes secuenciales `4 + 4 + 2` y publicación posterior al último;
  el reenvío real de `order-74702632` validó el `2026-08-20` que la segunda
  apertura conserva el chat y permite enviar el álbum. Mantener pendiente la
  observación equivalente para aviso por `@usuario`. En postpago, el reenvío
  autorizado de `order-72687222` validó el `2026-08-21` la regla de un solo clic:
  la vista previa coexistió con el compositor y después aparecieron `3/3`
  burbujas PDF y el texto completo, sin segundo clic. Desde el `2026-08-25`,
  un reloj visible veta `sent`, mientras un check visible o una etiqueta exacta
  de enviado, entregado o leído confirma el texto; los marcadores ocultos y las
  etiquetas genéricas no deciden. El contexto no se cierra mientras el resultado
  queda pendiente. Validar con el
  siguiente postpago natural los estados separados `documents` y
  `payment_confirmation`, y validar la guarda del reloj con el siguiente aviso
  natural, sin crear un reenvío de prueba;
- siguiente cierre diario: confirmar en tráfico real la regla simplificada de
  compositor validado antes del clic y burbuja saliente nueva confirmada
  después, sin comparar nuevamente texto ni emojis;
- siguiente timeout natural de un alta por Telegram: comprobar que la orden
  persistida termina `applied` con `confirmation=recovered_after_*`, que el
  operador recibe su `order_id` y que no se genera un segundo alta;
- si se reactiva el canario V6, continuar desde sus contadores preservados,
  revisar cada resultado y conservar 2Captcha como fallback; cada 100 CAPTCHA
  frescos, registrar avance sin reentrenar;
- siguiente reinicio de Windows: tarea, supervisor raiz, Docker, Admin API,
  worker, Telegram, CAPTCHA y perfiles.

## Trabajos externos o no autorizados

- Despublicar el registro alojado y revocar claves: pendiente fuera de este
  repositorio.
- Cloudinary para evidencia publica: diseño documentado, pero su despliegue no
  esta autorizado en esta fase.
- Tres sesiones concurrentes: no autorizado.
- CAPTCHA local sin limite, breaker o fallback: no autorizado. El unico alcance
  vigente es el canario V6 `20` con umbrales `0.60/0.60` y 2Captcha de respaldo.
- Reescritura del historial Git para borrar datos antiguos: requiere una
  operacion separada, respaldo y autorizacion explicita.
