from appointment_bot.flows.appointments import AvailabilityResult


def notify_result(result: AvailabilityResult) -> None:
    print(f"[{result.status.upper()}] {result.message}")


def notify_error(error: Exception) -> None:
    message = f"[ERROR] {error}"
    print(message.encode("ascii", errors="replace").decode("ascii"))
