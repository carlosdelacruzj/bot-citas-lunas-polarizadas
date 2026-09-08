# Resumen del negocio

Ultima verificacion conceptual: `2026-08-29`.

Este archivo describe la oferta estable. Ingresos, conversiones, costos y
volumenes actuales deben consultarse en PostgreSQL o reportes con fecha de corte.

## Servicio

Gestionamos la busqueda y reserva de citas de peritaje vinculadas al permiso de
lunas polarizadas en Peru. La Policia Nacional entrega la autorizacion; el
servicio no vende el permiso ni garantiza una fecha.

El valor ofrecido es:

- validar acceso y datos necesarios;
- monitorear disponibilidad;
- reservar automaticamente un cupo compatible;
- conservar evidencia;
- guiar pago y pasos posteriores;
- comunicar avances y recordatorios;
- acompañar la cita y revision posterior.

## Servicios y precios

El precio se acuerda y persiste por orden.

| Modalidad | Referencia | Condicion |
|---|---:|---|
| Regular | `S/50` | Disponibilidad normal dentro de reglas generales. |
| Restringida | `S/70` | Ventana cerrada y dias/rangos específicos. |
| Personalizada | Definida por el operador | Requiere dejar monto y condiciones antes del preflight. |

Los valores son referencias operativas actuales, no una garantia permanente de
tarifa. Una orden existente conserva su precio aunque cambie el default.

## Recorrido del cliente

1. Registro de contacto, credenciales, modalidad, precio y restricciones.
2. Validacion de identidad y acceso.
3. Monitoreo de cupos compatibles.
4. Reserva con evidencia.
5. Cobro y envio de documentos o instrucciones aplicables.
6. Recordatorio previo.
7. Seguimiento posterior a la cita.

Cada etapa conserva estado separado. Buscar no significa reservar; reservar no
significa cobrar; preparar WhatsApp no significa enviar; enviar no significa que
el cliente lo leyó.

## Promesa comercial segura

Comunicar “busqueda, gestion, reserva y acompañamiento”. No prometer:

- una fecha que el portal no ha ofrecido;
- aprobacion del permiso;
- entrega o lectura de WhatsApp sin evidencia;
- plazos garantizados a partir de muestras pequeñas;
- ausencia total de costos o trámites posteriores.

## Control financiero

Separar:

- cobros realizados;
- saldos pendientes;
- costos reconocidos;
- recargas prepagadas frente a consumo real;
- devoluciones y diferencias;
- overhead y tiempo humano aun no medidos.

Contrato: [`contracts/finance.md`](contracts/finance.md). Un snapshot mensual no
es utilidad neta si faltan costos o conciliaciones.

## Indicadores utiles

- ordenes creadas y aptas;
- reservas confirmadas por intento compatible;
- tiempo hasta reserva por cohorte comparable;
- cobrado frente a pendiente;
- costo por reserva y por cliente cobrado;
- fallos/`uncertain` de comunicaciones;
- recordatorios y revisiones post-cita completadas;
- origen comercial cuando la atribucion existe.

Toda cifra debe incluir periodo, muestra, cobertura y limites. Asociación
temporal no demuestra causalidad.

## Riesgos

- dependencia del portal y su disponibilidad;
- datos o credenciales incorrectos del cliente;
- ventanas demasiado restrictivas;
- envios ambiguos de WhatsApp;
- evidencia sensible local;
- costos y atribucion comercial incompletos;
- automatizaciones externas sin autoridad sobre reservas.

El estado tecnico actual está en [`project-status.md`](project-status.md) y el
trabajo futuro en [`roadmap/README.md`](roadmap/README.md).
