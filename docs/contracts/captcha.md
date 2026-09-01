# Contrato CAPTCHA

Estado: vigente. Ultima verificacion: `2026-08-29`.

## Dos problemas distintos

1. El portal actual puede presentar una suma HTML. Se resuelve localmente con
   parser estricto y validacion del resultado.
2. El CAPTCHA grafico pertenece al sistema de muestreo/aprendizaje en sombra.
   Está en almacenamiento frio por defecto y no participa si
   `CAPTCHA_SHADOW_SERVICE_ENABLED=false`.

Nunca mezclar datasets, autoridad ni métricas entre ambos mecanismos.

## Autoridad y fallback

El servicio grafico opcional es fail-open: una prediccion local, timeout o fallo
del servicio no bloquea el flujo autorizado. Reactivarlo o ampliar su autoridad
requiere decision explicita, limite de canario, umbrales, breaker y fallback
externo preservado.

Una prediccion en sombra no confirma una reserva ni autoriza un submit por si
sola.

La solucion usada puede vivir durante la correlacion inmediata dentro del
dominio CAPTCHA, pero se retira antes de construir un reporte general. La
sanitizacion recursiva por clave y contenedor protege lecturas historicas sin
reescribir automaticamente filas anteriores.

## Integridad de evidencia

- conservar bytes y SHA del artefacto antes de etiquetar;
- separar prediccion local, respuesta externa, etiqueta humana y verdad del
  portal;
- no publicar imagen, respuesta ni identificador personal;
- paginar revision y exportacion desde el servidor;
- presentar calidad por cohorte comparable y con tamaño de muestra.

CAPTCHA no forma parte del total comercial de Pendientes. Si el muestreo está
inactivo, la UI puede ocultarlo sin afectar ordenes ni reservas.

La evolucion V1-V6 y sus benchmarks fueron retirados del working tree; pueden
recuperarse puntualmente mediante [`../history/README.md`](../history/README.md).
