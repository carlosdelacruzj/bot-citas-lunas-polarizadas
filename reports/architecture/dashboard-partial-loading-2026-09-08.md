# Cierre 6.3: cargas parciales y cancelacion

Fecha de corte: 2026-09-08. Informe de validacion local con API simulada; no es
estado vivo del worker ni aceptacion natural de WhatsApp.
Base comparada: `1d30293bf781ba006c0aa74dab4d14bda56060a3` (6.2).

## Resultado

Los ocho destinos publican datos por bloque y muestran error y ultima lectura
correcta. Una tarjeta auxiliar fallida no invalida toda la vista. Los scopes
cancelan lecturas al sustituir consultas, cerrar detalles o abandonar la vista;
las generaciones descartan respuestas, errores y finally obsoletos.
El detalle A/B/A queda asociado a la ultima seleccion, incluido el inicio del pago.

El smoke existente incluye calidad financiera con HTTP 503, ingresos visibles,
cancelacion del detalle antiguo y salida de Resumen con respuesta retenida.
La escritura inmediata tras cerrar detalle expuso una carrera de inicializacion
del buscador; se enlazo input directamente al signal y se preserva el foco nuevo.
El smoke ampliado paso tres repeticiones para comprobar esa intermitencia.
No se agregaron casos nuevos ni se ejecutaron pagos, reservas o envios reales.

## Validacion

- Python: compileall y Ruff correctos; 181 tests y 24 subtests aprobados.
- Arquitectura: 318 modulos, una excepcion autorizada, cero ciclos.
- Dashboard: typecheck, build, 14 pruebas unitarias y smoke de ocho pantallas.
- Bundle inicial: 579.00 kB frente a 572.83 kB; transferencia 143.16 kB frente a
  141.12 kB. Persisten avisos de presupuesto inicial (535 kB) y CSS del shell
  (30.04 kB frente a 30 kB). No se elevaron los limites.
- Documentacion y diff del alcance comprobados antes del commit.

## Limites

El cierre es de 6.3. La encapsulacion de estilos, focus trap, inert, accesibilidad
y reduccion de bundle siguen en 6.4. La aceptacion natural de 5.5.5 y 2.6 sigue
pendiente. Los artefactos de evidencia actualizados por el worker no forman parte
del cambio. Contratos y matriz: [cargas parciales](../../docs/architecture/dashboard-loading.md).
