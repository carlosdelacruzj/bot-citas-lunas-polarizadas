# Frontend Angular

## P0 - Detalle sanitizado de runs

Estado: completado el 12 de julio de 2026.

Implementado:

1. La tabla permite seleccionar una corrida y conserva una fila activa visible.
2. El dashboard consulta `GET /api/v1/runs/{run_id}` sin
   `include_details=1`.
3. El detalle muestra estado, orden, resultado, tiempos, codigo de salida,
   mensaje y rutas publicas de evidencia.
4. `details` crudos no forman parte del contrato solicitado ni de la vista.
5. La vista incluye carga, error con reintento, ausencia de evidencia y retorno
   a la lista.
6. Build de produccion y flujo responsive validados.

Criterio de cierre cumplido: un operador entiende una corrida sin abrir
PostgreSQL ni exponer payloads internos.

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
