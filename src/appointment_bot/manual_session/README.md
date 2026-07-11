# Manual Session

Sesion Playwright visible, local y separada de las sesiones del worker.

Endpoint:

```text
GET /api/v1/manual-sessions
POST /api/v1/manual-session/open
POST /api/v1/manual-session/close
```

Payload:

```json
{"order_id": "order-12345678"}
```

Close payload:

```json
{"session_id": "manual-session-abc123"}
```

Reglas:

- deshabilitada por defecto;
- requiere `MANUAL_SESSION_ENABLED=true`;
- solo acepta host y cliente loopback;
- usa una sesion Playwright nueva y visible;
- resuelve credenciales en backend y nunca devuelve password ni cookies;
- no reutiliza contexto del worker;
- hace login, selecciona el tramite, abre el modal de cita y selecciona la sede
  requerida configurada, por defecto `LIMA-LA VICTORIA`;
- no cambia estado de reserva por si sola;
- no selecciona fecha/hora, no resuelve CAPTCHA y no pulsa el boton final de
  reserva;
- permite multiples sesiones manuales activas por proceso, cada una en un
  navegador/contexto Playwright separado;
- cada sesion se limpia cuando se cierra su ventana, termina su hilo o el
  dashboard pide cerrar por `session_id`.
