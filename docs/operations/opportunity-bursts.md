# Runbook de rafagas de oportunidad

Estado: estable y vigente.

## Activacion

Solo una disponibilidad real y compatible inicia una rafaga. La rafaga admite
como maximo tres sesiones Playwright aisladas: el detector y hasta dos
auxiliares. Cada orden conserva credenciales, cookies, claim, lease, reglas e
intento propios.

Los auxiliares compatibles con menos oportunidades observadas y con reglas mas
restrictivas entran antes que los clientes amplios. La prioridad exclusiva
conserva precedencia y las subordenes mantienen su regla de continuidad. Haber
pertenecido al bloque activo no adelanta a un cliente amplio sobre otro mas
restringido.

## Admisión deslizante

Después de un `registered`, el coordinador puede admitir el siguiente candidato
compatible sin exceder el limite. Esto es admision concurrente dentro de la
rafaga, no un traspaso de la reserva confirmada. No sustituye una sesion activa
ni transfiere estado del navegador.

El traspaso secuencial queda reservado para una orden que observo un cupo real
pero no pudo usarlo por sus propias reglas. Una orden que ya reservo continua
por la cola general y no genera ese traspaso.

Despues de recorrer candidatos compatibles, la orden restringida que origino el
traspaso obtiene una revision final dentro de la misma ventana. No se repite si
no hubo ningun candidato que justificara abrir el traspaso.

## Reobservacion de cupo perdido

Solo un `slot_lost` explicito permite una reobservacion. Es unica, conserva el
intento anterior y vuelve a validar compatibilidad. No se ejecuta tras submit,
resultado ambiguo, defensa, claim perdido o error tecnico sin autoridad.

## Breakers

Cerrar admision ante:

- `403`, `429` o defensa;
- `reservation_unconfirmed`;
- claim/lease perdido;
- navegador huerfano;
- fallo de coordinacion;
- cualquier riesgo de submit duplicado.

El breaker abierto prevalece sobre el modo deseado. Resetear requiere actor,
motivo y revision vigente.

## Evidencia

Cada rafaga debe reconstruir inicio/fin, candidatos, concurrencia, roles,
seleccion, tiempos, claims, intentos y causa de salida. Cada auxiliar enlaza
`burst_id` y posicion. La reobservacion enlaza el intento `slot_lost` original y
su resultado.

## Drenaje y desactivacion

Usar `draining` para bloquear reemplazos y dejar terminar sesiones existentes.
Al cerrar la ultima, el control pasa a `disabled`. No reiniciar durante submit ni
marcar rafagas como cerradas borrando evidencia.

Contrato: [`../contracts/worker-control.md`](../contracts/worker-control.md).
