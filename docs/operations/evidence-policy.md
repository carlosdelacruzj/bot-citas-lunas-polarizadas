# Politica de evidencia

## Orden de lectura

1. `docs/evidence-summary.md`: resumen vigente.
2. `docs/evidence-index.csv`: indice compacto y filtrable.
3. `reports/evidence/`: salidas fechadas regenerables.
4. HTML y screenshots: solo para investigar un evento concreto.

`docs/` conserva la lectura vigente; `reports/evidence/` conserva resultados
fechados. No copiar el mismo artefacto pesado entre ambos.

## Retencion

- Conservar confirmaciones, `reservation_unconfirmed`, `slot_lost`, rechazos,
  defensas y fallos importantes.
- Conservar HTML cuando pruebe la respuesta del portal o explique un fallo.
- Eliminar capturas rutinarias sin hallazgo conforme a la retencion configurada.
- El CAPTCHA original derivado del HTML es canonico; no conservar un recorte
  duplicado salvo que el original no exista.

## Datos compartibles

- Documento, WhatsApp, cuentas, tokens y passwords deben estar enmascarados.
- Los generadores pasan texto por sanitizacion antes de escribir CSV/Markdown.
- Antes de compartir, revisar el resumen y el indice; nunca compartir dumps,
  `.env`, cookies, HTML crudo o screenshots sin inspeccion.
