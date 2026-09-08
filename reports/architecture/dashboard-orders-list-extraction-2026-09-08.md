# Extraccion del listado de ordenes

Fecha de corte: `2026-09-08`. Evidencia local del primer bloque de `6.1`;
no representa estado operativo vivo ni cierre del dominio completo.

## Alcance y criterio

Separar el listado sin alterar busqueda, filtros, orden de cola, fechas nulas,
paginacion ni preferencias. El fallo a evitar es perder o duplicar el estado
al navegar entre Ordenes y Resumen, o permitir a la vista reemplazar la lista.
No cambia el contrato HTTP, las confirmaciones ni el comportamiento visual.

`OrdersListFacade` es un proveedor del shell, compartido con las vistas hijas.
Posee siete senales privadas con acceso publico de solo lectura, derivados y
comandos del listado. `OrdersListView` excluye consulta, reemplazo e insercion
desde la vista. Los metodos de carga reciben el mismo `RequestScope` existente;
el shell conserva la aplicacion de resultados, seleccion y detalle al finalizar
el lote. No se introduce otro store global ni se cambia la politica de refresh.

Las preferencias se leen al crear la instancia; antes se leian al importar
`App`. Se conservan claves, valores validos y fallback ante storage bloqueado.
La busqueda sigue en sessionStorage y las preferencias no sensibles en localStorage.
La paginacion compartida tiene una sola implementacion en `pagination.ts`.

## Verificacion

- Comparacion estructural local de 37 miembros trasladados: 37 equivalentes,
  normalizando nombres de senales privadas y lectura de preferencias por instancia.
- Cero miembros equivalentes definidos en `App`; pasa de 5400 a 4988 lineas.
- Angular build con templates estrictos correcto; typecheck correcto.
- `typecheck` ahora especifica `tsconfig.app.json`: el comando anterior apuntaba
  a un tsconfig con `files: []` y referencias, sin recorrerlas en ese modo.
- Suite existente: 14 pruebas unitarias y un smoke E2E correctos. El smoke
  intercepta API y conserva la comprobacion de cero mutaciones inesperadas.
- Compilacion Python, Ruff y arquitectura correctos: 318 modulos, una excepcion
  conocida y cero ciclos. No se modificaron codigo Python ni casos de prueba.
- Suite Python existente: 181 pruebas y 24 subtests correctos. Documentacion
  y whitespace correctos.

| Medida | Antes | Despues |
|---|---:|---:|
| Bundle inicial | 552.25 kB | 553.51 kB |
| Transferencia inicial estimada | 138.27 kB | 139.64 kB |
| Chunk diferido de Ordenes | 21.98 kB | 21.95 kB |
| CSS de App | 30.04 kB | 30.04 kB |

El bundle inicial crece 1.26 kB. Persisten advertencias de presupuesto inicial
y CSS; no se elevaron limites ni se presenta esta extraccion como una mejora
de peso. Las pruebas existentes no cubren todas las combinaciones de filtros;
la comparacion estructural respalda la preservacion de sus reglas.

## Pendiente y rollback

Alta, detalle, edicion, confirmaciones y comandos de ordenes siguen en `App`.
La vista todavia usa la fachada global para esas acciones y otras integraciones.
Los otros cinco dominios de `6.1` permanecen pendientes. No se marca `6.1` como
cerrado ni se cierra la aceptacion natural de `5.5.5` o `2.6`.

Rollback mediante revert del commit de extraccion y rebuild del dashboard;
no necesita migracion, cambios de entorno ni conciliacion de datos. No se
reiniciaron servicios ni se enviaron mensajes reales durante este bloque.
