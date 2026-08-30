# Trabajo pendiente

Ultima priorizacion: `2026-08-29`.

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

## P0 - Aceptacion natural y seguridad

### Flujos naturales pendientes

Observar, sin crear envios de prueba:

- proximo album de reserva/cobro procesado por el dispatcher;
- proximo postpago con documentos y texto separados;
- variantes pendientes del aviso de registro;
- proximo recordatorio con plantilla versionada;
- primer lote post-cita natural de las `20:00`;
- primer cierre diario natural con adjuntos marcados;
- proximo reinicio de Windows y recuperacion de Telegram/runtime.

Cierre: revisiones congeladas, evidencia tecnica suficiente y ningun reintento
de resultados `uncertain`.

## P1 - Operacion y datos accionables

### Pendientes

Persistir `actionable_since`, vencimiento, responsable, causa y prioridad por
tarea. Extender conciliacion guiada de WhatsApp a avisos, recordatorios y resumen
diario. Mantener CAPTCHA fuera del total comercial.

Cierre: cada tarea muestra quien, desde cuando y que debe hacer.

### Salud y controles

Agregar salud compuesta, pausa, drenaje y readiness. Rechazar con `409` acciones
incompatibles y exponer frescura de cada fuente.

Cierre: dashboard y Telegram distinguen proceso vivo, servicio funcional,
fuente stale y accion bloqueada.

### Rendimiento del dashboard

Paginar post-cita, mensajes y detalle; evitar listados completos cuando una vista
solo necesita resumen. Medir la carga periodica de `/service-orders` y
`/operator-inbox`.

Cierre: payloads proporcionales a la vista y sin consultas duplicadas costosas.

## P2 - Resiliencia, evidencia y experiencia

### Backup, retencion y restore

- configurar backup externo y verificar restauracion;
- completar watchdogs, rotacion y retencion;
- crear agregados diarios antes de purgar datos crudos;
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

No iniciar antes de estabilizar P0-P2:

1. romper el ciclo entre `appointments.py` y `appointment_selection.py`;
2. sustituir mutaciones globales de `queue_runtime.py`;
3. dividir `dashboard/src/app/app.ts` por dominio;
4. reducir `ViewEncapsulation.None` gradualmente;
5. uniformar errores HTTP con `request_id` y respuesta sanitizada;
6. tipar facades y payloads del dashboard que aun usan `any`.

### Limpieza integral auditada

Ejecutar por etapas el
[`plan de limpieza y alineacion`](system-cleanup-audit.md): alinear primero
runtime, esquema y documentacion; despues retirar codigo, compatibilidad,
artefactos y evidencia redundante solo con consumidores revalidados.

Cierre: codigo, datos, procesos y documentos coinciden; cada elemento conservado
tiene proposito y cada retiro tiene evidencia y rollback proporcional.

## Fuera de alcance o sin autorizacion

- desplegar Cloudinary;
- usar tres sesiones Playwright concurrentes;
- activar CAPTCHA grafico sin limite, breaker y fallback;
- reintentar automaticamente entregas ambiguas;
- reescribir historial Git;
- revocar servicios o credenciales externas desde este repositorio.

## Mantenimiento

- no registrar tareas completadas ni cronologias;
- no copiar cronologias al working tree; Git conserva versiones anteriores;
- mantener este archivo por debajo de `180` lineas;
- una tarea sin siguiente accion y criterio de cierre no pertenece al roadmap.
