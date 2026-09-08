from __future__ import annotations

from psycopg import Connection


def v72_to_v73(connection: Connection) -> None:
    connection.execute(
        """
            UPDATE service_orders
            SET service_type = 'standard'
            WHERE service_package = 'integral'
              AND service_type <> 'standard'
              AND status = 'paid'
              AND charge_required = true
              AND reservation_price = 160.00
              AND official_fee_amount = 71.40
              AND initial_payment_amount = 80.00
            """
    )
    connection.execute(
        """
            ALTER TABLE service_orders
            ADD CONSTRAINT ck_service_orders_integral_terms CHECK (
                service_package <> 'integral' OR (
                    charge_required = true
                    AND service_type = 'standard'
                    AND reservation_price = 160.00
                    AND official_fee_amount = 71.40
                    AND initial_payment_amount = 80.00
                    AND (
                        status <> 'archived'
                        OR COALESCE(closure_reason = 'uncollectible', false)
                    )
                )
            )
            """
    )
    connection.execute(
        "UPDATE schema_version SET version = %s WHERE id = 1",
        (73,),
    )
