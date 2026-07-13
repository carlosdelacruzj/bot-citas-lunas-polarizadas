# Manual operativo

## Arranque recomendado

Terminal 1:

```powershell
scripts/start-worker.ps1
```

Terminal 2:

```powershell
scripts/start-admin-dashboard.ps1
```

Abrir `http://127.0.0.1:8766/`. El admin API sirve Angular y usa una sesión
local `HttpOnly`/`SameSite=Strict`; no exponer ni redirigir este puerto fuera de
loopback.

Los recursos del dashboard local se sirven con revalidación obligatoria para
evitar que una pestaña recargada conserve un build anterior durante cambios de
interfaz. Una pestaña que ya estaba abierta debe actualizarse una vez después de
publicar un build nuevo.

Rollback/desarrollo: ejecutar `appointment-bot-admin-api` y `npm start` dentro
de `dashboard/`. El proxy sigue apuntando a `127.0.0.1:8766`.

## Salud y calendario

- `http://127.0.0.1:8765/health`: vida del worker.
- Dashboard `/api/v1/worker`: fase real del worker.
- `outside_hot_window` con `worker_running=true`: espera saludable.
- Las búsquedas automáticas funcionan de lunes a sábado; domingo no abre
  sesiones ni consulta el portal.

## Cambiar prioridad desde el dashboard

1. Abrir **Órdenes** y seleccionar la orden.
2. Pulsar **Editar**.
3. En **Prioridad de búsqueda**, ingresar un entero no negativo y confirmar.
4. Usar `0–99` para cola normal o `100` o más para enfoque.

Si dos órdenes deben ocupar los dos observadores, asignar `100` a cada una por
separado. El cambio entra en la siguiente selección y no requiere reiniciar el
worker.

## Consultar contacto operativo

Al seleccionar una orden se abre un panel lateral con el detalle administrativo:
nombre, WhatsApp completo, fuente, reglas, reserva, pago, trámite y acciones. El
panel no reduce ni desplaza la tabla y se cierra con **Cerrar**, `Esc` o pulsando
fuera. En móvil ocupa la pantalla completa. La tabla, los filtros, los snapshots
y las copias masivas continúan usando el número enmascarado para no exponer todos
los contactos a la vez.

## Flujo simplificado del operador

- La tabla muestra solo cliente, estado, reserva, pago y una acción
  contextual; prioridad, reglas, cierre y trámite permanecen en el panel lateral.
- El identificador técnico `order_id` no aparece en la tabla principal; se
  conserva en el panel lateral para diagnósticos. La tabla usa nombre, documento
  enmascarado y fuente para reconocer al cliente.
- La acción principal cambia según la orden: abrir sesión, activar, registrar
  pago o ver detalle.
- El panel ofrece accesos directos para editar, pausar/activar y gestionar otros
  cierres, además de presets **Cola normal** (`0`) y **Enfoque 100**.
- Las confirmaciones y resultados usan SweetAlert2 con mensajes claros; las
  acciones de lectura o navegación no solicitan confirmación innecesaria.
- La navegación por teclado conserva el foco al abrir y cerrar el panel.
- Al cerrar una sesión manual, la fila desaparece inmediatamente y el backend
  fuerza la limpieza del registro si Playwright no termina en ocho segundos.

## Resumen mensual

La vista **Resumen** permite elegir un mes y muestra ingresos realmente
cobrados, reservas, altas, ticket promedio, conversión, comparación con el mes
anterior, ingresos diarios y resultados por fuente. Los cobros pendientes y las
órdenes activas aparecen separados como trabajo por atender. Pulsar un pendiente
abre directamente su orden en el panel operativo.

Las fechas se agrupan en `America/Lima`: `paid_at` para ingresos, `reserved_at`
para reservas y `created_at` para órdenes nuevas. No sumar el importe pendiente
al ingreso cobrado.

## Formato de fecha y hora

Toda fecha visible del dashboard usa `DD-MM-YYYY`. Las horas usan formato de 24
horas `HH:mm` y los timestamps completos `DD-MM-YYYY HH:mm:ss`, siempre en la
zona `America/Lima`. Los controles HTML de captura pueden conservar internamente
`YYYY-MM-DD`, porque ese es el formato técnico exigido por el navegador.

## Recuperación

### Worker

1. Revisar health, fase, `next_check_at` y último error.
2. No reiniciar si está esperando fuera de ventana.
3. Si no responde, cerrar solo el worker y ejecutar `scripts/start-worker.ps1`.
4. Confirmar health y fase.

### Admin API y dashboard

1. Revisar `http://127.0.0.1:8766/health`.
2. Cerrar solo admin-dashboard.
3. Ejecutar `scripts/start-admin-dashboard.ps1 -SkipBuild`; reconstruir sin el
   flag si falta el build.
4. Comprobar órdenes y runs.

## Reportes

```powershell
appointment-bot-client weekly-report --start YYYY-MM-DD --end YYYY-MM-DD
appointment-bot-client optimization-observation --start YYYY-MM-DD --end YYYY-MM-DD
```

Las salidas vigentes están en `reports/operations/latest.md` y
`reports/optimization/latest.md`. Agregar `--notify` al reporte semanal solo
cuando se desee enviar sus alertas por Telegram.

## Simulacro de backup/restore

```powershell
scripts/verify-postgres-backup.ps1
```

El script restaura en una base temporal, compara tablas esenciales y elimina la
base y el dump al finalizar. Es una verificación de restaurabilidad, no una
política de backup durable. No versionar `.dump`, `.sql` ni `backups/`.

## Evidencia

Seguir [`evidence-policy.md`](evidence-policy.md). La primera lectura es
`docs/evidence-summary.md`, luego `docs/evidence-index.csv`; las bitácoras
extensas viven en `reports/evidence/history/`.
