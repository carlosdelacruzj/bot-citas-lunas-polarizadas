# Trazado del dashboard de WhatsApp — 22-07-2026

## Objetivo

Validar el simulacro **Probar post-pago** desde el dashboard local, usando el
número personal del operador y sin modificar órdenes reales.

## Resultado

La ejecución terminó correctamente:

- se creó un paquete de prueba;
- se enviaron `Formato_Tramite.pdf` y `requisitos.pdf`;
- se envió el texto ficticio de `CLIENTE DE PRUEBA`;
- el backend respondió HTTP 200 y registró el paquete como `sent`;
- el operador confirmó que los dos PDF y el texto estaban visibles;
- los tres elementos alcanzaron doble check azul.

El worker de citas estaba detenido durante la prueba. El Admin API fue
suficiente para ejecutar el simulacro, por lo que no se iniciaron consultas al
portal ni búsquedas de citas.

## Hitos y tiempos

| Hito | Hora local | Tiempo desde la creación |
| --- | --- | --- |
| Modal listo | 23:05:49.644 | No aplica |
| Paquete creado | 23:06:19.589 | 0 s |
| Dos PDF enviados | 23:06:29.014 | 9,425 s |
| Texto enviado | 23:06:31.948 | 12,359 s |
| Automatización declaró `sent` | 23:06:33.405 | 13,816 s |
| Respuesta HTTP 200 | 23:06:33.415 | 13,826 s |
| Doble check azul confirmado | 23:08:53.832 | Confirmación humana |

El último intervalo incluye el tiempo que tomó al operador revisar y responder;
no representa la latencia real de lectura de WhatsApp.

## Evidencia

La evidencia cruda local está en:

```text
reports/diagnostics/whatsapp/22-07-2026/session-02-dashboard/
```

El registro del backend está en `logs/run-20260722-133254.log`, líneas del
evento comprendido entre las 23:06:19 y las 23:06:33. Las carpetas de
diagnóstico y los logs no se versionan porque pueden contener datos privados.

## Conclusión operativa

El flujo automático post-pago funcionó en esta ejecución y fue
considerablemente más rápido que el recorrido manual. Este resultado no elimina
la intermitencia observada en ejecuciones anteriores: se necesita una serie de
pruebas controladas antes de considerarlo estable para clientes reales.

## Hallazgo de UX y seguridad

Durante esta prueba, el botón **Crear prueba post-pago** no creaba solamente un
borrador: abría WhatsApp, adjuntaba los PDF, los enviaba y después enviaba el
texto sin una confirmación adicional. Esto contradecía el mensaje del modal que
indicaba que WhatsApp no se consideraba enviado hasta confirmarlo manualmente.

La corrección recomendada es separar claramente las acciones:

1. **Preparar prueba**: crea el paquete y muestra destinatario, archivos y texto.
2. **Enviar prueba**: exige confirmación inmediata y realiza un único intento.

## Corrección implementada

Después de este trazado, el simulacro quedó separado en dos acciones:

1. **Preparar prueba post-pago** crea el paquete y muestra el destinatario, los
   cuatro bloques de texto y los enlaces a los PDF. No abre WhatsApp ni envía.
2. **Enviar prueba por WhatsApp** muestra una confirmación inmediata con el
   destinatario y la cantidad de PDF. Solo después de aceptar ejecuta un intento
   de envío.

Cancelar la confirmación devuelve al paquete preparado sin transmitir archivos
ni texto. Mientras el envío está en curso, el botón permanece deshabilitado
para evitar un doble clic.

## Siguiente evaluación

Ejecutar varias pruebas controladas al mismo número personal, espaciadas y sin
reintentos automáticos. Registrar por intento:

- creación del paquete;
- envío de documentos;
- envío del texto;
- estado HTTP final;
- recepción y lectura;
- duplicados o ventanas cerradas.

No probar todavía con clientes reales hasta corregir la ambigüedad del botón y
obtener una serie estable.
