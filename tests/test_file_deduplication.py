from __future__ import annotations

import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from appointment_bot.db.whatsapp_followup_messages import _copy_followup_documents
from appointment_bot.db.whatsapp_messages import _copy_payment_attachment
from appointment_bot.utils.file_deduplication import (
    copy_deduplicated_file,
    deduplicate_files_in_place,
)


class FileDeduplicationTests(unittest.TestCase):
    def test_copies_share_immutable_canonical_content(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "source.pdf"
            source.write_bytes(b"original")
            store = root / "store"

            first = copy_deduplicated_file(
                source,
                root / "package-a" / "document.pdf",
                content_store=store,
            )
            second = copy_deduplicated_file(
                source,
                root / "package-b" / "document.pdf",
                content_store=store,
            )
            source.write_bytes(b"updated")

            self.assertTrue(os.path.samefile(first, second))
            self.assertEqual(first.read_bytes(), b"original")
            self.assertEqual(second.read_bytes(), b"original")

    def test_existing_paths_are_preserved_while_content_is_deduplicated(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            first = root / "package-a.pdf"
            second = root / "package-b.pdf"
            first.write_bytes(b"same-content")
            second.write_bytes(b"same-content")

            result = deduplicate_files_in_place(
                [first, second],
                content_store=root / "store",
            )

            self.assertEqual(result["inspected"], 2)
            self.assertEqual(result["linked"], 2)
            self.assertTrue(first.is_file())
            self.assertTrue(second.is_file())
            self.assertTrue(os.path.samefile(first, second))

    def test_copy_falls_back_when_hard_links_are_unavailable(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "source.pdf"
            destination = root / "package" / "document.pdf"
            source.write_bytes(b"portable-copy")

            with patch(
                "appointment_bot.utils.file_deduplication.os.link",
                side_effect=OSError("unsupported"),
            ):
                copy_deduplicated_file(
                    source,
                    destination,
                    content_store=root / "store",
                )

            self.assertEqual(destination.read_bytes(), b"portable-copy")
            self.assertFalse(os.path.samefile(source, destination))

    def test_relative_destination_contract_is_preserved(self) -> None:
        with tempfile.TemporaryDirectory(dir=Path.cwd()) as directory:
            root = Path(directory)
            source = root / "source.pdf"
            source.write_bytes(b"relative-path")
            destination = Path(os.path.relpath(root / "package.pdf", Path.cwd()))

            returned = copy_deduplicated_file(
                source,
                destination,
                content_store=root / "store",
            )

            self.assertEqual(returned, destination)
            self.assertFalse(returned.is_absolute())
            self.assertTrue(destination.is_file())

    def test_payment_packages_share_content_without_sharing_the_source(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            config_root = root / "payment"
            config_root.mkdir()
            image = config_root / "payment.jpeg"
            image.write_bytes(b"payment-image")
            config = config_root / "payment-details.json"
            config.write_text(
                json.dumps(
                    {
                        "phone": "999999999",
                        "account_name": "TEST",
                        "image": image.name,
                    }
                ),
                encoding="utf-8",
            )
            outgoing = root / "outgoing"

            with (
                patch(
                    "appointment_bot.db.whatsapp_messages.PAYMENT_CONFIG_PATH",
                    config,
                ),
                patch(
                    "appointment_bot.db.whatsapp_messages.OUTGOING_ROOT",
                    outgoing,
                ),
                patch(
                    "appointment_bot.utils.file_deduplication.DEFAULT_CONTENT_STORE",
                    root / "unused-default",
                ),
            ):
                first = _copy_payment_attachment("message-a")
                second = _copy_payment_attachment("message-b")

            self.assertTrue(os.path.samefile(first, second))
            self.assertFalse(os.path.samefile(first, image))
            self.assertEqual(first.read_bytes(), image.read_bytes())

    def test_followup_packages_reference_the_original_document(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            document = root / "requirements.pdf"
            document.write_bytes(b"followup-document")
            first = Path(_copy_followup_documents("message-a", [document])[0])
            second = Path(_copy_followup_documents("message-b", [document])[0])

            self.assertEqual(first, document.resolve())
            self.assertEqual(second, document.resolve())
            self.assertEqual(first.read_bytes(), document.read_bytes())


if __name__ == "__main__":
    unittest.main()
