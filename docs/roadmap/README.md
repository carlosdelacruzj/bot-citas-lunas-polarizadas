# Trabajo pendiente

Ultima priorizacion: `2026-09-19`.

Esta es la unica cola futura. El estado construido vive en
[`../project-status.md`](../project-status.md); cierres, incidentes y resultados
fechados se recuperan mediante [`../history/`](../history/) o viven como
generados en `reports/`.

## Reglas

1. Trabajar un cambio de comportamiento a la vez.
2. No mezclar refactor, rediseño visual y motor de reservas.
3. No modificar `.env` sin autorizacion explicita.
4. No reintentar automaticamente un submit o WhatsApp ambiguo.
5. Antes de reiniciar, comprobar trabajo activo.
6. Cerrar una tarea solo con evidencia de aceptacion.

## Congelamiento temporal de features

La implementacion tecnica de las fases 0 a 4 del
[`plan integral de endurecimiento`](development-hardening-plan.md) esta completa.
La fase 2.6 conserva pendiente su aceptacion funcional: el esquema `v74` ya esta
activo, pero el paquete integral debe cerrar su primer caso natural posterior
antes de otro crecimiento funcional.

### Entrada al punto 6.4

Iniciar solo cuando el operador lo indique; esta preparacion no inicia 6.4.
Su alcance independiente queda limitado a encapsulacion visual y accesibilidad,
sin features comerciales, cambios del portal ni retiro de compatibilidad.
Antes de editar, comprobar el corte de [preparacion](../../reports/architecture/pre64-readiness-2026-09-19.md),
Git y cambios posteriores. Usar dependencias del lock en entorno aislado.
Conservar 2.6, 5.5.5 y la ventana de compatibilidad abiertos hasta su evidencia;
no forzar casos reales ni usar el refactor visual para cerrarlos.

## P0 - Aceptacion natural y seguridad

### Ventana de retiro de compatibilidad actual

La ventana `2026-08-31` a `2026-09-06` no acredita cero consumidores.
Migrar primero `AdminApiClient.get_service_orders()` y los demas accesos sin
proyeccion; luego medir siete dias completos conforme a
[`../operations/current-only-observation.md`](../operations/current-only-observation.md).

- comprobar cero accesos al resumen mensual v1 y conservar trazabilidad;
- confirmar cero sondeos naturales a `8765` y salud continua por Admin API;
- medir llamadas sin `projection` a ordenes y sin query a post-cita;
- cerrar la nueva ventana con Telegram, dashboard, finanzas, worker y postpago
  funcionando con contratos actuales antes de retirar respuestas o puertos.

Cierre: siete dias sin consumidores antiguos, sin alertas perdidas y con
rollback conservado; entonces retirar codigo, puerto y documentacion remanente.

### Flujos naturales pendientes

Observar o conciliar sin crear envios de prueba:

- aceptar naturalmente el presupuesto 2 fechas / 2 horarios / 1 envio y la rotacion
  de cuentas: revisar contadores, restricciones, descansos y exclusiones sin forzar cupos;

- primer aviso conjunto natural tras resolver expedientes: texto revisado,
  precios, restricciones y confirmacion tecnica de un unico trabajo;
- primer integral nuevo posterior a `v74`: abono, tasa, saldo, mensaje y resumen;
- revisar texto y evidencia retenida de los dos `no_pending_request` con estado
  tecnico `sent` del 10 de septiembre antes de cerrar su aceptacion;
- siguiente alta natural con exclusiones: comprobar objetivo, motivo por
  expediente y aviso unico; conciliar identidades antiguas cuando exista
  evidencia exacta, conservando en revision las cuentas no resueltas;
- primer cierre diario completo: investigar la confirmacion de la publicacion
  final y conciliar componentes; refrescar el inventario, no reutilizar seis casos historicos;
- revisar albumes, postpagos y avisos ambiguos antes de cualquier recuperacion;
- observar el siguiente "Operacion no disponible temporalmente" natural: descanso por cuenta de al menos 180 segundos y consulta nueva sin duplicar citas; no generar reservas de prueba.

