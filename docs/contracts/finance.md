# Contrato financiero

Estado: vigente.

Ultima verificacion: `2026-09-01`.

Responsable: `db/finance.py` y `services/api/finance_routes.py`.

## Fuente de verdad

PostgreSQL es la fuente de verdad. `finance_categories` normaliza las categorias
y `finance_entries` conserva los movimientos. No existe un CSV activo como
fuente o intercambio autorizado para los calculos del dashboard.

`payment_receipts` conserva cada entrada de caja por separado. El total
acumulado de `payments` gobierna saldo y cierre operativo. Los recibos nativos
gobiernan la fecha real del ingreso en el resumen financiero; una fila con
`source=historical_backfill` conserva el monto acumulado anterior, pero su
`received_at` es una fecha inferida mediante `paid_at`, `updated_at` o
`created_at` y no demuestra cada abono. Cada recibo pertenece al par exacto
pago/orden mediante FK compuesta y no admite actualizacion, borrado ni cascada
destructiva.

Finanzas y el resumen mensual calculan `revenue_collected`, la serie diaria y
sus conteos desde la misma consulta de recibos. `payments_received` conserva su
nombre de contrato, pero cuenta movimientos firmados de `payment_receipts`, no
ordenes ni pagos cerrados. `distinct_payments` y `orders_with_receipts`
distinguen esos otros universos. Un abono pertenece al periodo de
`received_at`, aunque el pago se complete en otro mes.

Los cobros normales son positivos. Una correccion es otro movimiento negativo
con `source=payment_correction`, referencia al recibo original, motivo y actor;
la suma firmada conserva la caja corregida sin reescribir el hecho previo. El
esquema impide corregir una correccion o exceder el monto original. No existe
todavia una accion API para registrar estas correcciones.

## Semantica contable operativa

| `entry_kind` | Caja del periodo | Costo reconocido | Uso |
| --- | --- | --- | --- |
| `expense` | Si | Si | TikTok, Internet, comisiones y otros pagos consumidos |
| `prepaid_topup` | Si | No | Compra de saldo de 2Captcha u otro prepago |
| `prepaid_consumption` | No | Si | Saldo efectivamente consumido |
| `refund` | Resta | Resta | Reembolso recuperado |

Los importes se guardan en moneda original. `amount_pen` se calcula con
`exchange_rate_pen`; para PEN el tipo es 1. Si una moneda extranjera no tiene tipo de cambio,
el movimiento se conserva pero el resumen se marca incompleto y no debe llamarse utilidad
final.

`operating_margin_before_unregistered_costs` significa ingreso cobrado menos costos
reconocidos registrados. No es utilidad neta mientras falten costos, tiempo humano o
impuestos.

## Auditoria

No se elimina fisicamente un movimiento. La accion de eliminar en la interfaz produce una
anulacion con `status=voided`, `voided_at` y `void_reason`. Los anulados quedan visibles y se
excluyen de todos los calculos. Solo los registros activos pueden editarse.

## API local protegida

```text
GET  /api/v1/finance/categories
GET  /api/v1/finance/entries?month=YYYY-MM&include_voided=1
GET  /api/v1/finance/summary?month=YYYY-MM
GET  /api/v1/finance/data-quality?month=YYYY-MM
GET  /api/v1/finance/month-closure?month=YYYY-MM
POST /api/v1/finance/entries
POST /api/v1/finance/entries/{entry_id}/edit
POST /api/v1/finance/entries/{entry_id}/void
POST /api/v1/finance/payments/{payment_id}/reconcile-amount
POST /api/v1/finance/month-closure
```

Crear y editar reciben el movimiento completo. Campos obligatorios:
`occurred_on`, `entry_kind`, `category_code`, `description` y `amount_original`. Los campos
opcionales incluyen proveedor, tipo de cambio, cantidad/unidad, canal/campana, orden,
evidencia y notas.

No guardar tokens, credenciales ni datos personales dentro de evidencia o notas.

## Calidad y cierre mensual

`receipt_date_quality` se expone en el resumen financiero, centro de calidad y
metricas mensuales. Distingue `exact`, `inferred`, `mixed` y `no_receipts`,
separa cantidades y montos exactos/inferidos y publica `exact_since`. Este
corte es el instante de creacion del backfill en cada base, no una constante
global. Si un rango contiene al menos un recibo inferido,
`comparison_conclusive=false` y la interfaz no presenta una variacion mensual
de ingresos como concluyente.

`conversion_complete` significa únicamente que todos los movimientos activos
del periodo tienen conversión monetaria a PEN. No
certifica captura completa de costos, utilidad neta ni conciliación contable.

El centro de calidad separa movimientos `actual`, `estimated` y `pending`,
importes sin conversión y pagos `paid` cuyo monto difiere de `amount_agreed`.
Estos últimos requieren una clasificación humana explícita: `discount`,
`waiver` o `correction`, además de motivo y responsable. La API nunca infiere
la causa.

`finance_month_closures` conserva saldo prepago inicial/final, recargas,
consumo, reembolsos, notas, estado, fecha de conciliación y responsable. Un mes
actual o futuro no puede cerrarse. Tampoco puede marcarse `reconciled` mientras
existan movimientos pendientes o sin conversión, diferencias de pago sin
resolver, o si el saldo final no coincide con:

`saldo inicial + recargas - consumo + reembolsos prepagos`.

El margen porcentual, costo por reserva, costo CAPTCHA por reserva, CAC y ROAS
permanecen ocultos mientras la captura de costos o atribución no esté
conciliada.

Para prepagos, la conciliación operativa del consumo debe cumplir:

`consumo = saldo inicial + recargas - saldo final - reembolsos`.

Recarga y consumo son hechos distintos: una recarga mueve caja y el consumo
reconoce costo. Registrar ambos como gasto duplicaría el mismo importe.

Las métricas de captación usan un mismo periodo y solo atribución demostrable:

```text
CAC = gasto de captación / clientes nuevos cobrados atribuibles
ROAS = ingreso cobrado atribuible / gasto publicitario
```

Una publicación orgánica puede tener gasto publicitario cero. El tiempo humano
solo entra como costo cuando existen minutos y valor por hora documentados.

## Categorias iniciales

`captcha`, `marketing`, `payment_fee`, `government_fee`, `refund`, `internet`, `electricity`, `hosting`,
`backup`, `equipment`, `human_time`, `tax` y `other`. Cada categoria se clasifica como costo
variable, fijo o mixto.

`government_fee` representa tasas oficiales pagadas por cuenta del cliente. El
paquete integral crea el movimiento de `S/71.40`, con la orden vinculada, al
confirmar en el alta que la tasa ya fue pagada. Repetir el alta no duplica el
movimiento. Cancelar con saldo incobrable conserva este costo y el abono; una
devolucion o correccion exige movimientos contables auditados y no reescribe los
hechos originales.

La secuencia operativa del cierre vive en
[`../finance/README.md`](../finance/README.md).
