# Trazado manual de WhatsApp Web — 22-07-2026

> Evidencia historica del flujo inicial. El contrato actual es automatico y
> durable; consultar `docs/contracts/order-lifecycle.md`.

## Objetivo

Comprobar el flujo real de WhatsApp Web con una sesión Playwright visible,
dejando las acciones finales bajo control del operador. La prueba se realizó
únicamente contra el chat personal del operador y con una imagen de prueba no
sensible.

## Resultado

La prueba manual terminó correctamente:

- el perfil local abrió WhatsApp Web autenticado;
- el chat personal pudo abrirse;
- el menú de adjuntos y el selector de fotos respondieron;
- la imagen mostró su vista previa;
- el texto `PRUEBA MANUAL WHATSAPP - SESION 01` quedó visible;
- el botón de envío se habilitó;
- el envío se realizó una sola vez después de autorización explícita;
- el mensaje apareció en el chat y alcanzó doble check azul;
- el navegador cerró limpiamente y no dejó procesos Playwright activos.

Esto demuestra que, en este equipo y con el perfil vigente, la cuenta, la
sesión y el envío básico de WhatsApp Web funcionan. No demuestra todavía que
la automatización del dashboard sea estable. Los fallos intermitentes deben
buscarse en sus selectores, esperas, control de ventanas y confirmación de
estado.

## Hitos

| Hito | Hora local | Evidencia |
| --- | --- | --- |
| H0 | 22:39:31.412 | Inicio del navegador |
| H1 | 22:39:38.016 | WhatsApp listo y autenticado |
| H2 | 22:40:31.590 | Chat personal abierto |
| H3/H4 | 22:41:07.586 | Adjuntar pulsado y menú visible |
| H5 | 22:42:26.504 | Selector de archivos abierto |
| H6/H7 | 22:43:16.105 | Archivo elegido y vista previa visible |
| H8/H9 | 22:44:39.123 | Texto visible y envío habilitado |
| H9 confirmación | 22:45:41.599 | Autorización explícita del operador |
| H10 | 22:46:09.216 | Mensaje visible en el chat |
| H11 | 22:47:11.937 | Doble check azul confirmado |
| H12 | 22:48:15.228 | Navegador cerrado |

## Tiempos medidos

- Inicio de Playwright hasta WhatsApp listo: **6,604 s**.
- Autorización explícita hasta salida de la vista previa: **10,441 s**.
- Autorización hasta confirmación humana de mensaje visible: **27,616 s**.
- Confirmación de mensaje visible hasta reporte humano de doble check azul:
  **62,722 s**.
- Sesión completa: **8 min 43,816 s**.

Los tiempos que terminan en una confirmación del operador son límites
superiores: incluyen el tiempo humano de observar y responder. No deben
interpretarse como latencia pura de WhatsApp.

## Evidencia y privacidad

La evidencia cruda se guarda localmente en:

```text
reports/diagnostics/whatsapp/22-07-2026/session-01/
```

Incluye eventos JSONL, salida del trazador y una captura inicial. La carpeta
`reports/diagnostics/` está excluida de Git porque puede contener nombres,
números, conversaciones o imágenes personales. No copiar esos archivos a la
documentación versionada sin sanitizarlos.

## Repetir el trazado

```powershell
python scripts/whatsapp-manual-trace.py `
  --output-dir reports/diagnostics/whatsapp/DD-MM-YYYY/session-NN
```

El trazador solo abre WhatsApp Web, observa cambios estructurales y registra
eventos. No elige destinatarios, no adjunta archivos, no escribe mensajes y no
pulsa Enviar.

## Siguiente validación recomendada

Repetir el mismo recorrido desde la función manual del dashboard, todavía con
el número personal. Comparar sus hitos con esta línea base y capturar el primer
punto divergente. Antes de automatizar el envío final se deben estabilizar:

1. detección de una única ventana activa;
2. apertura del menú de adjuntos por estado visible, no por pausas fijas;
3. selección del control `input[type=file]` según tipo y capacidad múltiple;
4. verificación de vista previa, texto y destinatario;
5. confirmación real posterior al envío;
6. límite de un intento para evitar duplicados.
