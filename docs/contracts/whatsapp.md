# Contrato de comunicaciones WhatsApp

Estado: vigente. Ultima verificacion: `2026-08-29`.

Codigo propietario: `src/appointment_bot/services/whatsapp*` y
`src/appointment_bot/db/whatsapp*`.

## Propiedad y cola

Admin API posee el unico perfil persistente de WhatsApp Web y su dispatcher.
Otros procesos preparan o encolan trabajos durables; no abren emisores paralelos.

Cada job conserva tipo, orden, payload, deduplicacion, intentos, resultado
tecnico y, cuando aplica, mensaje o paquete asociado.

## Estados y evidencia

- `sent`: evidencia tecnica suficiente de salida;
- `uncertain`: hubo riesgo de interaccion o envio, pero no confirmacion segura;
- `failed`: fallo antes de una posible entrega o fallo clasificado;
- `dismissed`: decision de revision que cierra el trabajo original sin cambiar
  su resultado tecnico historico.

Un reloj o estado pendiente visible veta `sent`. Un check o etiqueta exacta de
enviado, entregado o leido puede confirmar el componente correspondiente.
Marcadores ocultos o etiquetas genericas no deciden.

`sent`, llegada al destinatario, lectura y confirmacion del cliente son hechos
distintos. `uncertain` nunca se reintenta automaticamente.

## Paquetes

Albumes y postpagos conservan estado por componente. El sistema no repite el
clic de adjuntos después de un posible envio. Si una recuperacion es autorizada,
crea un trabajo separado y enlaza la conciliacion del original.

Los postpagos nuevos referencian los PDF originales definidos por el contrato
de negocio; no crean copias por cliente. El orden documental debe preservarse.

## Plantillas

Las plantillas se versionan en PostgreSQL y usan variables allowlisted. Preview,
edicion, restauracion y guardado aplican revision optimista.

Al preparar un trabajo futuro se congela:

- texto renderizado;
- clave de plantilla;
- revision utilizada.

Una edición nunca modifica trabajos históricos, preparados o encolados.

## Conciliacion

La revision guiada puede registrar que el flujo ya estaba completo, completar
solo lo faltante o cerrar sin envio. Debe conservar capturas, componentes y
resultado tecnico original. Revisar no equivale a reintentar.

La observacion natural se rige por
[`../operations/whatsapp-natural-acceptance.md`](../operations/whatsapp-natural-acceptance.md).
