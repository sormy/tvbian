"""tools/validate/display.py: the display freed from a running session for the run."""

from __future__ import annotations

import subprocess
import sys
import unittest
from contextlib import nullcontext
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools/validate"))
import display  # noqa: E402


def systemctl(active: bool) -> tuple[mock.MagicMock, list[list[str]]]:
    calls: list[list[str]] = []

    def run(command: list[str], check: bool = False) -> subprocess.CompletedProcess[str]:
        calls.append(command)
        return subprocess.CompletedProcess(command, 0 if active else 3)

    return mock.MagicMock(side_effect=run), calls


class DisplayFreeTest(unittest.TestCase):
    def test_a_running_session_is_stopped_for_the_run_and_started_after(self) -> None:
        run, calls = systemctl(active=True)
        with mock.patch.object(display.subprocess, "run", run):
            with display.display_free():
                stops = [c[2] for c in calls if c[1] == "stop"]
                self.assertEqual(stops, list(display.SESSION_UNITS))
        starts = [c[2] for c in calls if c[1] == "start"]
        self.assertEqual(starts, list(reversed(display.SESSION_UNITS)))

    def test_no_session_is_left_alone(self) -> None:
        run, calls = systemctl(active=False)
        with mock.patch.object(display.subprocess, "run", run):
            with display.display_free():
                pass
        self.assertEqual({c[1] for c in calls}, {"is-active"})

    def test_a_failing_run_still_brings_the_session_back(self) -> None:
        run, calls = systemctl(active=True)
        with mock.patch.object(display.subprocess, "run", run):
            with self.assertRaises(RuntimeError), display.display_free():
                raise RuntimeError("a check crashed")
        self.assertEqual(calls[-1], ["systemctl", "start", display.SESSION_UNITS[0]])


class DisplayOrderTest(unittest.TestCase):
    def test_hdmi_capture_failure_after_composite_has_its_own_result(self) -> None:
        box = SimpleNamespace(passes=1, failures=0, check=mock.Mock())
        composite = SimpleNamespace(passes=1, failures=0, mode_set=True)
        checks = mock.Mock()
        checks.hdmi.return_value = box
        checks.composite.return_value = composite
        checks.capture.side_effect = [True, False]
        with (
            mock.patch.object(display, "hdr_sink", side_effect=lambda *_: nullcontext(True)),
            mock.patch.object(display, "run", checks.hdmi),
            mock.patch.object(display, "run_composite", checks.composite),
            mock.patch.object(display, "hdmi_writeback_available", checks.capture),
            mock.patch("builtins.print"),
        ):
            display.main([], False)
        self.assertEqual(
            checks.mock_calls,
            [mock.call.hdmi(True), mock.call.capture(), mock.call.composite(), mock.call.capture()],
        )
        box.check.assert_called_once_with("HDMI writeback after composite", False)


if __name__ == "__main__":
    unittest.main()
