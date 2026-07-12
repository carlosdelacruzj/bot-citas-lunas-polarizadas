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

Estado: completado el 12 de julio de 2026.

Implementado:

1. La orden seleccionada separa cliente, reglas, reserva, pago/cierre y
   jerarquia de tramite en bloques operativos.
2. Una tarjeta calcula la siguiente accion valida segun estado; las acciones
   incompatibles quedan deshabilitadas.
3. La prioridad explica cola normal `0-99` y enfoque `>=100` en lenguaje de
   operador.
4. Padre, expediente, placa y subordenes navegables forman una jerarquia clara.
5. Toda accion POST conserva el paso de confirmacion visible existente.

Criterio de cierre cumplido: seleccionar una orden presenta contexto, siguiente
paso y acciones compatibles sin exigir conocimiento de PostgreSQL.

## P1 - Accesibilidad y movil

Estado: completado el 12 de julio de 2026.

Implementado:

1. Los modales reciben foco inicial, cierran con Escape y restauran el foco al
   control de origen.
2. Dialogos y avisos usan etiquetas, `aria-live`, `aria-invalid` y asociaciones
   con la ayuda de campos obligatorios.
3. Los controles tactiles principales miden al menos 44 px en movil; tablas y
   bloques operativos colapsan a una columna sin ancho minimo forzado.
4. Foco visible, contraste semantico y estados `disabled`/`busy` permanecen
   distinguibles.

Criterio de cierre cumplido: build Angular limpio, dashboard y API accesibles
por HTTP y reglas responsive verificadas. La inspeccion visual integrada no
estuvo disponible en esta sesion.

## P2 - Entrega local estable

Estado: completado el 12 de julio de 2026.

Implementado:

1. `scripts/start-admin-dashboard.ps1` construye Angular e inicia admin API y
   dashboard con un solo comando.
2. El admin API sirve el build en `http://127.0.0.1:8766/`, limitado a loopback,
   con CSP y sesion local `HttpOnly`/`SameSite=Strict`; el token no entra en
   Angular.
3. La operacion normal queda en dos procesos: worker y admin-dashboard.
4. `npm start` con `dashboard/proxy.conf.cjs` sigue disponible como rollback y
   desarrollo, sin cambiar `.env`.

Criterio de cierre cumplido: portada y API respondieron HTTP 200 mediante la
sesion del dashboard; la API rechazo una llamada sin token ni sesion y el build
Angular se mantuvo verde.
