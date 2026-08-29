# Runbook de rafagas de oportunidad

Estado: vigente. No contiene tamaños de muestra; esos viven en el roadmap.

## Activacion

Solo una disponibilidad real y compatible inicia OBS-006. La rafaga admite como
maximo dos sesiones Playwright aisladas. Cada orden conserva credenciales,
cookies, claim, lease, reglas e intento propios.

## Admisión deslizante

Después de un `registered`, el coordinador puede admitir el siguiente candidato
compatible sin exceder el limite. No sustituye una sesion activa ni transfiere
estado del navegador.

## Reobservacion OBS-007

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
Aceptacion pendiente: [`../roadmap/README.md`](../roadmap/README.md).
