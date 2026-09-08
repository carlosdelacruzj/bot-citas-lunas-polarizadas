# Trabajo pendiente

Ultima priorizacion: `2026-09-08`.

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

Las fases 0 a 4 del
[`plan integral de endurecimiento`](development-hardening-plan.md) estan
cerradas. El esquema `v74` ya esta activo; el paquete integral debe cerrar su
primera aceptacion natural antes de otro crecimiento funcional.

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

- primer integral nuevo posterior a `v74`: abono, tasa, saldo, mensaje y resumen;
- variante de registro `no_pending_request`;
- primer cierre diario completo: investigar la falta de confirmacion de la
  publicacion final y conciliar componentes de los seis casos `uncertain`;
- album ambiguo pendiente: revisar componentes antes de cualquier recuperacion.

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

Continuar con la extraccion 5.5.5 de WhatsApp Web. En 5.5.4 queda retirar
la fachada Settings cuando los consumidores de composicion y copias por cliente
usen grupos propios sin perder el contrato de carga. Las fases 6 a 8 cubren
dashboard por dominio, contratos, consultas y cierre. No combinar estas
extracciones con cambios funcionales del portal.

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
