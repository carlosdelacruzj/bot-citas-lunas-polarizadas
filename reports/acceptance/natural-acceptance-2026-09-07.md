# Aceptacion natural: corte del 7 de septiembre de 2026

Snapshot generado por revision de solo lectura. Corte de la consulta principal:
`2026-09-07 15:55:53 America/Lima`; comprobaciones complementarias hasta las
`16:04`. No representa el estado vivo posterior.

## Metodo y alcance

Se consultaron primero `/health` y `/api/v1/runs` de Admin API. Para los detalles
faltantes se uso PostgreSQL con `default_transaction_read_only=on`, timeout y
snapshot repetible. Se cruzaron runs, reservas, intentos, rafagas, mensajes,
jobs, recibos y revisiones; despues se comprobaron archivos y logs retenidos.
No se crearon clientes, reservas, cobros, envios ni reintentos, ni se reinicio
el runtime. Los indices CSV no se usaron como prueba suficiente.

Los casos se identifican con los primeros diez caracteres de SHA-256 del
`run_id`, `message_id` o `job_key` indicado. Los identificadores originales,
destinatarios y artefactos con datos personales permanecen fuera de Git.

## Resultado por verificacion

| Verificacion | Decision al corte | Evidencia y limite |
|---|---|---|
| Reserva con CAPTCHA previo verificado, sin CAPTCHA final | Aceptada | 11 confirmaciones enlazadas a intento y reserva; un `slot_lost` adicional. Los 12 casos conservan captura canonica, respuesta y video. |
| Tres sesiones frente a dos, fase 1.3A | Aceptada en la ventana observada | 36 rafagas alcanzaron tres sesiones reales. Sin defensas, errores tecnicos, CAPTCHA rechazado, resultados inciertos ni lease perdido registrados en las cohortes comparadas. No demuestra una mejora causal de conversion. |
| Album reserva/cobro | Aceptada con caso confirmado | Job y mensaje `sent`, un intento, dos imagenes observadas, monto y destinatario contrastados. El caso ambiguo historico permanece abierto. |
| Postpago con PDF y texto separado | Aceptada con caso confirmado | Tres PDF originales en orden, texto independiente, plantilla congelada y envio tecnico confirmado. Las conciliaciones historicas no se cuentan como nuevos exitos automaticos. |
| Aviso de registro | Parcial | Observados inicio de monitoreo y credenciales invalidas; falta variante sin solicitud pendiente. |
| Recordatorio versionado | Aceptada | 14 jobs `sent`, revision 6, fecha de cita enlazada, barrera diaria durable y captura inspeccionada. |
| Lote post-cita de las 20:00 | Aceptada | Seis lotes, 118 revisiones, limite diario respetado; un caso con acceso perdido se conserva como tal. |
| Cierre diario con adjuntos marcados | Pendiente | Los seis jobs consultados son `uncertain` en la publicacion final. Ninguno se reintento. |
| Recuperacion tras reinicio Windows | Aceptada para el runtime observado | Arranque real el 7 de septiembre, recuperacion supervisada de Telegram y 100 controles saludables. No equivale a haber recargado el refactor publicado mas tarde. |
| Primer integral posterior a v74 | Pendiente | Solo existe el integral creado el 29 de agosto, ya pagado; no sustituye un alta nueva con abono y saldo naturales. |
| Retiro de compatibilidad | Pendiente | 25 accesos retenidos a ordenes sin proyeccion y un consumidor vigente en Telegram. No se retiro ningun endpoint ni puerto. |

## Reservas y cambios del portal

Del 1 de septiembre al corte hay 58 reservas `confirmed`: 56 corresponden a
runs `registered` y dos a runs `completed` que reconocieron una programacion
existente. Estas dos ultimas no se atribuyen a un submit nuevo.
Los 106 intentos se distribuyen en 56 `confirmed` y 50 `rejected`; en esta
ventana no hay intentos ambiguos. Esto no descarta ambiguos de ventanas previas.

