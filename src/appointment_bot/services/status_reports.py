from __future__ import annotations

import sys

from appointment_bot.reports import status as _impl

sys.modules[__name__] = _impl
