# Diagnostico tecnico del negocio e inversiones

> Analisis historico con corte cerrado. Sus cifras y recomendaciones no
> gobiernan el estado ni el roadmap actuales.

Fecha de corte: `2026-07-12` (America/Lima).

Este documento resume el negocio, su sistema operativo, los resultados economicos
registrados y las inversiones recomendadas. Esta escrito para que una persona u otra IA
pueda continuar el analisis sin confundir ingresos, utilidad, reservas y capacidad tecnica.

## 1. Resumen ejecutivo

El negocio ofrece un servicio de busqueda y reserva de citas para el tramite de lunas
polarizadas, actualmente enfocado en `LIMA-LA VICTORIA`. El cliente entrega los datos de su
orden; el sistema la prioriza, monitorea el portal, intenta reservar cuando aparece un cupo,
conserva evidencia y permite controlar cobros y atencion desde un dashboard local.

A la fecha de corte, PostgreSQL registra:

- 42 ordenes ingresadas.
- 28 ordenes distintas con reserva confirmada.
- 24 pagos cobrados por `S/ 945.00` en total.
- 9 ordenes activas: 8 `ready` y 1 `paused`.
- 1 reserva con pago pendiente por `S/ 40.00`.
- 8 ordenes archivadas y 8 ordenes marcadas como no cobrables.
- 6,126 runs registrados entre el 29 de junio y el 12 de julio.

El ingreso cobrado acumulado es `S/ 945.00`. **No debe llamarse ganancia neta** porque la
base todavia no registra todos los costos. La utilidad demostrable solo podra calcularse
cuando se incorporen los consumos de CAPTCHA, energia, Internet, captacion, infraestructura
y horas humanas.

Estado tecnico observado en el corte:

- PostgreSQL 16: activo y saludable en Docker.
- Admin API/dashboard: activo en `127.0.0.1:8766`.
- Worker automatico: no respondia en `127.0.0.1:8765`; el admin API reportaba
  `worker_running=false`, `reason=api_only`.

Por tanto, la plataforma administrativa esta disponible, pero el motor que busca y reserva
no estaba trabajando al momento de esta fotografia. Antes de captar mas volumen se debe
restablecer y supervisar ese componente.

## 2. Tiempo de trabajo y madurez

Hay tres edades diferentes y conviene no mezclarlas:

| Hito | Inicio verificable | Tiempo al corte | Significado |
| --- | --- | ---: | --- |
| Desarrollo del software | 21-05-2026, primer commit | 52 dias, aproximadamente 7 semanas y 3 dias | Antiguedad del proyecto tecnico |
| Operacion comercial registrada | 19-06-2026, primera orden en PostgreSQL | 23 dias | Historial comercial disponible |
| Telemetria de ejecuciones | 29-06-2026, primer run conservado | 13 dias | Periodo medible del bot |

El repositorio tiene 64 commits. Ya no es solo un prototipo: cuenta con reservas reales,
cola multi-cliente, persistencia, cobros, dashboard, reportes y controles de seguridad. Sin
embargo, sigue siendo una operacion local dependiente de una PC, una red y una persona; aun
no es una plataforma autonomamente operada con continuidad empresarial.

## 3. Modelo de negocio actual

### Propuesta de valor

Reducir para el cliente el tiempo y la incertidumbre de vigilar cupos, usando monitoreo
automatizado y una cola por prioridad. El resultado comercial es una cita confirmada; un
simple hallazgo de disponibilidad no equivale a servicio terminado.

### Flujo operativo

1. El cliente llega principalmente por TikTok o WhatsApp.
2. Se crea una orden con identidad, contacto, credenciales cifradas y reglas de fecha/hora.
3. El worker selecciona ordenes por `priority DESC, created_at ASC`.
4. Cada cliente usa una sesion Playwright nueva; no comparte cookies ni login.
5. Una cuenta observadora detecta disponibilidad y puede activar una cola rapida.
6. La reserva solo se considera exitosa con confirmacion estricta del portal.
7. Telegram envia alertas y evidencia; el operador gestiona excepciones desde el dashboard.
8. El pago se registra por separado en PostgreSQL.

### Precio y ticket

