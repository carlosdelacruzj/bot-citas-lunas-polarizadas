# Estado maestro del proyecto

Última revisión integral: `2026-07-14`.

## Estado ejecutivo

| Área | Estado | Conclusión |
| --- | --- | --- |
| Reserva automática | Operativa | Confirmación estricta y reservas `registered` reales. |
| Cola multi-cliente | Operativa | Sesión, cookies, lease y confirmación independientes por orden. |
| Backend y PostgreSQL | Operativos | API, persistencia, comandos y módulos separados por responsabilidad. |
| Dashboard | Operativo | Flujo por tarea, runs sanitizados, accesibilidad y entrega integrada. |
| Operación | Operativa | Runbook, reportes, alertas y restore temporal verificado. |
| Optimización | Observación activa | Línea base e instrumentación listas; flujo funcional sin cambios. |

Baseline estable de reserva: tag `best-performing-2026-07-12`, commit
`a43c6a1`. Los cambios posteriores de administración, reportes e
instrumentación no alteraron la regla de confirmación final.

## Qué se realizó

- Se incorporó un sistema visual reutilizable para el dashboard con tokens de
  color, tipografía, espaciado, radios, sombras, foco y movimiento reducido. La
  navegación, encabezados, controles, tarjetas, tablas, estados y modales usan
  una misma base sin fuentes ni librerías visuales externas.
- Se reforzó la jerarquía de cada área sin añadir pasos al operador: Pendientes
  prioriza las tareas, Órdenes conserva filtros y contexto al desplazarse,
  CAPTCHA destaca la imagen y las respuestas, Resumen/Finanzas separan métricas
  ejecutivas y Actividad diferencia comandos, corridas y evidencias.
- Desde `Editar orden > Acceso al portal`, las credenciales de una orden activa
  o pausada pueden reemplazarse sin crear otra orden ni perder contacto, pagos o
  historial. El cambio se guarda cifrado, pausa todas las subórdenes de la
  cuenta, limpia el error operativo anterior y exige una nueva validación del
  portal antes de reactivarlas.
- Reserva automática con resultado `registered` o evidencia explícita del
  portal; estados ambiguos no autorizan un segundo submit.
- `reservation_attempts`, submission pendiente y heartbeat de lease.
- Cola rápida, prioridades, restricciones por fecha/hora/día y subórdenes por
  trámite.
- Admin API separado mediante `worker_commands` y dashboard Angular en
  `127.0.0.1:8766`.
- Listados enmascarados; detalle sensible solicitado solo bajo autenticación.
- Flujo de operador: orden seleccionada, siguiente acción, pagos, cierres,
  sesiones manuales y runs sanitizados.
- UX simplificada: tabla compacta, acción contextual, panel lateral, prioridad
  rápida y confirmaciones SweetAlert2.
- Menú lateral estable sin contadores dependientes de filtros; los totales y
  estados accionables viven dentro de cada sección.
- Estados técnicos traducidos mediante un catálogo visual único; colores y
  etiquetas son consistentes en órdenes, actividad, comandos y WhatsApp. Los
  éxitos usan avisos temporales y los errores globales se retiran a los ocho
  segundos.
- Órdenes paginadas en el navegador con 20 filas por defecto y opciones de
  10/20/50; conserva filtro rápido, orden, dirección, tamaño y página. La
  búsqueda libre se mantiene solo durante la sesión del navegador.
- Edición de restricciones por orden desde el dashboard: fecha mínima, fecha
  máxima, hora mínima, días permitidos y varios rangos de fechas excluidas; los
  límites también se pueden quitar y los rangos aparecen resumidos en la orden.
- Creación y edición reutilizan el mismo editor de reglas de reserva para fechas,
  días permitidos y rangos excluidos. Las validaciones, textos y comportamiento
  responsive quedan definidos en un solo componente.
- El editor de reglas ofrece presets comprensibles (`Cualquier fecha`, `Solo
  sábados`, `Desde una fecha`, `Excepto un rango` y `Entre dos fechas`) y siete
  botones de día con estado visible y accesible. Los presets solo preparan el
  formulario; la confirmación existente sigue siendo necesaria para guardar.
- Las cinco vistas principales del dashboard están separadas en componentes:
  Resumen, Finanzas, Órdenes, CAPTCHA y Actividad. `App` conserva la navegación,
  el estado compartido y los modales para evitar duplicar lógica operativa.
- La carga inicial, la navegación y el refresco automático consultan únicamente
  los datos de la vista activa, además de salud, worker y sesiones manuales. Se
  evitan ciclos superpuestos y las categorías financieras se reutilizan después
  de su primera carga.
