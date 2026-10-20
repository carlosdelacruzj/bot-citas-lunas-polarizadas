# Contrato CAPTCHA

Estado: vigente. Ultima verificacion: `2026-09-04`.

## Dos problemas distintos

1. El portal actual puede presentar una suma HTML antes de habilitar la sede o
   antes de reservar. Se resuelve localmente con parser estricto y validacion
   explicita del resultado devuelto por el portal.
2. El CAPTCHA grafico pertenece al sistema de muestreo/aprendizaje en sombra.
   Está en almacenamiento frio por defecto y no participa si
   `CAPTCHA_SHADOW_SERVICE_ENABLED=false`.

Nunca mezclar datasets, autoridad ni métricas entre ambos mecanismos.

La barrera previa a sede exige una unica suma, campo, boton, confirmacion y
honeypot vacio. Se envia una sola vez y solo continua cuando el portal marca la
verificacion y hace visible la sede. Una estructura distinta, una confirmacion
ambigua o un honeypot no vacio genera evidencia y pausa globalmente el worker;
no se prueba una variante ni se reintenta automaticamente.

Al abrir o reabrir el panel, el motor espera que la sede o la interfaz CAPTCHA
sea visible antes de validar la barrera. Controles solo adjuntos al HTML no
demuestran que el panel haya abierto. Si sigue cerrado, se permite una sola
apertura alternativa por postback; nunca se repite un envio CAPTCHA ambiguo.
El observador tambien espera visibilidad tras su postback de apertura, hasta
15 segundos. Si el panel no aparece, devuelve flujo no disponible sin intentar
resolver el CAPTCHA ni repetir ese postback.

La barrera final es independiente. Un candidato obtenido por consulta directa
debe reproducirse primero en el modal vivo; el aviso de deteccion no espera al CAPTCHA.
Comprobar que la pregunta CAPTCHA
es visible no autoriza calcularla, llenar su campo ni enviar `Reservar`. Con
`AUTO_RESERVE=false`, la captura canonica cierra el flujo en ese punto.
Antes de resolver y en cada frontera previa al clic, el formulario debe mantener
un unico `form1` POST a `Seguimiento.aspx`, controles criticos unicos, tokens
ASP.NET presentes, honeypot presente y vacio, y ningun campo inesperado. La
estructura se firma al inicio y debe permanecer estable; una
diferencia genera `PortalContractChanged`, evidencia y pausa sin submit.
Las dos formas conocidas del honeypot son el legado `txtHoneypot` y el actual
`#hfHoneypot` serializado como `website_url`; debe existir exactamente una. La
telemetria solo conserva presencia, estado vacio y longitud, nunca su valor.

El formulario actual tambien admite la variante sin CAPTCHA final: cero campos
`txtimg` y cero preguntas finales, CAPTCHA previo confirmado con token, honeypot
vacio y formulario conocido. El boton `btgSiguiente` se trata como submit real:
exige captura, seleccion e identidad validas, lease, intencion y pending durables.
Su POST y respuesta se miden y capturan. Si aparece el CAPTCHA final conocido,
continua el mismo intento bajo validacion estricta; una respuesta ambigua nunca
origina otro clic. `AUTO_RESERVE=false` bloquea ambos caminos de envio.

## Autoridad y fallback

El servicio grafico opcional es fail-open: una prediccion local, timeout o fallo
del servicio no bloquea el flujo autorizado. Reactivarlo o ampliar su autoridad
requiere decision explicita, limite de canario, umbrales, breaker y fallback
externo preservado.

Una prediccion en sombra no confirma una reserva ni autoriza un submit por si
sola.

El motor consume solucion, muestreo y correlacion mediante `CaptchaAuthority`;
el worker conecta ese puerto con la autoridad y persistencia productivas.

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