El precio dominante observado es `S/ 40.00`; existe al menos un cobro de `S/ 25.00` y dos
subordenes cobradas a `S/ 40.00`. El ticket promedio acumulado es `S/ 39.38`
(`S/ 945 / 24 pagos`). No hay una tabla formal de precios, descuentos, devoluciones o costo
por tipo de tramite; crearla es necesario para medir margen.

## 4. Resultados financieros registrados

### Ingreso realizado

| Mes de cobro | Pagos | Ingreso cobrado | Ticket promedio |
| --- | ---: | ---: | ---: |
| Mayo 2026 | 0 | S/ 0.00 | S/ 0.00 |
| Junio 2026 | 3 | S/ 120.00 | S/ 40.00 |
| Julio 2026, hasta el dia 12 | 21 | S/ 825.00 | S/ 39.29 |
| **Total** | **24** | **S/ 945.00** | **S/ 39.38** |

Julio concentra `87.3%` del ingreso acumulado. El crecimiento es fuerte, pero la muestra es
corta y julio es un mes incompleto; no debe extrapolarse linealmente como pronostico.

### Fuentes en julio

| Fuente registrada | Ordenes creadas | Reservas confirmadas | Ingreso cobrado |
| --- | ---: | ---: | ---: |
| TikTok | 16 | 12 | S/ 400.00 |
| WhatsApp | 10 | 7 | S/ 240.00 |
| Sin fuente | 7 | 5 | S/ 185.00 |

TikTok es la mayor fuente identificada de volumen e ingreso en julio. Esto no demuestra
rentabilidad del canal porque no se registra gasto publicitario ni tiempo dedicado a crear
contenido. Las ordenes sin fuente reducen la calidad de cualquier decision de marketing.

### Embudo observable

- 42 ordenes historicas.
- 28 con reserva confirmada: `66.7%` sobre todas las ordenes registradas.
- 24 pagos cobrados: `57.1%` sobre todas las ordenes y `85.7%` sobre reservas confirmadas.
- 9 ordenes activas y 1 pago pendiente por S/ 40.00.

Estas razones describen el estado acumulado, no una cohorte cerrada: varias ordenes activas
aun pueden convertirse y algunas reservas fueron gratuitas o externas.

### Utilidad real: dato aun no disponible

Formula correcta:

```text
utilidad_neta = ingresos_cobrados
              - CAPTCHA consumido
              - publicidad y captacion
              - energia e Internet imputables
              - hosting, backups y herramientas
              - devoluciones y comisiones de cobro
              - costo del tiempo humano
              - impuestos aplicables
```

Con la informacion actual solo se puede afirmar:

```text
ingreso cobrado acumulado = S/ 945.00
cuentas por cobrar registradas = S/ 40.00
utilidad neta verificable = no calculable todavia
```

No se debe sumar el pendiente a los ingresos ni asumir costos cero.

## 5. Capacidad tecnica y rendimiento

La semana del 6 al 12 de julio contiene 4,416 runs y 37 intentos compatibles. Hubo 15
resultados `registered`, una conversion tecnica base de `40.5%`. Ademas se reportaron 6
casos ya `Programado/completed`, que se mantienen separados para no atribuirlos dos veces al
bot. Los tiempos p50/p90 fueron:

| Tramo | p50 | p90 |
| --- | ---: | ---: |
| Deteccion a fin | 6.977 s | 11.283 s |
| Seleccion de fecha/hora | 1.719 s | 1.891 s |
| CAPTCHA | 1.359 s | 3.047 s |

El principal problema observable no es la latencia media: `slot_lost` alcanzo 16 casos y
`43.2%` de los intentos compatibles. No hubo senales de defensa del portal esa semana. La
etapa vigente es observacional: no se deben cambiar concurrencia, CAPTCHA, esperas o flujo
de reserva hasta completar la muestra del 13 al 18 de julio y revisar resultados.

## 6. Recursos utilizados actualmente

### Software e infraestructura

- Windows y PowerShell como host operativo.
- Python 3.12.
- Playwright y Chromium para automatizacion web.
- PostgreSQL 16 dentro de Docker, con volumen persistente.
- Angular para el dashboard local.
- Servicio 2Captcha para resolver CAPTCHA.
- Telegram Bot para alertas, screenshots y resultados diferidos.
- n8n como supervisor externo, no como ejecutor de reservas.
- FFmpeg opcional para videos de reservas confirmadas.
- Git/GitHub para versionado y trazabilidad.
- Criptografia Fernet para credenciales almacenadas.

