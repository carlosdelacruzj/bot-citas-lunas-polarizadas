# Propuesta de captación y registro digital de clientes

Fecha de análisis: `2026-07-28`.

Estado: análisis histórico parcialmente superado. No representa una tarea ni
modifica el orden vigente del roadmap.

Las decisiones posteriores que prevalecen son:

- el piloto web se ofrece primero solo a contactos directos de WhatsApp;
- TikTok conserva el registro manual;
- las restricciones abarcan fechas y se coordinan por WhatsApp, sin texto libre
  ni horarios en la web;
- Carlos crea las invitaciones desde el dashboard local, pero el token se
  genera en el servicio alojado;
- el formulario no vuelve a pedir el WhatsApp vinculado a la invitación;
- la validación puede quedar pendiente si la PC está apagada;
- el piloto no incluye una página persistente de estado;
- primero se implementa y valida la parte alojada en
  `lunas-polarizadas-clientes` y después se integra este proyecto.

La única tarea vigente está en [`roadmap/README.md`](roadmap/README.md).

## 1. Resumen ejecutivo

La propuesta inicial consistía en acelerar el alta manual pegando los datos de
un cliente en el dashboard. Después de revisar el proceso comercial real, esa
idea resultó insuficiente: los clientes no entregan toda la información en un
solo mensaje ni respetan siempre un formato.

La alternativa con mayor potencial es crear una experiencia pública de
registro que combine:

1. una landing page que explique el servicio y genere confianza;
2. un formulario móvil y guiado;
3. validación automática de la cuenta en el portal;
4. captura estructurada de disponibilidad;
5. creación segura de la orden en el bot;
6. traslado de la conversación a WhatsApp.

Al recibir credenciales, consultar el bot y mostrar resultados, deja de ser
solamente una landing page. Se convierte en un sistema pequeño de incorporación
de clientes. La recomendación es mantenerlo deliberadamente acotado y no
convertirlo todavía en un portal completo de clientes.

## 2. Proceso comercial actual

### Etapa 1: primer contacto por TikTok

Carlos explica:

- qué servicio ofrece;
- precio vigente de `S/50 por trámite`;
- pago únicamente después de confirmar la reserva;
- rango aproximado de fechas que está apareciendo;
- tiempo estimado de `2 a 7 días hábiles`;
- consulta sobre solicitudes y cantidad de trámites.

El mensaje cambia ligeramente según el cliente haya contactado primero o Carlos
haya encontrado al posible cliente.

### Etapa 2: aceptación y solicitud de credenciales

Cuando el cliente acepta, se solicita:

- tipo de documento;
- usuario o número de documento;
- contraseña exacta del portal.

Se recomienda copiar y pegar la contraseña para reducir errores.

### Etapa 3: validación y disponibilidad

Después de comprobar el acceso, se solicita una de estas opciones:

1. reservar cualquier fecha, priorizando la más próxima;
2. registrar restricciones concretas de fechas u horarios.

También se solicita el número de WhatsApp.

La mayoría de los clientes responde con expresiones breves como:

- `quiero el 1`;
- `opción 1`;
- `solo 1`;
- `cualquier fecha`.

La interpretación depende de la etapa de la conversación. Por ejemplo, `solo
1` después del primer mensaje puede indicar un solo trámite, mientras que
`quiero el 1` después del tercer mensaje significa disponibilidad para cualquier
fecha.

### Etapa 4: traslado a WhatsApp

Una vez validada la cuenta y conocida la disponibilidad, se envía por WhatsApp
la confirmación de inicio del monitoreo, las condiciones del servicio y,
posteriormente, las evidencias, el QR de pago y los documentos.

## 3. Problemas del proceso actual

1. Carlos debe buscar, adaptar, copiar y enviar varias plantillas.
2. Los datos llegan en mensajes separados y con formatos diferentes.
3. Es necesario copiar manualmente documento, contraseña, contacto y WhatsApp.
4. Una respuesta breve puede ser ambigua fuera de su contexto.
5. Las contraseñas pueden copiarse incorrectamente.
6. Las restricciones pueden quedar expresadas de forma imprecisa.
7. El alta de una orden ocurre después de varios intercambios manuales.
8. No existe medición estructurada del abandono entre una etapa y la siguiente.
9. Los posibles clientes dependen de que Carlos esté disponible para continuar.

## 4. Alternativas consideradas

### 4.1 Pegado rápido en el dashboard

Consiste en pegar un mensaje y extraer nombre, documento, contraseña, teléfono y
fuente.

Ventajas:

- implementación relativamente pequeña;
- reduce algunos clics y errores de transcripción;
- conserva el proceso comercial actual.

Limitaciones:

- Carlos todavía debe copiar cada respuesta;
- el cliente puede omitir información;
- no elimina la conversación manual;
- un extractor genérico no conoce siempre la etapa del cliente;
- el ahorro real sería limitado.

