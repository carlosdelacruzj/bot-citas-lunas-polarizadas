from psycopg import Connection


def create_whatsapp_delivery_schema(connection: Connection) -> None:
    connection.execute("""
        ALTER TABLE whatsapp_automation_jobs
        ADD COLUMN IF NOT EXISTS recovery_components jsonb,
        ADD COLUMN IF NOT EXISTS source_job_key text
            REFERENCES whatsapp_automation_jobs(job_key)
    """)
    connection.execute("""
        CREATE TABLE IF NOT EXISTS whatsapp_delivery_attempts (
            attempt_id text PRIMARY KEY,
            job_key text REFERENCES whatsapp_automation_jobs(job_key),
            message_id text,
            recipient_masked text NOT NULL,
            manifest jsonb NOT NULL DEFAULT '[]'::jsonb,
            finished_at timestamptz,
            created_at timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP
        )
    """)
    connection.execute("""
        CREATE INDEX IF NOT EXISTS idx_whatsapp_delivery_attempt_job
        ON whatsapp_delivery_attempts(job_key, created_at DESC)
    """)
    connection.execute("""
        CREATE TABLE IF NOT EXISTS whatsapp_delivery_events (
            event_id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
            attempt_id text NOT NULL REFERENCES whatsapp_delivery_attempts(attempt_id),
            component_key text NOT NULL,
            state text NOT NULL CHECK (state IN ('not_attempted', 'uncertain', 'confirmed')),
            evidence_path text,
            outgoing_id text,
            created_at timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP
        )
    """)
    connection.execute("""
        CREATE INDEX IF NOT EXISTS idx_whatsapp_delivery_event_attempt
        ON whatsapp_delivery_events(attempt_id, event_id DESC)
    """)
    connection.execute("""
        CREATE OR REPLACE FUNCTION reject_whatsapp_delivery_event_mutation()
        RETURNS trigger LANGUAGE plpgsql AS $$
        BEGIN
            RAISE EXCEPTION 'WhatsApp delivery events are append-only';
        END;
        $$
    """)
    connection.execute("""
        DROP TRIGGER IF EXISTS whatsapp_delivery_event_immutable ON whatsapp_delivery_events
    """)
    connection.execute("""
        CREATE TRIGGER whatsapp_delivery_event_immutable
        BEFORE UPDATE OR DELETE ON whatsapp_delivery_events
        FOR EACH ROW EXECUTE FUNCTION reject_whatsapp_delivery_event_mutation()
    """)


def v76_to_v77(connection: Connection) -> None:
    create_whatsapp_delivery_schema(connection)
    connection.execute("UPDATE schema_version SET version = 77 WHERE id = 1")
