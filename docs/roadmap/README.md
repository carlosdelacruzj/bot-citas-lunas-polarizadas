# Trabajo pendiente

Ultima priorizacion: `2026-08-09`.

Esta es la unica lista de trabajo futuro y su orden de ejecucion. El estado de
lo construido, validado y activo vive en
[`../project-status.md`](../project-status.md). Los contratos, runbooks,
incidentes, reportes y bitacoras aportan detalle o evidencia, pero no pueden
crear colas paralelas.

## Reglas de ejecucion

1. Trabajar una sola fase o experimento de comportamiento a la vez.
2. No mezclar refactor, cambios visuales y cambios del motor de reservas.
3. No modificar `.env` sin autorizacion explicita.
4. No usar CAPTCHA local como autoridad de reserva: 2Captcha permanece como
   unica respuesta enviada al portal hasta cerrar el gate prospectivo.
5. No reintentar automaticamente un submit o envio de WhatsApp ambiguo.
6. Antes de reiniciar, comprobar submissions, leases, sesiones y trabajos
   WhatsApp activos.
7. Una fase solo termina cuando cumple sus criterios de aceptacion, actualiza
   `project-status.md` y deja este archivo alineado.

## Orden inmediato

1. Completar la **Fase 1 - Seguridad y medicion del canario** antes de seguir
   evaluando o ampliar `OBS-006/OBS-007`.
2. Corregir en la **Fase 2** los falsos pendientes y la mezcla temporal del
   Resumen; no tomar decisiones comerciales desde la comparacion actual de mes
   parcial contra mes completo.
3. Incorporar controles seguros y salud compuesta en la **Fase 3**.
4. Cerrar backup externo, watchdogs y dependencias vulnerables en la **Fase 4**.
5. Reorganizar flujos y datos del dashboard antes del rediseño visual.
6. Ejecutar deuda tecnica solo despues de estabilizar las fases funcionales.

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
- modificar seleccion de sede, CAPTCHA o confirmacion;
- promover modelos locales;
- rediseñar el dashboard.

### Validacion

- simulaciones de agotamiento, reemplazo, pausa, expiracion y rollback;
- validaciones Python y Angular aplicables;
- autorizacion explicita antes de agregar tests automatizados nuevos;
- luego, muestra real minima de `10` rafagas y `30` auxiliares;
- comparar contra el baseline del 1 al 8 de agosto.

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

## Fase 4 - Resiliencia y seguridad

Prioridad: **P1**.

Objetivo: recuperar la operacion ante perdida de PC, volumen, proceso o perfil,
y reducir riesgos de dependencias y exposicion local.

### Alcance

1. Backup automatico cifrado fuera de la PC con retencion diaria/semanal,
   checksum y alarma por antiguedad.
2. Restauracion mensual probada de PostgreSQL y metadatos necesarios; documentar
   recuperacion de Docker, perfiles y configuracion operativa.
3. Monitor externo real; mientras n8n permanezca local, limitar `5678` a
   loopback y no publicar dashboard/Admin API.
4. Rotar logs por fecha y tamaño; mostrar espacio libre y crecimiento.
5. Actualizar Angular desde `20.3.26` a una version corregida `20.3.27+`, con
   build y auditoria posterior.
6. Definir retencion por finalidad para mensajes, jobs WhatsApp, Post-cita,
   capturas y telemetria detallada.
7. Minimizar permanencia de credenciales reveladas en Telegram sin romper el
   comprobante autorizado del alta.

### Criterio de aceptacion

Existe un backup externo reciente, una restauracion completa documentada y una
alerta que sobrevive a la caida de la PC operativa; npm no reporta la
vulnerabilidad Angular identificada en este corte.

## Fase 5 - Flujos funcionales del dashboard

Prioridad: **P1/P2**.

Objetivo: priorizar decisiones de clientes y dinero, y retirar diagnosticos de
la superficie principal.

### Alcance

1. Separar Pendientes comerciales del backlog de entrenamiento CAPTCHA.
2. Mostrar antiguedad, vencimiento, responsable y siguiente accion.
3. Mover pruebas de WhatsApp a `Diagnostico de comunicaciones`, con destinatario
   y alcance visibles.
4. Implementar reconciliacion guiada: `recibido`, `no recibido`, `sigue
   incierto`; solo `no recibido` permite preparar un reenvio deliberado.
5. Sacar configuracion CAPTCHA avanzada de Resumen; dejar una franja cuando el
   muestreo este activo.
6. Mantener IDs, `details_json`, estados crudos y copiar snapshot dentro de
   detalle tecnico.
7. Añadir frescura: ultima reserva, cupo, defensa, WhatsApp confirmado, backup y
   actualizacion de cada fuente.
8. Cargar Post-cita y textos sensibles de manera progresiva y paginada; evitar
   transportar las 108 historias completas cuando solo se necesita el resumen.

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
- siguientes trabajos WhatsApp: album, postpago, aviso de registro y resumen
  diario, preservando `uncertain` sin reintento;
- siguiente cierre diario: confirmar por separado resumen, imagenes y
  publicacion;
- cada 100 CAPTCHA frescos: registrar avance v6 sin reentrenar el corte;
- siguiente reinicio de Windows: tarea, supervisor raiz, Docker, Admin API,
  worker, Telegram, CAPTCHA y perfiles.

## Trabajos externos o no autorizados

- Despublicar el registro alojado y revocar claves: pendiente fuera de este
  repositorio.
- Cloudinary para evidencia publica: diseño documentado, pero su despliegue no
  esta autorizado en esta fase.
- Tres sesiones concurrentes: no autorizado.
- CAPTCHA local como autoridad: no autorizado hasta superar el gate prospectivo
  de mas de `99%` sobre al menos `500` muestras frescas.
- Reescritura del historial Git para borrar datos antiguos: requiere una
  operacion separada, respaldo y autorizacion explicita.
