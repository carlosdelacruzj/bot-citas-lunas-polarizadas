# Resumen integral del negocio

Última actualización: `2026-08-25`.

## 1. Qué negocio operamos

Ofrecemos un servicio de gestión y acompañamiento para conseguir una cita de
peritaje vinculada al permiso de lunas oscurecidas o polarizadas en Perú. El
cliente no nos paga por emitir el permiso: la autorización la entrega la Policía
Nacional del Perú después de que el propietario cumpla los requisitos y apruebe
los peritajes correspondientes.

Nuestro valor está en reducir la incertidumbre y el trabajo manual del cliente:

- validamos el acceso al portal;
- monitoreamos continuamente la disponibilidad de citas;
- reservamos automáticamente cuando aparece una oportunidad compatible;
- conservamos evidencia de la reserva;
- guiamos el pago y las acciones posteriores;
- enviamos comunicaciones y recordatorios;
- damos seguimiento después de la cita.

La promesa comercial debe expresarse como **gestión, monitoreo, reserva y
acompañamiento**, no como venta del permiso ni como garantía de una fecha
determinada.

## 2. Cliente objetivo

El cliente principal es el propietario de un vehículo que:

- necesita obtener por primera vez el permiso de lunas polarizadas;
- tiene poco tiempo para revisar continuamente el portal;
- quiere evitar errores de registro, pago o asistencia;
- valora recibir evidencia y acompañamiento por WhatsApp;
- puede necesitar posteriormente un duplicado, una actualización o gestionar
  otro vehículo.

También existe potencial para familias, personas que gestionan varios vehículos,
talleres de polarizado, concesionarios y pequeñas flotas.

## 3. Precios comerciales actuales

La tarifa base vigente es **S/50 por trámite** para las altas nuevas. El cambio
desde S/40 se aplicó desde agosto de 2026 y fue aceptado sin una caída visible
de la conversión.

Desde el 25 de agosto de 2026 queda disponible para ofrecer **Día elegido por S/70**. En
este servicio el operador registra un día recurrente de la semana —por ejemplo,
solo lunes o solo sábados— y el sistema no puede reservar en otro día. Además,
puede indicar desde qué fecha empezar, hasta qué fecha buscar o un rango completo;
el sistema buscará únicamente el día elegido dentro de esos límites. La
disponibilidad continúa dependiendo de la PNP:
se cobra únicamente si se consigue la reserva solicitada y no se garantiza que
aparezca un cupo.

Durante el alta por Telegram el operador debe elegir y confirmar uno de estos
valores antes de iniciar el monitoreo:

- Estándar — S/50;
- Día elegido — S/70;
- monto personalizado para una excepción acordada.

Después de validar el acceso, todos los clientes reciben una misma estructura de
confirmación con el servicio, precio acordado, condiciones de búsqueda y fechas
excluidas cuando correspondan. Esto permite que el cliente revise claramente el
alcance registrado antes de que se consiga una cita.

Los S/50 o S/70 corresponden a nuestro servicio. No incluyen las tasas oficiales, el
costo de instalar o retirar láminas, traslados, peritajes adicionales ni otros
pagos que correspondan al propietario.

Como referencia verificada el 23 de agosto de 2026, la página oficial del Estado
publica estas tasas:

- permiso nuevo: S/71.40;
- duplicado: S/13.20;
- actualización: S/18.60.

Estas cantidades pueden cambiar y deben comprobarse antes de comunicarlas a un
cliente:
<https://www.gob.pe/459-obtener-permiso-de-lunas-polarizadas>.

## 4. Qué incluye actualmente el servicio base de S/50

### Registro y validación

- Alta manual desde Telegram o administración desde el dashboard.
- Documento de identidad, contraseña, contacto, fuente y restricciones de fecha.
- Validación previa de las credenciales contra el portal.
- Detección diferenciada de contraseña incorrecta y errores técnicos.
- Corrección guiada de contraseña desde Telegram cuando el portal rechaza el
  acceso.
- Protección contra registros duplicados después de respuestas ambiguas o
  timeouts.

### Búsqueda y reserva

- Monitoreo continuo del portal.
- Una sesión de navegador independiente por cliente, sin compartir cookies ni
  credenciales entre usuarios.
