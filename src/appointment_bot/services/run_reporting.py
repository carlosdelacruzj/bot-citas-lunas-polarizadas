from __future__ import annotations

import sys

from appointment_bot.reports import run_reporting as _impl

sys.modules[__name__] = _impl
