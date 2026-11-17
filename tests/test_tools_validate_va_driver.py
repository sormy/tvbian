"""tools/validate/va_driver.py: a box's decode speed held against its previous report."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools/validate"))
import va_driver  # noqa: E402


def report(*lines: str) -> str:
    return "\n".join(["va.vainfo.vendor TVBian VA-API driver: rkmpp", *lines]) + "\n"


BEFORE = report(
    "va.speed.ffmpeg.vp9 pass: 85.0 fps, 4.00 ms CPU a frame",
    "va.speed.gstreamer.vp9 pass: 81.0 fps, 3.00 ms CPU a frame",
)


class SlowerTest(unittest.TestCase):
    CASES = [
        # (what, the new report, the regressions it holds)
        ("the same", BEFORE, []),
        (
            "within the noise",
            report(
                "va.speed.ffmpeg.vp9 pass: 78.0 fps, 4.90 ms CPU a frame",
                "va.speed.gstreamer.vp9 pass: 90.0 fps, 2.00 ms CPU a frame",
            ),
            [],
        ),
        (
            "slower past the noise",
            report(
                "va.speed.ffmpeg.vp9 pass: 70.0 fps, 4.00 ms CPU a frame",
                "va.speed.gstreamer.vp9 pass: 81.0 fps, 3.00 ms CPU a frame",
            ),
            ["ffmpeg.vp9: 85.0 to 70.0 fps"],
        ),
        (
            "a copy back in: the same rate, more CPU",
            report(
                "va.speed.ffmpeg.vp9 pass: 85.0 fps, 4.00 ms CPU a frame",
                "va.speed.gstreamer.vp9 pass: 81.0 fps, 9.00 ms CPU a frame",
            ),
            ["gstreamer.vp9: 3.0 to 9.0 ms CPU a frame"],
        ),
        (
            "CPU a frame up a third, but a millisecond: noise",
            report(
                "va.speed.ffmpeg.vp9 pass: 85.0 fps, 5.30 ms CPU a frame",
                "va.speed.gstreamer.vp9 pass: 81.0 fps, 3.00 ms CPU a frame",
            ),
            [],
        ),
        (
            "a line gone, or failed: nothing to hold it against",
            report("va.speed.ffmpeg.vp9 failed: no frames"),
            [],
        ),
    ]

    def test_slower(self) -> None:
        for what, after, expected in self.CASES:
            with self.subTest(what):
                self.assertEqual(va_driver.slower(BEFORE, after), expected)


if __name__ == "__main__":
    unittest.main()
