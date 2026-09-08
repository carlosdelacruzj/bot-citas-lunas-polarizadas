# Configuracion por dominio

`configuration/` define grupos inmutables de runtime, reservas, CAPTCHA,
evidencia, Telegram y WhatsApp. No lee el entorno al importar ni mantiene un
objeto global de configuracion. Logging recibe directamente `RuntimeSettings`.

`config.load_settings` conserva el orden de carga y validacion para mantener
defaults, limites, mensajes de error y prioridad cuando varias variables son
invalidas. Los parsers puros viven en `configuration/parsers.py`.

`Settings` es una fachada temporal de composicion. Conserva sus campos planos,
constructor y `dataclasses.replace`, usados para configuraciones por cliente.
Sus propiedades de dominio crean snapshots inmutables, almacenados por instancia;
una copia mediante `replace` obtiene snapshots propios, sin reutilizar datos del
cliente anterior. `asdict` conserva el contrato plano.

Los nuevos componentes deben recibir el grupo que necesitan. La fachada no se
retira hasta migrar tambien las fronteras que cargan, copian y transmiten la
configuracion completa. No sustituirla por otro singleton o contenedor global.

La [comparacion del 2026-09-08](../../reports/architecture/configuration-domains-2026-09-08.json)
usa 1744 escenarios sinteticos con dotenv desactivado; no modifica `.env`.
