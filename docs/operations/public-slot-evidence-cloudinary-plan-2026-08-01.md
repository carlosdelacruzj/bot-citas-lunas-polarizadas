# Evidencia pública de cupos y Cloudinary — 01-08-2026

## Objetivo

Reutilizar las capturas originales de cupos únicos que el bot ya archiva para
mostrar evidencia real de actividad en la landing de
`Citas Lunas Polarizadas`.

La interfaz pública las describirá como `Cupos encontrados recientemente`. Las
capturas demuestran detecciones del monitoreo; no demuestran por sí solas una
reserva completada ni que el cupo continúe disponible.

## Fuente existente

`archive_unique_slot_screenshot()` conserva una sola imagen por combinación de
fecha y hora bajo:

```text
screenshots/DD-MM-YYYY/cupos-unicos/
```

El resumen diario de las `18:00`, hora de Lima, ya enumera esas imágenes de
forma ordenada e idempotente. Ese mismo conjunto es la fuente aprobada para la
futura publicación web.

Las capturas se utilizarán completas y sin modificar su contenido. No se
publicarán capturas de conversaciones, credenciales, órdenes o comprobantes de
clientes dentro de este flujo.

## Contrato futuro de publicación

1. La integración parte únicamente de `cupos-unicos` después de cerrar la
   recolección diaria.
2. El bot selecciona recursos originales y los sube mediante la API autenticada
   de Cloudinary.
3. `cloud_name`, `api_key` y `api_secret` viven en una configuración específica
   bajo `.runtime`; el secreto no entra en Git, logs, PostgreSQL ni Angular.
4. El `public_id` es estable e idempotente e incluye la fecha de detección y la
   clave del cupo.
5. Cada imagen guarda contexto público mínimo: fecha de detección, sede, fecha
   de cita, hora y texto alternativo.
6. Una etiqueta exclusiva, por ejemplo `landing-slot-evidence`, permite listar
   solo los recursos destinados a la landing.
7. La landing muestra como máximo las tres evidencias más recientes.
8. La ausencia o falla de Cloudinary no afecta reservas, WhatsApp, Telegram ni
   el resumen diario.

## Orden de implementación

1. Copiar manualmente tres imágenes a la landing y validar la composición en
   los cuatro anchos requeridos.
2. Crear la cuenta y credenciales de Cloudinary solo con autorización expresa.
3. Implementar un comando local de preparación y subida firmada, desactivado
   por defecto.
4. Validar idempotencia, metadatos, orden y recuperación ante una subida
   parcial.
5. Conectar la lista pública de Cloudinary en la landing.
6. Solo después de una prueba controlada, evaluar el disparo desde el cierre de
   las `18:00`.

## Guardas

- No llamar `reservas` a estas capturas.
- No afirmar disponibilidad en tiempo real.
- No subir automáticamente todo el árbol de screenshots.
- No reutilizar el secreto de Cloudinary en el navegador.
- No marcar la publicación como completa si la subida o el listado quedan en
  un estado ambiguo.
- No convertir un fallo del proveedor de imágenes en un fallo operativo del
  bot.
- No desplegar esta integración mientras siga solo documentada.

## Repositorio consumidor

La composición, contenido y criterios UX viven en
`lunas-polarizadas-clientes/docs/design/public-slot-evidence.md`. Ambos
documentos deben evolucionar juntos cuando cambie el contrato.
