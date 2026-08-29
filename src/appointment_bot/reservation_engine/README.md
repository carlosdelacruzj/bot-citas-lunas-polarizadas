# Motor de reservas

Implementa acceso al portal, lectura de disponibilidad, seleccion, CAPTCHA,
submit y confirmacion. Recibe reglas de una orden y devuelve resultados
persistibles; no administra la cola global ni expone HTTP.

Invariantes:

- contexto Playwright aislado por cliente;
- screenshot del cupo unico antes de CAPTCHA o submit;
- restricciones verificadas antes de seleccionar;
- confirmacion estricta del resultado del portal;
- submit ambiguo sin reintento automatico;
- CAPTCHA HTML separado del muestreo grafico opcional.

Contrato: [`../../../docs/contracts/reservation-safety.md`](../../../docs/contracts/reservation-safety.md).