### Recursos fisicos y humanos

- Una PC Windows encendida durante las ventanas de operacion.
- Conexion estable a Internet y una IP con comportamiento aceptado por el portal.
- Energia electrica y capacidad de recuperacion tras reinicios.
- Operador para altas, contactos, cobros, excepciones, sesiones manuales y revision de
  Telegram.
- Cuenta observadora del portal y credenciales individuales de los clientes.
- Telefono/canal de WhatsApp y presencia de captacion en TikTok.

### Datos sensibles

Se procesan documentos, contactos y credenciales del portal. PostgreSQL, `.env`, screenshots,
videos y logs deben tratarse como informacion sensible. El dashboard y ambas APIs estan
diseñados para loopback; no deben exponerse directamente a Internet.

## 7. Dependencias y puntos unicos de falla

| Dependencia | Fallo posible | Impacto | Control actual | Brecha |
| --- | --- | --- | --- | --- |
| PC Windows | apagado, suspension, update | se detiene toda busqueda | script supervisor | no hay segundo host |
| Worker | proceso caido | no hay monitoreo ni reserva | health y reinicio | estaba apagado en este corte |
| Internet/IP | corte, latencia, bloqueo | login o submit fallan | recovery/backoff | sin enlace alterno medido |
| PostgreSQL local | corrupcion o disco perdido | perdida operativa | restore temporal probado | falta backup durable cifrado |
| 2Captcha | saldo, demora, error | se pierde el cupo | metricas y reintento acotado | costo no se registra por orden |
| Portal externo | cambios DOM o defensas | automatizacion deja de funcionar | errores claros, screenshots | dependencia fuera de control |
| Telegram | token/API caidos | operador pierde alertas | envio desde Python | sin canal secundario |
| Operador unico | indisponibilidad | cobros y excepciones se atrasan | dashboard/runbook | sin cobertura ni SLA |

## 8. Inversiones recomendadas

### Prioridad 0: medir economia unitaria antes de escalar

Crear un registro mensual de costos y asociar, cuando sea posible, costos variables a cada
orden. Campos minimos: fecha, categoria, proveedor, monto, moneda, orden opcional y
comprobante. Medir:

- saldo cargado y consumo real de 2Captcha;
- gasto de TikTok/publicidad y leads por canal;
- horas humanas por alta, seguimiento, cobro y excepcion;
- energia, Internet, hosting, comisiones y devoluciones;
- ingreso cobrado por orden y fuente.

Indicadores resultantes: margen por reserva, costo de adquisicion (CAC), ingreso por lead,
tasa de cobro, horas humanas por reserva y periodo de recuperacion de cada inversion.

Esta es la inversion de informacion mas urgente: sin ella se puede aumentar ventas y, aun
asi, perder dinero.

El registro inicial ya esta definido en [`finance/cost-register.csv`](finance/cost-register.csv)
y sus reglas de uso en [`finance/README.md`](finance/README.md). Las recargas de 2Captcha se
registran como saldo prepagado y el consumo como costo del periodo, evitando sumar ambos como
si fueran dos gastos. Los gastos de TikTok se agregan individualmente con canal y campana
cuando esta ultima se conozca.

### Prioridad 1: continuidad y proteccion de datos

1. Automatizar un backup cifrado diario de PostgreSQL hacia un destino distinto de la PC.
2. Definir retencion, prueba mensual de restauracion y alerta ante backup fallido.
3. Evitar suspension automatica; agregar arranque tras reinicio y vigilancia del worker.
4. Considerar UPS si los cortes electricos son frecuentes.
5. Medir disponibilidad de Internet; contratar enlace de respaldo solo si las caidas
   justifican su costo.

Esta prioridad protege el activo central: ordenes, credenciales cifradas, pagos, historial y
evidencia. Un segundo servidor no compensa la falta de backups.

### Prioridad 2: operacion comercial

1. Normalizar precios y reglas de cobro por servicio/suborden.
2. Registrar fuente obligatoria y, si aplica, campana/contenido.
3. Crear estados de seguimiento de cobro, vencimiento y devolucion.
4. Definir mensajes y tiempos de atencion para WhatsApp.
5. Medir cuantas reservas gratuitas o externas consumen capacidad.

