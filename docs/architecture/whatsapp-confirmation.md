# Confirmacion de WhatsApp y tiempos

La lectura de burbujas obtiene identidad, texto completo (incluidos emojis) y
marcadores en una sola consulta DOM. Las comprobaciones de texto/PDF excluyen las
identidades anteriores al clic; solo despliegan Leer mas del candidato exacto.
Relojes, errores y cargas visibles vetan confirmacion; marcadores ocultos no deciden.
Los albumes conservan su comprobacion de cantidad y componentes del grupo.

Texto espera 60 s mas 5 s de gracia; PDFs esperan 60 s. El presupuesto exterior
incluye preparacion y componentes: texto 180 s, album 240 s, PDFs 120 s mas 60 s
por archivo, resumen 180 s mas 75 s por lote. Paquetes y resumen tienen techo de
510 s. Al vencer se impiden componentes nuevos, se avisa confirmacion demorada y
se esperan hasta 60 s adicionales (techo absoluto 570 s, lease 600 s), sin reenviar.
La cola no admite otro trabajo automatico mientras el navegador anterior siga activo;
un comando que vence en cola no inicia su accion.

Si el mismo intento termina confirmado en la gracia, se persiste el envio y se
encola una actualizacion de Telegram. Si termina despues, solo los nuevos trabajos
con marcador `confirmation_deadline_exceeded:<attempt_id>` pueden cerrar su
incidencia automaticamente: intento terminado, mensaje exacto y todos los
componentes confirmados con identidad o captura. Conserva `status=uncertain` y
error original; agrega `confirmed_complete` con actor `system:late_confirmation`.
No toca historicos sin ese marcador, decisiones manuales ni trabajos con recuperacion.
La actualizacion Telegram se encola atomicamente con el cierre y se deduplica.
Esto es observacion del mismo envio, nunca otro intento ni prueba de lectura.

Logs registran duracion de espera, preparacion por componente, confirmacion y
cierre, con identificadores tecnicos; no registran texto ni contacto completo.
La validacion aislada no sustituye la aceptacion del siguiente caso natural lento.

