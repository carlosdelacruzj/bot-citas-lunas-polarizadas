from psycopg import Connection


def create_observer_rotation_schema(connection: Connection) -> None:
    connection.execute("""
        CREATE TABLE IF NOT EXISTS observer_rotation_control (
            id integer PRIMARY KEY CHECK (id = 1),
            next_allowed_at timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP
        )
    """)
    connection.execute("""
        INSERT INTO observer_rotation_control(id) VALUES (1) ON CONFLICT DO NOTHING
    """)
    connection.execute("""
        CREATE TABLE IF NOT EXISTS observer_account_state (
            portal_account_id text PRIMARY KEY REFERENCES portal_accounts(portal_account_id)
                ON DELETE CASCADE,
            last_observed_at timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP,
            next_allowed_at timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP,
            blocked_until timestamptz,
            blocked_at timestamptz,
            last_status text NOT NULL DEFAULT 'started',
            verified_at timestamptz
        )
    """)


def v75_to_v76(connection: Connection) -> None:
    create_observer_rotation_schema(connection)
    connection.execute("UPDATE schema_version SET version = 76 WHERE id = 1")
