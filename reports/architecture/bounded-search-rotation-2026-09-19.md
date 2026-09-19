# Busqueda acotada y observador rotativo

Artefacto generado. Fecha de corte: 19 de septiembre de 2026, 18:42 Lima.
Describe la validacion y activacion de este cambio; no es un estado vivo.

## Resultado

- `9a1c596`: presupuesto de reserva por revision: dos fechas compatibles, dos
  comprobaciones adicionales de horario en total y un unico envio.
- `36de220`: observador rotativo, propietario de navegador por cuenta y descansos
  persistidos; migracion PostgreSQL de v75 a v76.
- La seleccion de horarios agotados conocidos no repite su solicitud, incluso
  cuando el cero aparece al cargar una fecha nueva.
- Una revision nueva vuelve a las primeras fechas compatibles del listado fresco;
  no avanza por todo el calendario mediante un cursor.
- La ruta automatica utiliza el DOM vivo y desactiva fetch alternativo, reload,
  segundo submit de CAPTCHA rechazado y reobservacion posterior al envio.

## Rotacion y clientes

Un observador logico usa una cuenta validada distinta cuando corresponde por
antiguedad y elegibilidad. Cierra y libera la sesion antes del siguiente trabajo.
Se excluyen accesos no validados, cuentas ocupadas, bloqueadas o con incertidumbre.
Cada turno verifica como maximo una fecha y un horario, sin reservar ni muestrear
CAPTCHA repetidamente. La sede exigida debe poder observarse en esa cuenta.

Los listados de fechas disparan comprobaciones propias de clientes compatibles;
no equivalen a cupos confirmados. Esto permite atender sabados aunque aun existan
cupos del viernes. Cada cliente usa su cuenta y restricciones. La ruta nueva usa
la cola secuencial acotada; no inicia la antigua rafaga desde una orden detectora.
Las alertas de disponibilidad requieren el resultado materializado del observador.

La configuracion operativa anterior de intervalo global era 5-9 segundos. La
rotacion impone un piso de 30 segundos y 180 por cuenta. Defensas del portal
frenan los siguientes turnos globalmente; demasiadas solicitudes: 900 segundos;
indisponibilidad temporal: 180. Se conservan los descansos despues de reiniciar.
Tambien se propaga al observador la defensa detectada en la cola de reservas.

## Validacion aislada

- Suite existente: 181 pruebas y 24 subcasos aprobados; cobertura critica aprobada.
- Tras los ajustes finales: 29 pruebas y ocho subcasos de worker, evidencia y
  exclusividad; despues, diez pruebas de evidencia aprobadas.
- Compilacion, Ruff, documentacion y `git diff --check` aprobados.
- Arquitectura: 330 modulos, cero ciclos y una excepcion preexistente.
- Ocho escenarios de comprobacion aislada, sin agregar tests a la suite:

| Caso | Resultado observado |
|---|---|
| Viernes, sabado y lunes; cliente solo sabados | Selecciona sabado; una fecha y un horario |
| 59 fechas sin horarios | Se detiene tras dos fechas |
| Tres horarios en la primera fecha | Maximo dos comprobaciones totales; no llega al tercero |
| Primera fecha sin horarios, segunda valida | Selecciona la segunda; no consulta la tercera |
| Cero ya visible | Descarta ese horario localmente; comprueba el siguiente |
| Todas las fechas incompatibles | `partial / blocked_by_order_rule`, cero consultas de fechas |
| Rotacion y migracion en esquema sintetico | Excluye cuenta ocupada; conserva descansos y bloqueo; v75 -> v76 |
| Ciclo del observador con respuesta de defensa simulada | Una sesion, lease liberado y espera global de 900 segundos |

Los escenarios usan datos sinteticos y motor simulado, nunca el portal ni envios
reales. El dashboard no cambio y 6.4 no se inicio.

## Activacion y comprobacion operativa

Antes de actualizar: worker detenido por horario y pausado; cero submissions,
leases, sesiones manuales, preflights, rafagas, ejecuciones de rafaga, trabajos
WhatsApp, revisiones post-cita y comandos activos. Una reserva `unknown` historica
sin ejecucion activa permanecio bloqueada.

Se actualizo PostgreSQL a v76 y se reinicio exclusivamente Admin API mediante su
supervisor existente. La API responde y existe al menos una cuenta elegible.
No se reanudo el worker ni se altero `.env`. La version nueva se cargara en su
proximo arranque y seguira respetando la pausa persistida.

Las huellas SHA-256 completas antes/despues coinciden para las 608 filas de
intentos, 372 reservas y 1044 trabajos WhatsApp. No se crearon reservas ni mensajes
de prueba, ni se reconciliaron resultados ambiguos.

## Pendiente natural

La operacion real del nuevo observador no se ejecuto durante esta validacion.
Tras reanudar normalmente, revisar cambio de cuenta, tiempos, `review_budget`,
restricciones y evidencia del primer caso natural. No declarar mayor estabilidad
ni cierre de aceptacion hasta contar con esa evidencia.

Para detener el cambio, usar la pausa del worker y conservar v76. No arrancar un
binario que exija v75 sobre esta base ni borrar los descansos. 6.4 sigue pendiente
hasta la indicacion expresa del usuario; 2.6 y 5.5.5 mantienen su aceptacion natural.
