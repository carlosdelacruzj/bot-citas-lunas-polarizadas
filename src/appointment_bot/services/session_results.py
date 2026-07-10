from __future__ import annotations

import sys

from appointment_bot.reservation_engine import results as _impl

sys.modules[__name__] = _impl
