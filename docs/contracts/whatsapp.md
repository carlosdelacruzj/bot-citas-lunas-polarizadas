# Contrato de comunicaciones WhatsApp

Estado: vigente. Ultima verificacion de codigo: `2026-10-07`.

Codigo propietario: `src/appointment_bot/core/whatsapp_delivery.py`, `src/appointment_bot/browser/whatsapp/`,
`src/appointment_bot/services/whatsapp*` y `src/appointment_bot/db/whatsapp*`.

## Propiedad y cola

Admin API posee el unico perfil persistente de WhatsApp Web y su dispatcher.
Otros procesos preparan o encolan trabajos durables; no abren emisores paralelos.

Cada job conserva tipo, orden, payload, deduplicacion, intentos, resultado
tecnico y, cuando aplica, mensaje o paquete asociado.

Detectar o bloquear varios expedientes pendientes no encola WhatsApp. Al
resolver uno o todos, Dashboard y Telegram permiten revisar y autorizar un unico
aviso conjunto, o registrar que el cliente ya fue informado y omitirlo. Mantener
pausado no admite envio. La vista previa no modifica ordenes ni encola trabajos.
Confirmar verifica una huella del listado, condiciones, contacto, texto y revision
de plantilla; un cambio exige revisar nuevamente. Resolucion y aviso se guardan
en una sola transaccion. Repetir la misma decision no duplica el trabajo.

El aviso elige `registration_monitoring_started` para un tramite y
`registration_monitoring_started_multiple` para varios. Ambas plantillas son
editables por separado en Mensajes. El texto individual conserva placa,
expediente, servicio, precio y disponibilidad sin encabezados colectivos. El conjunto
incluye solo expedientes seleccionados, placas, servicio, precio o ausencia de
cobro por expediente y total. Agrupa restricciones iguales y separa las distintas.
Con varios expedientes advierte que las citas pueden tener fechas u horas
distintas. Los expedientes numericos se conservan completos en el texto dirigido
al cliente. Las subordenes y las revalidaciones posteriores omiten bienvenidas
individuales; reserva, cobro y postpago siguen siendo independientes por orden.

La seleccion automatica de un unico expediente incluye su identidad, precio y
condiciones. El contexto de ejecucion conserva `charge_required` desde la orden
persistida para preparar correctamente avisos con cobro y sin cobro.
Si todos los candidatos ya tienen cita, el preflight informa al
operador y no envia la plantilla que pide crear una solicitud pendiente.
Las citas externas y el historial incierto nunca generan cobro ni aviso de reserva.

## Estados y evidencia

- `sent`: evidencia tecnica suficiente de salida;
- `uncertain`: hubo riesgo de interaccion o envio, pero no confirmacion segura;
- `failed`: fallo demostrado antes de iniciar una posible interaccion;
- `dismissed`: decision de revision que cierra el trabajo original sin cambiar
  su resultado tecnico historico.

La confirmacion admite checks SVG con titulo exacto y exige identidad estable
`data-id`, propia o del contenedor; cambios de HTML no cuentan como otro mensaje.
Los textos largos se despliegan con Leer mas dentro de la burbuja correspondiente,
y se leen tambien los emojis representados como imagenes. La verificacion exige
todo el contenido alfanumerico, sin aceptar fragmentos por palabras conocidas.
Un reloj, error o estado pendiente visible veta `sent`. Antes de adjuntar o iniciar
un nuevo texto, un envio anterior visible con reloj, carga o error detiene
el flujo y conserva captura; no se vuelve a pulsar su reintento. La vista previa
exige controles y nombres fuera de las burbujas historicas. El compositor
normal debe estar visible, habilitado y sin una ventana que lo cubra. En albumes enviados como grupo,
no se atribuye una confirmacion parcial a una imagen sin poder identificarla: se
conserva la incertidumbre del grupo hasta confirmar todos sus componentes. Un check o etiqueta exacta de
enviado, entregado o leido puede confirmar el componente correspondiente.
Marcadores ocultos o etiquetas genericas no deciden.

`sent`, llegada al destinatario, lectura y confirmacion del cliente son hechos
distintos. `uncertain` nunca se reintenta automaticamente.

