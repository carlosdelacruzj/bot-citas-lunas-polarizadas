# Obtener Lunas Polarizadas

Automatizador personal para revisar manualmente la disponibilidad de citas en una pagina web.

La primera version se ejecuta a mano, muestra el resultado por consola, escribe logs y guarda screenshots cuando ocurre un error. Las capturas de cada paso se pueden activar solo cuando se necesite depurar. Cuando la disponibilidad no se puede determinar, guarda un diagnostico de texto sanitizado para facilitar el ajuste de selectores y textos.

## Requisitos

- Python 3.12
- Navegadores de Playwright

## Instalacion

Crear y activar un entorno virtual:

```bash
python -m venv .venv
.\.venv\Scripts\Activate.ps1
```

Instalar dependencias:

```bash
python -m pip install -e .
python -m playwright install chromium
```

Crear el archivo de configuracion local:

```bash
Copy-Item .env.example .env
```

Editar `.env` con la URL y credenciales reales. No compartas ese archivo.

## Ejecucion

```bash
python -m appointment_bot.main
```

Por defecto el navegador se abre visible (`HEADLESS=false`) para poder mirar que pasa paso a paso.

## Configuracion

Variables iniciales:

```env
TARGET_URL=
LOGIN_USERNAME=
LOGIN_PASSWORD=
HEADLESS=false
BLOCK_HEAVY_ASSETS=true
SCREENSHOT_ON_ERROR=true
SCREENSHOT_ON_RELEVANT_RESULT=true
DEBUG_SNAPSHOTS=false
LOG_LEVEL=INFO
```

Para depurar visualmente cada paso, usar:

```env
DEBUG_SNAPSHOTS=true
```

Para ejecucion mas rapida, mantener:

```env
HEADLESS=true
BLOCK_HEAVY_ASSETS=true
SCREENSHOT_ON_RELEVANT_RESULT=true
DEBUG_SNAPSHOTS=false
```

## Ajuste De Selectores

Como cada pagina web tiene formularios y textos distintos, probablemente haya que ajustar:

- `src/appointment_bot/flows/login.py`
- `src/appointment_bot/flows/appointments.py`

La primera version usa selectores genericos para el login y textos comunes para detectar disponibilidad. Si la web cambia o no coincide, el programa debe fallar con logs y screenshot para facilitar el ajuste.

## Validacion Manual

Al ejecutar, revisar:

- que abre la URL correcta
- que carga credenciales desde `.env`
- que intenta iniciar sesion
- que navega o permanece en la zona esperada
- que muestra en consola si hay cupo, no hay cupo o si no pudo determinarlo
- que crea logs en `logs/`
- que guarda screenshot en `screenshots/` cuando falla
- que guarda diagnosticos en `diagnostics/` si el resultado queda como indeterminado

## Seguridad Y Limites

Este proyecto no debe usarse para saltar captchas, colas virtuales, controles anti-bot ni restricciones del sitio. Si aparece un captcha o control manual, el flujo debe detenerse o requerir intervencion humana.
