# Preparacion para iniciar 6.4

Fecha de corte: `2026-09-19`, America/Lima. Informe generado de una revision
local; no representa el runtime vivo ni sustituye el roadmap.

## Alcance y resultado

El punto de partida era `8a5d84c` (dashboard 6.3). Los cambios acumulados se
conservaron y separaron por comportamiento: evidencia diaria, cupos agotados,
rechazos temporales, recuperacion WhatsApp, plantillas, elegibilidad de
expedientes, consulta protegida y consulta de empresas. No se implemento 6.4.

La base local permite iniciar el bloque visual cuando el operador lo indique.
Esta autorizacion de preparacion no cierra aceptaciones naturales ni habilita
features comerciales, retirada de compatibilidad o despliegue automatico.
Los commits son locales; no se publico esta preparacion ni se ejecuto CI remoto.
El fetch inicial verifico coincidencia de `8a5d84c` con upstream.

## Validacion tecnica

- Python `3.12.6`, instalacion limpia de `requirements-dev.lock` con hashes en
  `.runtime/pre64/venv`, sin modificar el entorno operativo ni `.env`.
- Backend: `181 passed, 24 subtests passed`; cobertura critica aprobada sin
  reducir umbrales. Mismo resultado en Python compartido y entorno del lock.
- Compileall y Ruff aprobados; arquitectura: 326 modulos, cero ciclos y una
  dependencia inversa previamente baselinada.
- `pip check` y `pip-audit` del entorno aislado aprobados. El Python compartido
  conserva un conflicto ajeno entre torch y setuptools; no se altero.
- Dashboard: instalacion limpia `npm ci`, 14 pruebas unitarias, typecheck y smoke Chromium aprobados.
  El smoke simula la API y no opera sobre clientes reales.
- Build emitido bajo `.runtime/pre64/dashboard`, sin sustituir el dashboard
  servido por Admin API. Bundle inicial: 581.93 kB; CSS de App: 30.04 kB.
  Ambos conservan warnings de presupuesto que pertenecen a 6.4.
- Auditoria npm: 11 avisos moderados, cero altos/criticos; pasa el umbral
  vigente `--audit-level=high`. Una actualizacion mayor queda fuera de 6.4.
- No se agregaron pruebas automatizadas nuevas. Se conservaron los ajustes de
  fixtures que ya formaban parte del trabajo acumulado.
- El validador documental excluye `.runtime`, igual que entornos/dependencias:
  no trata README de paquetes instalados para validacion como documentos del proyecto.
- Evidencia local detallada: `.runtime/pre64/locked-pytest.xml`,
  `locked-coverage.json`, `architecture.json`, `runtime.json` y
  `no-pending-acceptance.json`. No se versionan datos operativos crudos.

La validacion local no equivale a CI Linux: el workflow fija Python 3.12.14.

## Operacion observada, sin mutaciones

Consulta PostgreSQL `REPEATABLE READ READ ONLY` a las 16:38 Lima:

- esquema real v75;
- un intento `unknown` y un lease de orden activo;
- cero preflights pendientes/en curso, rafagas abiertas, comandos pendientes
  y trabajos WhatsApp queued/blocked/running en ese instante;
- Admin API responde; su `/health` es `api_only` y no mide el worker remoto.
  La consulta posterior a `/api/v1/worker`, 16:41 Lima, confirma lease activo
  y worker pausado. Esta revision no solicito pausa ni reanudacion.

No hubo reinicios, migraciones operativas, reservas, envios, reintentos ni
conciliaciones. La version exacta cargada por cada proceso no se certifico;
los resultados de codigo corresponden al checkout validado.

## Aceptaciones que no deben confundirse con el cierre tecnico

- **2.6:** solo existe un integral creado el 29 de agosto con recibo historico
  acumulado. No acredita el primer integral nuevo posterior a v74.
- **5.5.5:** hay actividad natural posterior a la recarga documentada del
  8 de septiembre: 75 albumes, 65 postpagos, 77 avisos y 37 recordatorios con
  estado tecnico `sent` en la ventana consultada. Falta revisar componentes
  concretos y evidencia antes de retirar reexports; no se retiraron.
- **Sin solicitud pendiente:** dos avisos `sent` del 10 de septiembre con
  plantilla/revision/texto congelados y tres capturas retenidas por caso.
  La existencia de archivos no sustituye su inspeccion visual; sigue abierta.
- **Aviso conjunto:** no se observaron jobs de la plantilla multiple en la
  ventana; no se genero un caso artificial.
- **Comunicaciones por conciliar:** inventario historico sin review_resolution:
  38 cierres diarios, 14 albumes, 9 postpagos y 15 avisos `uncertain`, ademas
  de 6 fallos. No equivale a no entrega ni autoriza reenvios.
- **Compatibilidad:** `AdminApiClient.get_service_orders()` sigue usando la
  lista sin projection. La ventana nueva de siete dias no puede darse por
  completada; no se retiraron puertos ni respuestas.

## Frontera de inicio

6.4 mantiene sus casillas abiertas. Al recibir la indicacion del operador:
releer estado/roadmap, comparar Git con este corte y comenzar exclusivamente
por encapsulacion visual, foco/inert, Escape, teclado, contraste, reduced motion
y responsive a 360/768/1024/1440 px. No aumentar presupuestos para ocultar warnings.
Los cambios de evidencia generados despues de este corte no son cambios del
codigo del dashboard y deben conservarse separados.
