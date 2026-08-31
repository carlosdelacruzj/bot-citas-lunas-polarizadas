# Trabajo pendiente

Ultima priorizacion: `2026-08-31`.

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

No iniciar features comerciales nuevas hasta cerrar las fases 0 a 4 del
[`plan integral de endurecimiento`](development-hardening-plan.md). Se permiten
correcciones, pruebas, observabilidad y refactors incluidos en ese plan. El
cambio del esquema `v72` y paquete integral debe estabilizarse antes de
otro crecimiento funcional.

## P0 - Aceptacion natural y seguridad

### Endurecimiento tecnico integral

Ejecutar en orden las fases 0 a 4 del
[`plan integral de endurecimiento`](development-hardening-plan.md): linea base,
riesgos de reserva/WhatsApp/sesiones/leases, estabilizacion financiera `v72`,
privacidad y red automatizada de seguridad.

Cierre: los riesgos P0 tienen pruebas, el paquete integral es coherente de
extremo a extremo y un clon limpio pasa CI backend/frontend reproducible.

### Ventana de retiro de compatibilidad actual

Observar del `2026-08-31` al `2026-09-06` conforme a
[`../operations/current-only-observation.md`](../operations/current-only-observation.md).
El monitor n8n ya esta inactivo; no apagar aun `8765` ni retirar respuestas API
historicas sin demostrar cero consumidores.

- retirar el resumen mensual v1 desde `2026-09-04` si no registra accesos;
- confirmar cero sondeos naturales a `8765` y salud continua por Admin API;
- medir llamadas sin `projection` a ordenes y sin query a post-cita;
- cerrar la ventana solo con Telegram, dashboard, finanzas, worker y paquetes
  postpago funcionando con los contratos actuales.

Cierre: siete dias sin consumidores antiguos, sin alertas perdidas y con
rollback conservado; entonces retirar codigo, puerto y documentacion remanente.

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

No iniciar antes de cerrar las fases 0 a 4 del plan integral. Las fases 5 a 8
gobiernan fronteras backend, ciclos, globals, modulos grandes, dashboard por
dominio, errores HTTP, contratos, consultas y estandar permanente. Ejecutar una
frontera por vez y no combinar refactor con cambios funcionales ajenos.

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
