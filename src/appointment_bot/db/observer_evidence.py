from __future__ import annotations

from appointment_bot.configuration.runtime import RuntimeSettings
from appointment_bot.db.common import _connection, _database_url


def load_observer_evidence_progress(settings: RuntimeSettings, site: str) -> dict:
    with _connection(_database_url(settings)) as connection:
        row = connection.execute("""
            SELECT details_json -> 'observer_evidence_collection' AS progress
            FROM runs
            WHERE started_at >= (date_trunc('day', CURRENT_TIMESTAMP
                AT TIME ZONE 'America/Lima') AT TIME ZONE 'America/Lima')
              AND details_json -> 'observer_evidence_collection' ->> 'site' = %s
            ORDER BY finished_at DESC LIMIT 1
        """, (site,)).fetchone()
    progress = dict(row["progress"]) if row else {"site": site, "captured": [], "visits": {}}
    progress.update(session_queries=0, session_captures=[])
    return progress
