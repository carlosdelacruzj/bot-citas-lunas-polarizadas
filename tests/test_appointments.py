from __future__ import annotations

import unittest

from appointment_bot.reservation_engine.appointments import (
    _is_real_appointment_option,
)
from appointment_bot.reservation_engine.stages import appointment_stage_result


class AppointmentFlowTests(unittest.TestCase):
    def test_missing_stage_is_unknown(self) -> None:
        result = appointment_stage_result([])
        self.assertIsNotNone(result)
        self.assertEqual(result.status, "unknown")

    def test_disabled_or_empty_options_are_not_available(self) -> None:
        self.assertFalse(
            _is_real_appointment_option(
                {"text": "10:00", "value": "10", "disabled": True, "hidden": False}
            )
        )
        self.assertFalse(
            _is_real_appointment_option(
                {"text": "Información", "value": "", "disabled": False, "hidden": False}
            )
        )

if __name__ == "__main__":
    unittest.main()
