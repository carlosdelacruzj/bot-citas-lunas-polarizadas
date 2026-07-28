# AGENTS.md

Instrucciones para Codex, agentes de IA y contribuidores.

## Reglas Del Proyecto

- Antes de implementar cualquier cambio, leer completos
  `docs/project-status.md` y `docs/roadmap/README.md`.
- `docs/project-status.md` es la fuente de verdad del estado actual;
  `docs/roadmap/README.md` es la unica lista de trabajo pendiente.
- Al cerrar un cambio relevante, actualizar esos archivos en el mismo cambio
  si vario una capacidad, validacion, riesgo, metrica, tarea o prioridad.
- No guardar credenciales reales en el repositorio.
- No modificar `.env` salvo que el usuario lo pida explicitamente.
- No agregar tests automatizados salvo pedido explicito del usuario.
- Mantener el proyecto simple, modular y facil de leer.
- Separar responsabilidades:
  - `browser/`: creacion y cierre del navegador.
  - `flows/`: pasos de la web.
  - `services/`: logs y notificaciones.
  - `utils/`: utilidades compartidas.
- Guardar screenshot cuando falle un paso importante.
- Preferir mensajes de error claros antes que silencios o reintentos infinitos.
- El modo de monitoreo por ventana debe ser opcional y configurable; `MONITOR_WINDOW_SECONDS=0` conserva una sola revision por ejecucion.
- n8n debe usarse como orquestador externo. Las alertas principales de Telegram y screenshots deben salir desde el bot Python.
- La cola multi-cliente debe usar una sesion Playwright nueva por cliente; no reutilizar login, cookies ni contexto entre clientes.
- PostgreSQL guarda historial, estado y credenciales de ordenes; no versionar backups ni dumps reales.

## Estilo

- Python 3.12.
- Codigo en ingles para nombres de modulos, funciones y variables.
- Documentacion del proyecto en espanol.
- Comentarios solo cuando aclaren una decision no obvia.
- Evitar abstracciones grandes antes de necesitarlas.

## Comandos Habituales

Instalar:

```bash
python -m pip install -e .
python -m playwright install chromium
```

Ejecutar:

```bash
appointment-bot-worker
```

Administrar ordenes:

```bash
appointment-bot-client orders
```

n8n consulta la API iniciada por el worker continuo; no ejecuta corridas manuales.

Revisar sintaxis:

```bash
python -m compileall src
```

Formateo/lint opcional:

```bash
python -m ruff check src
python -m ruff format src
```
