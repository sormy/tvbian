"""tools/validate/video.py: the clip corpus is made once, remade only when what made it changes."""

from __future__ import annotations

import sys
import hashlib
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

    def clips(
        self, encoder: list[str], conformance: dict[str, tuple[str, str, str]] | None = None
    ) -> None:
        codecs = {"h264": ("mp4", encoder, ["16x16"], None)}
        with (
            mock.patch.object(video, "CORPUS", self.corpus),
            mock.patch.object(video, "CODECS", codecs),
            mock.patch.object(video, "CONFORMANCE", conformance or {}),
            mock.patch.object(video, "sh", self.ffmpeg),
            mock.patch("builtins.print"),
        ):
            video.cmd_clips(Namespace())

    def test_a_conformance_stream_is_fetched_once_and_must_match_its_pin(self) -> None:
        served = b"stream"
        pinned = {"vc1-a.vc1": ("vc1", "vc1/a.vc1", hashlib.sha256(served).hexdigest())}
        fetched: list[str] = []

        def fetch(url: str, path: Path) -> None:
            fetched.append(url)
            Path(path).write_bytes(served)

        with mock.patch.object(video.urllib.request, "urlretrieve", fetch):
            self.clips(["-c:v", "libx264"], pinned)
            self.clips(["-c:v", "libx264"], pinned)
            self.assertEqual(fetched, [video.FATE + "vc1/a.vc1"])
            (self.corpus / "vc1-a.vc1").unlink()
            served = b"another"
            with self.assertRaises(SystemExit):
                self.clips(["-c:v", "libx264"], pinned)

    def test_made_once_then_kept_then_remade_when_its_recipe_changes(self) -> None:
        self.clips(["-c:v", "libx264"])
        self.assertEqual(self.calls, ["encode", "decode"])
        self.clips(["-c:v", "libx264"])
        self.assertEqual(self.calls, ["encode", "decode"])
        self.clips(["-c:v", "libx264", "-crf", "20"])
        self.assertEqual(self.calls, ["encode", "decode", "encode", "decode"])


class FieldDecodeTest(unittest.TestCase):
    def test_a_repeated_field_fails_even_with_the_expected_count(self) -> None:
        first = "0, 0, 0, 1, 10, " + "a" * 32
        second = "0, 1, 1, 1, 10, " + "b" * 32
        source = f"{first}\n{second}\n"
        duplicate = f"{first}\n{first}\n"
        engine = video.ENGINES["rkmpp"]
        for output, verdict in ((source, "pass"), (duplicate, "broken")):
            with (
                self.subTest(verdict=verdict),
                mock.patch.object(video, "sh", side_effect=[(0, source, 0), (0, output, 0)]),
                mock.patch.object(video, "kernel_errors", return_value=[]),
            ):
                result = video.field_decode_verdict(
                    "ffmpeg9", engine, "clip.mp4", engine["decode"]("h264i"), 1, []
                )
                self.assertEqual(result["frames_hw"], 2)
                self.assertEqual(result["verdict"], verdict)


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


class ConformanceTest(unittest.TestCase):
    def test_a_verdict_that_changes_between_runs_is_flaky(self) -> None:
        for runs, verdict in [
            (["pass", "pass"], "pass"),
            (["broken", "broken"], "broken"),
            (["pass", "broken"], "flaky"),
            (["unoffered"], "unoffered"),
        ]:
            with self.subTest(runs=runs):
                left = iter(runs)
                rec = video.conformance_case(lambda: {"verdict": next(left)})
                self.assertEqual(rec["verdict"], verdict)

    def test_every_stream_is_pinned(self) -> None:
        for name, (codec, fate, digest) in video.CONFORMANCE.items():
            with self.subTest(name=name):
                self.assertTrue(
                    name.startswith(f"{codec}-") and name.endswith(fate.rsplit("/")[-1])
                )
                self.assertRegex(digest, r"^[0-9a-f]{64}$")


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
