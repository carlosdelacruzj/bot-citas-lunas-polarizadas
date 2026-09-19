# Contrato de comunicaciones WhatsApp

Estado: vigente. Ultima verificacion: `2026-09-08`.

Codigo propietario: `src/appointment_bot/core/whatsapp_delivery.py`,
`src/appointment_bot/browser/whatsapp/`,
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

Un reloj o estado pendiente visible veta `sent`. Un check o etiqueta exacta de
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
el componente exacto. El diagnostico durable conserva fase, componente,
destinatario enmascarado, identificadores de contexto y la ruta de la captura
cuando el navegador pudo producirla.

Dispatcher y scheduler solo admiten trabajos `queued` o `blocked`. Un lease
`running` vencido se cierra como `uncertain`; ni el recuperador ni los lotes de
recordatorios vuelven a encolarlo. Un nuevo trabajo de recuperacion requiere una
accion separada y autorizada del operador.

## Paquetes

Albumes y postpagos conservan estado por componente. El sistema no repite el
clic de adjuntos después de un posible envio. Si una recuperacion es autorizada,
crea un trabajo separado y enlaza la conciliacion del original.

Los postpagos nuevos referencian los PDF originales definidos por el contrato
de negocio; no crean copias por cliente. El orden documental debe preservarse.

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

La revision guiada puede registrar que el flujo ya estaba completo, completar
solo lo faltante o cerrar sin envio. Debe conservar capturas, componentes y
resultado tecnico original. Revisar no equivale a reintentar.

La observacion natural se rige por
[`../operations/whatsapp-natural-acceptance.md`](../operations/whatsapp-natural-acceptance.md).

## Reintento manual de fallo total

El dashboard permite reintentar avisos de registro, albumes y postpago mediante
`POST /api/v1/whatsapp-automation-jobs/{job_key}/retry`. Un resultado incierto
exige `confirmed_no_delivery=true`, tras comprobar en el chat que no salio ningun
componente. Un envio parcial se completa manualmente, solo con lo faltante.

El servidor bloquea trabajos activos, resueltos, enviados o superados por otro
intento. La clave determinista de recuperacion y el bloqueo transaccional del
original evitan duplicados por doble clic o repeticion HTTP. La respuesta `202`
indica aceptacion, no entrega; el dispatcher unico procesa el nuevo trabajo.

El original conserva estado tecnico y error; su conciliacion `dismissed` guarda
actor, fecha y clave del nuevo intento en la misma transaccion que lo encola.
El nuevo trabajo reutiliza el mensaje preparado y su revision. Si el fallo fue
anterior a preparar el paquete, el dashboard lo indica y el nuevo intento usa
los datos actuales. Los avisos conservan siempre su texto y destinatario.
