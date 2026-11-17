"""tools/validate/browser.py: the page server's ranges and reports, and a clip's rate by its name."""

from __future__ import annotations

import sys
import tempfile
import unittest
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools/validate"))
import browser  # noqa: E402

CLIP = bytes(range(256)) * 4


class ServerTest(unittest.TestCase):
    def setUp(self) -> None:
        self.root = Path(tempfile.mkdtemp())
        (self.root / "clip.webm").write_bytes(CLIP)
        self.server = browser.Server(self.root)
        self.addCleanup(self.server.shutdown)

    def get(self, path: str, headers: dict[str, str] | None = None) -> tuple[int, bytes]:
        url = f"http://127.0.0.1:{self.server.port}{path}"
        with urllib.request.urlopen(urllib.request.Request(url, headers=headers or {})) as reply:
            return reply.status, reply.read()

    def test_ranges(self) -> None:
        for wanted, status, body in [
            ("bytes=10-19", 206, CLIP[10:20]),
            ("bytes=1000-", 206, CLIP[1000:]),
            ("bytes=1000-5000", 206, CLIP[1000:]),
            ("", 200, CLIP),
        ]:
            with self.subTest(wanted=wanted):
                self.assertEqual(self.get("/clip.webm", {"Range": wanted}), (status, body))

    def test_report_kept_by_tag(self) -> None:
        self.get("/report?tag=chromium-vp9-4k60&fps=59.9&media=1.00&size=3840x2160")
        self.assertEqual(
            self.server.reports["chromium-vp9-4k60"],
            {"fps": "59.9", "media": "1.00", "size": "3840x2160"},
        )


class ClipRateTest(unittest.TestCase):
    def test_rate_from_name(self) -> None:
        for name, rate in [("vp9-4k60.webm", 60), ("h264-4k30.mp4", 30), ("hevc-1080p60.mp4", 60)]:
            with self.subTest(name=name):
                self.assertEqual(browser.clip_rate(Path(name)), rate)


if __name__ == "__main__":
    unittest.main()
