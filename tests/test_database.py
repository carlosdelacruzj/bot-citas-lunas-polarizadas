from __future__ import annotations

import sqlite3
import tempfile
import unittest
from contextlib import closing
from pathlib import Path

from appointment_bot.services.database import (
    SCHEMA_VERSION,
    get_worker_state,
    init_database,
)
from tests.helpers import make_settings


class DatabaseMigrationTests(unittest.TestCase):
    def test_existing_database_gets_owner_column_and_schema_version(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            settings = make_settings(root)
            settings.database_path.parent.mkdir(parents=True)
            with closing(sqlite3.connect(settings.database_path)) as connection:
                connection.executescript(
                    """
                    CREATE TABLE worker_state (
                        id INTEGER PRIMARY KEY,
                        phase TEXT NOT NULL,
                        paused INTEGER NOT NULL,
                        current_client_id TEXT,
                        masked_account TEXT,
                        session_started_at TEXT,
                        last_check_at TEXT,
                        next_check_at TEXT,
                        confirmed_reservations INTEGER NOT NULL,
                        consecutive_errors INTEGER NOT NULL,
                        last_error TEXT,
                        availability_signature TEXT,
                        updated_at TEXT NOT NULL
                    );
                    INSERT INTO worker_state (
                        id, phase, paused, confirmed_reservations,
                        consecutive_errors, updated_at
                    ) VALUES (1, 'stopped', 0, 0, 0, CURRENT_TIMESTAMP);
                    PRAGMA user_version = 1;
                    """
                )

            init_database(settings)

            with closing(sqlite3.connect(settings.database_path)) as connection:
                version = connection.execute("PRAGMA user_version").fetchone()[0]
                columns = {row[1] for row in connection.execute("PRAGMA table_info(worker_state)")}
            self.assertEqual(version, SCHEMA_VERSION)
            self.assertIn("owner_token", columns)
            self.assertIsNone(get_worker_state(settings).owner_token)


if __name__ == "__main__":
    unittest.main()
