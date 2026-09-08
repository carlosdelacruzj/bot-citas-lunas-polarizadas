# Operacion financiera mensual

Este runbook explica como registrar costos y cerrar un mes desde la vista
**Finanzas**. La semantica contable, estados, categorias y reglas de calculo
pertenecen al [`contrato financiero`](../contracts/finance.md).

## Registro cotidiano

Registrar desde el dashboard cada costo con la mejor evidencia disponible:

1. fecha real del movimiento;
2. tipo y categoria definidos por el contrato;
3. importe y moneda originales;
4. tipo de cambio realmente aplicado cuando no sea PEN;
5. proveedor, canal, campana u orden solo cuando correspondan;
6. referencia de evidencia sin tokens, credenciales ni datos personales.

La accion **Anular** conserva auditoria. No intentar borrar directamente un
movimiento en PostgreSQL.

## 2Captcha

Al cierre, obtener del panel el saldo inicial, recargas, saldo final,
reembolsos y consumo informado. Registrar recarga y consumo como movimientos
distintos conforme al contrato para evitar contar dos veces el mismo dinero.

Si el consumo debe reconstruirse, conservar la fuente y comprobar:

```text
consumo = saldo_inicial + recargas - saldo_final - reembolsos
```

Nunca guardar la API key como evidencia o nota.

## TikTok y captacion

Registrar cada pago o recarga publicitaria con `channel=tiktok` y la campana
cuando se conozca. Para calcular CAC o ROAS, usar un mismo periodo y solamente
clientes o ingresos con atribucion demostrable. Una publicacion organica tiene
gasto publicitario cero; el tiempo humano se registra aparte cuando exista una
metodologia documentada.

No presentar CAC o ROAS como concluyentes si faltan gastos, atribucion o
conversion monetaria. Las formulas y barreras de publicacion viven en el
contrato.

## Checklist de cierre mensual

1. Revisar movimientos `pending`, estimados y sin conversion a PEN.
2. Conciliar saldo inicial, recargas, consumo, reembolsos y saldo final de
   prepagos.
3. Revisar publicidad por canal y campana.
4. Registrar comisiones, devoluciones y costos demostrables faltantes.
5. Resolver diferencias entre pagos cobrados y montos acordados.
6. Separar ingresos cobrados, costos reconocidos y overhead aun no medido.
7. Valorar tiempo humano solo con minutos y tarifa documentados.
8. Confirmar que no existan bloqueos de calidad antes de conciliar el mes.
9. Registrar responsable, notas y estado del cierre desde el dashboard.

No reconstruir costos historicos sin evidencia. Si se hace una estimacion,
marcarla como tal y explicar su metodo.

## Resultado esperado

El cierre debe permitir distinguir caja, costo reconocido, margen operativo
antes de costos no registrados y calidad del dato. Una vista incompleta no debe
presentarse como utilidad neta.