Conclusión: útil como herramienta auxiliar, pero no como mejora principal.

### 4.2 Formulario externo sin integración

Consiste en una landing que envía los datos a un correo, archivo o notificación.

Ventajas:

- el cliente completa los datos;
- mejora la presentación comercial;
- ordena la información.

Limitaciones:

- Carlos todavía debe validar y crear la orden manualmente;
- duplica información entre el formulario y el bot;
- no informa al cliente del resultado real.

Conclusión: reduce desorden, pero no automatiza el alta.

### 4.3 Sistema de registro conectado

Consiste en una landing, un formulario público seguro, una cola intermediaria y
un conector con el bot local.

Ventajas:

- el cliente registra sus propios datos;
- la cuenta se valida automáticamente;
- la disponibilidad queda estructurada;
- la orden puede crearse sin transcripción;
- permite medir cada etapa;
- puede iniciar el contacto por WhatsApp.

Limitaciones:

- requiere alojamiento, backend y medidas de seguridad;
- debe funcionar aunque la computadora local esté temporalmente apagada;
- aumenta la responsabilidad sobre datos personales y credenciales;
- necesita una estrategia clara para WhatsApp mientras no se use la API oficial
  de Meta.

Conclusión: es la alternativa recomendada, con un alcance inicial pequeño.

## 5. Experiencia propuesta para el cliente

### Paso 1: conversación inicial

El primer mensaje de TikTok se conserva. La comunicación humana permite adaptar
el saludo, resolver dudas y explicar el valor del servicio.

### Paso 2: enlace después de la aceptación

El enlace se envía únicamente cuando el cliente confirma que desea comenzar.
No se recomienda enviar un formulario de credenciales como primer contacto.

Texto de referencia:

> Perfecto. Para validar correctamente tu cuenta y evitar errores al copiar tus
> datos, completa este registro seguro. Toma aproximadamente dos minutos y no
> se realiza ningún cobro. Cuando terminemos la validación, te confirmaremos por
> WhatsApp.

### Paso 3: confianza antes de solicitar credenciales

La página debe mostrar antes del formulario:

- nombre e identidad comercial;
- explicación concreta del servicio;
- precio y condición de pago posterior;
- razón por la que se necesita acceso a la cuenta;
- manejo de documento y contraseña;
- WhatsApp de contacto;
- preguntas frecuentes;
- evidencias o testimonios anonimizados;
- política de privacidad y condiciones.

La primera pantalla no debe limitarse a pedir DNI y contraseña, porque podría
parecer una página de suplantación o phishing.

### Paso 4: datos de acceso

Campos mínimos:

- tipo de documento;
- documento o usuario;
- contraseña.

La página debe:

- funcionar correctamente desde celular;
- permitir pegar la contraseña;
- permitir mostrarla temporalmente;
- validar longitud y formato del documento;
- evitar guardar credenciales en el navegador, analítica o logs;
- explicar que se respetan mayúsculas, minúsculas y caracteres especiales.

No es necesario preguntar la cantidad definitiva de trámites si el portal puede
proporcionarla durante la validación.

### Paso 5: validación

El bot intenta acceder y obtiene:

- resultado de las credenciales;
- nombre del titular;
- trámites pendientes identificados.

Si el acceso falla, el cliente corrige los datos desde la misma página. Si el
acceso funciona, se muestra una confirmación con información parcialmente
oculta, por ejemplo:

```text
Cuenta validada correctamente.
Titular: Carlos D. C.
Trámites encontrados: 1.
```

La orden todavía puede permanecer pausada hasta completar disponibilidad y
WhatsApp.

### Paso 6: disponibilidad

La opción principal debe requerir un solo toque:

```text
Pueden reservarme cualquier fecha disponible, priorizando la más próxima.
```

Solo al elegir `Tengo restricciones` se muestran:

- días permitidos o excluidos;
- fecha mínima;
- fecha máxima;
- rangos de fechas excluidos;
- restricciones horarias compatibles con las reglas del bot.

Las expresiones ambiguas no deben convertirse automáticamente en reglas sin una
confirmación explícita.

### Paso 7: WhatsApp y consentimiento

Se solicita el número de WhatsApp y autorización para recibir mensajes sobre el
servicio.

Hay dos variantes:

#### Variante recomendada inicialmente: cliente inicia el chat

La página termina con `Continuar por WhatsApp`. El botón abre el chat de Carlos
con un mensaje preparado. El cliente pulsa enviar.

Beneficios:

- verifica de forma práctica que el número pertenece al cliente;
- reduce el riesgo de enviar información a un número incorrecto;
- la conversación es iniciada por el cliente;
- depende menos de la automatización de WhatsApp Web.

#### Variante automática

