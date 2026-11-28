"""tools/validate/power_switch.py: a box asleep or off must stay so; the switch brings it back."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools/validate"))
import power_switch  # noqa: E402

KERNEL = "7.3.6-tvb-rk35xx-next2"


class Box:
    """A box answering its board id from a script: each entry one query's answer, None silent."""

    def __init__(self, answers: list[str | None]) -> None:
        self.answers, self.commands = list(answers), []

    def raw(
        self, command: str, stdin: bytes = b"", seconds: float = 0, check: bool = False
    ) -> bytes:
        self.commands.append(command)
        if not command.startswith("cat /usr/lib/tvb/board-id"):
            return b""
        answer = self.answers.pop(0) if self.answers else None
        if answer is None:
            raise ConnectionError("no route")
        return answer.encode()


def switch(answers: list[str | None]) -> tuple[power_switch.PowerSwitch, Box]:
    box = Box(answers)
    return power_switch.PowerSwitch("r69-1", box, "true", sleep=lambda _: None), box


class HoldTest(unittest.TestCase):
    def test_a_box_silent_through_the_hold_passes_and_comes_back(self) -> None:
        holds = power_switch.HOLD_S["sleep"] // power_switch.POLL_S
        test, box = switch([f"r69-1 {KERNEL}"] + [None] * holds + ["r69-1 6.1.172-tvb-rk35xx"])
        lines = test.hold("sleep", KERNEL)
        self.assertEqual(
            lines, [f"power.sleep held {power_switch.HOLD_S['sleep'] + power_switch.SETTLE_S} s"]
        )
        self.assertTrue(any("systemctl suspend" in c for c in box.commands))

    def test_a_box_back_on_its_own_fails(self) -> None:
        test, _ = switch([f"r69-1 {KERNEL}", None, None, "r69-1 6.1.172-tvb-rk35xx"])
        self.assertEqual(
            test.hold("poweroff", KERNEL),
            [
                f"FAIL power.poweroff: back on its own {2 * power_switch.POLL_S + power_switch.SETTLE_S} s after it"
            ],
        )

    def test_a_box_that_never_boots_after_the_cycle_fails(self) -> None:
        holds = power_switch.HOLD_S["sleep"] // power_switch.POLL_S
        test, _ = switch([f"r69-1 {KERNEL}"] + [None] * holds)
        lines = test.hold("sleep", KERNEL)
        self.assertEqual(lines[-1], "FAIL power.sleep: no boot after the switch's power cycle")

    def test_another_board_answering_is_not_this_box(self) -> None:
        test, _ = switch(["h96max-m20 7.3.5-tvb-meson64"])
        self.assertFalse(test.answers())


if __name__ == "__main__":
    unittest.main()