Cierre: revisiones congeladas, evidencia tecnica suficiente y ningun reintento
automatico de resultados `uncertain`. El
[informe de aceptacion](../../reports/acceptance/natural-acceptance-2026-09-07.md)
delimita la muestra observada y los pendientes; no sustituye monitoreo futuro.

## P1 - Operacion y datos accionables

### Pendientes

Persistir `actionable_since`, vencimiento, responsable, causa y prioridad por
tarea. Extender conciliacion guiada de WhatsApp a avisos, recordatorios y resumen
diario. Mantener CAPTCHA fuera del total comercial.

Cierre: cada tarea muestra quien, desde cuando y que debe hacer.

### Salud y controles

Agregar salud compuesta, drenaje y readiness. La pausa y reanudacion del worker
ya son operables desde Resumen con transicion pendiente visible. Rechazar con
`409` acciones incompatibles y exponer frescura de cada fuente.

Cierre: dashboard y Telegram distinguen proceso vivo, servicio funcional,
fuente stale y accion bloqueada.

### Rendimiento del dashboard

Paginar mensajes y detalles restantes; evitar listados completos cuando una
vista solo necesita resumen. La lista de ordenes ya usa una proyeccion propia y
post-cita pagina en servidor.

Cierre: payloads proporcionales a la vista y sin consultas duplicadas costosas.

## P2 - Resiliencia, evidencia y experiencia

### Backup, retencion y restore

- configurar backup externo y verificar restauracion;
- completar watchdogs y retencion de artefactos externos;
- mostrar cobertura, ultimo backup y proxima purga;
- bloquear reportes con datos personales o respuestas CAPTCHA.

Cierre: restore probado y purga sin perder comparabilidad.

### Diseño visual y accesibilidad

Consolidar el flujo visual
`Solicitud -> Validacion -> Cupo -> Reserva -> Pago -> Post-cita`.

- reducir tarjetas equivalentes y diagnostico en superficies principales;
- usar foco contenido, contraste y reduced motion;
- revisar Pendientes, Citas y recordatorios y Mensajes en `360`, `768`, `1024`
  y `1440 px`.

Cierre: teclado correcto y aprobacion visual real. El build no la sustituye.

### Calidad financiera

Conciliar diferencias abiertas y reunir saldos y costos para cierres reales.
Separar cobrado, pendiente, costo reconocido y overhead no medido.

Cierre: cada diferencia tiene estado, responsable y evidencia.

## P3 - Deuda tecnica posterior

Evaluar por familia los 11 avisos moderados del lock frontend observados el
19 de septiembre; validar cada actualizacion sin `npm audit fix --force` ni
mezclar una migracion mayor con 6.4. Cierre: auditoria y puertas del frontend aprobadas.

Cerrar 5.5.5: observar el siguiente caso natural de WhatsApp con la version
extraida cargada en Admin API antes de retirar los reexports.
No generar envios para forzar la aceptacion. Conservar tambien `2.6` pendiente
hasta reunir su evidencia integral natural.
Siguiente bloque del dashboard: `6.4`, encapsulacion visual, focus trap e inert,
teclado, contraste, reduced motion y revision responsive; reducir bundle y CSS.
Las fases 7 y 8 restantes cubren API, consultas y cierre integral.
No combinar estas extracciones con cambios funcionales del portal.

## Fuera de alcance o sin autorizacion

- desplegar Cloudinary;
- activar CAPTCHA grafico sin limite, breaker y fallback;
- reintentar automaticamente entregas ambiguas;
- reescribir historial Git;
- revocar servicios o credenciales externas desde este repositorio.

## Mantenimiento

- no registrar tareas completadas ni cronologias;
- no copiar cronologias al working tree; Git conserva versiones anteriores;
- mantener este archivo por debajo de `180` lineas;
- una tarea sin siguiente accion y criterio de cierre no pertenece al roadmap.