- La bandeja `Pendientes` concentra bloqueos de acceso, contacto/WhatsApp,
  cobros, seguimiento post-pago y validaciones CAPTCHA. Cada orden muestra un
  único siguiente paso y el menú solo presenta un contador cuando hay trabajo
  accionable.
- La navegación usa rutas reales con carga diferida por vista. Órdenes y runs
  aceptan enlaces directos; Resumen/Finanzas conservan el mes en la URL y
  CAPTCHA conserva el modo de revisión o historial.
- SweetAlert2 también se carga bajo demanda. La compilación del cambio redujo
  el bundle inicial de aproximadamente 563 kB a 501 kB, por debajo del límite
  preventivo configurado en 520 kB.
- Las vistas comparten un único estado visual para carga inicial, ausencia de
  resultados, errores recuperables y datos posiblemente desactualizados. Las
  actualizaciones con información existente son silenciosas: conservan el
  contenido visible, informan en una franja compacta y permiten reintentar sin
  bloquear el trabajo.
- Los siete modales operativos están separados por responsabilidad (WhatsApp,
  pago, edición, acciones, alta, finanzas y reinicio) y se cargan bajo demanda
  al abrirse. `App` conserva únicamente la coordinación de efectos, la
  confirmación final y la restauración de foco para no duplicar comportamiento.
- La actualización automática usa una frecuencia por vista: 10 segundos para
  Pendientes/Actividad, 20 para Órdenes y revisión CAPTCHA, 60 para Resumen e
  historial CAPTCHA y 120 para Finanzas. Una pestaña oculta pausa lecturas; al
  regresar solo refresca si la vista venció. Navegar o filtrar cancela la
  petición HTTP anterior y aplica siempre la respuesta más reciente.
- Resumen mensual de negocio con ingresos cobrados, pendientes separados,
  conversión, comparación, fuentes y alertas accionables.
- Reporte semanal, alertas CAPTCHA/`slot_lost`, política de evidencia y
  simulacro de backup/restore.
- Medición observacional de selección, CAPTCHA, secuencia y `fetch_probe`.
- Calendario automático de lunes a sábado; domingo permanece en espera.
- WhatsApp asistido sin API de Meta: un clic prepara constancia y cobro como álbum
  local con textos individuales; el operador conserva el envío final y su
  confirmación manual auditable en PostgreSQL.

## Validación vigente

- `python -m compileall -q src`.
- `python -m ruff check src tests`.
- `python -m pytest -q`: 53 tests.
- `npm run build` para Angular.
- `git diff --check`.
- Worker activo y domingo reportado como `outside_hot_window`.
- Restore temporal comprobado y limpiado; los conteos variables están en el
  reporte operacional, no se duplican aquí.

## Riesgos y límites conocidos

- La sesión del dashboard confía en procesos locales; no exponer loopback.
- `include_details=1` es una superficie sensible para clientes autorizados.
- La evidencia versionada sigue siendo telemetría operacional aunque esté
  sanitizada; revisar antes de compartir.
- El simulacro de restore no reemplaza un backup durable cifrado.
- La nueva instrumentación agrega overhead mínimo de medición, no cero.
- WhatsApp no confirma entregas: `sent` significa que el operador declaró haber
  completado el envío. El sistema prepara WhatsApp Web, pero nunca pulsa Enviar.
- Persisten deuda técnica en el ciclo `appointments`/`appointment_selection` y
  en fachadas que mutan dependencias globales.

## Qué leer y qué sigue

1. [`README.md`](README.md): mapa documental.
2. [`roadmap/README.md`](roadmap/README.md): únicos pendientes activos.
3. [`operations/README.md`](operations/README.md): operación y recuperación.
4. [`optimization.md`](optimization.md): medición y decisiones.

El siguiente paso no es cambiar la reserva: es acumular muestras reales con el
nuevo desglose, regenerar reportes y elegir con el usuario un único experimento.
El periodo y la fecha de la próxima revisión están definidos en
[`roadmap/README.md`](roadmap/README.md#próximo-checkpoint).

## Panel de calidad CAPTCHA

El apartado CAPTCHA incorpora el modo `Calidad` sobre las etiquetas humanas vigentes. Presenta
exactitud, confianza y tiempos promedio/p50/p90 por modelo; tiempos agregados de 2Captcha;
unanimidad, mayoría y consensos incorrectos; evolución semanal y casos útiles paginados. Una
advertencia evita interpretar como tendencia una muestra menor de treinta imágenes o dos semanas.

La misma vista permite descargar un ZIP trazable con `labels.csv`, `manifest.csv` e imágenes. La
API rechaza la exportación completa si alguna imagen está fuera del directorio autorizado, falta o
no coincide con el SHA-256 registrado. El consenso nunca se exporta como verdad: solo se incluyen
validaciones humanas.
