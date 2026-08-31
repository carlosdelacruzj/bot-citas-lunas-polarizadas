from __future__ import annotations

import unittest
from unittest.mock import patch

from appointment_bot.reservation_engine.appointments import AppointmentWorkflowUnavailable
from appointment_bot.reservation_engine.programs import click_program_action


def _row(
    index: int,
    *,
    status: str,
    expediente: str = "",
    placa: str = "",
) -> dict[str, object]:
    return {
        "action_index": index,
        "status": status,
        "expediente": expediente,
        "placa": placa,
    }


class _Button:
    def __init__(self, index: int) -> None:
        self.index = index
        self.scrolled = False
        self.clicked = False

    def scroll_into_view_if_needed(self, *, timeout: int) -> None:
        self.scrolled = True

    def click(self, *, timeout: int) -> None:
        self.clicked = True


class _ButtonCollection:
    def __init__(self, count: int) -> None:
        self.buttons = [_Button(index) for index in range(count)]

    @property
    def first(self) -> _Button:
        return self.buttons[0]

    def count(self) -> int:
        return len(self.buttons)

    def nth(self, index: int) -> _Button:
        return self.buttons[index]


class _Page:
    url = "https://example.invalid/programs"

    def __init__(self, button_count: int) -> None:
        self.actions = _ButtonCollection(button_count)

    def locator(self, selector: str) -> _ButtonCollection:
        return self.actions


