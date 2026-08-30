# Politica de evidencia

## Orden de lectura

1. `docs/evidence-summary.md`: snapshot del mes activo; leer su fecha de corte.
2. `docs/evidence-index.csv`: indice compacto del mes activo.
3. `reports/evidence/index.md`: manifiesto de indices y agregados mensuales.
4. `reports/evidence/`: salidas fechadas y bitacoras mensuales.
5. HTML y screenshots: solo para investigar un evento concreto.

`docs/project-status.md` conserva el estado vigente. `docs/evidence-summary.md`
y `docs/evidence-index.csv` son snapshots generados; deben declarar fecha de
generacion, cobertura real y faltantes antes de usarse para comparar periodos.
`reports/evidence/` conserva la historia mensual y resultados fechados. No
copiar el mismo artefacto pesado entre ambos.

## Retencion

- Conservar confirmaciones, `reservation_unconfirmed`, `slot_lost`, rechazos,
  defensas y fallos importantes.
- Conservar disponibilidades completas y parciales solo cuando exista fecha y
  hora seleccionables, o cuando documenten un bloqueo de regla, intento final
  o defensa real.
- No incorporar al indice compacto fechas sin hora (`Sin Cupos`) ni repetirlas
  como eventos utiles. Permanecen disponibles en PostgreSQL y logs para una
  investigacion tecnica puntual.
- Conservar HTML cuando pruebe la respuesta del portal o explique un fallo.
- Eliminar capturas rutinarias sin hallazgo conforme a la retencion configurada.
- El CAPTCHA original derivado del HTML es canonico; no conservar un recorte
  duplicado salvo que el original no exista.
- La limpieza configurada recorre subcarpetas de logs, screenshots y videos.
  Nunca entra en `screenshots/whatsapp/`, `screenshots/whatsapp-outgoing/` ni
  `screenshots/preflight/`. Los seguimientos post-pago referencian directamente
  los PDF originales de `pdfs/` y no generan una carpeta de screenshots.
- Dentro de las carpetas fechadas conserva por nombre confirmaciones, cupos,
  preenvios, respuestas del portal, resultados parciales, errores, defensas,
  rechazos, `reservation_unconfirmed`, `slot_lost` y CAPTCHA `original-html`.
  La retencion automatica elimina solamente artefactos antiguos que no entren
  en esas categorias.

## Datos compartibles

- Nombres, apellidos, documento, placa, expediente, WhatsApp, identificadores
  completos de orden, cuentas, tokens, passwords y respuestas CAPTCHA deben
  estar enmascarados en todo archivo versionado.
- Los generadores pasan texto por sanitizacion antes de escribir CSV/Markdown.
- Una ruta sanitizada del indice no prueba que el artefacto siga retenido. El
  manifiesto mensual declara esa disponibilidad como no verificada; una
  investigacion concreta debe comprobar el archivo antes de citarlo.
- Antes de compartir, revisar el resumen y el indice; nunca compartir dumps,
  `.env`, cookies, HTML crudo o screenshots sin inspeccion.

La captura `programado-final` es una excepcion operativa deliberada al
enmascaramiento: muestra los nombres del cliente porque funciona como constancia
individual para ese mismo cliente. Se conserva solo en `screenshots/` y en la copia
local `screenshots/whatsapp-outgoing/`, ambas fuera de Git. No debe incluir CAPTCHA,
documento, credenciales, HTML ni capturas tecnicas, y debe inspeccionarse antes de
compartirla por un canal distinto al WhatsApp del contacto correspondiente.
