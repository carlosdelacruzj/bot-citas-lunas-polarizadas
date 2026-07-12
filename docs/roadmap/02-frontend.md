# Frontend Angular

## P0 - Detalle sanitizado de runs

Estado: pendiente. Ejecutar despues del P0 backend.

1. Seleccionar una corrida desde la tabla.
2. Consultar `GET /api/v1/runs/{run_id}` sin `include_details=1`.
3. Mostrar estado, orden, tiempos, intento/confirmacion y rutas de evidencia
   permitidas.
4. No mostrar ni copiar `details` crudos por defecto.
5. Agregar estado de carga, vacio, error y retorno a la lista.
6. Validar desktop y movil.

Criterio de cierre: un operador entiende una corrida sin abrir PostgreSQL ni
exponer payloads internos.

## P1 - Flujo de orden centrado en tarea

Estado: parcial; la base responsive, filtros, seleccion y edicion ya existen.

1. Separar visualmente datos del cliente, reglas, reserva, pago y cierre.
2. Mostrar la siguiente accion valida segun estado, evitando botones imposibles.
3. Explicar prioridades `0-99` y enfoque `>=100` sin pedir conocimiento de DB.
4. Mostrar suborden padre, expediente y placa como jerarquia clara.
5. Conservar confirmacion visible antes de todo POST.

## P1 - Accesibilidad y movil

1. Revisar orden de foco y cierre de modales con teclado.
2. Asociar errores con campos y anunciar respuestas administrativas.
3. Verificar controles tactiles, tablas estrechas y ausencia de overflow.
4. Confirmar contraste y estados disabled/busy.

## P2 - Entrega local estable

1. Documentar un solo comando de arranque del dashboard y admin API.
2. Evaluar servir el build Angular desde el admin API local para reducir tres
   terminales a dos, sin exponerlo a Internet.
3. Mantener rollback al proxy actual hasta validar la alternativa.