class ProgramSelectionTests(unittest.TestCase):
    def _select(
        self,
        rows: list[dict[str, object]],
        *,
        button_count: int | None = None,
        program_expediente: str | None = None,
        program_plate: str | None = None,
    ) -> tuple[_Page, list[dict], list[dict]]:
        page = _Page(len(rows) if button_count is None else button_count)
        decisions: list[dict] = []
        selections: list[dict] = []
        with (
            patch(
                "appointment_bot.reservation_engine.programs._read_program_action_rows",
                return_value=rows,
            ),
            patch("appointment_bot.reservation_engine.programs._wait_for_program_detail"),
        ):
            click_program_action(
                page,
                on_multiple_programs=decisions.append,
                on_program_selected=selections.append,
                program_expediente=program_expediente,
                program_plate=program_plate,
            )
        return page, decisions, selections

    def _assert_blocked(
        self,
        rows: list[dict[str, object]],
        expected_decision: str | None,
        *,
        button_count: int | None = None,
        program_expediente: str | None = None,
        program_plate: str | None = None,
    ) -> tuple[_Page, list[dict]]:
        page = _Page(len(rows) if button_count is None else button_count)
        decisions: list[dict] = []
        selections: list[dict] = []
        with (
            patch(
                "appointment_bot.reservation_engine.programs._read_program_action_rows",
                return_value=rows,
            ),
            patch("appointment_bot.reservation_engine.programs._wait_for_program_detail"),
            self.assertRaises(AppointmentWorkflowUnavailable),
        ):
            click_program_action(
                page,
                on_multiple_programs=decisions.append,
                on_program_selected=selections.append,
                program_expediente=program_expediente,
                program_plate=program_plate,
            )
        self.assertFalse(any(button.scrolled for button in page.actions.buttons))
        self.assertFalse(any(button.clicked for button in page.actions.buttons))
        self.assertEqual(selections, [])
        if expected_decision is not None:
            self.assertEqual(decisions[-1]["decision"], expected_decision)
        return page, decisions

    def test_single_pending_program_is_selected(self) -> None:
        row = _row(0, status=" PENDIENTE ", expediente="EXP-1")

        page, decisions, selections = self._select([row])

        self.assertTrue(page.actions.buttons[0].clicked)
        self.assertEqual(decisions, [])
        self.assertEqual(selections, [row])

    def test_cancelled_and_pending_selects_only_pending(self) -> None:
        rows = [
            _row(0, status="CANCELADO", expediente="EXP-0"),
            _row(1, status="PENDIENTE", expediente="EXP-1"),
        ]

        page, decisions, selections = self._select(rows)

        self.assertFalse(page.actions.buttons[0].clicked)
        self.assertTrue(page.actions.buttons[1].clicked)
        self.assertEqual(decisions[-1]["decision"], "single_pending_selected")
        self.assertEqual(decisions[-1]["pending_count"], 1)
        self.assertEqual(selections, [rows[1]])

    def test_multiple_pending_without_target_blocks(self) -> None:
        rows = [
            _row(0, status="PENDIENTE", expediente="EXP-1"),
            _row(1, status="PENDIENTE", expediente="EXP-2"),
        ]

        _, decisions = self._assert_blocked(rows, "multiple_pending_blocked")

        self.assertNotIn("selected_row", decisions[-1])
        self.assertEqual(decisions[-1]["pending_count"], 2)

    def test_no_pending_blocks_even_with_one_action(self) -> None:
        self._assert_blocked(
            [_row(0, status="CANCELADO", expediente="EXP-1")],
            "no_pending_blocked",
        )

    def test_unknown_status_is_not_pending(self) -> None:
        self._assert_blocked(
            [_row(0, status="", expediente="EXP-1")],
            "no_pending_blocked",
        )

    def test_target_by_expediente_selects_exact_pending_match(self) -> None:
        rows = [
            _row(0, status="PENDIENTE", expediente="EXP-1"),
            _row(1, status="PENDIENTE", expediente="EXP-2"),
        ]

        page, decisions, selections = self._select(
            rows,
            program_expediente=" exp-2 ",
        )

        self.assertFalse(page.actions.buttons[0].clicked)
        self.assertTrue(page.actions.buttons[1].clicked)
        self.assertEqual(decisions[-1]["decision"], "target_selected")
        self.assertEqual(selections, [rows[1]])

    def test_target_by_expediente_counts_only_pending_matches(self) -> None:
        rows = [
            _row(0, status="CANCELADO", expediente="EXP-1"),
            _row(1, status="PENDIENTE", expediente="EXP-1"),
        ]

        page, decisions, selections = self._select(
            rows,
            program_expediente="EXP-1",
        )

        self.assertFalse(page.actions.buttons[0].clicked)
        self.assertTrue(page.actions.buttons[1].clicked)
        self.assertEqual(decisions[-1]["decision"], "target_selected")
        self.assertEqual(selections, [rows[1]])

    def test_repeated_pending_expediente_blocks(self) -> None:
        rows = [
            _row(0, status="PENDIENTE", expediente="EXP-1", placa="ABC-123"),
            _row(1, status="PENDIENTE", expediente="EXP-1", placa="XYZ-789"),
        ]

        self._assert_blocked(
            rows,
            "target_ambiguous",
            program_expediente="EXP-1",
        )

    def test_target_by_plate_selects_exact_pending_match(self) -> None:
        rows = [
            _row(0, status="CANCELADO", placa="OLD-111"),
            _row(1, status="PENDIENTE", placa="ABC 123"),
        ]

        page, decisions, _ = self._select(rows, program_plate="abc123")

        self.assertTrue(page.actions.buttons[1].clicked)
        self.assertEqual(decisions[-1]["decision"], "target_selected")

    def test_repeated_pending_plate_blocks(self) -> None:
        rows = [
            _row(0, status="PENDIENTE", expediente="EXP-1", placa="ABC-123"),
            _row(1, status="PENDIENTE", expediente="EXP-2", placa="ABC-123"),
        ]

        _, decisions = self._assert_blocked(
            rows,
            "target_ambiguous",
            program_plate="abc123",
        )

        self.assertEqual(len(decisions[-1]["matching_rows"]), 2)

    def test_repeated_plate_selects_if_only_one_match_is_pending(self) -> None:
        rows = [
            _row(0, status="CANCELADO", expediente="EXP-1", placa="ABC-123"),
            _row(1, status="PENDIENTE", expediente="EXP-2", placa="ABC-123"),
        ]

        page, decisions, selections = self._select(
            rows,
            program_plate="abc123",
        )

        self.assertFalse(page.actions.buttons[0].clicked)
        self.assertTrue(page.actions.buttons[1].clicked)
        self.assertEqual(decisions[-1]["decision"], "target_selected")
        self.assertEqual(selections, [rows[1]])

    def test_expediente_and_plate_can_disambiguate_repeated_plate(self) -> None:
        rows = [
            _row(0, status="PENDIENTE", expediente="EXP-1", placa="ABC-123"),
            _row(1, status="PENDIENTE", expediente="EXP-2", placa="ABC-123"),
        ]

        page, _, selections = self._select(
            rows,
            program_expediente="EXP-2",
            program_plate="ABC-123",
        )

        self.assertTrue(page.actions.buttons[1].clicked)
        self.assertEqual(selections, [rows[1]])

    def test_target_not_pending_blocks(self) -> None:
        self._assert_blocked(
            [_row(0, status="ATENDIDO", expediente="EXP-1")],
            "target_not_pending",
            program_expediente="EXP-1",
        )

    def test_target_not_found_blocks(self) -> None:
        self._assert_blocked(
            [_row(0, status="PENDIENTE", expediente="EXP-1")],
            "target_not_found",
            program_expediente="EXP-2",
        )

    def test_incomplete_row_read_blocks(self) -> None:
        self._assert_blocked(
            [_row(0, status="PENDIENTE", expediente="EXP-1")],
            "program_rows_unavailable",
            button_count=2,
        )

    def test_duplicate_action_index_blocks(self) -> None:
        rows = [
            _row(0, status="PENDIENTE", expediente="EXP-1"),
            _row(0, status="CANCELADO", expediente="EXP-2"),
        ]

        self._assert_blocked(rows, "program_rows_unavailable")

    def test_no_action_button_blocks_without_decision_callback(self) -> None:
        page, decisions = self._assert_blocked([], None)

        self.assertEqual(page.actions.buttons, [])
        self.assertEqual(decisions, [])


if __name__ == "__main__":
    unittest.main()
