from __future__ import annotations

import sys

from appointment_bot.worker import state_callbacks as _impl

sys.modules[__name__] = _impl
