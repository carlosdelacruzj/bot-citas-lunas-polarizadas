# Migraciones PostgreSQL

`db/migrations.py` conserva la version requerida y el registro explicito de
60 pasos consecutivos desde `v14` hasta `v74`. El registro se valida al importar:
rechaza saltos, duplicados, desorden y una version final distinta de la requerida.

Una base sin fila de version se crea directamente con `schema_definition.py`.
Una base existente aplica los pasos pendientes de `migration_steps/vNN_to_vNN.py`
y valida el resultado con `schema_validation.py`. Las versiones fuera del rango
soportado producen un error; no se intenta reinterpretarlas ni degradarlas.

El llamador conserva la transaccion. El migrador usa la misma conexion y un
advisory lock transaccional; no hace commit ni abre otra conexion. Una excepcion
debe propagarse al contexto transaccional para revertir DDL, datos y version.
`init_database` mantiene ese contexto mediante la conexion del pool.

Los pasos historicos, sus parametros y los helpers que consumen son inmutables.
Al agregar una version, crear un paso nuevo y extender el registro y el esquema
de base nueva. Si un helper compartido necesita otro comportamiento, separar
el nuevo helper para conservar el resultado de las actualizaciones anteriores.
`whatsapp_legacy.py` conserva los creadores de tablas de sus versiones originales.

La cobertura critica suma dispatcher, constructor, validador y todos los modulos
de pasos; exige datos de cada archivo y conserva el umbral del 45%.
La [verificacion del 2026-09-08](../../reports/architecture/migration-chain-2026-09-08.json)
compara SQL y parametros contra el dispatcher previo corregido, normalizando
solo timestamps generados durante la ejecucion. Incluye bases temporales, datos
sinteticos y dump/restore; no acredita un backup externo de la base operativa.
