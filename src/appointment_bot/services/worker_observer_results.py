from __future__ import annotations

import sys

from appointment_bot.worker import observer_results as _impl

sys.modules[__name__] = _impl
