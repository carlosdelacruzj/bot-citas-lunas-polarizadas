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
