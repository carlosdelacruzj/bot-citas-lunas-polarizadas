from __future__ import annotations

import sys

from appointment_bot.worker import windows_runtime as _impl

sys.modules[__name__] = _impl
