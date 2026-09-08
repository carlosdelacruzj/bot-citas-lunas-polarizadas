# Aceptacion natural de WhatsApp

Estado: vigente. El roadmap indica qué flujos faltan; este runbook explica como
validar cualquiera de ellos.

## Limites

- no crear clientes, jobs ni envios ficticios;
- observar el siguiente caso natural;
- no reenviar `uncertain`;
- no editar historicos para forzar aceptacion;
- una recuperación autorizada es un job separado.

## Evidencia comun

Para cada flujo registrar:

- tipo, orden y destinatario enmascarado;
- texto, clave y revision de plantilla congelados;
- adjuntos esperados y confirmacion por componente;
- captura/contexto de WhatsApp;
- estado tecnico del job;
- conciliacion posterior, si existe.

`sent`, llegada, lectura y confirmacion del cliente son afirmaciones distintas.
Un reloj visible veta `sent`; marcadores ocultos no confirman.

## Criterios por flujo

| Flujo | Evidencia adicional |
|---|---|
| Aviso de registro | Variante correcta, destinatario y deduplicacion. |
| Reserva/cobro | Dos imagenes, monto y componentes separados. |
| Postpago | PDF originales en orden y texto posterior independiente. |
| Recordatorio | Fecha/hora/sede, lead days y barrera durable. |
| Resumen diario | Adjuntos marcados completos antes de publicar texto. |

## Revision

1. Consultar primero dashboard/API.
2. Abrir PostgreSQL o evidencia técnica solo si falta detalle.
3. Comparar componentes sin convertir preparación en envio.
4. Si la evidencia es suficiente, registrar aceptación del flujo.
5. Si es ambigua, conservar `uncertain` y cerrar sin reintento.

Las consultas directas son diagnostico excepcional; no deben convertirse en un
segundo dispatcher ni modificar el resultado original.

Contrato: [`../contracts/whatsapp.md`](../contracts/whatsapp.md).
Pendientes: [`../roadmap/README.md`](../roadmap/README.md).
