from __future__ import annotations

import tempfile
import unittest
from contextlib import contextmanager
from pathlib import Path
from typing import Any

from appointment_bot.core.models import ServiceOrderCreateResult
from appointment_bot.services.application.create_service_order import (
    CreateServiceOrder,
    CreateServiceOrderRequest,
)
from tests.helpers import database_connection, make_settings


class CreateServiceOrderUseCaseTests(unittest.TestCase):
    def test_forwards_one_request_through_the_supplied_unit_of_work(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            settings = make_settings(Path(directory))
            connection = object()
            observed: dict[str, Any] = {}

            @contextmanager
            def unit_of_work(received_settings, connection_override):
                observed["uow"] = (received_settings, connection_override)
                yield connection

            def repository(**values):
                observed["repository"] = values
                return ServiceOrderCreateResult(
                    order_id="order-12345678",
                    applicant_id="applicant-12345678",
                    portal_account_id="portal-12345678",
                    contact_id=None,
                )

            use_case = CreateServiceOrder(
                repository=repository,
                unit_of_work_factory=unit_of_work,
            )
            request = CreateServiceOrderRequest(
                document_number="12345678",
                password="secret",
                contact_name="Cliente",
                contact_source="whatsapp",
            )

            result = use_case.execute(request, settings=settings)

            self.assertEqual(result.order_id, "order-12345678")
            self.assertEqual(observed["uow"], (settings, None))
            persisted = observed["repository"]
            self.assertIs(persisted["settings"], settings)
            self.assertIs(persisted["_connection_override"], connection)
            self.assertEqual(persisted["document_number"], "12345678")
            self.assertEqual(persisted["password"], "secret")

    def test_rolls_back_all_creation_rows_when_repository_fails(self) -> None:
        from appointment_bot.db.service_order_repository import persist_service_order

        with tempfile.TemporaryDirectory() as directory:
            settings = make_settings(Path(directory))

            def failing_repository(**values):
                persist_service_order(**values)
                raise RuntimeError("forced failure after persistence")

            use_case = CreateServiceOrder(repository=failing_repository)
            request = CreateServiceOrderRequest(
                document_number="12345678",
                password="secret",
                contact_name="Cliente",
                contact_source="whatsapp",
            )

            with self.assertRaisesRegex(RuntimeError, "forced failure"):
                use_case.execute(request, settings=settings)

            with database_connection(settings) as connection:
                counts = {
                    table: connection.execute(f"SELECT COUNT(*) AS total FROM {table}").fetchone()[
                        "total"
                    ]
                    for table in (
                        "applicants",
                        "portal_accounts",
                        "service_orders",
                        "order_state",
                    )
                }
            self.assertEqual(counts, {table: 0 for table in counts})

    def test_request_representation_never_exposes_password(self) -> None:
        request = CreateServiceOrderRequest(document_number="12345678", password="secret")

        self.assertNotIn("secret", repr(request))


if __name__ == "__main__":
    unittest.main()