- Reglas por fecha mínima, fecha máxima, días permitidos y rangos excluidos.
- Prioridad operativa Normal, Enfocada o Exclusiva.
- Selección de la fecha compatible más cercana y del horario más temprano.
- Reserva automática cuando aparece un cupo compatible.
- Manejo controlado de CAPTCHA, pérdida de cupo, errores temporales y bloqueos del
  portal.
- Evidencia durable de oportunidades, intentos y resultado final.

No se debe prometer una fecha exacta ni asegurar que aparecerá un cupo. Las
prioridades organizan el monitoreo interno, pero no controlan la disponibilidad
de la PNP.

### Evidencia y cobro

- Confirmación estricta de que la reserva quedó registrada.
- Álbum con evidencia de la reserva y QR de Yape.
- Registro de monto acordado, abonos, saldo y pago completo.
- Validación manual de pagos desde Telegram.
- Los abonos mantienen el cobro pendiente y no disparan el postpago.
- El pago completo cambia la orden a pagada y encola el acompañamiento postpago.
- Los trabajos ambiguos de WhatsApp no se reenvían automáticamente; requieren
  revisión del operador para evitar mensajes o documentos duplicados.

### Comunicación y acompañamiento

- Aviso después de validar correctamente el registro.
- Envío de evidencia y solicitud de pago después de reservar.
- Paquete postpago con documentos y texto de orientación.
- Recordatorio para las reservas del día siguiente con nombre de la persona que
  asistirá, fecha, hora y sede.
- Seguimiento post-cita mediante la información disponible en el portal.
- Atención operativa desde Telegram y revisión ampliada desde el dashboard.

El sistema acepta contacto por número telefónico o por usuario de WhatsApp. Si
existen ambos, se usa preferentemente el número.

## 5. Recorrido actual del cliente

1. El cliente llega principalmente por WhatsApp o TikTok.
2. El operador registra sus datos y condiciones.
3. El sistema valida las credenciales del portal.
4. Si la contraseña es incorrecta, el cliente queda pendiente y el operador puede
   corregirla desde Telegram.
5. Con acceso válido, la orden entra a la cola de búsqueda.
6. El sistema monitorea oportunidades y reserva automáticamente.
7. Se envían evidencia y datos de pago.
8. El operador registra un abono o confirma el pago completo.
9. Se envía el paquete postpago.
10. Antes de la cita puede enviarse un recordatorio.
11. Después de la cita se revisa el avance disponible en el portal.
12. Todavía falta convertir de manera estructurada la satisfacción final en una
    recomendación o referido medible.

## 6. Herramientas internas

### Telegram

Telegram es la superficie rápida del operador. Actualmente permite:

- consultar pendientes y seleccionar al cliente mediante botones identificados;
- ver usuarios buscando cupo;
- revisar y registrar cobros;
- registrar clientes;
- buscar órdenes;
- consultar próximas citas y estado operativo;
- corregir contraseñas rechazadas;
- cambiar prioridad y reglas;
- revalidar accesos;
- acceder a herramientas y diagnósticos secundarios.

Las mutaciones sensibles exigen chat privado, usuario autorizado, confirmación y
relectura del estado antes de aplicarse.

### Dashboard

El dashboard concentra la visión completa:

- resumen mensual y comparación de periodos;
- órdenes, credenciales, restricciones y prioridades;
- pagos y saldos;
- próximas citas, recordatorios y post-cita;
- seguimiento y conciliación de WhatsApp;
- finanzas y calidad de datos;
- controles del worker, CAPTCHA y oportunidades;
- evidencia y detalle técnico cuando hace falta.

### Automatización

- PostgreSQL es la fuente de verdad de clientes, órdenes, estados, reservas,
  pagos, comunicaciones y auditoría.
- El worker se encarga de buscar y reservar.
- Admin API aplica las operaciones administrativas.
- Telegram y dashboard consumen la misma información.
- WhatsApp Web es controlado por un único proceso para evitar conflictos.
- n8n queda como orquestador externo, no como motor principal de reservas.

## 7. Cómo nos está yendo en agosto de 2026

Fotografía de PostgreSQL al 23 de agosto de 2026, 12:54 p. m. de Lima:

