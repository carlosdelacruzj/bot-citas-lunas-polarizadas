# Trabajo pendiente

Última priorización: `2026-08-01`.

Esta es la única lista de tareas futuras y el orden vigente de ejecución. El
estado de lo construido, validado y observado vive en
[`../project-status.md`](../project-status.md).

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

### WhatsApp automático

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
  reintento manual autorizado terminó `sent` con cuatro confirmaciones. Validar
  el siguiente disparo automático directamente desde el cierre de las 18:00.
- Completado el `2026-07-30`: el resumen diario incorpora después del álbum una
  publicación variable para TikTok, sin IA ni consumo de tokens. El generador
  conserva datos comerciales fijos y rota 138,240 combinaciones por fecha. Una
  prueba controlada terminó con el texto completo y doble check azul después de
  normalizar los emojis transformados por WhatsApp; la prueba repetida añadió
  soporte para historial virtualizado e identidad de nuevas burbujas. Validar
  el recorrido completo desde el siguiente cierre diario.
- No habilitar reintentos automáticos para resultados ambiguos.

### Reglas y backoff

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

### Observer

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
- Completado el `2026-07-30`: eliminadas las promociones automáticas de
  prioridad y el diferimiento entre clientes. Validar en el siguiente cupo real
  que la orden que lo detecta reserva inmediatamente, que las demás conservan
  su prioridad y que los empates respetan el orden de registro.
- Comparar al menos dos o tres días con el ciclo ligero `15/1-2/8` antes de
  conservarlo como nuevo baseline.
- Revisar lecturas por hora, sesiones, errores, `slot_lost`, CAPTCHA y señales
  `403`, `429` o `recovery_backoff`.
- Cambiar una sola variable por experimento.
- Mejora futura `OBS-006`, en evaluación y todavía no aprobada: conservar una
  sola sesión durante la operación normal y, ante disponibilidad completa real,
  iniciar un pool deslizante de hasta tres clientes. El detector reserva sin
  esperar; hasta dos sesiones nuevas se abren en paralelo y cada posición
  liberada por una reserva confirmada puede tomar el siguiente cliente
  compatible. La ráfaga termina al agotarse clientes, desaparecer los cupos o
  alcanzar sus guardas.
- Antes de implementar `OBS-006`, diseñar el controlador separado, el estado
  multisesión, claims/heartbeats independientes, cancelación conjunta, límites
  de duración/clientes y telemetría. Preparar primero detrás de una bandera
  desactivada y validar apertura/cierre sin enviar reservas.
