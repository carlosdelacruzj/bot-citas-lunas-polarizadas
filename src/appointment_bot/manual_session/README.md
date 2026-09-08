# Sesion manual

Administra una unica sesion Playwright controlada para diagnostico o intervencion
autorizada.

Modos:

- `auto`: selecciona el recorrido aplicable;
- `appointment`: exige una orden apta;
- `portal`: se detiene tras acceder al portal;
- `diagnostic`: conserva trazas sanitizadas para investigar selectores.

La sesion no comparte contexto con la cola y no puede abrirse sobre recursos
incompatibles activos. Las capturas diagnosticas se escriben bajo la jerarquia
que define `diagnostics.py`; verificar el codigo antes de asumir una ruta fija.