| Indicador | Agosto 1-23 | Julio 1-23 | Variación |
|---|---:|---:|---:|
| Órdenes creadas | 76 | 75 | +1% |
| Reservas confirmadas | 74 | 68 | +9% |
| Pagos recibidos | 73 | 64 | +14% |
| Ingreso cobrado | S/3,535 | S/2,545 | +39% |
| Ticket promedio | S/48.42 | S/39.77 | +22% |

Lecturas principales:

- agosto ya superó los S/3,105 cobrados durante todo julio;
- 64 de 73 pagos de agosto fueron de S/50;
- la cohorte de agosto tiene 69 reservas entre 76 altas, equivalente a 90.8%;
- 68 de las 76 altas ya pagaron, equivalente a 89.5%;
- la mediana entre registro y reserva fue de 3.68 horas;
- 93% de quienes reservaron lo hicieron dentro de 24 horas y 97% dentro de 72;
- al corte había cinco usuarios buscando cupo;
- no había pagos pendientes, contactos faltantes ni órdenes activas antiguas.

Los ingresos son dinero efectivamente cobrado. No equivalen a utilidad neta.
Solamente había S/9.44 de costos reconocidos en agosto y la captura de CAPTCHA,
internet, electricidad, tiempo, impuestos y otros gastos todavía es incompleta.

## 8. Canales y adquisición

La cohorte de agosto figura así:

| Fuente registrada | Altas | Reservadas | Pagadas | Ingreso de la cohorte |
|---|---:|---:|---:|---:|
| WhatsApp | 67 | 61 | 60 | S/2,955 |
| TikTok | 9 | 8 | 8 | S/380 |

La atribución todavía tiene límites:

- solo 53 de las 76 órdenes conservaron la fuente en el momento exacto del alta;
- 21 fuentes provienen de una reconstrucción histórica;
- dos no tienen fuente congelada;
- no existe todavía una categoría estructurada de referido;
- compartir un contacto entre varios clientes o registrar un segundo trámite es
  una señal, pero no prueba quién recomendó a quién.

Por eso no podemos medir todavía cuántos clientes nuevos llegaron por recomendación
ni cuánto ingreso generaron los referidos.

## 9. Recordatorios y percepción de seguridad

Hasta el corte se habían procesado 22 recordatorios de cita y los 22 quedaron en
estado técnico `sent`, sin contactos faltantes ni días con error.

Esto demuestra funcionamiento técnico, pero no demuestra por sí solo que el
cliente leyó el mensaje, asistió gracias a él o se sintió más seguro. El control
vigente está nuevamente en modo `canary` para una sola orden, por lo que la
capacidad no cubre automáticamente a todos los clientes futuros.

Para medir el impacto comercial necesitamos registrar:

- recordatorio elegible, enviado y técnicamente confirmado;
- asistencia o inasistencia;
- respuesta del cliente;
- satisfacción después de la cita;
- recomendación compartida;
- referido que se registró, reservó y pagó.

## 10. Fortalezas actuales

- Conversión cercana al 90% durante agosto.
- Aceptación comprobada del precio de S/50.
- Reservas rápidas cuando el portal publica disponibilidad.
- Cero cobros pendientes al corte.
- Evidencia y trazabilidad superiores a una gestión manual informal.
- Automatización de registro, reserva, cobro, comunicaciones y seguimiento.
- Operación rápida desde Telegram sin perder la profundidad del dashboard.
- Guardas contra duplicados, reintentos ambiguos y envíos repetidos.
- Acompañamiento antes y después de reservar, que aumenta la confianza percibida.

## 11. Límites y riesgos conocidos

- Dependemos de la disponibilidad y estabilidad del portal de la PNP.
- No controlamos cuándo se publican cupos.
- WhatsApp Web puede cambiar su interfaz y producir estados `uncertain`.
- Existen trabajos históricos ambiguos que requieren conciliación manual y no
  deben reenviarse automáticamente.
- Los recordatorios todavía no están en modo general para todos los clientes.
- La medición de referidos y satisfacción no está implementada.
- La captura de costos no permite afirmar utilidad neta real.
- No existe todavía una política comercial formal documentada de cancelación,
  devolución, cambio de condiciones o nivel de servicio.
- No se ha validado que el flujo automatizado soporte duplicados y actualizaciones;
  no deben venderse hasta comprobarlo.

## 12. Qué conviene mantener incluido en S/50

Por su bajo costo marginal y alto valor percibido, conviene mantener dentro del
precio base:

