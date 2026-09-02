# Verificacion de backup y restauracion de PostgreSQL

Ultima verificacion documental: `2026-08-30`.

Este runbook comprueba que PostgreSQL puede generar y restaurar un dump en una
base temporal aislada. No crea un backup durable, no copia datos fuera del
host y no sustituye la tarea pendiente de backup externo.

## Alcance

El script [`../../scripts/verify-postgres-backup.ps1`](../../scripts/verify-postgres-backup.ps1):

1. lee `POSTGRES_USER` y `POSTGRES_DB` dentro del contenedor;
2. crea un dump temporal en formato custom con `pg_dump`;
3. restaura el dump en una base temporal con nombre unico;
4. compara conteos de tablas operativas y `schema_version`;
5. elimina siempre la base temporal y el dump mediante `finally`.

Las tablas comparadas son `service_orders`, `runs`, `reservations`,
`reservation_attempts` y `payments`. Esta comprobacion detecta fallos basicos
de dump/restore y diferencias de conteo; no valida el contenido fila por fila,
la restauracion en otro host ni la recuperacion de archivos locales.

## Requisitos

- Docker y el contenedor PostgreSQL en ejecucion.
- Espacio suficiente dentro del contenedor para el dump y la base temporal.
- Ninguna operacion administrativa concurrente que cree o elimine bases.
- Ejecutar desde la raiz del repositorio.

La operacion puede ejecutarse con el runtime activo porque solo lee la base
principal y escribe en una base temporal separada. Aun asi, conviene evitar una
ventana de migracion o mantenimiento para obtener una comprobacion estable.

## Ejecucion

Con el nombre predeterminado del contenedor:

```powershell
powershell -ExecutionPolicy Bypass -File scripts/verify-postgres-backup.ps1
```

Con otro nombre:

```powershell
powershell -ExecutionPolicy Bypass -File scripts/verify-postgres-backup.ps1 `
  -Container NOMBRE_DEL_CONTENEDOR
```

El resultado correcto enumera los conteos verificados, confirma
`schema_version` y termina con `Backup and restore verification completed
without keeping a dump.`

## Fallo y comprobacion posterior

El script devuelve error ante cualquier comando Docker fallido o diferencia de
conteos/version. El bloque `finally` intenta retirar los recursos temporales
incluso después de un fallo. Si la limpieza tambien falla, comprobar dentro del
contenedor que no queden nombres con estos prefijos antes de repetir:

- base: `appointment_bot_verify_`;
- dump: `/tmp/appointment-bot-verify-`.

No borrar otras bases ni dumps. Investigar primero espacio, permisos, version de
PostgreSQL y el comando exacto que fallo.

## Limite operativo

Una ejecucion satisfactoria demuestra recuperabilidad local basica en ese
momento. El cierre real de resiliencia sigue requiriendo backup externo,
retencion definida y una restauracion probada fuera del contenedor principal.
