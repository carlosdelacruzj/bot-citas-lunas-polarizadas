# AGENTS.md

Instrucciones para Codex, agentes de IA y contribuidores.

## Reglas Del Proyecto

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
python -m appointment_bot.main
```

Revisar sintaxis:

```bash
python -m compileall src
```

Formateo/lint opcional:

```bash
python -m ruff check src
python -m ruff format src
```
