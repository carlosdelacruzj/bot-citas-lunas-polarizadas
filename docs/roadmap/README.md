# Trabajo pendiente

Última priorización: `2026-08-09`.

Esta es la única lista de tareas futuras y el orden vigente de ejecución. El
estado de lo construido, validado y observado vive en
[`../project-status.md`](../project-status.md).

## Orden inmediato

1. Validar en el próximo cupo real la ráfaga `OBS-006`: detector + auxiliar,
   preferencia por el otro usuario del bloque, reemplazos continuos solo tras
   `registered`, máximo concurrente, tiempo hasta cada submit y cierre limpio.
2. Cerrar dos o tres días comparables del observer `15/1-2/8` antes de cambiar
   otra variable. El corte semanal del 1 al 8 de agosto quedó actualizado.
3. Confirmar en eventos reales pendientes el modal CSS, los backoffs por reglas
   y CAPTCHA, y los cuatro tipos de trabajos WhatsApp; no provocar mensajes de
   prueba a clientes.
4. Si aparece defensa, reserva incierta, claim perdido, navegador huérfano o
   regresión operativa, aplicar `OPPORTUNITY_BURST_ENABLED=false`, reiniciar
   únicamente el worker cuando no haya submissions pendientes y conservar la
   cadena secuencial como fallback.
