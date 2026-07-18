# Plan de control remoto por Telegram

Estado general: planificado, sin implementacion funcional iniciada.

Ultima actualizacion: `2026-07-18`.

Este es el documento principal para implementar, probar y registrar el control
remoto del sistema. Debe actualizarse al terminar cada fase y despues de cada
prueba operativa relevante.

## Meta

Poder administrar el sistema desde el celular cuando el operador no se
encuentre frente a la computadora, sin exponer el dashboard ni PostgreSQL a
Internet y sin crear una segunda logica de negocio paralela.

El operador debe poder:

- consultar si el sistema esta activo, detenido, pausado o esperando una
  ventana de trabajo;
- solicitar pausa, reanudacion y reinicio del worker;
- consultar la cola y el estado de los clientes;
- agregar clientes mediante un flujo guiado y validado;
- consultar y actualizar prioridad y restricciones de reserva;
- recibir confirmacion del resultado de cada accion;
- consultar errores operativos recientes sin acceder a la computadora.

## Fin esperado

Al cerrar el proyecto, el mismo bot de Telegram usado para alertas tambien
servira como interfaz de administracion remota. La recepcion de comandos vivira
en un proceso independiente del worker, pero reutilizara la Admin API y sus
validaciones.

```text
Celular del operador
  -> Telegram
  -> proceso telegram_control
  -> Admin API local
  -> PostgreSQL / worker_commands
  -> worker
```

n8n podra vigilar disponibilidad y escalar incidentes, pero no sera necesario
para ejecutar una reserva, modificar una orden o controlar el worker.

## Principios y limites

- Reutilizar la Admin API; Telegram no ejecutara PowerShell ni SQL arbitrario.
- Mantener la Admin API en loopback durante la primera version.
- Autorizar exclusivamente una lista explicita de `chat_id`.
- Exigir confirmacion para acciones que cambien estado.
- Registrar quien solicito cada accion, cuando, con que parametros y cual fue
  el resultado.
- No enviar contrasenas, tokens ni credenciales completas por Telegram.
- No modificar `.env` como parte de pruebas temporales.
- No cambiar el flujo de reserva para implementar el control remoto.
- No agregar tests automatizados salvo que el usuario lo solicite de forma
  explicita; las fases de este documento usan validaciones existentes y pruebas
  manuales controladas.
- Si la computadora esta apagada, suspendida o sin Internet, el bot local no
  podra responder. Resolver ese escenario exige infraestructura externa o una
  maquina siempre encendida.

## Base disponible

El proyecto ya cuenta con:

- Admin API separada en `127.0.0.1:8766`;
- autenticacion para las operaciones administrativas;
- endpoints para crear ordenes, editar prioridad y editar restricciones;
- comandos persistidos `pause`, `resume` y `restart` en `worker_commands`;
- estado del worker y endpoint de salud;
- bootstrap de Windows para iniciar y supervisar el worker;
- bootstrap separado para Admin API y dashboard;
- Telegram como canal de alertas y screenshots.

La implementacion debe ampliar estas capacidades, no reemplazarlas.

## Significado de reinicio

Se deben distinguir dos casos:

1. **Worker vivo:** `/reiniciar` solicita el reinicio mediante la Admin API y
   `worker_commands`. El worker consume y aplica el comando.
2. **Proceso del worker caido:** no existe un worker que pueda consumir el
   comando. El bootstrap/supervisor de Windows debe volver a levantarlo. El bot
   de control solo informa el diagnostico y verifica la recuperacion.

Un reinicio no se considerara exitoso solo porque la API acepte la solicitud.
Debe verificarse el cambio de estado, la aplicacion del comando y la nueva
actividad del proceso.

## Alcance de la primera version

Comandos previstos:

| Comando | Funcion | Cambia estado | Confirmacion |
|---|---|---:|---:|
| `/ayuda` | Mostrar comandos permitidos | No | No |
| `/estado` | Salud, fase, ultima y proxima revision | No | No |
| `/clientes` | Resumen de la cola | No | No |
| `/cliente ORDEN` | Detalle administrativo permitido | No | No |
| `/pausar` | Pausar el worker | Si | Si |
| `/reanudar` | Reanudar el worker | Si | Si |
| `/reiniciar` | Reiniciar el worker y verificar resultado | Si | Si |
| `/prioridad ORDEN VALOR` | Actualizar prioridad | Si | Si |
| `/reglas ORDEN` | Consultar restricciones | No | No |
| `/reglas_editar ORDEN` | Flujo guiado para restricciones | Si | Si |
| `/cliente_nuevo` | Flujo guiado para crear una orden | Si | Si |
| `/cancelar` | Cancelar el flujo conversacional actual | No | No |
| `/ultimos_errores` | Resumen saneado de incidentes recientes | No | No |