- validación y corrección de acceso;
- monitoreo y reserva;
- evidencia;
- guía de pago;
- checklist oficial básico;
- recordatorio previo;
- seguimiento post-cita;
- canal de ayuda ante problemas;
- mecanismo sencillo para compartir el servicio con otra persona.

El paquete base debe sentirse completo. Los extras deberían cobrar principalmente
trabajo humano, atención preferente o manejo de varios vehículos, no funciones
automáticas baratas que ayudan a diferenciar el servicio.

## 13. Servicios adicionales recomendados, todavía no incluidos

Estas son propuestas comerciales, no capacidades ofrecidas actualmente:

| Propuesta | Precio inicial sugerido | Alcance |
|---|---:|---|
| Acompañamiento Plus | +S/15 | Revisión humana de documentos, voucher y respuesta prioritaria |
| Segundo vehículo | S/40 adicional | Nueva gestión para otro vehículo del mismo contacto |
| Paquete familiar | S/90 por dos | Dos trámites y seguimiento coordinado |
| Duplicado o actualización | S/25-S/35 de servicio | Solo después de validar el flujo; tasa estatal separada |
| Empresas o flotas | Desde S/40 por unidad | Alta múltiple y reporte consolidado |
| Acompañamiento presencial | S/60-S/100 | Requiere personal o aliado confiable y alcance por zona |

También puede evaluarse una alianza con talleres de polarizado que cumplan la
normativa. El negocio podría recibir una comisión por derivación sin asumir la
instalación ni garantizar el resultado del peritaje.

## 14. Programa de referidos recomendado

La opción inicial de menor costo es conservar el precio de S/50 y ofrecer:

> Si un referido completa su pago, el cliente que lo recomendó y el nuevo cliente
> reciben Acompañamiento Plus sin costo.

Reglas sugeridas:

- generar un código o vínculo por cliente;
- registrar el referente durante el alta;
- considerar válido el referido únicamente después del pago completo;
- aplicar una sola recompensa por orden;
- separar una recomendación de una reseña pública;
- nunca condicionar un beneficio a que la opinión sea positiva.

Antes de ofrecer dinero o descuentos mayores deben registrarse todos los costos y
calcular el margen real por trámite.

## 15. Próximas mejoras comerciales prioritarias

1. Capturar `referido` y `cliente recurrente` como fuentes estructuradas.
2. Guardar quién recomendó a quién y la conversión final del referido.
3. Ampliar los recordatorios mediante un canario mayor antes de pasar a `live`.
4. Añadir una encuesta breve después de la cita: **Todo bien / Necesito ayuda**.
5. Pedir la recomendación solamente después de una experiencia satisfactoria.
6. Conciliar los trabajos WhatsApp ambiguos sin reenviarlos automáticamente.
7. Completar el registro de costos para conocer utilidad y CAC reales.
8. Medir conversión, tiempo hasta reserva y margen de Estándar frente a Día elegido.
9. Definir por escrito cancelaciones, devoluciones, cambios y límites del servicio.
10. Validar técnicamente duplicados y actualizaciones antes de anunciarlos.

## 16. Indicadores que deberían guiar el negocio

- altas por fuente;
- porcentaje con acceso validado;
- conversión de alta a reserva;
- conversión de reserva a pago;
- tiempo mediano hasta reserva;
- ticket promedio;
- ingreso cobrado;
- costo completo por trámite;
- margen por paquete;
- recordatorios enviados y asistencia;
- satisfacción post-cita;
- referidos generados, pagados e ingreso por referidos;
- comunicaciones fallidas o ambiguas pendientes de revisión.

## 17. Resumen ejecutivo

El negocio ya no es solamente un bot que encuentra citas. Es un servicio de
acompañamiento operativo completo que registra, valida, monitorea, reserva,
documenta, cobra, comunica y da seguimiento.

Agosto demuestra que el mercado aceptó S/50 y que la operación puede mantener una
conversión cercana al 90%. La siguiente etapa no debería ser bajar el precio ni
añadir muchas funciones inconexas. El piloto de Día elegido por S/70 debe
medirse por separado. La siguiente etapa debe convertir la buena experiencia actual en
un ciclo medible:

`reserva rápida -> confianza -> acompañamiento -> satisfacción -> referido -> nuevo cliente`