- No activar `OBS-006` mientras se evalúe otra variable operativa. Los criterios,
  tiempos medidos, riesgos, métricas y pasos están en
  [`../optimization.md`](../optimization.md#hipótesis-futura-ráfaga-multicliente).

## Prioridad 2 - Cerrar el corte documental

Estado: iniciado con el punto de partida del `2026-07-25`.

1. Mantener `project-status.md` como estado maestro.
2. Mantener este archivo como única cola futura.
3. Corregir documentos con texto o fechas obsoletas solo cuando afecten una
   decisión actual; los documentos históricos no se reescriben.
4. Añadir a `history/` un nuevo cierre cuando termine esta fase de
   consolidación.

## Prioridad 3 - Reducir riesgo operativo

Estado: iniciado.

1. Verificar backup durable cifrado y restauración fuera del volumen activo.
2. Documentar recuperación de la PC, Docker y perfiles de navegador.
3. Medir dependencia de intervención humana en WhatsApp y pagos.
4. Mantener Telegram como interfaz remota y Admin API como frontera de
   autorización.
5. Completado el `2026-08-01`: simplificado el menú remoto, retirada la función
   antigua de etiquetado CAPTCHA y convertida la búsqueda por botón en un flujo
   guiado que no requiere recordar comandos.
6. Confirmar en el siguiente reinicio que Kaspersky conserva la tarea
   `AppointmentBotContinuousWorker` y el supervisor raíz PowerShell. La
   recuperación individual de los cuatro supervisores ya quedó implementada;
   falta observarla después de un reinicio real.

## Integración - Invitaciones y registro alojado

Estado: integración controlada completada el `2026-07-29`; producción y datos
reales bloqueados.

El contrato alojado v1, la infraestructura remota, los secretos y la prueba
controlada ya están implementados. La activación con datos reales continúa
bloqueada hasta cerrar las condiciones de seguridad y recibir autorización
expresa.

El alcance integrado comprende:

1. añadir al dashboard local una sección de invitaciones;
2. permitir crear, copiar, consultar, revocar y reemitir enlaces;
3. seleccionar o registrar el WhatsApp antes de crear la invitación, conservar
   el número completo en local y enviar a la API alojada solo una referencia
   opaca y una pista parcialmente oculta;
4. hacer que el navegador llame solo a la Admin API local;
5. implementar en la Admin API un cliente HTTPS autenticado hacia la API
   alojada, con secreto fuera del frontend y de los logs;
6. implementar un conector saliente que consulte y reclame solicitudes
   pendientes con lease e idempotencia;
7. entregar cada solicitud a las fronteras internas existentes para validar el
   portal y, cuando corresponda, crear una sola orden;
8. devolver a la nube solo estados mínimos y sanitizados;
9. conservar PostgreSQL local como registro operativo definitivo;
10. mantener WhatsApp, Telegram, evidencia y reservas exclusivamente en local;
11. informar por el WhatsApp existente cuando una validación diferida requiera
    corrección y permitir emitir una invitación nueva;
12. probar primero con una cuenta y un número controlados, manteniendo el alta
    manual como alternativa.

Progreso:

- sección `Invitaciones` añadida al dashboard;
- creación, copia inmediata, listado, revocación y reemisión añadidas;
- WhatsApp completo y nombre de referencia conservados en PostgreSQL local;
- cliente HTTPS con HMAC-SHA256 implementado, sin secretos en Angular;
- conector saliente con claim, lease, renovación, liberación y ACK implementado;
- descifrado RSA-OAEP-256 y AES-256-GCM implementado con reconstrucción de AAD;
- payload validado nuevamente después del descifrado;
- registros de fecha quedan pausados hasta coordinación por WhatsApp;
- registros generales atraviesan la frontera existente de creación y
  prevalidación de órdenes;
- resultado alojado limitado a categorías sanitizadas;
- conector integrado al proceso de la Admin API, desactivado por defecto;
- modo `controlled` disponible para pruebas ficticias sin crear una orden;
- migración PostgreSQL v38 preparada;
- Ruff, compilación Python y build Angular correctos;
- secretos generados bajo `.runtime/hosted-registration/` y cargados por el
  supervisor del dashboard sin modificar `.env`;
- PostgreSQL operativo migrado a `v39`;
- Worker y D1 desplegados bajo
  `https://registro.citaspolarizadasperu.com`;
- cliente local identificado con un `User-Agent` propio para evitar el bloqueo
  automático de Cloudflare sin relajar HMAC;
- conector activado en modo `controlled`;
- prueba ficticia completa terminada en `accepted`, con `order_id` nulo y sin
  variar las `95` órdenes existentes;
- limpieza terminal del sobre, contacto, pista y lease confirmada en D1;
- flujo de operación mejorado con nombre opcional y editable, advertencia por
  WhatsApp repetido, reemplazo directo y comprobante visible para copiar el
  enlace o el mensaje;
- interfaz de invitaciones armonizada con los tokens del dashboard: paleta
  semántica por estado, confirmaciones propias para acciones sensibles y
  comprobante contextual para primera emisión o reemplazo;
- HTTP `409` de reemisión corregido en la API alojada mediante una secuencia
  compatible con la clave foránea y una excepción limitada a
  `credentials_invalid`;
- desincronización local posterior corregida: el listado ya no sustituye la
  invitación más nueva por una histórica del mismo contacto y PostgreSQL se
  reconcilia por `contact_ref` al reemitir;
- excepción PostgreSQL que se mostraba como desconexión corregida mediante una
  clave de búsqueda explícita; el contacto de prueba quedó sincronizado y con
  una sola invitación activa después de revocar cuatro accesos históricos;
- pendiente únicamente el trabajo previo al modo `production`: respaldo
  cifrado externo de la clave privada, revisión legal, procedimiento de
  incidente, prueba visual directa y autorización expresa para datos reales.

Condiciones obligatorias:

- no abrir puertos ni publicar la Admin API;
- no conectar la nube directamente a PostgreSQL;
- no generar en el navegador ni guardar localmente el token de invitación;
- no volver a pedir el WhatsApp dentro del registro alojado;
- no enviar ni conservar el número completo de WhatsApp en la nube;
- no depender de una página persistente de estado del cliente;
- no exponer credenciales del portal o de servicio en logs;
- no crear órdenes por abrir un enlace;
- no activar datos reales hasta que `lunas-polarizadas-clientes` despliegue y
  valide de extremo a extremo la parte alojada que consume este proyecto.

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
