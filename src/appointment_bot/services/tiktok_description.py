from __future__ import annotations

from datetime import date
from math import prod

TITLES = (
    "🚨 Nuevas citas pueden aparecer en cualquier momento",
    "🚗 ¿Sigues buscando una cita para lunas polarizadas?",
    "📅 Los cupos para el peritaje pueden durar pocos minutos",
    "⚠️ Encontrar una cita no debería quitarte todo el día",
    "🔍 Nosotros monitoreamos las citas por ti",
    "✅ Tu cita para lunas polarizadas puede aparecer cuando menos lo esperas",
    "🚘 Deja de revisar la plataforma a cada momento",
    "⏰ Un nuevo cupo puede liberarse en cualquier momento",
    "📲 Te ayudamos a monitorear tu cita para el peritaje",
    "🚦 Monitoreamos nuevos cupos para lunas polarizadas",
    "🗓️ ¿Tu trámite está registrado pero todavía no tienes cita?",
    "💡 Así puedes evitar revisar las citas todo el día",
)

OPENINGS = (
    (
        "Conseguir una cita para el peritaje de lunas polarizadas no siempre "
        "es fácil."
    ),
    (
        "Los cupos para el peritaje pueden aparecer sin previo aviso y agotarse "
        "rápidamente."
    ),
    (
        "Revisar la plataforma durante todo el día puede tomar tiempo y aun así "
        "no garantiza encontrar disponibilidad."
    ),
    (
        "Si tu trámite ya está registrado, no tienes que estar actualizando la "
        "página a cada momento."
    ),
    (
        "Muchas personas encuentran la plataforma sin disponibilidad justo "
        "cuando necesitan programar su peritaje."
    ),
    (
        "Las fechas disponibles cambian constantemente y algunos horarios duran "
        "solo unos minutos."
    ),
    (
        "Encontrar el horario adecuado requiere revisar la plataforma cuando la "
        "PNP libera nuevos cupos."
    ),
    (
        "Tu trámite puede estar listo, pero todavía falta encontrar una fecha "
        "disponible para el peritaje."
    ),
)

SERVICE_EXPLANATIONS = (
    (
        "Nosotros monitoreamos la plataforma e intentamos separar una cita "
        "cuando aparece un cupo compatible con tu trámite."
    ),
    (
        "Podemos encargarnos del monitoreo e intentar reservar cuando se libera "
        "una fecha compatible."
    ),
    (
        "Nuestro servicio revisa la disponibilidad e intenta obtener la cita "
        "apenas aparece una opción compatible."
    ),
    (
        "Monitoreamos los nuevos horarios para intentar reservar sin que tengas "
        "que revisar manualmente durante todo el día."
    ),
    (
        "Hacemos seguimiento a la disponibilidad e intentamos separar el cupo "
        "cuando la plataforma muestra una opción válida."
    ),
    (
        "Nos encargamos de vigilar los cupos e intentar la reserva cuando aparece "
        "una fecha que cumple las condiciones de tu trámite."
    ),
)

CALLS_TO_ACTION = (
    "¿Quieres que monitoreemos tu trámite?",
    "¿Todavía estás buscando una cita?",
    "¿Quieres empezar con el monitoreo?",
    "¿Necesitas ayuda para encontrar disponibilidad?",
    "¿Tu trámite ya está registrado?",
    "¿Quieres dejar de revisar la plataforma manualmente?",
    "¿Buscas una fecha para tu peritaje?",
    "¿Listo para comenzar?",
)

DISCLAIMERS = (
    (
        "⚠️ La disponibilidad depende de los cupos que libera la PNP. "
        "Las fechas pueden agotarse en pocos minutos."
    ),
    (
        "⚠️ Los cupos son liberados por la PNP y pueden agotarse rápidamente. "
        "El servicio no garantiza una fecha específica."
    ),
    (
        "⚠️ La reserva depende de la disponibilidad publicada por la PNP. "
        "Los horarios pueden cambiar o agotarse."
    ),
    (
        "⚠️ No controlamos la liberación de cupos. Intentamos reservar únicamente "
        "cuando la plataforma de la PNP muestra disponibilidad."
    ),
    (
        "⚠️ Las citas dependen exclusivamente de los cupos disponibles en la "
        "plataforma de la PNP."
    ),
)

HASHTAG_GROUPS = (
    "#LunasPolarizadas #CitasPNP #PeritajeVehicular #PermisoLunasPolarizadas #Perú",
    "#LunasOscurecidas #LunasPolarizadas #CitaPNP #PeritajePNP #Perú",
    "#PermisoLunasPolarizadas #PeritajeVehicular #CitasPNP #AutosPerú #WhatsApp",
    "#LunasPolarizadasPerú #CitasPeritaje #PNP #TrámitesPerú #Vehículos",
    "#PeritajeLunasPolarizadas #CuposPNP #PermisoLunas #Lima #Perú",
    "#CitasPNP #LunasOscurecidas #PeritajeVehicular #ConductoresPerú #WhatsApp",
)


def generate_tiktok_publication(
    publication_date: date,
    *,
    public_whatsapp: str,
) -> str:
    combination_count = prod(
        (
            len(TITLES),
            len(OPENINGS),
            len(SERVICE_EXPLANATIONS),
            len(CALLS_TO_ACTION),
            len(DISCLAIMERS),
            len(HASHTAG_GROUPS),
        )
    )
    index = (publication_date.toordinal() * 7919 + 104729) % combination_count
    title, index = _select(TITLES, index)
    opening, index = _select(OPENINGS, index)
    explanation, index = _select(SERVICE_EXPLANATIONS, index)
    call_to_action, index = _select(CALLS_TO_ACTION, index)
    disclaimer, index = _select(DISCLAIMERS, index)
    hashtags, _ = _select(HASHTAG_GROUPS, index)
    phone = _emoji_phone(public_whatsapp)

    return "\n\n".join(
        (
            f"Título del video:\n{title}",
            f"Descripción:\n\n{opening}\n\n{explanation}",
            (
                "🚗 Monitoreo de disponibilidad\n"
                "📅 Intento de reserva de citas\n"
                "✅ Atención rápida por WhatsApp\n"
                "💰 Servicio: S/40 por trámite\n"
                "💳 Pagas solo cuando la cita ya fue obtenida."
            ),
            f"📲 {call_to_action}\n\nEscríbenos por WhatsApp:\n{phone}",
            disclaimer,
            hashtags,
        )
    )


def _select(options: tuple[str, ...], index: int) -> tuple[str, int]:
    return options[index % len(options)], index // len(options)


def _emoji_phone(value: str) -> str:
    digits = "".join(character for character in value if character.isdigit())
    local_digits = digits[-9:]
    if len(local_digits) != 9:
        raise ValueError("El WhatsApp público debe contener nueve dígitos locales.")
    emoji_digits = {
        "0": "0️⃣",
        "1": "1️⃣",
        "2": "2️⃣",
        "3": "3️⃣",
        "4": "4️⃣",
        "5": "5️⃣",
        "6": "6️⃣",
        "7": "7️⃣",
        "8": "8️⃣",
        "9": "9️⃣",
    }
    groups = (
        local_digits[0:3],
        local_digits[3:6],
        local_digits[6:9],
    )
    return " • ".join("".join(emoji_digits[digit] for digit in group) for group in groups)


__all__ = ["generate_tiktok_publication"]
