from __future__ import annotations

import unittest
from unittest.mock import patch

from appointment_bot.services.api.finance_routes import (
    reconcile_payment_amount_payload,
    upsert_finance_month_closure_payload,
)


class FinanceActorTests(unittest.TestCase):
    @patch("appointment_bot.services.api.finance_routes.reconcile_payment_amount")
    def test_reconciliation_uses_authenticated_actor_not_body(self, reconcile) -> None:
        reconcile.return_value = {"payment_id": "payment-1"}

        status, _payload = reconcile_payment_amount_payload(
            "payment-1",
            {
                "resolution_type": "discount",
                "reason": "Acuerdo comercial",
                "reconciled_by": "forged-owner",
            },
            requested_by="dashboard:local",
        )

        self.assertEqual(status, 200)
        self.assertEqual(reconcile.call_args.kwargs["reconciled_by"], "dashboard:local")

    @patch("appointment_bot.services.api.finance_routes.upsert_finance_month_closure")
    def test_month_closure_uses_authenticated_actor_not_body(self, upsert) -> None:
        upsert.return_value = {"month": "2026-08"}

        status, _payload = upsert_finance_month_closure_payload(
            {
                "month": "2026-08",
                "opening_prepaid_balance": "10",
                "closing_prepaid_balance": "10",
                "status": "reconciled",
                "reconciled_by": "forged-owner",
            },
            requested_by="api:sha256:trusted",
        )

        self.assertEqual(status, 200)
        values = upsert.call_args.args[2]
        self.assertEqual(values["reconciled_by"], "api:sha256:trusted")


if __name__ == "__main__":
    unittest.main()