Después de validar el registro, el sistema crea un trabajo en la cola durable de
WhatsApp y envía el mensaje inicial mediante el flujo local ya existente.

Beneficios:

- experiencia más automática;
- el cliente recibe confirmación sin realizar otro paso.

Riesgos:

- un número incorrecto puede recibir información ajena;
- WhatsApp Web depende de una interfaz externa cambiante;
- un resultado ambiguo no debe reintentarse automáticamente;
- requiere consentimiento explícito y trazabilidad del envío.

Ambas variantes pueden probarse. La segunda no debe activarse sin una validación
previa con números controlados.

## 6. Arquitectura recomendada

```text
Cliente
  |
  v
Landing y formulario público con HTTPS
  |
  v
API pública limitada y cola intermediaria alojada
  |
  | conexión saliente segura
  v
Conector ejecutado en la PC de Carlos
  |
  +--> Bot local y preflight del portal
  |
  +--> PostgreSQL y creación de la orden
  |
  +--> Cola de WhatsApp
  |
  v
Resultado mínimo devuelto al servicio público
  |
  v
Estado visible para el cliente
```

### Frontera de seguridad

La API administrativa local no debe exponerse directamente a internet.

No se recomienda que el sitio público llame directamente a la PC de Carlos ni
publique los puertos actuales del worker, Admin API, PostgreSQL o CAPTCHA.

La comunicación recomendada es:

1. el servidor público recibe la solicitud;
2. la guarda como pendiente;
3. el conector local consulta solicitudes nuevas mediante HTTPS;
4. procesa una solicitud;
5. devuelve un resultado mínimo;
6. el servidor público actualiza el estado visible.

La conexión principal se inicia desde la PC hacia el servicio alojado, no desde
internet hacia la red local.

### Cuando la PC está apagada

El registro puede aceptarse y quedar pendiente:

```text
Recibimos correctamente tu solicitud.
La validación está pendiente y te notificaremos por WhatsApp cuando termine.
```

Al encenderse la PC y recuperarse los supervisores, el conector procesa las
solicitudes pendientes.

Para validación inmediata durante las 24 horas sería necesario mantener la PC y
la conexión activas o trasladar el validador a infraestructura alojada. No se
propone migrar inicialmente todo el motor de reservas.

## 7. Qué puede mostrar el portal

Estados adecuados:

- solicitud recibida;
- validando acceso;
- credenciales incorrectas;
- cuenta validada;
- disponibilidad pendiente;
- registro completado;
- monitoreo iniciado;
- cita reservada.

Datos que pueden mostrarse parcialmente:

- nombre del titular;
- documento;
- número de WhatsApp;
- cantidad de trámites;
- restricciones registradas.

Datos que no deben mostrarse:

- contraseña;
- datos de otros clientes;
- posición o detalles internos de la cola;
- logs;
- CAPTCHA;
- errores técnicos completos;
- credenciales o direcciones de servicios internos.

Cada solicitud debe usar un identificador aleatorio, firmado y difícil de
adivinar. No debe permitirse consultar información escribiendo únicamente el
DNI.

## 8. Seguridad y privacidad

Requisitos mínimos:

1. dominio propio y HTTPS;
2. cifrado de credenciales antes de almacenarlas;
3. credenciales excluidas de logs, eventos de analítica y mensajes;
4. contraseñas ocultas en interfaces administrativas;
5. acceso del cliente mediante token seguro y temporal;
6. límites de intentos y protección contra automatización abusiva;
7. validación del origen de las solicitudes;
8. auditoría de estados sin registrar el contenido sensible;
9. consentimiento previo, informado, expreso e inequívoco;
10. política de retención y eliminación al finalizar el servicio;
11. mecanismo para solicitar acceso, corrección o eliminación de datos;
12. revisión jurídica antes de abrir el sistema al público.

La página debe explicar:

- quién recibe los datos;
- para qué se utilizan;
- cuáles son obligatorios y cuáles opcionales;
- durante cuánto tiempo se conservarán;
- con quién pueden compartirse;
- cómo revocar el consentimiento o ejercer derechos.

## 9. Fricción y confianza

### Posibles mejoras

- apariencia más profesional;
- precio y condiciones visibles;
- menos errores de contraseña;
- disponibilidad estructurada;
- registro disponible sin esperar una respuesta inmediata de Carlos;
- confirmación clara de cada paso;
- continuidad hacia WhatsApp;
- evidencia de que existe un proceso formal.

### Posibles causas de abandono

- abrir un enlace adicional;
- temor a entregar una contraseña en una página desconocida;
- formulario demasiado largo;
- dominio gratuito o poco reconocible;
- diseño genérico;
- validación lenta sin explicación;
- solicitar información innecesaria;
- errores que obliguen a empezar nuevamente.

### Lectura de negocio

