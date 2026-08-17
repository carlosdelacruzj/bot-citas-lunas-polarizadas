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

Para medir un flujo manual completo desde el portal, sin abrir el modal por el
operador:

```json
{"order_id": "order-12345678", "mode": "diagnostic"}
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

El modo `diagnostic` instala la medicion antes del login y deja el navegador en
el portal para que el operador realice el flujo completo. Persiste un JSON
incremental bajo `screenshots/<fecha>/manual-diagnostics/<session_id>/` con
nombres y longitudes de campos, cambios DOM, POST y estados HTTP. No guarda
password, cookies, respuesta CAPTCHA, tokens ASP.NET completos ni el cuerpo
crudo del POST. Sede, fecha y hora son los unicos valores operativos
allowlisted. Si el honeypot contiene datos, el envio se bloquea en el navegador
y el incidente queda registrado.

La medicion del honeypot distingue su estado visible en el DOM, escrituras
programaticas sobre la propiedad o el atributo `value`, el estado inmediatamente
antes de `submit` y lo que finalmente integra cada POST. Solo persiste si estaba
vacio y las longitudes anterior y posterior; nunca conserva el contenido. Esto
permite detectar un llenado transitorio aunque otro script lo borre antes del
siguiente sondeo.
