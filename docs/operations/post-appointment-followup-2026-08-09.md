# Seguimiento post-cita

Fecha de implementación: `2026-08-09`.

## Objetivo

Conservar una lectura interna y trazable de lo que ocurre después de una cita
confirmada: etapas, fechas, estados, continuidad posterior y pérdida de acceso
al portal. Esta primera versión es deliberadamente manual y de solo lectura.
No envía recordatorios, no cambia la orden, no modifica la reserva y no ejecuta
CAPTCHA.

Esta descripción corresponde al corte inicial. Desde el `2026-08-28`, la
clasificación temporal y el barrido post-cita pendiente también tienen una
automatización diaria segura, documentada al final de este archivo.

## Datos que se guardan

Cada revisión crea un evento en `post_appointment_reviews` y una instantánea de
sus etapas en `post_appointment_stage_snapshots`:

- acceso correcto, credenciales rechazadas, flujo no identificable o error del
  portal;
- resultado operativo conservador: cita próxima, esperando actualización, en
  progreso, completado, observación con o sin avance, acceso perdido o revisión
  requerida;
- nombre de etapa, fecha, hora y estado genérico;
- texto completo del mensaje del portal y su clase: `none`, `ok`,
  `observation` o `unknown`;
- expediente y placa de la reserva, cuando están disponibles, para distinguir
  los trámites que comparten una cuenta;
- fecha de la consulta y relación con la orden.

El texto se conserva por decisión operativa para análisis interno y posibles
servicios posteriores. Es información sensible: no se incluye en avisos
automáticos, Telegram, WhatsApp ni reportes públicos; solo se expone mediante
la API administrativa autenticada y su dashboard. Su uso posterior requiere
una finalidad legítima y controles de acceso acordes.

## Uso desde el dashboard

1. Abrir **Post-cita**.
2. La vista inicial **En seguimiento** excluye los accesos perdidos. Revisar
   primero las observaciones sin avance y las fechas pasadas sin actualización.
3. Pulsar **Revisar ahora** en una sola orden.
4. Esperar el resultado individual. La consulta abre un contexto Playwright
   nuevo, inicia sesión, entra al trámite y lee la tabla de etapas.
5. Si el portal rechaza las credenciales, el caso pasa a **Historial sin
   acceso**. Conserva su última instantánea y la fecha de revisión, pero deja de
   ofrecer nuevos intentos desde Post-cita.

La vista permite buscar por cliente, expediente, placa o mensaje, filtrar los
casos que requieren atención y ordenar por prioridad, cita, revisión o nombre.
**Requieren atención** no incluye accesos perdidos: esos registros se consultan
únicamente desde **Historial sin acceso** y no ocupan la paginación operativa.
Presenta `10` seguimientos por página de forma predeterminada. Cada ficha tiene
un número estable dentro del resultado paginado y mantiene las etapas plegadas
hasta que el operador elige **Ver recorrido completo**. El recorrido usa nodos
`1-6`; en escritorio el conector queda separado de los títulos y en móvil se
convierte en una línea vertical.

Los colores no se calculan por el texto aislado de una fila. `Atendido`,
`Programado`, `Por programar`, `OK` y cualquier etapa con fecha se muestran en
verde. Una observación se muestra en rojo únicamente cuando no hay avance en
`Peritaje Vehicular`, `Peritaje Lunas` o `Validación`; si sí existe continuidad,
el mensaje permanece visible pero la etapa se pinta verde. Un estado futuro sin
fecha queda neutral.

Una revisión no implica que el resultado de la PNP sea definitivo. La
clasificación **observación con avance** significa únicamente que el portal
también muestra actividad en `Peritaje Vehicular`, `Peritaje Lunas` o
`Validación`; no interpreta ni aprueba el contenido del mensaje.

## Límites de esta versión

- La interfaz revisa una orden por vez; el primer recorrido masivo fue una
  operación controlada y no existe calendario automático.
- No se crean mensajes ni recordatorios.
- No se determina por cuenta propia si una persona es apta o no apta.
- Una falla técnica del portal se separa de credenciales inválidas.
- `access_lost` es un archivo operativo, no un pendiente: no crea reintentos ni
  recordatorios y no se suma a **Requieren atención**.
- La ausencia de avance en una lectura no prueba un rechazo definitivo.

Después de observar varios casos reales se podrá decidir una periodicidad segura
y, recién entonces, diseñar recordatorios basados únicamente en fecha de cita y
consentimiento operativo.

## Rollback

El cambio no depende de `.env`. Para volver al comportamiento anterior:

1. revertir la ruta Angular `/post-cita`, su enlace lateral y los métodos del
   cliente API;
2. retirar las rutas `GET /api/v1/post-appointment-followups` y
   `POST /api/v1/service-orders/{order_id}/post-appointment/review`;
3. reiniciar únicamente Admin API/dashboard cuando no haya trabajos WhatsApp
   en estado `running`.

Las tablas y columnas de los esquemas `v48-v49` pueden permanecer: son aditivas y ningún flujo de
reserva, CAPTCHA, WhatsApp o cola las consulta. Si se decide eliminarlas, primero
exportar los eventos sanitizados y ejecutar una migración explícita; no borrar
tablas manualmente durante la operación.

