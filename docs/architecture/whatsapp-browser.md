# Infraestructura WhatsApp Web

Los servicios consumen `browser/whatsapp/api.py`. Preparacion comercial,
persistencia y politica de trabajos permanecen en `services/` y `db/`.

| Modulo | Responsabilidad |
|---|---|
| `manager` | Unica cola serial y propietario del contexto persistente. |
| `session` | Apertura, validacion, paginas y cierre del contexto. |
| `navigation` | Busqueda y comprobacion del destinatario. |
| `dom` | Inspeccion de controles, previews y texto. |
| `confirmation` | Evidencia tecnica y veto de indicadores pendientes. |
| `attachments` | Seleccion de imagenes y documentos. |
| `composition` | Edicion de texto y captions. |
| `sending` | Interaccion de envio y espera de confirmacion. |
| `album`, `documents` | Secuencia y resultados por tipo de paquete. |
| `notifications`, `drafts` | Flujos de navegador y seleccion de operacion. |
| `evidence`, `common` | Capturas, excepciones y contrato de resultado. |

`browser/whatsapp_web.py` conserva reexports temporales; no crea otra cola ni
otro contexto. No hay imports productivos de esa fachada. Su retiro requiere la
siguiente aceptacion natural posterior a la extraccion, conforme al
[runbook](../operations/whatsapp-natural-acceptance.md).

La [verificacion del 2026-09-08](../../reports/architecture/whatsapp-extraction-2026-09-08.json)
compara 90 definiciones por AST, 48 escenarios DOM y siete payloads publicos.
Incluye interaccion sobre HTML sintetico con red bloqueada: la confirmacion y
el indicador pendiente producen resultados distintos y un solo clic en ambos
casos. No usa el perfil persistente ni acredita un envio o aceptacion natural.