La rama `pre_access_verified / pre_access_only_submit` aparece entre el 5 y el
7 de septiembre: 11 reservas confirmadas y una perdida de cupo. En los 12 runs
se observa POST HTTP 200, captura previa retenida y video existente. HTTP 200
solo acredita respuesta; el estado confirmado se sustenta ademas en el portal
y en el enlace run/intento/reserva.

Caso `run_id` SHA-256 `62c79c96f0`, 7 de septiembre, 12:51:

- captura canonica inspeccionada: sede, fecha, hora y boton visibles, sin
  CAPTCHA final;
- aviso inmediato encolado a las `12:51:20.228` y enviado a las `12:51:20.943`;
  la ruta invoca el aviso tras archivar la captura y antes de entrar al submit;
- POST auditado a las `12:51:21.394`, HTTP 200, honeypot vacio;
- tiempo clic/respuesta `0.937 s`; disponibilidad/fin de reserva `3.531 s`;
- video retenido y legible con ffprobe: H.264, `19.867 s`.

El envio asincrono del aviso no se presenta como entrega anterior al clic: el
contrato es encolarlo antes del submit. La confirmacion final y su fotografia
son posteriores y distintas del aviso temprano.

Fuente: tablas `runs`, `reservation_attempts`, `reservations`; campos
`captcha_kind`, `canonical_slot_capture`, `reservation_button_interaction`,
`reservation_post_audit`, `reservation_timing`, `video_path`; log local
`logs/run-20260907-062826.log` y archivos referenciados por el run.

## Comparacion natural de rafagas

| Medida | Dos sesiones reales | Tres sesiones reales |
|---|---:|---:|
| Ventana | 24 al 29 de agosto | 31 de agosto al 4 de septiembre |
| Rafagas | 30 | 36 |
| Ejecuciones enlazadas a runs | 93 | 160 |
| Reservas nuevas confirmadas | 52 | 46 |
| Perdidas de cupo | 22 | 49 |
| Bloqueos por regla | 2 | 17 |
| Intentos CAPTCHA registrados | 76 | 112 |
| Intentos CAPTCHA por ejecucion | 0.817 | 0.700 |
| Defensas, errores tecnicos, rechazos CAPTCHA o resultados inciertos registrados | 0 | 0 |
| Leases perdidos | 0 | 0 |

Todos los runs con intento CAPTCHA en esas cohortes registraron uno solo.
Hubo ademas cinco rafagas configuradas para tres que solo alcanzaron dos; se
excluyen de la columna de tres sesiones reales. El total configurado para tres
fue 41 rafagas y 170 ejecuciones.

El cierre corresponde a la seguridad observada de la fase 1.3A. La proporcion
de confirmaciones bajo de 52/93 a 46/160 y las perdidas de cupo aumentaron:
no se afirma mayor eficacia. Las ventanas, reglas, oportunidades y clientes
son distintos; no hay experimento controlado. Esta comparacion es anterior
a la nueva rama sin CAPTCHA final y no demuestra su comportamiento concurrente.

Fuente: `opportunity_bursts`, `opportunity_burst_executions`, `runs`, incluyendo
`max_active_sessions`, `lease_lost`, resultados y detalle de intentos CAPTCHA.

## Comunicaciones y seguimiento

La consulta incluye 180 jobs: 170 `sent` y diez `uncertain`. Estos ultimos
conservan `attempt_count=1`: seis cierres diarios, un album y tres postpagos.
Los tres postpagos tienen conciliacion `completed_missing`; esa decision no
reescribe su resultado tecnico original.

- Album, `message_id` SHA-256 `1f112d15d1`: envio registrado el 7 de septiembre
  a las `12:52:04`; plantillas confirmacion revision 2 y cobro revision 1.
  El log acredita `items=2`; la captura muestra constancia y QR con sus
  confirmaciones visibles. El destinatario coincide con el mensaje persistido
  y el monto de S/50 con su pago. La captura generica se cotejo con la hora,
  contenido y mensaje: su nombre por si solo no identifica un envio historico.
