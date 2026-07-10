from __future__ import annotations

import sys

from appointment_bot.worker import deferred_reports as _impl

sys.modules[__name__] = _impl
