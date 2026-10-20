# Contrato de Actividad y capturas

Estado: vigente. Verificacion de codigo: `2026-10-06`.

## Capturas de runs

`GET /api/v1/runs/{run_id}/screenshots/{index}` sirve la imagen original local
solo con autenticacion. El indice base cero corresponde al orden de
`screenshot_paths` del detalle, con fallback a `screenshot_path`. La ruta se
resuelve desde PostgreSQL, nunca desde un path proporcionado por el cliente.
Solo admite imagenes bajo el directorio configurado de screenshots; una captura
eliminada responde `404`. No usa cache. Disponibilidad y reserva confirmada
siguen siendo hechos separados. Los listados de runs incluyen `availability`
con sede, fecha, hora y cupos registrados, sin transportar detalles completos.

Actividad prioriza runs recientes y disponibilidad. Los comandos del worker
quedan plegados. El visor conserva filtro y scroll, confina/restaura foco,
permite navegar, ampliar y descargar, y cancela lecturas al cerrar o cambiar.

Al abrir una corrida, Actividad agrupa todas las fechas guardadas en
`date_options` o `selection_observation.visible_dates`, y las de sus
`observed_appointments` y `session_captures`. Presenta las cuatro primeras y
permite desplegar el listado completo. Muestra todos los horarios leidos para
cada fecha, incluidos `hour_options` de la fecha seleccionada, como "Listado"
cuando no hay cupos positivos comprobados. Las capturas de esta sesion y el
resultado principal aportan cupos verificados, sin atribuirlos a otros horarios.
Las fechas sin lista de horas conservan "Horarios no consultados". No usa el
acumulado diario `captured`. La pantalla no consulta el portal ni genera avisos;
el observador guarda `session_schedule` con los horarios leidos de las primeras
cuatro fechas cuando no hay clientes listos, bajo el presupuesto del contrato
[lectura de horarios](#lectura-de-horarios-para-actividad).
Disponibilidad ocupa el centro del detalle; resultado y datos tecnicos quedan
plegados. Los historicos solo muestran lo que efectivamente conservaron.

## Lectura de horarios para Actividad

Con cero ordenes `ready`, el observador lee adicionalmente los horarios listados
de hasta cuatro fechas mas proximas en un maximo de 25 segundos, con espera de
postback de hasta 8 segundos por fecha. No selecciona horarios, resuelve CAPTCHA,
reserva, captura cupos ni llama al alert sink durante esta lectura. Conserva
`session_schedule` y `schedule_status` por corrida, independientes del avance
diario de fotos. Los listados no acreditan cupos positivos. Un timeout conserva
los horarios ya leidos y una captura de diagnostico, sin reintentar el postback.
Clientes listos, cancelacion, pausa, perdida de lease y defensas detienen la
lectura; los presupuestos de deteccion y reserva permanecen vigentes.
