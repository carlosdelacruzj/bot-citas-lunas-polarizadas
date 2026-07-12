# Backend y seguridad

## P0 - Reducir exposicion de datos en API administrativa

Estado: completado el 12 de julio de 2026.

Problema: el listado general de ordenes necesita datos para operar, pero hoy el
contrato y la implementacion no separan con suficiente claridad campos
enmascarados de documento/WhatsApp y datos completos usados al editar.

Implementado:

1. `GET /api/v1/service-orders` devuelve documento y WhatsApp enmascarados.
2. `GET /api/v1/service-orders/{order_id}` entrega el detalle
   administrativo explicito, protegido y con allowlist propia.
3. El dashboard solicita el detalle solo al abrir edicion y lo descarta al
   cerrar.
4. Snapshots, filtros, tablas y copiado general no incluyen datos
   completos por defecto.
5. Contrato y pruebas existentes actualizados.
6. Listado, detalle, autenticacion, build y suite validados.

Criterio de cierre cumplido: el listado y snapshot solo contienen valores
enmascarados; la edicion usa una solicitud protegida y deliberada.

## P1 - Validacion compartida de altas

Estado: parcial.

Ya esta hecho: contacto y fuente son obligatorios en dashboard, API y CLI; la
fuente se limita en CLI a TikTok, Facebook o WhatsApp.

Pasos restantes:

1. Centralizar la lista de fuentes permitidas para API y CLI.
2. Normalizar espacios, mayusculas y telefonos sin inventar datos.
3. Devolver errores de campo consistentes al dashboard.
4. Confirmar que altas avanzadas siguen disponibles por contrato sin recargar
   el formulario normal.

## P2 - Dividir modulos grandes

Estado: pendiente no bloqueante. Ejecutar despues de optimizacion P1.

1. Dividir `db/orders.py` en credenciales, contactos/pagos, estado/leases y
   seleccion/promocion de cola.
2. Dividir `worker/queue_runtime.py` en recorrido de cola, ejecucion individual
   y politica de transferencia/diferimiento.
3. Mantener migraciones historicas y contratos publicos estables.
4. Mover consumidores por cortes pequenos y retirar compatibilidad solo al
   final.

Criterio de cierre: ningun cambio funcional, suite completa verde y runtime
del worker verificado.
