# Manual Session

Sesion Playwright visible, local y separada de las sesiones del worker.

Endpoint:

```text
POST /api/v1/manual-session/open
```

Payload:

```json
{"order_id": "order-12345678"}
```

Reglas:

- deshabilitada por defecto;
- requiere `MANUAL_SESSION_ENABLED=true`;
- solo acepta host y cliente loopback;
- usa una sesion Playwright nueva y visible;
- resuelve credenciales en backend y nunca devuelve password ni cookies;
- no reutiliza contexto del worker;
- no cambia estado de reserva por si sola;
- permite solo una sesion manual activa por proceso.