No se puede asegurar anticipadamente si la conversión subirá o bajará. Es
probable que exista algo de abandono al abrir el enlace, pero también se
reducirán abandonos posteriores causados por datos incompletos, credenciales
incorrectas y demasiados intercambios.

La contraseña será el principal punto de confianza, no necesariamente la
cantidad de pantallas.

## 10. Estrategia de prueba

No se recomienda reemplazar inmediatamente el proceso actual.

### Línea base

Antes del piloto, medir en el flujo actual:

- primeros contactos;
- respuestas;
- clientes que aceptan;
- credenciales recibidas;
- accesos validados;
- WhatsApp recibido;
- monitoreos iniciados;
- reservas;
- pagos;
- tiempo manual aproximado por cliente.

### Piloto híbrido

Ofrecer el enlace a un grupo pequeño de clientes que ya aceptaron el servicio,
manteniendo esta alternativa:

> Si tienes algún problema para completar el registro, escríbeme y te ayudo
> personalmente.

Medir:

- enlace enviado;
- enlace abierto;
- formulario iniciado;
- abandono por paso;
- credenciales válidas al primer intento;
- registro completado;
- conversación iniciada o mensaje entregado en WhatsApp;
- orden creada;
- reserva y pago posteriores;
- tiempo manual ahorrado.

### Criterio de decisión

Comparar el piloto con la línea base, prestando atención a:

- conversión desde aceptación hasta monitoreo;
- conversión hasta pago;
- errores de credenciales;
- minutos de trabajo manual;
- solicitudes de ayuda;
- incidentes de seguridad o privacidad.

Si el formulario ahorra tiempo pero reduce fuertemente la conversión, debe
mantenerse como alternativa y no como única vía.

## 11. Alcance recomendado para una primera versión

Incluir:

- landing pública;
- registro sin crear una cuenta adicional;
- tipo de documento, usuario y contraseña;
- validación automática;
- nombre y trámites detectados;
- opción de cualquier fecha o restricciones;
- WhatsApp y consentimiento;
- creación pausada y posterior activación de la orden;
- página de estado simple;
- auditoría sin datos sensibles;
- notificación operativa;
- transición controlada a WhatsApp.

No incluir todavía:

- cuentas y contraseñas propias del nuevo portal;
- chat interno;
- pagos en línea;
- panel completo para clientes;
- reprogramación;
- soporte tipo ticket;
- exposición de la cola;
- migración del motor de reservas a la nube;
- envío automático masivo.

## 12. Fases posibles

### Fase 0: medir el proceso actual

Registrar conversión y tiempo manual para tener una comparación real.

### Fase 1: prototipo de experiencia

Diseñar y probar la landing y el formulario sin conectarlos todavía a clientes
reales. Validar comprensión, confianza y duración desde un celular.

### Fase 2: registro conectado

Implementar alojamiento, API pública limitada, cola intermediaria, conector
local, preflight y creación segura de órdenes.

### Fase 3: transición a WhatsApp

Probar primero el botón iniciado por el cliente. Después evaluar el mensaje
automático mediante la cola existente y números controlados.

### Fase 4: piloto comercial

Usar el nuevo recorrido con una muestra pequeña, medir abandono, tiempo,
reservas y pagos, y decidir si se convierte en el flujo principal.

### Fase 5: mejoras posteriores

Solo si el piloto funciona:

- recuperación de solicitudes incompletas;
- recordatorios;
- atribución detallada por campaña o video;
- testimonios;
- seguimiento de conversión;
- estado ampliado para el cliente.

## 13. Decisiones pendientes

Antes de implementar se debe decidir:

1. nombre comercial y dominio;
2. proveedor de alojamiento;
3. si la validación debe ser inmediata o puede quedar pendiente;
4. tiempo de conservación de credenciales;
5. cuándo se elimina o inutiliza el acceso del cliente;
6. si WhatsApp lo inicia el cliente o el sistema;
7. información exacta que se mostrará después de validar;
8. reglas y horarios del envío automático;
9. estrategia de respaldo y recuperación del servicio alojado;
10. texto legal y responsable del tratamiento de datos;
11. métricas y tamaño del piloto;
12. presupuesto máximo para construcción y operación.

## 14. Recomendación actual

La propuesta merece evaluarse porque ataca trabajo manual real y puede hacer el
servicio más consistente. La solución recomendada no es una landing aislada ni
un portal grande: es un sistema pequeño de incorporación conectado de forma
segura al bot local.

El orden recomendado es:

1. medir el embudo actual;
2. diseñar la experiencia móvil;
3. probar confianza y comprensión con un prototipo;
4. construir la integración mediante una cola intermediaria;
5. mantener una vía manual durante el piloto;
6. automatizar WhatsApp solo después de validar el registro y el número;
7. ampliar el alcance únicamente si mejora conversión, tiempo y calidad.
