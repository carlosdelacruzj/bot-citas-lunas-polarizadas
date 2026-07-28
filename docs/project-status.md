# Estado maestro del proyecto

Última revisión integral: `2026-07-28`.

Este archivo es la fuente principal para entender dónde está el proyecto. Debe
actualizarse cuando se termina, valida o descarta un cambio relevante. Las
tareas futuras y su orden viven únicamente en
[`roadmap/README.md`](roadmap/README.md).

## Resumen ejecutivo

El sistema ya funciona como una operación comercial completa: recibe y
prioriza órdenes, monitorea el portal, realiza reservas con confirmación
estricta, conserva evidencia, permite administración local y remota, registra
pagos y automatiza seguimientos por WhatsApp sin bloquear el motor de citas.

Estado verificado el `2026-07-28`:

| Área | Estado | Lectura actual |
| --- | --- | --- |
| Worker de reservas | En espera nocturna | `127.0.0.1:8765/health` no responde antes del arranque diario; verificar el siguiente inicio supervisado. |
| Admin API y dashboard | Operativos | `127.0.0.1:8766`; `api_only` no significa que el worker esté apagado. |
| PostgreSQL | Operativo | PostgreSQL 16 en Docker, saludable. |
| Telegram remoto | Operativo | Consultas, clientes, reglas, prioridad, credenciales y control del worker. |
| CAPTCHA sombra | Operativo | Servicio CUDA en `127.0.0.1:8787`; solo observa, 2Captcha conserva autoridad. |
| WhatsApp automático | Operativo con vigilancia | Emisor único en Admin API, cola durable y sin reintentos automáticos ambiguos. |
| Dashboard | Operativo | Build Angular correcto; bundle inicial de `498.07 kB`. |
| Calidad Python | Operativa | Ruff y `compileall` correctos; pytest tiene `59 passed`. |

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
- El mensaje explícito de éxito del portal confirma la reserva sin reabrir el
  trámite; si ese mensaje falta, la etapa `Programado` conserva la validación
  secundaria. Esta decisión operativa evita añadir latencia a la ruta exitosa.
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
- Los cuatro supervisores quedan desacoplados y vigilados por un supervisor raíz
  persistente. La tarea programada permanece activa, revisa su presencia cada
  15 segundos y recupera individualmente el que desaparezca.
- La tarea usa `pythonw.exe` y `scripts/start-runtime.pyw` como host sin consola;
  no depende de VBS, Windows Script Host ni una ventana visible de PowerShell.
- La recuperación se validó cerrando únicamente el supervisor de Telegram:
  reapareció con otro PID en el siguiente ciclo, conservó intactos los procesos
  Python existentes y Admin API/CAPTCHA continuaron saludables.
- El mantenimiento local del 28 de julio eliminó `447.34 MB` de artefactos
  regenerables u obsoletos: un respaldo antiguo y un perfil de prueba de
  WhatsApp Web, la caché de Angular y reportes temporales de estado y
  diagnóstico. Se conservaron el perfil activo, `dashboard/node_modules`,
  `dashboard/dist` y toda la evidencia histórica versionada.
- La limpieza estática del 28 de julio retiró `198` líneas sin consumidores:
  seis funciones Python, un conjunto de selectores obsoleto, cuatro métodos y
  dos asignaciones sin uso en Angular, además del proxy JSON reemplazado por
  `proxy.conf.cjs`. Compilación, lint, TypeScript y build conservaron el mismo
  comportamiento observable.
- El reporte general PNG de `reports/daily/` se retiró por falta de uso,
  incluyendo su generación automática al cierre y el comando `daily-report`.
  El corte de las 18:00, la revisión final de órdenes listas y el reinicio de
  las 07:30 permanecen sin cambios.
- La retención de 14 días ahora recorre las subcarpetas de logs, capturas y
  videos, elimina directorios vacíos y conserva explícitamente evidencia de
  reserva, disponibilidad, fallos, defensas, CAPTCHA originales, preflight y
  paquetes de WhatsApp. Antes solo inspeccionaba archivos directamente bajo
  cada raíz y dejaba intactas todas las carpetas fechadas.
- La base depuró `91` mensajes marcados explícitamente como prueba, sin
  referencias desde la cola automática. La limpieza diaria ahora elimina
  mensajes de prueba y eventos CAPTCHA ya procesados después de `14` días, y
  comandos del worker aplicados después de `90` días. No alcanza mensajes
  reales, comandos pendientes o fallidos, trabajos WhatsApp, órdenes, pagos,
  reservas ni intentos.
- Los `395` archivos de paquetes WhatsApp conservaron sus rutas y hashes, pero
  ahora comparten `55` contenidos físicos mediante un almacén local inmutable.
  La migración recuperó `91.04 MB`; las nuevas constancias, imágenes de pago y
  PDFs se deduplican por SHA-256, con copia normal como fallback si el sistema
  de archivos no admite enlaces físicos.
- Se retiraron `10` módulos de compatibilidad que solo reexportaban símbolos y
  las fachadas públicas de cinco paquetes. Código, tests y entrypoints importan
  ahora desde `core`, `db`, `reports`, `reservation_engine` y `worker` en su
  módulo propietario. `queue_runtime.py` y los selectores CAPTCHA se conservaron
  porque todavía contienen lógica activa.
- Los 11 fallos de pytest se clasificaron como contratos de prueba obsoletos:
  preflight, `document_type`, cinco restricciones por orden y muestreo CAPTCHA
  sombra. Se actualizaron únicamente las pruebas; no fue necesario relajar ni
  modificar código productivo. La suite completa quedó en `59 passed`.

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

1. La suite local está en verde, pero no sustituye una validación real del
   recorrido cupo -> reserva -> confirmación exacta en el portal.
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
- `python -m pytest -q`: `59 passed`.
- Admin API, PostgreSQL y CAPTCHA sombra: saludables; worker pendiente del
  siguiente arranque diario.

## Regla de mantenimiento

Después de cada cambio relevante:

1. actualizar este archivo si cambió el estado, una capacidad, un riesgo, una
   métrica o una validación;
2. actualizar [`roadmap/README.md`](roadmap/README.md) si una tarea avanzó,
   terminó, se bloqueó o cambió de prioridad;
3. mover el detalle largo a `operations/`, `contracts/`, `history/` o un
   documento de incidente;
4. no convertir reportes generados ni bitácoras en listas paralelas de tareas.
