from __future__ import annotations

import sys

from appointment_bot.worker import error_policy as _impl

sys.modules[__name__] = _impl
