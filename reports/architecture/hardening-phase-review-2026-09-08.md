# Revision de fases de endurecimiento

Snapshot generado el `2026-09-08`, durante el cierre de pendientes de `5.5.4`
y `5.5.5`. Incluye las correcciones tecnicas verificadas en este corte; no constituye
una nueva aceptacion operativa.

## Alcance y metodo

Se contrastaron las casillas del plan, codigo propietario, escenarios de
prueba existentes, workflow CI y evidencia fechada explicitamente referenciada.
La proteccion de `main` se consulto mediante la API de GitHub. Esta revision
no ejecuto reservas, cobros, mensajes, migraciones ni reinicios, y no modifico
`.env`. La validacion final aprobo 181 pruebas y 24 subpruebas, cobertura critica y
la guarda de arquitectura (318 modulos, una excepcion conocida, cero ciclos).
No sustituye la aceptacion natural exigida por contrato.

## Matriz de cierre

| Fase | Resultado del cotejo | Accion restante al corte |
|---|---|---|
| 0: linea base | Inventario, barreras y rollback conservados como fotografia fechada. | Refrescar barreras antes de cada accion operativa, sin tratar el snapshot como estado vivo. |
| 1: riesgos operativos | Implementacion y escenarios de multiples pendientes, captura canonica, exclusividad, ambiguedad y heartbeat presentes. La ventana natural de 1.3A esta acreditada. | Corregir la frase que todavia la declaraba abierta; conservar el limite observacional. |
| 2: pagos e integral | Invariantes, recibos, backfill y caja comun tienen implementacion y escenarios. Activacion tecnica v74 documentada. | 2.6 exige el primer integral natural posterior a v74; no cerrar funcionalmente la fase ni fabricar un caso. |
| 3: privacidad | Limpieza del formulario, redaccion CAPTCHA y actor autenticado presentes y con escenarios. | No se identifico una omision nueva en el alcance revisado. |
| 4: seguridad automatica | Locks, CI, cobertura critica, pruebas frontend y guardas presentes; Backend y Frontend exigidos en main. | Administradores pueden omitir la proteccion actual; no se modificaron permisos. |
| 5: fronteras backend | Extracciones documentadas; la revision detecto acceso directo de auditoria Telegram a DB y los dos retiros de fachada abiertos. | Telegram corregido mediante Admin API y Settings retirado; queda aceptacion natural de WhatsApp con el codigo extraido cargado. |

Las fases 6 a 8 siguen siendo trabajo futuro. En 7.2, el registro y transporte
comun ya se adelantaron con 5.5.2; quedan parsers por ruta y criterios completos
de contrato y compatibilidad. No corresponde repetir la extraccion del router
ni marcar cerrada toda 7.2.

## Evidencia de implementacion y escenarios

- `tests/test_program_resolution.py`: atomicidad, idempotencia, listado obsoleto,
  rollback y ausencia de jobs WhatsApp durante la resolucion.
- `tests/test_manual_session_exclusivity.py`: admision concurrente por cuenta,
  conflictos de propietario y permanencia de `close_timeout` en inventario.
- `tests/test_worker.py`: bloqueo simulado de seis minutos, recuperacion de BD
  y perdida conservadora del lease.
- `tests/test_whatsapp_delivery.py`: excepciones de navegador, persistencia y
  callback posteriores a una posible interaccion conservan `uncertain`.
- `reservation_engine/slot_evidence.py` y `monitor.py`, bajo
  `src/appointment_bot/`: captura canonica inicial y recuperada antes del intento.
- `tests/test_database.py` y `tests/test_finance_receipt_quality.py`: importes
  integrales, constraints, saldo, recibos inmutables, caja entre meses y restore
  aislado con forma v70.
- `dashboard/src/app/app.ts`, pruebas de modales y
  `src/appointment_bot/core/statuses.py`: limpieza sensible y redaccion recursiva.
- `tests/test_finance_actor.py`: la identidad del body no gobierna la auditoria.
- `.github/workflows/ci.yml`, `requirements-dev.lock`, `dashboard/package-lock.json`
  y `scripts/check-critical-coverage.py`: instalacion, pruebas, auditorias y pisos
  de cobertura obligatorios.

La API de proteccion de `main` devolvio `Backend` y `Frontend` como checks
requeridos, `strict=true` y `enforce_admins=false`. Este ultimo valor limita la
afirmacion de obligatoriedad para administradores.

## Pendientes que no sustituye esta auditoria

El [informe natural del 7 de septiembre](../acceptance/natural-acceptance-2026-09-07.md)
acredita la ventana de 1.3A, pero conserva pendiente el integral posterior a v74.
Tambien distingue los cierres diarios y album ambiguos, la variante de registro
sin solicitud pendiente y el retiro de compatibilidad. Ya estaban contemplados
en el roadmap y no constituyen aceptacion de refactors posteriores.

La [revision de WhatsApp posterior a la extraccion](whatsapp-acceptance-review-2026-09-08.json)
no encontro un caso suficiente: el propietario observado arranco antes del
refactor. Primero debe cargar la implementacion extraida mediante un reinicio
coordinado seguro y despues observarse el trabajo natural aplicable. No se
generaron envios para forzar ese cierre.

El acceso directo detectado en Telegram se corrigio con un endpoint
autenticado de auditoria. Se retiraron sus reexports sin consumidores y la
fachada Settings, sin crear otro contenedor global. La
[verificacion de configuracion](configuration-retirement-2026-09-08.json)
detalla equivalencia y limites. Ninguno de estos trabajos pertenece a una fase nueva.
