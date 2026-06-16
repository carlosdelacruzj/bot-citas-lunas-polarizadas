from __future__ import annotations

import tempfile
import unittest
from datetime import timedelta
from pathlib import Path

from appointment_bot.services.runtime import LockBusyError, ProcessLock


class ProcessLockTests(unittest.TestCase):
    def test_second_lock_cannot_acquire_and_owner_file_is_not_deleted(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "worker.lock"
            first = ProcessLock(path, stale_after=timedelta(minutes=1))
            second = ProcessLock(path, stale_after=timedelta(minutes=1))

            with first:
                with self.assertRaises(LockBusyError):
                    second.__enter__()
                self.assertIsNotNone(first.owner_token)

            self.assertTrue(path.exists())
            self.assertIn("owner_token=", path.read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
