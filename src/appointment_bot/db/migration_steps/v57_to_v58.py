from __future__ import annotations

from psycopg import Connection


def v57_to_v58(connection: Connection) -> None:
    connection.execute(
        """
            ALTER TABLE whatsapp_automation_jobs
            ADD COLUMN review_resolution text CHECK (
                review_resolution IS NULL OR review_resolution IN (
                    'confirmed_complete',
                    'completed_missing',
                    'dismissed'
                )
            ),
            ADD COLUMN review_note text,
            ADD COLUMN reviewed_at timestamptz,
            ADD COLUMN reviewed_by text,
            ADD CONSTRAINT ck_whatsapp_automation_job_review CHECK (
                (
                    review_resolution IS NULL
                    AND review_note IS NULL
                    AND reviewed_at IS NULL
                    AND reviewed_by IS NULL
                )
                OR (
                    review_resolution IS NOT NULL
                    AND reviewed_at IS NOT NULL
                    AND reviewed_by IS NOT NULL
                )
            )
            """
    )
    connection.execute(
        "UPDATE schema_version SET version = %s WHERE id = 1",
        (58,),
    )