- Postpago, `message_id` SHA-256 `f501200bcd`: envio el 7 de septiembre a las
  `14:48:08`, plantilla `post_payment_confirmation` revision 2, un intento y
  sin conciliacion. Se observaron `Formato_Tramite.pdf`, `requisitos.pdf` y
  `Formato_Tramite_Ejemplo.pdf`, en ese orden, seguidos del texto separado.
  Los originales existen; log `documents=3`, destinatario y captura coinciden.
- Registro: 49 avisos de monitoreo con revisiones 3 a 6 y tres de credenciales
  invalidas con revision 1. Texto congelado no vacio; cero duplicados por
  orden/variante/ciclo. Capturas inspeccionadas para jobs SHA-256 `bf068d9ce1`
  y `e9022bfee1`. No aparece `registration_no_pending_request` en la ventana.
- Recordatorios: 14/14 coinciden con la fecha de su reserva y conservan texto
  y revision 6. Seis controles diarios `complete`, anticipacion de dos dias y
  cero duplicados de job por reserva/fecha. Captura del job `9dfc1a68eb`
  inspeccionada. La jornada del 6 se proceso tarde, a las 21:43-21:46.
- Post-cita: 18 revisiones el dia 1 y 20 por dia del 2 al 6. Los primeros
  cinco lotes comenzaron alrededor de las 20:02-20:04; el dia 6 se recupero a
  las 21:44. Los 118 resultados persistieron: 72 esperando actualizacion,
  28 observacion sin avance, 16 en progreso, uno completado y uno con acceso
  perdido por credenciales. Completar una revision no significa completar el
  tramite del cliente.
- Cierre diario: los seis errores indican falta de confirmacion de la
  publicacion final. El envio parcial de imagenes no cierra el paquete. Se
  mantiene pendiente investigar y conciliar sus componentes sin reenviar.

Las conclusiones de WhatsApp son tecnicas; no afirman llegada ni lectura.
Fuentes: `whatsapp_automation_jobs`, `whatsapp_messages`,
`whatsapp_followup_messages`, `appointment_reminder_days`, tablas post-cita,
capturas locales y `logs/run-20260907-062824.log`.

## Operacion y pendientes reales

Windows arranco el 7 de septiembre a las `06:27:30`. El supervisor inicio sus
hijos; Telegram fallo dos veces porque Admin API aun no respondia y se recupero
desde las `06:28:40`. Hay 100 controles de lease saludables entre las 07:34 y
15:59. A las 16:00 PostgreSQL mostraba worker sin pausa, en observacion, con
ultimo check fresco, cero errores consecutivos y lease hasta las 16:04.
`/health` informa `api_only`; su `worker_running=false` no describe el lease
del proceso worker separado. No se forzo un reinicio durante esta revision.

La ventana de compatibilidad vencida no acredita cero consumidores: 112
archivos de log retenidos de la ventana contienen 25 GET de ordenes sin
proyeccion. `services/telegram/admin_api_client.py` mantiene ese consumo.
No se encontraron accesos al resumen mensual en esos archivos, pero la
retencion no demuestra siete dias completos sin accesos a todos los contratos
ni al puerto 8765. Primero hay que migrar consumidores y medir otra ventana.

El unico integral sigue siendo el creado el 29 de agosto: S/160 pagados y
S/71.40 de tasa activa. Falta observar una nueva alta posterior a v74 con
abono de S/80, tasa, reserva, saldo de S/80, mensaje y resumen coherentes.

El cierre tecnico de 5.5.1 se publico en `cfdcef4`: 181 pruebas y 24 subtests,
cobertura critica aprobada, 197 modulos sin ciclos y ambas ejecuciones de CI
aprobadas. La siguiente extraccion es 5.5.2. El proceso Telegram que arranco
antes de ese refactor no se reinicio para convertir esta revision en despliegue.