Los nombres finales pueden ajustarse durante la prueba de uso, pero cada accion
debe conservar una correspondencia clara con la Admin API.

## Fases de implementacion

### Fase 0 - Congelar contratos y linea base

Estado: pendiente.

1. Inventariar los endpoints exactos que usara cada comando.
2. Confirmar los campos admitidos al crear una orden y editar restricciones.
3. Confirmar como los bootstraps detectan y recuperan procesos caidos.
4. Registrar el estado inicial de worker, Admin API, Telegram y PostgreSQL.
5. Definir respuestas estandar de exito, rechazo, espera y error.

Criterio de cierre:

- existe un mapa comando -> endpoint -> respuesta -> verificacion;
- ninguna operacion requiere SQL directo ni ejecucion arbitraria de shell.

### Fase 1 - Crear el receptor independiente de Telegram

Estado: pendiente.

1. Crear un modulo separado para recibir actualizaciones de Telegram.
2. Usar el mismo bot de alertas, manteniendo separado el codigo de envio y el
   codigo de recepcion.
3. Empezar con long polling para no publicar un webhook en Internet.
4. Procesar correctamente el `update_id` para evitar comandos duplicados.
5. Implementar lista permitida de `chat_id` y rechazo silencioso o saneado para
   usuarios no autorizados.
6. Incorporar `/ayuda`, `/estado` y `/cancelar`.
7. Integrar el proceso al arranque supervisado de Windows sin afectar el
   bootstrap del worker.

Criterio de cierre:

- el receptor sigue respondiendo aunque el worker se cierre;
- un chat no autorizado no obtiene datos ni puede cambiar estado;
- reiniciar el receptor no vuelve a ejecutar actualizaciones confirmadas.

### Fase 2 - Control seguro del worker

Estado: pendiente.

1. Implementar `/pausar`, `/reanudar` y `/reiniciar` mediante la Admin API.
2. Agregar botones de confirmar y cancelar.
3. Usar un identificador de operacion para impedir doble ejecucion.
4. Consultar `worker_commands` hasta obtener `applied` o `failed`, con un tiempo
   maximo definido.
5. Distinguir `outside_hot_window` de un worker detenido.
6. Informar cuando la recuperacion depende del supervisor porque el proceso
   esta completamente caido.

Criterio de cierre:

- Telegram confirma el resultado real, no solamente un HTTP aceptado;
- las solicitudes repetidas no generan reinicios duplicados;
- pausa, reanudacion y reinicio quedan auditados.

### Fase 3 - Consultas operativas

Estado: pendiente.

1. Implementar `/clientes` con una respuesta corta y paginada.
2. Separar ordenes activas, pausadas, reservadas pendientes de pago y cerradas.
3. Implementar `/cliente ORDEN` sin exponer credenciales.
4. Implementar `/reglas ORDEN`.
5. Implementar `/ultimos_errores` con mensajes saneados y limites de longitud.

Criterio de cierre:

- la informacion coincide con Admin API/PostgreSQL;
- ningun mensaje contiene tokens, contrasenas o datos completos innecesarios.

### Fase 4 - Actualizacion de reglas y prioridad

Estado: pendiente.

1. Implementar `/prioridad` con validacion y confirmacion.
2. Implementar el flujo conversacional de `/reglas_editar`.
3. Mostrar valores actuales antes de solicitar cambios.
4. Permitir conservar campos que el operador no quiera modificar.
5. Presentar un resumen final y pedir confirmacion.
6. Volver a consultar la orden despues de guardar para verificar persistencia.

Criterio de cierre:

- las reglas aplicadas coinciden con el detalle de la orden;
- cancelar o dejar vencer la conversacion no realiza cambios parciales;
- el worker observa las reglas nuevas sin requerir una modificacion manual de
  la base de datos.

### Fase 5 - Alta remota de clientes

Estado: pendiente.

1. Implementar `/cliente_nuevo` como conversacion con estado y vencimiento.
2. Solicitar solamente los campos definidos por el contrato vigente.
3. No inventar datos opcionales que el usuario no proporcione.
4. Validar cada campo mediante la Admin API.
5. Mostrar un resumen enmascarado antes de crear la orden.
6. Pedir confirmacion explicita.
7. Mostrar el `order_id`, estado inicial y resultado del preflight.
8. Definir un mecanismo seguro para los campos sensibles antes de habilitarlos
   en produccion; no enviarlos en texto abierto por Telegram.

Criterio de cierre:

- una orden valida queda creada una sola vez;
- una orden invalida muestra errores de campo comprensibles;
- reintentos y respuestas duplicadas no crean clientes duplicados.

