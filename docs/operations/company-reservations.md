# Consulta manual de reservas para empresas

Utilidad a demanda, independiente del worker:

```powershell
python scripts/review-company-reservations.py --workers 4 --open-report
```

El reporte local `.runtime/company-reservations/index.html` se recarga cada
cinco segundos. Muestra empresas primero, busqueda, filtros, cuentas sin acceso,
pendientes y capturas. Cada fila conserva fecha de consulta; no es estado vivo
una vez finalizado el proceso.

Selecciona reservas confirmadas con cita anterior a hoy en Lima o ultima revision
completada. `--order-id order-XXXXXXXX` limita ese conjunto. `--refresh-all`
reconsulta el conjunto; sin esa opcion reutiliza resultados y revisa pendientes,
cuentas ocupadas y errores. Importa resultados locales de la investigacion inicial
si existen; no importa credenciales ni HTML. El archivo JSONL conserva historia.

Hasta cuatro consultas, con navegador y contexto aislados por cuenta; respeta
leases del sistema. No modifica configuracion del worker, reservas, pagos ni
comunicaciones. Usa el flujo de expediente de solo lectura, sin CAPTCHA ni submit.
Un fallo tecnico reduce la concurrencia a uno; tres consecutivos detienen nuevas
admisiones. Las consultas ya iniciadas terminan. Un lock local impide dos instancias.

Empresa confirmada exige RUC y razon social no vacios en Datos Empresa.
Reserva confirmada no acredita asistencia ni autorizacion final del tramite.
Los datos personales y capturas quedan excluidos de Git bajo `.runtime/`.