## Validación mínima

```powershell
python -m compileall -q src
python -m ruff check src tests
python -m pytest -q
git diff --check
cd dashboard
npm run build
```

Validado el `2026-08-09` con consultas reales de solo lectura. PostgreSQL `v49`
conserva `message_text`, expediente y placa. Un segundo barrido dirigido volvió
a leer las seis órdenes clasificadas con observación y almacenó sus seis textos.
No se generaron CAPTCHA, reservas, mensajes ni capturas.

El archivado operativo se validó el mismo día contra los `108` registros
reales: `92` permanecen en seguimiento, `10` requieren atención y `16` quedan
en **Historial sin acceso**. Admin API se reinició de forma aislada con cero
trabajos WhatsApp `running` y publicó esos conteos; `/post-cita` siguió
respondiendo. `compileall`, Ruff, `59` pruebas, build Angular y
`git diff --check` quedaron correctos.

## Primera revisión completa

Ejecutada el `2026-08-09` de forma secuencial, con contexto Playwright nuevo por
orden y pausas aleatorias de `4-7` segundos. Se procesaron las `107` órdenes que
no tenían lectura inicial en `20 min 44 s`; sumadas a la prueba previa, las
`108` reservas confirmadas quedaron cubiertas. No hubo errores generales del
portal ni se activó la parada por tres fallos técnicos consecutivos.

Último resultado por orden:

| Resultado | Casos |
| --- | ---: |
| Cita próxima | 47 |
| Completado | 26 |
| Acceso perdido | 16 |
| En progreso | 9 |
| Observación sin avance | 6 |
| Esperando actualización | 4 |
| Revisión manual requerida | 0 |

Acceso al portal: `92` correctos y `16` credenciales rechazadas. Un caso fue
corregido de `review_required` a `completed` al abrir expresamente el expediente
`*****`, placa `******`: las seis etapas figuran `Atendido`.

El esquema `v49` también reconcilió de forma determinista las reservas antiguas
que tenían un único trámite históricamente `PENDIENTE`. Otro padre
quedó `archived` como contenedor sin reserva propia; sus dos subtrámites siguen
separados y confirmados con expediente y placa enmascarados. Ambos conservan
`access_lost` porque sus credenciales actuales ya no permiten una nueva lectura.

## Rollback de la identidad de trámite

El rollback funcional consiste en revertir el lector post-cita a la selección
anterior y ocultar expediente, placa y agrupación del dashboard. Las columnas
`reservations.program_expediente`, `reservations.program_plate` y
`post_appointment_stage_snapshots.message_text` pueden permanecer sin afectar
la reserva. No vaciar esos campos: son la trazabilidad que permite saber qué
trámite fue gestionado. Si se revierte únicamente la clasificación visual del
padre archivado, puede restaurarse manualmente su estado `paused`, pero no debe
reactivarse en la cola mientras existan sus dos subtrámites.

## Automatización diaria segura

Fecha de ampliación: `2026-08-28`.

PostgreSQL `v67` agrega `post_appointment_automatic_reviews`, con clave primaria
`(service_date, reservation_id)`. La tabla conserva claim, resultado, revisión
producida y error terminal; una misma reserva nunca abre el portal dos veces en
el mismo día Lima, incluso si la primera lectura falla.

La clasificación visible no depende de ejecutar Playwright. En cada `GET`, una
cita anterior a hoy en `America/Lima` deja de ser `upcoming` y pasa a
`review_required` si todavía no tiene un resultado concluyente. Por eso una
instantánea pre-cita antigua no puede volver a aparecer en **Próximas citas**.

El scheduler vive en Admin API y aplica este contrato:

1. Inicia el ciclo a las `20:00` de Lima y solo considera reservas confirmadas
   entre D+1 y D+30.
2. Excluye citas de hoy/futuras, `completed`, `access_lost` y cierres
   `client_withdrew`, `external_slot`, `duplicate`, `not_serviceable` o
   `uncollectible`.
3. Procesa una orden por vez, con contexto Playwright nuevo, y espera una pausa
   aleatoria de `4-7` segundos entre consultas.
4. Admite como máximo `20` aperturas por día. Prioriza nunca revisados,
   resultados que requieren atención, revisión más antigua y cita más antigua.
   Si existe más backlog, permanece visible y continúa en el siguiente ciclo.
5. Un fallo técnico queda terminal para ese día y vuelve a ser elegible recién
   al día siguiente. Tres fallos técnicos consecutivos abren el breaker y
   detienen el resto del lote diario. `invalid_credentials` produce
   `access_lost` y no cuenta como caída general del portal.
6. Un claim interrumpido se cierra como fallo sin reapertura el mismo día. El
   botón **Revisar ahora** sigue disponible fuera del ciclo automático.

La sesión conserva `headless=true`, `auto_reserve=false`, monitor en cero y
notificaciones desactivadas. No pulsa reservar, no resuelve CAPTCHA, no crea
WhatsApp, no modifica pagos, órdenes, reservas ni backoffs del worker.

El dashboard muestra frescura de cada caso, próxima revisión automática,
pendientes, revisiones activas/completadas/con fallo y breaker. Las citas con más
de 30 días siguen en **Necesitan revisión**, pero requieren intervención manual.
