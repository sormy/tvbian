"""tools/validate/video.py: the clip corpus is made once, remade only when what made it changes."""

from __future__ import annotations

import sys
import tempfile
import unittest
from argparse import Namespace
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools/validate"))
import video  # noqa: E402


class ClipsTest(unittest.TestCase):
    def setUp(self) -> None:
        self.corpus = Path(tempfile.mkdtemp())
        self.calls: list[str] = []

    def ffmpeg(self, cmd: list[str], timeout: float | None = None) -> tuple[int, str, float]:
        if "-version" in cmd:
            return 0, "ffmpeg version test", 0.0
        if "lavfi" in cmd:
            self.calls.append("encode")
            Path(cmd[-1]).write_bytes(b" ".join(c.encode() for c in cmd))
            return 0, "", 0.0
        self.calls.append("decode")
        return 0, "0, 0, 0, 1, 10, abc\n", 0.0

    def clips(self, encoder: list[str]) -> None:
        codecs = {"h264": ("mp4", encoder, ["16x16"], None)}
        with (
            mock.patch.object(video, "CORPUS", self.corpus),
            mock.patch.object(video, "CODECS", codecs),
            mock.patch.object(video, "sh", self.ffmpeg),
            mock.patch("builtins.print"),
        ):
            video.cmd_clips(Namespace())

    def test_made_once_then_kept_then_remade_when_its_recipe_changes(self) -> None:
        self.clips(["-c:v", "libx264"])
        self.assertEqual(self.calls, ["encode", "decode"])
        self.clips(["-c:v", "libx264"])
        self.assertEqual(self.calls, ["encode", "decode"])
        self.clips(["-c:v", "libx264", "-crf", "20"])
        self.assertEqual(self.calls, ["encode", "decode", "encode", "decode"])


class MemoryTest(unittest.TestCase):
    def test_a_decode_s_memory_by_size_and_depth(self) -> None:
        self.assertEqual(video.needed_mb("hevc", "8192x8192"), 768)
        self.assertEqual(video.needed_mb("hevc10", "8192x8192"), 1536)  # 10-bit, twice
        self.assertEqual(video.needed_mb("vp9p2", "7680x4320"), 759)


class ClampedTest(unittest.TestCase):
    TRIED = "\tWidth/Height      : {}\n\tPixel Format      : '{}' (H.265)\n"

    def test_the_size_the_driver_gives_back(self) -> None:
        self.assertEqual(
            video.clamped(self.TRIED.format("8192/4320", "S265"), "S265"), (8192, 4320)
        )

    def test_a_swapped_format_says_nothing(self) -> None:
        self.assertIsNone(video.clamped(self.TRIED.format("1920/1080", "S264"), "S265"))


class LadderTest(unittest.TestCase):
    def test_a_pass_too_slow_to_play_stops_the_climb(self) -> None:
        rates = {"1920x1080": 120.0, "3840x2160": 18.0, "7680x4320": 5.0}
        tried: list[str] = []

        def run(size: str) -> dict[str, object]:
            tried.append(size)
            return {"verdict": "pass", "fps": rates[size]}

        out: list[dict[str, object]] = []
        video.ladder(list(rates), run, out.append, lambda size: None)
        self.assertNotIn("7680x4320", tried)
        self.assertEqual([r["size"] for r in out], ["1920x1080", "3840x2160"])


if __name__ == "__main__":
    unittest.main()