Cada intento automatico se clasifica mediante cuatro fases:

1. `pre_interaction`: validacion y preparacion sin accion posible sobre el chat;
2. `interaction_started`: el navegador entro en el limite donde pudo enviar;
3. `confirmation_observed`: WhatsApp mostro evidencia tecnica de salida;
4. `confirmation_persisted`: la confirmacion quedo guardada.

Solo un resultado que demuestre `pre_interaction` puede terminar en `failed`.
Una excepcion de navegador, persistencia o callback desde
`interaction_started` termina en `uncertain`, incluso si no puede determinarse
el componente exacto. Desde v77, cada intento registra un manifiesto y eventos por PDF, imagen o texto en PostgreSQL.
`not_attempted` significa que no se inicio su accion; `uncertain`, que pudo salir;
`confirmed`, que se observo confirmacion tecnica. Los eventos son append-only.
El checkpoint se persiste antes de enviar; si falla, no se inicia esa accion.
Un comando vencido impide iniciar componentes posteriores. La recuperacion queda
bloqueada hasta registrar el cierre del comando del navegador. Los historicos sin
manifiesto se mantienen sin detalle; no se reconstruyen confirmaciones.

La busqueda por usuario admite un resultado unico de Chats o de Usuarios que no estan en tus contactos. El segundo exige usuario exacto en el titulo y abre el resultado sin agregar contactos. Si el encabezado carga un nombre comercial, el usuario exacto del compositor permite verificar el destinatario; sin identidad suficiente se detiene antes de escribir.
Antes de buscar usuarios, se cierra el aviso conocido de novedades y se verifica su desaparicion; si permanece, se detiene sin escribir ni enviar, con captura. El diagnostico durable conserva fase, componente,
destinatario enmascarado, identificadores de contexto y la ruta de la captura
cuando el navegador pudo producirla. Cuando falta confirmacion se conserva un diagnostico local acotado de las
ultimas burbujas visibles. Cada captura usa un nombre seguro para
Windows y unico bajo `.runtime/whatsapp-evidence/`; los reintentos no la sobrescriben.

Dispatcher y scheduler solo admiten trabajos `queued` o `blocked`. Un lease
`running` vencido se cierra como `uncertain`; ni el recuperador ni los lotes de
recordatorios vuelven a encolarlo. Un nuevo trabajo de recuperacion requiere una
accion separada y autorizada del operador.

## Paquetes

Las imagenes se seleccionan desde el control visible Fotos y videos y su
selector de archivos, sin reutilizar inputs genericos de imagen. Un album exige
un selector que acepte multiples archivos. El boton de envio del album debe
identificarse por nombre accesible o icono exacto. Textos y PDFs usan el mismo
control identificado, sin coordenadas, clicks forzados ni Enter como alternativa.
Los PDFs se adjuntan desde el control Documento; un fallo al seleccionar archivos
no repite la seleccion. Un cierre de navegador no vuelve a preparar el borrador.
Cada imagen conserva su descripcion: constancia con confirmacion, Yape con cobro.
Antes del unico envio se seleccionan ambas de nuevo y se exige coincidencia
completa de cada texto; si falla, se detiene sin unir textos ni enviar.

Albumes y postpagos conservan estado por componente. El sistema no repite el
clic de adjuntos después de un posible envio. Si una recuperacion es autorizada,
crea un trabajo separado y enlaza la conciliacion del original.

El envio automatico postpago confirma primero el texto y despues adjunta y envia
los PDFs. Un texto ambiguo detiene el paquete con PDFs pendientes sin intentar.
La decision final usa las identidades nuevas confirmadas de cada PDF; al vencer la espera hace una ultima lectura, sin reenviar.
El resumen diario confirma primero su texto, despues la publicacion de TikTok
y al final las imagenes en lotes de cuatro. Un componente ambiguo detiene los
siguientes. Su espera global agrega 30 s por lote a los 180 s base, hasta 540 s,
por debajo del lease de 600 s; conserva confirmaciones y nunca reenvia al vencer.
Las recuperaciones omiten componentes ya confirmados y conservan el orden de
los documentos seleccionados; no modifican el contenido congelado.

Los postpagos nuevos referencian los PDF originales, sin copias por cliente, y preservan su orden.

