# Estado maestro del proyecto

Última revisión integral: `2026-07-25`.

Este archivo es la fuente principal para entender dónde está el proyecto. Debe
actualizarse cuando se termina, valida o descarta un cambio relevante. Las
tareas futuras y su orden viven únicamente en
[`roadmap/README.md`](roadmap/README.md).

## Resumen ejecutivo

El sistema ya funciona como una operación comercial completa: recibe y
prioriza órdenes, monitorea el portal, realiza reservas con confirmación
estricta, conserva evidencia, permite administración local y remota, registra
pagos y automatiza seguimientos por WhatsApp sin bloquear el motor de citas.

Estado verificado el `2026-07-27`:

| Área | Estado | Lectura actual |
| --- | --- | --- |
| Worker de reservas | Operativo | `127.0.0.1:8765/health` responde y el worker está activo. |
| Admin API y dashboard | Operativos | `127.0.0.1:8766`; `api_only` no significa que el worker esté apagado. |
| PostgreSQL | Operativo | PostgreSQL 16 en Docker, saludable. |
| Telegram remoto | Operativo | Consultas, clientes, reglas, prioridad, credenciales y control del worker. |
| CAPTCHA sombra | Operativo | Servicio CUDA en `127.0.0.1:8787`; solo observa, 2Captcha conserva autoridad. |
| WhatsApp automático | Operativo con vigilancia | Emisor único en Admin API, cola durable y sin reintentos automáticos ambiguos. |
| Dashboard | Operativo | Build Angular correcto; bundle inicial de `498.58 kB`. |
| Calidad Python | Atención requerida | Ruff y `compileall` correctos; pytest tiene `42 passed / 11 failed`. |

## Resultado comercial acumulado

Datos consultados en PostgreSQL al `2026-07-25`:

| Periodo | Órdenes | Reservas confirmadas | Pagos | Ingreso cobrado |
| --- | ---: | ---: | ---: | ---: |
| Junio 2026 | 9 | 4 | 3 | S/ 120 |
| Julio 2026, días 1-25 | 83 | 81 | 76 | S/ 3,025 |

- Ticket promedio de julio: `S/ 39.80`.
- Pagos pendientes actuales: `2`, por `S/ 80`.
- TikTok aporta `S/ 2,240` del ingreso de julio.
- Estas cifras son ingresos cobrados, no utilidad neta.

## Punto de partida técnico

La referencia estable del motor de reserva sigue siendo:

- tag `best-performing-2026-07-12`;
- commit `a43c6a1`;
- confirmación estricta, leases, intentos persistidos y reglas por orden;
- ruta normal observada cercana a 6.5-7.3 segundos cuando CAPTCHA responde
  rápido.

Los cambios posteriores ampliaron administración, observabilidad y
comunicación. No reemplazan ese baseline para comparar regresiones del motor.

## Qué se realizó en julio

### Reserva y cola

- Primera reserva automática efectiva y reconciliación posterior.
- Confirmación estricta del portal; un estado ambiguo no autoriza otro submit.
- Registro durable de `reservation_attempts`, submission pendiente y heartbeat.
- Prioridad, prioridad exclusiva y restricciones por fecha, hora, día y rangos
  excluidos.
- Corrección para que fechas fuera de rango no provoquen un backoff general de
  30 minutos.

### Arquitectura y operación

- Separación modular de reserva, worker, base de datos, reportes y API.
- Admin API independiente mediante `worker_commands`.
- Dashboard Angular con vistas, rutas, carga diferida, estados y modales
  separados.
- Resumen mensual, finanzas, bandeja de pendientes y edición segura de
  credenciales.
- Arranque supervisado en Windows para worker, dashboard, Telegram y CAPTCHA
  sombra.
- El arranque automático ya no usa VBS ni `ExecutionPolicy Bypass`; una tarea
  programada ejecuta directamente el lanzador PowerShell versionado.
