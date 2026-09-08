from __future__ import annotations

from psycopg import Connection


def v70_to_v71(connection: Connection) -> None:
    connection.execute(
        """
            ALTER TABLE service_orders
            ADD COLUMN service_package text NOT NULL DEFAULT 'standard',
            ADD COLUMN official_fee_amount numeric(12, 2) NOT NULL DEFAULT 0,
            ADD COLUMN initial_payment_amount numeric(12, 2) NOT NULL DEFAULT 0
            """
    )
    connection.execute(
        """
            UPDATE service_orders
            SET service_package = CASE
                    WHEN service_type = 'selected_weekday' THEN 'restricted'
                    WHEN service_type = 'custom' THEN 'custom'
                    ELSE 'standard'
                END
            """
    )
    connection.execute(
        """
            ALTER TABLE service_orders
            ADD CONSTRAINT ck_service_orders_service_package CHECK (
                service_package IN ('standard', 'restricted', 'integral', 'custom')
            ),
            ADD CONSTRAINT ck_service_orders_official_fee CHECK (
                official_fee_amount >= 0 AND official_fee_amount <= reservation_price
            ),
            ADD CONSTRAINT ck_service_orders_initial_payment CHECK (
                initial_payment_amount >= 0 AND initial_payment_amount <= reservation_price
            )
            """
    )
    connection.execute(
        """
            INSERT INTO finance_categories (
                category_code, display_name, cost_behavior, created_at, updated_at
            )
            VALUES (
                'government_fee', 'Tasas oficiales por cuenta del cliente',
                'variable', CURRENT_TIMESTAMP, CURRENT_TIMESTAMP
            )
            ON CONFLICT (category_code) DO UPDATE SET
                display_name = excluded.display_name,
                cost_behavior = excluded.cost_behavior,
                active = true,
                updated_at = excluded.updated_at
            """
    )
    connection.execute(
        """
            CREATE TABLE payment_receipts (
                receipt_id text PRIMARY KEY,
                payment_id text NOT NULL REFERENCES payments(payment_id) ON DELETE CASCADE,
                order_id text NOT NULL REFERENCES service_orders(order_id) ON DELETE CASCADE,
                amount numeric(12, 2) NOT NULL CHECK (amount > 0),
                received_at timestamptz NOT NULL,
                source text NOT NULL,
                actor text,
                created_at timestamptz NOT NULL
            )
            """
    )
    connection.execute(
        """
            CREATE INDEX idx_payment_receipts_received
            ON payment_receipts(received_at, order_id)
            """
    )
    connection.execute(
        """
            INSERT INTO payment_receipts (
                receipt_id, payment_id, order_id, amount, received_at, source, created_at
            )
            SELECT 'legacy:' || payment_id, payment_id, order_id, amount_paid,
                   COALESCE(paid_at, updated_at, created_at), 'historical_backfill',
                   CURRENT_TIMESTAMP
            FROM payments
            WHERE amount_paid > 0
            ON CONFLICT(receipt_id) DO NOTHING
            """
    )
    connection.execute(
        "UPDATE schema_version SET version = %s WHERE id = 1",
        (71,),
    )
