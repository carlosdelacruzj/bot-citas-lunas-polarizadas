# Busqueda acotada y reserva

Estado: vigente.

## Presupuesto por actualizacion de disponibilidad

Se ordenan y filtran localmente todas las fechas listadas segun las restricciones.
Se consultan como maximo las dos primeras fechas compatibles. El cliente
recorre todos los horarios permitidos de la fecha mas cercana hasta verificar
un cupo o alcanzar la ventana de tiempo; solo pasa a la segunda si la primera
no ofrece ningun horario valido. El observador comprueba hasta dos horarios
en total por actualizacion y nunca reserva.
Cupos agotados ya conocidos se descartan sin otra solicitud. Se toma el primer
horario valido de la fecha compatible mas cercana que pueda verificarse.
La seleccion usa el DOM vivo; en este recorrido no se ejecuta el fetch alternativo,
reload ni cambio repetido de sede una vez iniciada la seleccion de fechas.
Una respuesta confirmada sin cupos permite otra actualizacion real de sede en
la misma sesion, hasta 15 revisiones o 120 segundos segun configuracion.
`MONITOR_WINDOW_SECONDS=0` conserva una sola revision. Cada actualizacion nueva
renueva solo el presupuesto de seleccion (observador: dos fechas/dos horarios;
cliente: dos fechas y todos sus horarios permitidos hasta encontrar cupo). La recarga interna no lo renueva.
El limite de un envio pertenece a toda la sesion y nunca se reinicia.
Al cambiar fecha, la espera de horarios exige fin de actualizacion ASP.NET sin
error, fecha seleccionada exacta, ausencia de carga y dos lecturas estables
separadas por 250 ms. Sin ASP.NET, exige reemplazo del selector marcado antes
de seleccionar. Una lista vacia o identica a la anterior puede terminar la espera
si su actualizacion esta confirmada; sin confirmacion se conserva el timeout y
se detiene con error, nunca se interpreta la espera agotada como ausencia de cupos.
Al agotarlo sin cupo se espera la siguiente actualizacion de sede, que empieza
desde las fechas mas proximas de su listado nuevo. Un intento de reserva, una
respuesta incierta, pausa o error detiene esta vigilancia.

Como maximo se envia una reserva por revision. Un rechazo de CAPTCHA o cupo
perdido no habilita otro envio ni reobservacion dentro de esa revision. Un resultado
ambiguo conserva `unknown`; los rechazos explicitos conservan sus cooldowns.
`review_budget` registra fechas, horarios, envios y solicitudes observadas durante
la revision; este limite no significa dos solicitudes HTTP para todo el login.
No se consultan fechas incompatibles solo para producir evidencia.

