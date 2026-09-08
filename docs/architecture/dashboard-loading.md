# Cargas parciales del dashboard

Cada facade conserva sus datos y un `LoadSection` por bloque. Este objeto posee
solo carga, error, ultima lectura correcta y generacion; no duplica DTO ni estado
de negocio. `app-load-status` presenta esa informacion junto al bloque.

## Datos esenciales y auxiliares

| Vista | Esenciales | Auxiliares |
| --- | --- | --- |
| Ordenes | Lista de ordenes | Sesiones y catalogo comunes |
| Pendientes | Bandeja canonica | Controles y contadores operativos |
| Resumen | Resumen mensual | Ordenes, ejecuciones, comandos, recordatorios y controles |
| Finanzas | Resumen y movimientos | Categorias, calidad, cierre y resumen mensual |
| Mensajes | Plantillas | Servicios comunes |
| Seguimiento | Citas | Recordatorios del editor |
| Actividad | Ejecuciones | Comandos |
| CAPTCHA | Cola, historial o calidad segun modo | Resumen, casos y controles |

Salud, worker, sesiones y catalogo se muestran en Estado de servicios. Una falla
auxiliar abre su estado pero no convierte toda la vista en error. Un error
esencial conserva los bloques que si respondieron y muestra el error principal.
Una respuesta vacia correcta tambien cuenta como datos cargados.

## Publicacion y frescura

Cada solicitud publica al terminar, sin esperar a sus hermanas. `loadSections`
agrega resultados esenciales y espera auxiliares con `allSettled`; estos ya
registraron su error local. Un fallo conserva datos y fecha de su ultimo exito.
Cambiar el mes financiero limpia datos y fechas del mes anterior.

`RequestScope` cancela GET mediante RxJS. Sus hijos permiten reemplazar consultas
locales sin cancelar cargas comunes, pero reciben la cancelacion del padre.
Las generaciones impiden que un exito, error o finally antiguo altere el estado
de una solicitud nueva. Cancelar no es un error visible ni un reintento.

El detalle de orden verifica scope, seleccion e identificador de respuesta.
Cerrar, sustituir la seleccion, salir de vista u ocultar la pagina cancela su GET;
finally libera el scope tambien tras exito o error. Abrir un pago solo continua
si sigue vigente el detalle cargado y el formulario no fue editado.
Ejecuciones, consultas de bandeja, seguimiento y CAPTCHA tienen limpieza propia.

Las mutaciones mantienen sus contratos y no se reintentan automaticamente.
La restauracion diferida de foco respeta un foco nuevo elegido por el usuario;
el buscador enlaza su evento input directamente al signal para conservar escritura
inmediata al recrear la ruta. Focus trap, inert y revision visual siguen en 6.4.

## Verificacion

Los casos existentes de contratos y smoke usan fixtures sinteticos. Cubren
cancelacion HTTP, generaciones, conservacion de datos y frescura, fallos
auxiliares, seleccion A/B/A y salida durante una respuesta pendiente. El smoke
recorre ocho pantallas y no produce mutaciones reales.
