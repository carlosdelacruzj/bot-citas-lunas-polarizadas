# Contrato financiero

## Fuente de verdad

PostgreSQL es la fuente de verdad. `finance_categories` normaliza las categorias y
`finance_entries` conserva los movimientos. El CSV de `docs/finance/` es solo antecedente e
intercambio manual; no participa en los calculos del dashboard.

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

`is_complete` se conserva por compatibilidad y significa únicamente que todos
los movimientos activos del periodo tienen conversión monetaria a PEN. No
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

## Categorias iniciales

`captcha`, `marketing`, `payment_fee`, `refund`, `internet`, `electricity`, `hosting`,
`backup`, `equipment`, `human_time`, `tax` y `other`. Cada categoria se clasifica como costo
variable, fijo o mixto.
