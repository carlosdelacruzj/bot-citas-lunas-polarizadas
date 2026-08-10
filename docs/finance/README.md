# Registro financiero operativo

Este directorio conserva los costos del negocio que no viven en las tablas de pagos. El
objetivo inicial no es tener contabilidad perfecta: es dejar de tratar los ingresos cobrados
como si fueran utilidad.

## Fuente de verdad

El registro serio vive en PostgreSQL y se administra desde la vista **Finanzas** del
dashboard. La estructura y API estan documentadas en
[`../contracts/finance.md`](../contracts/finance.md). El archivo
[`cost-register.csv`](cost-register.csv) queda como antecedente historico del primer dato;
ya no es fuente de calculo ni formato autorizado para nuevas altas.

Desde el dashboard se puede crear, editar y anular. La anulacion reemplaza la eliminacion
fisica para mantener auditoria.

## Regla para 2Captcha

La recarga y el consumo no son el mismo costo:

- categoria `captcha` + `entry_kind=prepaid_topup`: dinero convertido en saldo
  prepagado. Es salida de caja, pero no debe sumarse nuevamente como gasto
  cuando se calcula el consumo.
- categoria `captcha` + `entry_kind=prepaid_consumption`: saldo realmente
  consumido durante el periodo. Este es el costo que debe compararse con los
  ingresos del periodo.

Para conciliarlo al cierre de cada mes:

```text
consumo = saldo_inicial + recargas - saldo_final - reembolsos
```

Si 2Captcha muestra directamente el costo consumido, registrar ese valor y guardar en
`evidence` una referencia al panel o comprobante. Nunca guardar la API key.

## TikTok y captacion

Registrar cada pago o recarga publicitaria, incluso si el monto es pequeno. Completar
`channel=tiktok` y, si se conoce, `campaign`. El gasto debe compararse con ordenes e ingresos
atribuidos al mismo canal y periodo.

```text
CAC = gasto de captacion / clientes nuevos cobrados atribuibles
ROAS = ingreso cobrado atribuible / gasto publicitario
```

Si una publicacion fue organica, el gasto publicitario es cero, pero se pueden registrar las
horas humanas por separado cuando exista una estimacion razonable.

## Categorias minimas

Empezar solo con costos que tengan evidencia:

1. categoria `captcha`, usando `prepaid_topup` o `prepaid_consumption` segun el
   movimiento.
2. categoria `marketing` para TikTok u otros canales.
3. categorias de comision o devolucion cuando aparezcan y esten definidas en
   PostgreSQL.
4. Internet, electricidad, hosting, backup y equipo cuando exista recibo o una
   metodologia documentada de reparto.
5. Tiempo humano cuando se midan minutos y se defina un valor por hora.
6. Impuestos cuando corresponda y exista criterio contable.

No hace falta reconstruir hoy todos los costos historicos. Registrar desde ahora los gastos
reales y marcar cualquier reconstruccion anterior como `estimated`.

## Cierre mensual minimo

Al final de cada mes, usando la vista Finanzas:

1. Conciliar saldo inicial, recargas y saldo final de 2Captcha.
2. Sumar publicidad por canal y campana.
3. Registrar comisiones, devoluciones y otros pagos demostrables.
4. Convertir USD a PEN con el tipo de cambio realmente aplicado; conservar ambos importes.
5. Comparar costos del periodo con ingresos cuyo `paid_at` pertenezca al mismo mes.
6. Separar utilidad antes del tiempo del propietario y utilidad despues de valorizarlo.

```text
margen_operativo_pre_tiempo = ingresos_cobrados - costos_monetarios
utilidad_economica = margen_operativo_pre_tiempo - valor_del_tiempo_humano
```

## Calidad del dato

- `actual`: importe respaldado por panel, recibo o movimiento.
- `estimated`: calculo razonable que todavia debe conciliarse.
- `pending`: se conoce el evento, pero falta monto o evidencia.

Los campos `order_id`, `campaign` y `evidence` son opcionales. No registrar documentos,
credenciales, tokens ni datos personales del cliente en este archivo.
