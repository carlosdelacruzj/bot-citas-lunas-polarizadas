from __future__ import annotations

from psycopg import Connection

from appointment_bot.db.migration_steps.finance_schema import _create_payment_receipt_triggers


def v73_to_v74(connection: Connection) -> None:
    inconsistent_receipts = connection.execute(
        """
            SELECT COUNT(*) AS count
            FROM payment_receipts receipt
            LEFT JOIN payments payment
              ON payment.payment_id = receipt.payment_id
             AND payment.order_id = receipt.order_id
            WHERE payment.payment_id IS NULL
            """
    ).fetchone()
    if inconsistent_receipts is None or int(inconsistent_receipts["count"] or 0):
        raise RuntimeError(
            "Database schema v74 migration found payment_receipts that do not "
            "belong to the referenced payment and order."
        )
    connection.execute(
        """
            ALTER TABLE payments
            ADD CONSTRAINT uq_payments_payment_order UNIQUE (payment_id, order_id)
            """
    )
    connection.execute(
        """
            ALTER TABLE payment_receipts
            ADD COLUMN corrects_receipt_id text,
            ADD COLUMN correction_reason text,
            DROP CONSTRAINT payment_receipts_payment_id_fkey,
            DROP CONSTRAINT payment_receipts_order_id_fkey,
            DROP CONSTRAINT payment_receipts_amount_check,
            ADD CONSTRAINT uq_payment_receipts_identity_payment_order
                UNIQUE (receipt_id, payment_id, order_id),
            ADD CONSTRAINT fk_payment_receipts_payment_order
                FOREIGN KEY (payment_id, order_id)
                REFERENCES payments(payment_id, order_id) ON DELETE RESTRICT,
            ADD CONSTRAINT fk_payment_receipts_correction_original
                FOREIGN KEY (corrects_receipt_id, payment_id, order_id)
                REFERENCES payment_receipts(receipt_id, payment_id, order_id)
                ON DELETE RESTRICT,
            ADD CONSTRAINT ck_payment_receipts_movement CHECK (
                (
                    source <> 'payment_correction'
                    AND amount > 0
                    AND corrects_receipt_id IS NULL
                    AND correction_reason IS NULL
                ) OR (
                    source = 'payment_correction'
                    AND amount < 0
                    AND corrects_receipt_id IS NOT NULL
                    AND NULLIF(BTRIM(correction_reason), '') IS NOT NULL
                    AND NULLIF(BTRIM(actor), '') IS NOT NULL
                    AND corrects_receipt_id <> receipt_id
                )
            )
            """
    )
    connection.execute(
        """
            CREATE INDEX idx_payment_receipts_order_received
            ON payment_receipts(order_id, received_at DESC)
            """
    )
    connection.execute(
        """
            CREATE INDEX idx_payment_receipts_payment_order
            ON payment_receipts(payment_id, order_id)
            """
    )
    connection.execute(
        """
            CREATE INDEX idx_payment_receipts_correction_original
            ON payment_receipts(corrects_receipt_id, payment_id, order_id)
            WHERE corrects_receipt_id IS NOT NULL
            """
    )
    _create_payment_receipt_triggers(connection)
    connection.execute(
        "UPDATE schema_version SET version = %s WHERE id = 1",
        (74,),
    )