Con los datos actuales, TikTok merece medicion prioritaria, no gasto ciego: produjo S/ 400
de julio, pero su CAC es desconocido.

### Prioridad 3: confiabilidad tecnica basada en evidencia

1. Restablecer el worker y alertar si `8765/health` deja de responder durante horario activo.
2. Completar la observacion del 13 al 18 de julio.
3. Revisar `slot_lost`, CAPTCHA, p50/p90 y supervivencia secuencial el 20 de julio.
4. Elegir un solo experimento reversible; no activar concurrencia ni cambiar proveedor por
   intuicion.
5. Atender despues la deuda modular documentada, sin mezclarla con cambios del flujo real.

### Prioridad 4: escalamiento, solo con margen positivo

Evaluar un host dedicado o segundo equipo cuando el margen medido y el volumen lo paguen.
Antes de migrar a nube hay que comprobar que el portal tolere la IP/entorno y que el manejo
de datos sea adecuado. Mantener una unica instancia activa mediante leases; la redundancia
no significa ejecutar dos reservas simultaneas sobre la misma orden.

Una regla de inversion util es:

```text
reservas adicionales necesarias = costo mensual de la inversion / margen por reserva
```

Ejemplo puramente metodologico: una mejora de S/ 200 mensuales requeriria 10 reservas
adicionales si el margen real fuera S/ 20, o 5 si fuera S/ 40. No usar este ejemplo como
estimacion hasta medir el margen.

## 9. Lo que no conviene financiar todavia

- Exponer el dashboard local a Internet.
- Concurrencia agresiva para perseguir mas cupos sin revisar defensas y `slot_lost`.
- Un cambio de CAPTCHA sin costo, precision y latencia comparables.
- Infraestructura compleja de alta disponibilidad antes de tener backup durable y costos.
- Publicidad pagada sin fuente/campana obligatoria y CAC.
- Reescrituras grandes del software que no reduzcan costo, riesgo o tiempo operativo.

## 10. Plan de 30 dias

### Semana 1

- Recuperar y verificar el worker.
- Acumular la muestra planificada.
- Empezar libro de costos y saldo/consumo CAPTCHA.
- Configurar backup externo cifrado y alerta.

### Semana 2

- Ejecutar el analisis semanal del 13 al 18 de julio.
- Elegir como maximo un experimento tecnico.
- Hacer obligatoria la atribucion de fuente/campana en nuevas ordenes.
- Medir minutos humanos por orden.

### Semanas 3 y 4

- Calcular margen por reserva, CAC por fuente y tasa de cobro.
- Comparar el experimento contra la linea base.
- Decidir UPS, Internet de respaldo u host dedicado usando costo por reserva recuperada.
- Establecer metas mensuales de reservas cobradas, ingreso, margen y disponibilidad.

## 11. Indicadores que deben gobernar el negocio

| Categoria | Indicador |
| --- | --- |
| Ventas | leads, ordenes nuevas, reservas confirmadas, pagos cobrados |
| Embudo | orden a reserva, reserva a pago, tiempo hasta reserva |
| Finanzas | ingreso realizado, costo variable, margen por reserva, utilidad neta |
| Marketing | fuente completa, CAC, conversion e ingreso por canal |
| Operacion | minutos humanos por orden, pendientes, antiguedad, devoluciones |
| Tecnologia | uptime del worker, `registered`, `slot_lost`, defensas, p50/p90 |
| Riesgo | edad del ultimo backup valido, restore probado, incidentes de datos |

## 12. Fuentes y limites del diagnostico

Fuentes usadas: PostgreSQL en vivo, `appointment-bot-client orders`, health local, historial
Git, `docs/project-status.md`, `docs/roadmap/README.md`, `docs/optimization.md`,
`reports/operations/latest.md`, `reports/optimization/latest.md`, arquitectura, configuracion
y dependencias del repositorio.

Las cifras financieras son importes marcados `paid` con `paid_at` y no incluyen pendientes.
Los conteos son una fotografia y cambiaran con la operacion. No se inspeccionaron ni copiaron
valores secretos de `.env`; solo se comprobo la presencia de recursos necesarios. Este
documento no calcula impuestos ni reemplaza contabilidad profesional.