5. Ejecutar las revisiones semanales, mensuales, por cada 100 CAPTCHA y después
   del próximo reinicio definidas en
   [`../project-status.md`](../project-status.md#cadencia-de-revisión-vigente).

## Prioridad 0 - Recuperar una validación confiable

Estado: completado el `2026-07-28`.

Objetivo: volver a tener una suite que distinga regresiones reales de contratos
de prueba desactualizados.

Resultado:

1. Los 11 fallos correspondían a contratos de prueba desactualizados.
2. Claim y creación por API conservan el preflight obligatorio; las pruebas
   directas que necesitan una orden reclamable lo desactivan explícitamente.
3. Las expectativas ahora incluyen `document_type`, el contrato completo de
   restricciones y la firma vigente del muestreo CAPTCHA sombra.
4. No se modificó código productivo ni se redujeron protecciones de identidad,
   lease, selección o confirmación.
5. Suite final: `59 passed`.

Criterio de cierre: cumplido.

## Prioridad 1 - Consolidar los cambios recientes

Estado: en observación.

### Dashboard

- Completado el `2026-08-01`: el auto-refresh continúa funcionando en segundo
  plano sin insertar una franja temporal encima de la vista. El estado breve
  aparece en el encabezado y no provoca saltos verticales del contenido.

### WhatsApp automático

- Completado el `2026-08-07`: contactos y mensajes admiten destinatarios por
  `@usuario` cuando no hay numero. La resolucion prioriza el numero y la ruta por
  usuario exige un unico resultado en `Chats` y confirma en el encabezado el
  nombre que WhatsApp mostro en esa fila. Las lecturas repetidas validaron un
  alias no guardado y otro presentado con nombre local. Falta validar
  externamente el próximo aviso de registro real y no se hará un mensaje de
  prueba al cliente.
- Corregido el `2026-08-08`: ante un diálogo que bloquea el resultado por
  `@usuario`, se captura evidencia, se cierra solo de forma segura y se vuelve
  a exigir el mismo chat único una vez antes de escribir. El fallo terminal
  queda identificado como previo al envío y visible en la orden. Mantener
  pendiente la confirmación externa del próximo aviso real por usuario; no se
  enviará un mensaje de prueba al cliente.

- Completado el `2026-07-28`: la bandeja usa evidencia enviada y jobs durables,
  excluye `54` seguimientos históricos sin trabajo real y conserva los dos
  pagos vigentes. No borra paquetes ni reintenta resultados ambiguos.
- Medir trabajos `sent`, `failed`, `blocked` y `uncertain`.
- Confirmar que solo Admin API abre el perfil persistente.
- Verificar que evidencia y Yape permanezcan en un solo álbum y que sus rutas
  deduplicadas sigan resolviendo en los próximos envíos.
- Verificar que el postpago solo se cree después de confirmar `paid`.
- Completado el `2026-07-30`: el texto postpago requiere desaparición del
  compositor y una nueva burbuja saliente antes de marcar `sent`. El siguiente
  caso real reveló `msg-container`; el selector vigente y su marca saliente ya
  quedaron incorporados. Mantener observación ante futuros cambios de WhatsApp.
- Completado el `2026-07-30`: el corte diario encola un mensaje fechado y todas
  las imágenes únicas del día al número personal configurado. El primer envío
  reveló que cerrar al desaparecer la vista previa podía cancelar imágenes aún
  pendientes: solo una de cuatro llegó y el trabajo se corrigió a `uncertain`.
  La confirmación ahora espera todas las imágenes salientes sin reloj; el
  reintento manual autorizado terminó `sent` con cuatro confirmaciones. El
  resumen del 7 de agosto llegó completo y se reconcilió a `sent` sin reenviar;
  su falso `uncertain` quedó corregido acumulando todas las estructuras DOM
  compatibles. Mantener observación del siguiente cierre automático.
- Completado el `2026-08-07`: el álbum automático de evidencia y Yape posterior
  a una reserva aplica la misma confirmación estricta. Solo termina `sent` si
  aparecen las dos imágenes salientes aceptadas por WhatsApp; un timeout queda
  `uncertain`, guarda evidencia específica y no genera un reintento automático.
  Observar el próximo envío real antes de considerar cerrada la validación
  externa de WhatsApp Web.
- Completado el `2026-08-07`: el preflight inicial encola avisos automáticos
  distintos para solicitud validada, ausencia de trámite pendiente y
  credenciales rechazadas. Cada ciclo permite un solo intento de portal, la
  cola deduplica por orden/ciclo/resultado y los fallos técnicos no escriben al
  cliente. El dashboard muestra el estado del aviso y una entrega ambigua queda
  `uncertain` sin reintento. Validar externamente los tres textos en las
  próximas altas reales, sin realizar envíos retroactivos.
- Completado el `2026-07-30`: el resumen diario incorpora después del álbum una
  publicación variable para TikTok, sin IA ni consumo de tokens. El generador
  conserva datos comerciales fijos y rota 138,240 combinaciones por fecha. Una
  prueba controlada terminó con el texto completo y doble check azul después de
  normalizar los emojis transformados por WhatsApp; la prueba repetida añadió
  soporte para historial virtualizado e identidad de nuevas burbujas. Corregido
  el `2026-08-08`: el detector ya no deja de buscar al encontrar una familia DOM
  sin coincidencias; la evidencia real del 7 de agosto mostró la publicación
  completa y confirmada.
- Completado el `2026-08-02`: publicaciones, seguimiento y órdenes nuevas
  quedan alineados a `S/50 por trámite`. PostgreSQL v42 asignó `S/40` a las
  `99` órdenes anteriores y usa `S/50` como valor por defecto para futuras
  altas; los dos pagos pendientes de `S/40` no se modificaron.
- Planificada la reutilización de `cupos-unicos` en la landing bajo el título
  `Cupos encontrados recientemente`. Primero validar tres imágenes locales;
  después implementar subida firmada e idempotente a Cloudinary, desactivada
  por defecto y con secretos en `.runtime`. Detalle en
  [`../operations/public-slot-evidence-cloudinary-plan-2026-08-01.md`](../operations/public-slot-evidence-cloudinary-plan-2026-08-01.md).
- No habilitar reintentos automáticos para resultados ambiguos.
- Completado el `2026-08-07`: PostgreSQL v46 distingue deudas incobrables de
  pagos realizados. `uncollectible` archiva la orden y conserva la deuda como
  `written_off`; los abonos parciales permanecen `pending` y el dashboard
  descuenta `amount_paid` al calcular el saldo accionable.

### Reglas y backoff

- Completado en código el `2026-08-02`: se retiró la restricción horaria de
  dashboard, Telegram, CLI y del filtro de reserva. La API rechaza nuevos
  valores horarios y el campo histórico de PostgreSQL queda sin autoridad.
- Completado en código el `2026-08-02`: la selección ordena fechas permitidas
  de menor a mayor y horarios de menor a mayor, priorizando la combinación
  cronológicamente más próxima.
- Completado en código el `2026-08-02`: una incompatibilidad de reglas ya no
  aplica el cooldown de `900` segundos. La orden conserva el resultado y rota
  por `last_run_at`; validar este comportamiento ante el próximo cupo real.
- Completado en código el `2026-08-02`: la cola posterior ya no descarta en
  bloque a los clientes restringidos. Evalúa cada orden contra todas las
  oportunidades observadas y solo excluye a quien no admite ninguna.
- Completado en código el `2026-08-02`: la selección conserva las combinaciones
  fecha/hora realmente recorridas. El detector compatible reserva de inmediato;
  el bloqueado conserva el inventario completo que pudo leer. La cadena admite
  hasta `10` candidatos o `300` segundos y continúa después de cada reserva.
- Validar en el próximo caso real el orden prioridad exclusiva -> segundo
  trámite -> mayor cobertura, la detención por cupos desaparecidos y la
  telemetría `opportunity_elapsed_seconds`.

- Completado el `2026-07-31`: `captcha_invalid` después del segundo intento
  aplica `120` segundos solo a la orden afectada y no detiene la rotación de
  clientes. Los fallos ambiguos y las defensas del portal conservan su política
  protectora independiente.
- Confirmar en el próximo rechazo real de CAPTCHA que el worker procesa la
  siguiente orden elegible sin entrar en backoff global.
- Esperar una nueva aparición real de varias fechas fuera de rango.
- Confirmar `partial / blocked_by_order_rule`, sin CAPTCHA resuelto, submit ni
  backoff general.
- Confirmar que una opción compatible posterior todavía se selecciona.

### CAPTCHA y datos de entrenamiento

- Completado el `2026-08-02`: las bitácoras versionadas ocultan nombres,
  identificadores de orden y respuestas CAPTCHA; se sanitizó el lote pendiente
  antes de publicarlo.
- Completado en código el `2026-08-01`: `RESERVATION_CAPTCHA_SAMPLE_LIMIT=1`
  conserva el recorrido real vigente. Un valor mayor captura y refresca
  muestras adicionales, registra cada una en sombra y manda solamente el
  último CAPTCHA a 2Captcha.
- Completado en código el `2026-08-08`: el panel Resumen permite activar o
  desactivar el muestreo y elegir un total `2-50`, persistido en PostgreSQL
  `schema v47`. Desactivado equivale a `1`, conserva el total elegido y no exige
  reiniciar el worker; un cambio se congela al comenzar el siguiente lote. El
  modo rápido conserva el límite obligatorio de `1` y `.env` queda como fallback.
  Reorganizado visualmente para presentar en orden modo, cantidad, efecto del
  siguiente intento y confirmación de guardado, con ritmo de `16-24 px`,
  tarjetas internas separadas y acción final delimitada.
- Medido el `2026-08-01` con `.env` local en `10`: dos cupos incompatibles
  capturaron diez CAPTCHA originales cada uno. Las nueve muestras adicionales
  agregaron `3.609 s` y `3.625 s`, cerca de `0.402 s` por ciclo. No hubo submit
  ni llamada a 2Captcha porque ambas órdenes terminaron
  `partial / blocked_by_order_rule`.
- Cerrado el experimento con el control productivo desactivado; las nueve
  capturas adicionales ya no retrasan una reserva real.
- Corregida y recuperada la publicación de esa ruta hacia CAPTCHA sombra: los
  20 eventos tienen tres predicciones y quedaron pendientes de revisión humana
  en el dashboard.
- Completado el `2026-08-08`: Telegram recuperó el etiquetado humano conectado a
  la cola sombra actual, no al CSV antiguo. El botón muestra pendientes en orden,
  deduplica las respuestas coincidentes de los modelos, admite respuesta manual,
  omitir y salir, avanza automáticamente y vence tras `10` minutos sin actividad.
  Los tokens por imagen rechazan botones obsoletos y el guardado no sobrescribe
  una etiqueta creada simultáneamente desde el dashboard. Mantener 2Captcha como
  única autoridad para las reservas reales.
- Completado el `2026-08-09`: las inferencias residentes nuevas se redujeron a
  `v3_selected` como control y `v6_sequence_candidate` como candidata. V1, V2,
  V4 y V5 conservan checkpoints y predicciones históricas, pero ya no consumen
  GPU ni agregan opciones a los CAPTCHA nuevos.
- Completado en código el `2026-08-08`: la captura CAPTCHA de un cupo bloqueado
  por reglas permanece disponible localmente y en sombra, pero ya no se envía
  como evidencia diferida a Telegram. El selector de evidencia tampoco usa un
  CAPTCHA como foto sustituta cuando falta una captura operativa normal.
  Confirmar la ausencia de mensajes repetidos ante el próximo cupo real
  incompatible.
- Completado el `2026-08-02`: entrenado y seleccionado v3. Mejoró a `v2_selected` en los
  tres conjuntos comparables: `93/98` temporal, `147/150` humano y `77/78`
  sombra. El servicio carga cuatro modelos, el dashboard muestra
  `v3_selected` y solo se reprocesaron las 78 imágenes excluidas del
  entrenamiento para conservar una comparación honesta.
- Pendiente: medir un cupo compatible de extremo a extremo y comparar selección
  conservada, demora previa, tiempo de 2Captcha, submit, resultado del portal y
  posible `slot_lost`. No declarar validada la opción con casos bloqueados.
- Mejora futura documentada: resolución híbrida local con fallback a 2Captcha.
  No activarla hasta evaluar prospectivamente al menos 500 CAPTCHA frescos y
  sostener más de 99% con una regla fijada antes del corte. El desacuerdo, baja
  confianza, timeout o servicio local no saludable siempre deben derivar a
  2Captcha.
- En progreso desde la congelación de v6: reunir y revisar al menos `500`
  CAPTCHA nuevos sin usarlos para reentrenar. Comparar prospectivamente v6
  contra el control v3, auditar errores y estabilidad por día y sesión, y no
  promover ningún modelo hasta sostener más de `99%` con la regla fijada antes
  del corte. V1, V2, V4 y V5 quedan como comparaciones históricas fuera del
  servicio residente.
- Detalle operativo, tiempos y guardas en
  [`../operations/captcha-shadow-integration.md`](../operations/captcha-shadow-integration.md#muestreo-durante-una-reserva-real).

### Observer

- Completado en código y replay aislado el `2026-08-09`: el flujo compartido
  por el worker y las sesiones manuales detecta la firma CSS defectuosa del
  modal de citas y restaura la presentación anterior. Si el portal vuelve a
  entregar un diseño nativo válido, el fallback se retira automáticamente; un
  estado intermedio no reconocido no se modifica. La matriz aislada confirmó
  `fallback_applied`, `healthy` y `unknown` sin cambiar controles.
- Confirmar en la próxima sesión real el log `Appointment modal CSS` y una
  captura centrada correcta, sin considerar la validación aislada como prueba
  de comportamiento actual del portal.
- Completado en código el `2026-08-01`: las órdenes usan `15` consultas de sede
  por sesión, `vacío -> LIMA-LA VICTORIA` desde el segundo intento, espera
  aleatoria nueva de `1-2` segundos después de cada consulta completa y un solo
  `reload_probe` tras el intento `8`. Después se rota al siguiente cliente con
  una sesión Playwright nueva.
- Completado el `2026-08-01`: auditoría de configuración operativa. El ciclo
  `15/1-2/8`, sede, clientes activos, cooldown e intentos CAPTCHA y corte diario
  están expuestos en el `.env` comentado y en `.env.example`; los literales que
  quedan corresponden a invariantes técnicos internos.
- Validado de forma controlada el `2026-08-01`: dos usuarios completaron `15`
  consultas cada uno, con `reload_probe`, rotación, cierre limpio y sin
  CAPTCHA, errores ni reservas. Mantener observación en la ventana productiva
  para comparar duración, disponibilidad, `403/429` y cierres de sesión antes
  de reducir nuevamente el intervalo.
- Completado y validado el `2026-08-01`: cada selección conserva telemetría
  durable en `runs.details_json`. La prueba real registró `30/30` POST HTTP
  `200`, `30/30` finalizaciones ASP.NET y ninguna falla, diferenciando `15`
  selecciones de sede, `14` vaciados y la selección posterior al reload.
- Completado el `2026-08-01`: el intervalo fijo se reemplazó por límites
  configurables, reducidos luego a `1-2`; cada espera hace un sorteo independiente
  y la variable singular anterior queda como fallback compatible.
- Completado el `2026-08-01`: la orden que detecta un cupo compatible conserva
  la reserva inmediata. Ampliado el `2026-08-02`: luego se eligen hasta diez
  órdenes compatibles con alguna oportunidad observada y se recorren
  secuencialmente, sin pausa normal y con una sesión Playwright nueva. Tras una
  prioridad manual exclusiva, los segundos trámites van primero y la mayor
  cobertura favorece a los clientes más disponibles; una restricción simple no
  excluye si admite alguna fecha.
- Validar el traspaso ante el siguiente cupo real: medir tiempo desde la
  detección bloqueada hasta cada submit, resultado por candidato, leases,
  cierres de sesión y señales `403/429`. Confirmar también que el detector
  compatible continúa reservando primero para sí mismo.
- Comparar al menos dos o tres días con el ciclo ligero `15/1-2/8` antes de
  conservarlo como nuevo baseline.
- Revisar lecturas por hora, sesiones, errores, `slot_lost`, CAPTCHA y señales
  `403`, `429` o `recovery_backoff`.
- Cambiar una sola variable por experimento.
- Completado en código el `2026-08-09`: `OBS-006` implementa un pool deslizante
  de dos posiciones. El detector continúa su reserva y abre un auxiliar,
  priorizando al otro usuario del bloque activo si es compatible. Cada
  `registered` confirmado admite al siguiente cliente compatible.
- El corte del 1 al 8 de agosto registró seis tandas compartidas, seis intentos
  posteriores y un `registered` posterior (`16.7%`). Esto confirma una pérdida
  temporal posible; es la línea previa para evaluar el canario, no una promesa
  de mejora.
- Ampliado en código: detector + auxiliar conservan un máximo de dos sesiones y
  cada `registered` admite otro compatible. `OPPORTUNITY_BURST_MAX_CLIENTS=0`
  recorre toda la fotografía inicial de la cola durante hasta 300 segundos.
  La simulación cerró múltiples reemplazos, agotamiento, fin sin cupos,
  expiración y rollback; falta la prueba real.
- Pendiente real: confirmar `burst_id`, máximo concurrente, duración, orden de
  candidatos, resultados, liberación de claims y vuelta al observer normal.
- Evaluar después de al menos diez ráfagas reales y treinta ejecuciones
  auxiliares. Comparar reservas adicionales por tanda, tiempo a primera lectura
  y submit, `slot_lost`, `reservation_unconfirmed`, CAPTCHA, memoria y defensas
  contra la cadena secuencial.
- No cambiar otra variable mientras se evalúa `OBS-006`. Un submit
  ambiguo detiene nuevos auxiliares y nunca se reintenta; un `403`, `429`,
  defensa, pérdida de lease o fallo de coordinación detiene reemplazos. El
  comportamiento y rollback están en
  [`../operations/opportunity-burst-canary-2026-08-09.md`](../operations/opportunity-burst-canary-2026-08-09.md).
- Escalar a tres sesiones continúa siendo una mejora futura no autorizada hasta
  cerrar la muestra mínima sin incidentes. La ampliación vigente aumenta
  clientes y tiempo, pero mantiene dos sesiones como techo de carga concurrente.

## Prioridad 2 - Cerrar el corte documental

Estado: iniciado con el punto de partida del `2026-07-25`.

1. Mantener `project-status.md` como estado maestro.
2. Mantener este archivo como única cola futura.
3. Corregir documentos con texto o fechas obsoletas solo cuando afecten una
   decisión actual; los documentos históricos no se reescriben.
4. Completado el `2026-08-09`: se añadió a `history/milestones.md` el corte de
   revisión integral, las métricas del 1 al 8 de agosto y la decisión vigente
   sobre `OBS-006`.

## Prioridad 3 - Reducir riesgo operativo

Estado: iniciado.

1. Verificar backup durable cifrado y restauración fuera del volumen activo.
2. Documentar recuperación de la PC, Docker y perfiles de navegador.
3. Medir dependencia de intervención humana en WhatsApp y pagos.
4. Mantener Telegram como interfaz remota y Admin API como frontera de
   autorización.
5. Completado el `2026-08-08`: el menú remoto conserva la búsqueda guiada y
   recupera el etiquetado CAPTCHA sobre la cola sombra vigente. El flujo antiguo
   basado en un CSV separado permanece retirado.
6. Confirmar en el siguiente reinicio que Kaspersky conserva la tarea
   `AppointmentBotContinuousWorker` y el supervisor raíz PowerShell. La
   recuperación individual de los cuatro supervisores ya quedó implementada;
   falta observarla después de un reinicio real.
7. Completado el `2026-08-08`: separar las sesiones manuales operativas de las
   sesiones de consulta. Las órdenes no listas pueden abrir el portal sin
   ejecutar la navegación automática al panel de citas; la acción no reemplaza
   los controles principales de pago o postpago y cada navegador conserva
   cierre independiente.

## Retiro - Registro por invitaciones

Estado: capacidad local retirada el `2026-08-07`.

- El dashboard ya no muestra la sección ni carga su código.
- La Admin API ya no expone rutas ni inicia el conector alojado.
- Telegram conserva `/cliente_nuevo` y elimina el comando, botones y estados
  exclusivos del registro por enlace.
- PostgreSQL v43 elimina la tabla local de contactos alojados.
- El arranque y `.env.example` ya no declaran configuración del conector.
- Pendiente externo: despublicar el servicio alojado y revocar sus claves en la
  infraestructura que lo desplegó; no forma parte de este repositorio.

## Deuda técnica posterior

Estas tareas no deben adelantarse a la estabilización:

1. Romper el ciclo entre `appointments.py` y `appointment_selection.py`.
2. Sustituir mutaciones globales en módulos transicionales como
   `queue_runtime.py` por dependencias explícitas.
3. Dividir módulos grandes en cortes pequeños, sin mezclar refactor con cambios
   de comportamiento.
4. Revisar retención de `runs` para que las comparaciones históricas no dependan
   únicamente de snapshots manuales.

## Regla de ejecución

- Leer `docs/project-status.md` y este archivo antes de implementar un cambio.
- Trabajar una prioridad o experimento a la vez.
- No modificar `.env` sin autorización explícita.
- Mantener sesión, cookies, lease y confirmación independientes por orden.
- No usar CAPTCHA sombra como autoridad de reserva.
- Validar Python, Angular, runtime y documentación antes de cerrar una fase.
- Al terminar, actualizar el estado maestro y esta lista en el mismo cambio.
