from __future__ import annotations


def format_confirmed_reservation_message(
    *,
    person_name: object = None,
    date: object = None,
    hour: object = None,
    site: object = None,
) -> str:
    name = str(person_name or "").strip()
    heading = (
        f"Estimado/a {name}, su cita ha sido reservada con exito."
        if name
        else "Su cita ha sido reservada con exito."
    )
    lines = [heading]
    for label, value in (("Fecha", date), ("Hora", hour), ("Sede", site)):
        text = str(value or "").strip()
        if text:
            lines.append(f"{label}: {text}")
    if len(lines) == 1:
        return heading
    return f"{heading}\n\n" + "\n".join(lines[1:])


__all__ = ["format_confirmed_reservation_message"]