Para paquetes nuevos, la autoridad de seleccion y orden es
`.runtime/whatsapp-followup/followup-details.json`, campo `documents`. Cada ruta
debe resolver a un PDF original existente bajo `pdfs/`; el API vuelve a validar
esa pertenencia antes de servir un adjunto. El orden vigente es:

1. `pdfs/Formato_Tramite.pdf`;
2. `pdfs/requisitos.pdf`;
3. `pdfs/Formato_Tramite_Ejemplo.pdf`.

Al preparar el mensaje, la lista ordenada queda congelada dentro de sus pasos en
PostgreSQL. Cambiar la configuracion local solo afecta paquetes futuros y no
reescribe mensajes historicos o ya preparados.
## Plantillas

Las plantillas se versionan en PostgreSQL y usan variables allowlisted. Preview,
edicion, restauracion y guardado aplican revision optimista.

`whatsapp_message_templates` y `whatsapp_message_template_versions` son la
unica autoridad de texto para plantillas nuevas e historicas, incluido
`appointment_reminder`. El control de recordatorios conserva modo, anticipacion
y su propia revision operativa, pero no duplica el texto de la plantilla.

Al preparar un trabajo futuro se congela:

- texto renderizado;
- clave de plantilla;
- revision utilizada.

Una edición nunca modifica trabajos históricos, preparados o encolados.

## Conciliacion

El cierre administrativo `dismissed` admite tambien resumenes y recordatorios historicos, exige motivo y rechaza intentos de navegador sin cerrar. Conserva estado tecnico y no envia mensajes.

La revision guiada puede registrar que el flujo ya estaba completo, completar
solo lo faltante o cerrar sin envio. Debe conservar capturas, componentes y
resultado tecnico original. Revisar no equivale a reintentar.

La observacion natural se rige por
[`../operations/whatsapp-natural-acceptance.md`](../operations/whatsapp-natural-acceptance.md).

## Reintento manual de fallo total

El dashboard permite recuperar avisos de registro, albumes y postpago mediante
`POST /api/v1/whatsapp-automation-jobs/{job_key}/retry`. Un resultado incierto
con componentes inciertos exige `confirmed_no_delivery=true`, tras comprobar en
el chat que los componentes a recuperar no salieron y no siguen pendientes.
Con manifiesto durable, el nuevo trabajo selecciona solo los componentes no
confirmados y hereda los confirmados. Los componentes sin intentar no requieren
afirmar que todo el paquete fallo. Sin manifiesto historico, la recuperacion
conserva el criterio anterior de fallo total. Nunca se recupera automaticamente.

El servidor bloquea trabajos activos, resueltos, enviados o superados por otro
intento. La clave determinista de recuperacion y el bloqueo transaccional del
original evitan duplicados por doble clic o repeticion HTTP. La respuesta `202`
indica aceptacion, no entrega; el dispatcher unico procesa el nuevo trabajo.

El original conserva estado tecnico y error; su conciliacion `dismissed` guarda
actor, fecha y clave del nuevo intento en la misma transaccion que lo encola.
El nuevo trabajo reutiliza el mensaje preparado y su revision. Si el contacto
actual difiere del destinatario congelado, el servidor bloquea la recuperacion
sin confirmar `expected_recipient` contra el contacto vigente. Para un album
sin componentes confirmados, esa confirmacion crea un mensaje nuevo con el
contacto corregido y conserva texto, adjuntos y revisiones del anterior. El
original no cambia; un contacto que cambia durante la revision exige actualizar.
Otros tipos o albumes parcialmente confirmados requieren revision manual. Si el fallo fue
anterior a preparar el paquete, el dashboard lo indica y el nuevo intento usa
los datos actuales. Los avisos conservan siempre su texto; el cambio de destinatario solo admite la recuperacion de album descrita arriba.

La recuperacion operativa del resumen puede encolar solo las fotos pendientes,
con enlace al trabajo original y textos vacios. El dispatcher exige ese enlace
para omitir TikTok; el manifiesto incluye exclusivamente los componentes presentes.
Una captura con doble check permite conciliar manualmente un texto ambiguo,
sin convertir su resultado tecnico original en `sent` ni reenviarlo.
