# Configuracion por dominio

`configuration/` define grupos inmutables de runtime, reservas, CAPTCHA,
evidencia, Telegram y WhatsApp. No lee el entorno al importar ni mantiene un
objeto global de configuracion. Cada componente recibe los grupos que necesita.

`configuration.loading` conserva el orden de carga y validacion, defaults,
limites y mensajes de error. Sus loaders por dominio seleccionan el grupo tras
validar el entorno completo. Los entrypoints que componen varios servicios
desempaquetan la tupla de grupos en variables independientes; no la transmiten
como contenedor global. Los parsers puros viven en `configuration/parsers.py`.

`config.py` y la fachada plana `Settings` estan retirados. DB recibe
`RuntimeSettings`; limpieza y muestreo reciben adicionalmente evidencia o
CAPTCHA cuando corresponde. Los puertos del motor declaran grupos explicitos.
Las clases del worker almacenan sus dependencias por separado.

Las copias por cliente usan `dataclasses.replace` del grupo propietario.
`configuration.reservation.settings_for_order` solo transforma credenciales de
`ReservationSettings`. Cambiar evidencia o notificaciones no altera el grupo
original ni las credenciales de otro cliente.

La [verificacion del 2026-09-08](../../reports/architecture/configuration-retirement-2026-09-08.json)
compara 1744 escenarios de entorno y las ramas de ejecucion del worker sin
servicios reales. Las pruebas existentes conservan un adaptador de fixtures
exclusivamente bajo `tests/`; ningun modulo productivo depende de el.
