# Busqueda acotada y reserva

Estado: vigente.

## Presupuesto por revision automatica

Se ordenan y filtran localmente todas las fechas listadas segun las restricciones.
Se consultan como maximo las dos primeras fechas compatibles y se hacen como
maximo dos comprobaciones adicionales de horario en total, nunca dos por fecha.
Cupos agotados ya conocidos se descartan sin otra solicitud. Se toma el primer
horario valido de la fecha compatible mas cercana que pueda verificarse.
La seleccion usa el DOM vivo; en este recorrido no se ejecuta el fetch alternativo,
reload ni cambio repetido de sede. El presupuesto no se reinicia por fallback.
Al agotarlo se cierra la revision; la siguiente empieza otra vez desde las fechas
mas proximas de su listado nuevo, sin avanzar un cursor por todo el calendario.

Como maximo se envia una reserva por revision. Un rechazo de CAPTCHA o cupo
perdido no habilita otro envio ni reobservacion dentro de esa revision. Un resultado
ambiguo conserva `unknown`; los rechazos explicitos conservan sus cooldowns.
`review_budget` registra fechas, horarios, envios y solicitudes observadas durante
la revision; este limite no significa dos solicitudes HTTP para todo el login.
No se consultan fechas incompatibles solo para producir evidencia.