- Los cuatro supervisores quedan desacoplados del proceso corto de la tarea;
  cerrar una consola de instalación no termina el worker.

### Control remoto

- Menú de Telegram con búsqueda, recientes, resumen y estado.
- Alta guiada de clientes y edición de reglas, prioridad y credenciales.
- Pausa, reanudación y reinicio mediante Admin API y comandos persistidos.
- Expiración de conversaciones, botones obsoletos rechazados y un solo flujo
  guiado por chat.

### Evidencia y CAPTCHA

- Evidencia organizada por fecha y resumen compacto.
- CAPTCHA original utilizado para el solver.
- Servicio local en modo sombra, cola durable y revisión humana desde el
  dashboard.
- El modelo local no participa en la decisión de reserva; 2Captcha sigue siendo
  la respuesta enviada al portal.

### Comunicación y cobro

- Álbum único con evidencia y QR de Yape.
- Seguimiento postpago separado con PDFs y textos.
- Cola durable de trabajos WhatsApp con estados recuperables y auditables.
- Admin API como único propietario del perfil persistente de WhatsApp Web.
- Fallos de WhatsApp no bloquean reservas ni Telegram.

## Rendimiento observado

| Periodo | Runs conservados | Intentos | `registered` | `slot_lost` | Errores |
| --- | ---: | ---: | ---: | ---: | ---: |
| 13-19 julio | 5,356 | 61 | 28 | 29 (47.5%) | 14 |
| 20-25 julio | 4,662 | 43 | 20 | 17 (39.5%) | 3 |

La última semana muestra menos errores y menor proporción de `slot_lost`, pero
todavía se necesita una muestra mayor antes de atribuir la mejora a un solo
cambio.

La tabla `runs` conserva actualmente información desde el 11 de julio. Para
periodos anteriores deben usarse los reportes y documentos versionados; no se
debe reconstruir una comparación histórica únicamente desde la base viva.

## Fallos, límites y riesgos vigentes

1. La suite actual tiene 11 fallos. Varios contratos de pruebas quedaron atrás
   (`document_type`, restricciones, muestreo CAPTCHA), pero los fallos de claim
   y creación por API requieren clasificación explícita.
2. WhatsApp Web depende de una interfaz externa cambiante. Un resultado
   ambiguo nunca debe reintentarse automáticamente.
3. La corrección del backoff por fechas fuera de rango está validada en
   escenarios controlados, pero falta confirmarla ante otro caso real
   equivalente.
4. El ajuste del observer a cuatro intentos necesita comparación de varios días
   antes de conservarse como nuevo baseline.
5. La operación depende de una PC Windows, red local, Docker y perfiles
   persistentes de navegador.
6. El CAPTCHA local todavía no tiene evidencia suficiente para sustituir a
   2Captcha.
7. La evidencia versionada está sanitizada, pero sigue siendo telemetría
   operacional y debe revisarse antes de compartir.
8. Kaspersky puede clasificar lanzadores ocultos y persistentes como amenaza.
   El reemplazo PowerShell reduce esa superficie, pero debe vigilarse el
   historial del antivirus después de reinicios y actualizaciones de firmas.

## Validación del corte

- `python -m ruff check src tests`: correcto.
- `python -m compileall -q src`: correcto.
- `npm run build`: correcto.
- `python -m pytest -q`: `42 passed / 11 failed`.
- Worker, Admin API, PostgreSQL y CAPTCHA sombra: saludables.

## Regla de mantenimiento

Después de cada cambio relevante:

1. actualizar este archivo si cambió el estado, una capacidad, un riesgo, una
   métrica o una validación;
2. actualizar [`roadmap/README.md`](roadmap/README.md) si una tarea avanzó,
   terminó, se bloqueó o cambió de prioridad;
3. mover el detalle largo a `operations/`, `contracts/`, `history/` o un
   documento de incidente;
4. no convertir reportes generados ni bitácoras en listas paralelas de tareas.
