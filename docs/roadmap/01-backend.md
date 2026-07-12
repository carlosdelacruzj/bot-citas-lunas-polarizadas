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

Estado: completado el 12 de julio de 2026.

Implementado:

1. `CONTACT_SOURCES` centraliza TikTok, Facebook y WhatsApp para API, DB y CLI.
2. Nombre, fuente y WhatsApp se normalizan en `core/contacts.py`: espacios
   repetidos se colapsan, la fuente pasa a minusculas y el telefono conserva
   solo su `+` inicial y digitos, sin agregar codigo de pais.
3. Fuentes o telefonos invalidos producen `field_errors`; Angular los presenta
   con etiquetas de formulario comprensibles.
4. Dashboard, API y CLI exigen contacto y fuente en el alta normal.
5. Los campos avanzados siguen disponibles por API: prioridad, cobro, hora y
   fecha minima, dias, padre, expediente y placa. El formulario normal no se
   recargo con ellos.
6. La actualizacion de contacto reutiliza las mismas reglas y conserva la
   fuente existente cuando no se cambia.

Criterio de cierre cumplido: API, CLI y persistencia usan una sola regla de
contacto; los errores identifican el campo y el alta avanzada sigue cubierta
por la validacion existente.

## P2 - Dividir modulos grandes

Estado: completado el 12 de julio de 2026.

Implementado:

1. `db/order_credentials.py` concentra alta, credenciales, runtime y tramites.
2. `db/order_contacts.py` concentra resumen, contactos, pagos y cierre.
3. `db/order_state.py` concentra estado, leases y control de submission.
4. `db/order_queue.py` concentra restricciones, seleccion y promocion de cola.
5. `worker/order_execution.py`, `worker/queue_traversal.py` y
   `worker/queue_policy.py` separan ejecucion individual, recorrido y politica.
6. `db/orders.py` y `worker/queue_runtime.py` quedan como fachadas publicas
   pequenas, conservando imports y puntos de parcheo existentes.
7. No se alteraron migraciones, tablas, endpoints ni firmas publicas.

Criterio de cierre cumplido: sin cambio funcional; sintaxis, lint, suite
completa y carga del runtime del worker validados.