### Fase 6 - Auditoria, recuperacion y endurecimiento

Estado: pendiente.

1. Persistir auditoria de acciones remotas.
2. Definir vencimiento para confirmaciones y conversaciones abandonadas.
3. Aplicar limites de frecuencia por chat y por comando.
4. Sanear logs y respuestas de error.
5. Agregar aviso cuando el receptor de Telegram se reinicie.
6. Verificar la recuperacion independiente de worker, Admin API y receptor.
7. Documentar rotacion de token sin guardar secretos en el repositorio.

Criterio de cierre:

- cada cambio remoto puede reconstruirse desde la auditoria;
- la caida de un componente no provoca acciones duplicadas;
- no existe una ruta de ejecucion arbitraria desde Telegram.

### Fase 7 - Monitoreo externo con n8n

Estado: opcional y pendiente.

1. Ejecutar n8n fuera de la computadora operativa si se pretende detectar la
   caida completa de esa computadora.
2. Consultar salud con una frecuencia prudente.
3. Alertar solo por incidentes accionables y evitar mensajes repetidos.
4. Escalar cuando la maquina, Admin API o receptor permanezcan inaccesibles.
5. Mantener altas, reglas y control del worker en la Admin API.

Criterio de cierre:

- n8n detecta una indisponibilidad que el sistema local no puede reportar;
- una caida de n8n no impide la operacion normal del bot.

### Fase 8 - Acceso privado al dashboard

Estado: opcional y pendiente.

Evaluar una red privada para abrir el dashboard desde el celular o una laptop
sin publicar el puerto `8766` en Internet. Esta fase se ejecutara solamente
despues de cerrar autenticacion, autorizacion y pruebas del control por
Telegram.

## Matriz minima de pruebas operativas

| Escenario | Resultado esperado | Estado |
|---|---|---|
| Worker activo | `/estado` informa fase y siguiente accion reales | Pendiente |
| Fuera de ventana | Se informa activo pero esperando, no apagado | Pendiente |
| Worker pausado | Estado y motivo coherentes | Pendiente |
| Reinicio normal | Comando aplicado y nueva actividad verificada | Pendiente |
| Worker completamente caido | Supervisor lo recupera y Telegram lo verifica | Pendiente |
| Admin API caida | Error claro, sin ejecutar una ruta alternativa insegura | Pendiente |
| PostgreSQL no disponible | No se confirma ninguna escritura | Pendiente |
| Telegram sin Internet | Al recuperar conexion no duplica comandos | Pendiente |
| `update_id` repetido | La accion se procesa una sola vez | Pendiente |
| Chat no autorizado | No obtiene datos ni ejecuta acciones | Pendiente |
| Confirmacion vencida | No se realiza el cambio | Pendiente |
| Conversacion cancelada | No queda informacion parcial aplicada | Pendiente |
| Regla invalida | Se muestran errores y se conserva la regla anterior | Pendiente |
| Alta repetida | No se crean ordenes duplicadas | Pendiente |
| Mensaje de error | No revela tokens, credenciales ni datos sensibles | Pendiente |

## Validacion al cerrar cada fase

Como minimo:

```powershell
python -m compileall src
python -m ruff check src
git diff --check
```

Ademas se debe ejecutar la prueba manual propia de la fase contra los procesos
locales y registrar el resultado en este documento. Las validaciones no deben
alterar ordenes reales salvo que la prueba lo indique y el usuario lo autorice.

## Registro de avance

| Fecha | Fase | Cambio o prueba | Resultado | Evidencia | Proximo paso |
|---|---|---|---|---|---|
| 2026-07-18 | Plan | Creacion del documento principal | Completado | `docs/operations/remote-control-plan.md` | Ejecutar Fase 0 |

## Decisiones pendientes

- Definir el mecanismo seguro para ingresar o actualizar credenciales de una
  orden desde fuera de la computadora.
- Definir cuantos `chat_id` estaran autorizados inicialmente.
- Decidir si n8n se desplegara fuera de la computadora operativa.
- Decidir si se necesita acceso privado al dashboard despues de validar
  Telegram.

Estas decisiones no bloquean la Fase 0 ni los comandos de solo lectura de la
Fase 1.

## Regla de actualizacion del documento

Al terminar una fase:

1. cambiar su estado;
2. marcar las pruebas ejecutadas;
3. agregar una fila al registro de avance;
4. enlazar logs, capturas o reportes que sirvan como evidencia;
5. anotar problemas encontrados y decisiones tomadas;
6. dejar escrito el siguiente paso exacto.

No se marcara una fase como completada solo porque el codigo compile. Debe
cumplir su criterio de cierre y superar sus pruebas operativas.
