"""tools/validate/video.py: the clip corpus is made once, remade only when what made it changes."""

from __future__ import annotations

import re
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
        self.assertEqual(video.needed_mb("hevc", "8192x8192"), 1152)
        self.assertEqual(video.needed_mb("hevc10", "8192x8192"), 1440)  # 10-bit, packed in 5/4
        self.assertEqual(video.needed_mb("vp9p2", "7680x4320"), 711)


class ClampedTest(unittest.TestCase):
    TRIED = "\tWidth/Height      : {}\n\tPixel Format      : '{}' (H.265)\n"

    def test_the_size_the_driver_gives_back(self) -> None:
        self.assertEqual(
            video.clamped(self.TRIED.format("8192/4320", "S265"), "S265"), (8192, 4320)
        )

    def test_a_swapped_format_says_nothing(self) -> None:
        self.assertIsNone(video.clamped(self.TRIED.format("1920/1080", "S264"), "S265"))


class DownloadTest(unittest.TestCase):
    def test_a_frame_downloads_in_the_format_its_codec_comes_in(self) -> None:
        rkmpp = video.ENGINES["rkmpp"]
        for codec, download in (
            ("h264", "hwdownload,format=nv12,"),
            ("h264422", "hwdownload,format=nv16,"),
            ("h264gray", "hwdownload,format=gray,"),
        ):
            with self.subTest(codec=codec):
                self.assertEqual(video.download_filter(rkmpp, codec), download)

    def test_an_engine_without_a_download_stays_without(self) -> None:
        self.assertEqual(video.download_filter(video.ENGINES["meson"], "h264422"), "")


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
    def test_past_a_pass_too_slow_to_play_the_climb_goes_on_untimed(self) -> None:
        rates = {"1920x1080": 120.0, "3840x2160": 18.0, "7680x4320": 5.0, "8192x8192": 0.0}
        verdicts = {"8192x8192": "broken"}
        timed_sizes: list[str] = []

        def run(size: str, timed: bool) -> dict[str, object]:
            if timed:
                timed_sizes.append(size)
            return {"verdict": verdicts.get(size, "pass"), "fps": rates[size] if timed else None}

        out: list[dict[str, object]] = []
        video.ladder(list(rates), run, out.append, lambda size: None)
        self.assertEqual(timed_sizes, ["1920x1080", "3840x2160"])
        self.assertEqual(
            [(r["size"], r["verdict"]) for r in out],
            [
                ("1920x1080", "pass"),
                ("3840x2160", "pass"),
                ("7680x4320", "pass"),
                ("8192x8192", "broken"),
            ],
        )


class UsefulRateTest(unittest.TestCase):
    def test_a_case_is_useful_only_on_a_measured_rate(self) -> None:
        for case, useful in [
            ({"suite": "decode", "fps": 30.0}, True),
            ({"suite": "decode", "fps": 18.0}, False),
            ({"suite": "decode", "fps": None}, False),
            ({"suite": "encode", "fps": 40.0, "cpu_fps": 10.0}, True),
            ({"suite": "encode", "fps": 5.0, "cpu_fps": 10.0}, False),
            ({"suite": "encode", "fps": 40.0, "cpu_fps": None}, True),
            ({"suite": "encode", "fps": None, "cpu_fps": None}, False),
        ]:
            with self.subTest(case=case):
                self.assertEqual(video.useful_rate(case), useful)


class CodecTest(unittest.TestCase):
    def test_a_variant_decodes_as_its_base_codec(self) -> None:
        for codec, base in [
            ("h264", "h264"),
            ("h264422", "h264"),
            ("h264gray", "h264"),
            ("hevc10", "hevc"),
            ("mjpeg411", "mjpeg"),
            ("mpeg2", "mpeg2"),
        ]:
            with self.subTest(codec=codec):
                self.assertEqual(video.base_codec(codec), base)

    def test_every_jpeg_sampling_is_made_by_cjpeg(self) -> None:
        for sampling in video.JPEG_SAMPLINGS:
            with self.subTest(sampling=sampling):
                ext, enc, _, exact = video.CODECS[f"mjpeg{sampling}"]
                self.assertEqual((ext, enc[0], exact), ("jpg", video.CJPEG, False))


class LossyTest(unittest.TestCase):
    def test_a_lossy_decode_holds_luma_and_chroma(self) -> None:
        for y, uv, ok in [
            (77.9, 74.6, True),
            (77.9, 34.0, True),
            (77.9, 10.2, False),
            (45.0, 74.6, False),
            (77.9, None, True),
            (None, 74.6, False),
        ]:
            with self.subTest(y=y, uv=uv):
                self.assertEqual(video.lossy_ok(y, uv), ok)


class DamagedTest(unittest.TestCase):
    def test_the_middle_span_is_zeroed_and_the_rest_kept(self) -> None:
        with tempfile.TemporaryDirectory() as root:
            clip = Path(root) / "clip.mp4"
            clip.write_bytes(bytes(range(256)) * 64)
            with (
                mock.patch.object(video, "BOX_DIR", root),
                mock.patch.object(video, "CONCEAL_SPAN", 16),
            ):
                out = Path(video.damaged(str(clip))).read_bytes()
            middle = len(out) // 2
            self.assertEqual(out[middle : middle + 16], bytes(16))
            self.assertEqual(out[:middle], clip.read_bytes()[:middle])
            self.assertEqual(out[middle + 16 :], clip.read_bytes()[middle + 16 :])


if __name__ == "__main__":
    unittest.main()


class RecoveryTest(unittest.TestCase):
    """A job made to fail by its driver's test parameter, then the next one right."""

    def setUp(self) -> None:
        self.param = Path(tempfile.mkdtemp()) / "fail_next_job"
        self.param.write_text("0")

    def recovery(self, takes: bool, kernel: list[str], log: str, after: str) -> dict:
        def job() -> str:
            if takes:  # the driver clears the parameter as it takes the job
                self.param.write_text("0")
            return log

        with (
            mock.patch.object(video, "dmesg_lines", return_value=0),
            mock.patch.object(video, "kernel_errors", return_value=kernel),
        ):
            return video.recovery(self.param, "fault", job, lambda: after)

    def test_a_deinterlace_is_judged_on_luma_and_chroma(self) -> None:
        def stats(u: float) -> str:
            return "\n".join(
                f"n:{n} mse_avg:1 psnr_avg:40 psnr_y:42.30 psnr_u:{u} psnr_v:40.00"
                for n in range(1, 2 * video.FRAMES + 1)
            )

        for codec, u, verdict in (
            ("h264i422frame", 38.9, "pass"),
            ("h264i422frame", 9.5, "broken"),
            ("h264i", 41.3, "pass"),
        ):
            sh = mock.Mock(return_value=(0, stats(u), ""))
            with self.subTest(codec=codec, u=u), mock.patch.multiple(
                video,
                sh=sh,
                dmesg_lines=mock.Mock(return_value=0),
                kernel_errors=mock.Mock(return_value=[]),
            ):
                r = video.deinterlace_case("ffmpeg9", "rkvdec", codec, "clip.mp4")
                self.assertEqual(r["verdict"], verdict)
                self.assertEqual(r["psnr_uv"], min(u, 40.0))
                command = sh.call_args.args[0]
                self.assertEqual(
                    "setfield=tff," in " ".join(command), codec in video.INTERLACED_FRAMES
                )

    def test_a_deinterlace_rate(self) -> None:
        def stats(frames: int) -> str:
            return "\n".join(
                f"n:{n} mse_avg:1 psnr_avg:40 psnr_y:42.30 psnr_u:40.0 psnr_v:40.00"
                for n in range(1, frames + 1)
            )

        for rate, frames, out, verdict in (
            ("frame", video.FRAMES, stats(video.FRAMES), "pass"),
            ("frame", 0, "the deinterlacer gives no frame per frame", "unoffered"),
            ("field", 2 * video.FRAMES, stats(2 * video.FRAMES), "pass"),
            ("field", video.FRAMES - 1, stats(video.FRAMES - 1), "broken"),
        ):
            sh = mock.Mock(return_value=(0, out, ""))
            with self.subTest(rate=rate, frames=frames), mock.patch.multiple(
                video,
                sh=sh,
                dmesg_lines=mock.Mock(return_value=0),
                kernel_errors=mock.Mock(return_value=[]),
            ):
                r = video.deinterlace_case("ffmpeg9", "rkvdec", "h264i", "clip.mp4", rate)
                self.assertEqual(r["verdict"], verdict)
                command = " ".join(sh.call_args.args[0])
                self.assertIn(f"bwdif=mode=send_{rate}", command)
                self.assertEqual("deinterlace_v4l2m2m=rate=frame" in command, rate == "frame")

    def test_a_scale_records_what_was_asked_and_given(self) -> None:
        stream = "Stream #0:0: Video: rawvideo, nv12, {}"
        stats = "n:1 mse_avg:1 psnr_avg:40 psnr_y:41.00 psnr_u:40.0 psnr_v:40.00"
        for out, logs, verdict in (
            ("960x540", [stream.format("960x540"), stats], "pass"),
            ("3840x2160", [stream.format("3840x2160")], "full"),
            ("960x540", [stream.format("960x540"), stats.replace("41.00", "12.00")], "broken"),
        ):
            sh = mock.Mock(side_effect=[(0, log, 0.0) for log in logs])
            with self.subTest(out=out, verdict=verdict), mock.patch.object(video, "sh", sh):
                r = video.scale_case("ffmpeg9", "rkvdec", "h264", "h264-3840x2160.mp4", 540)
                self.assertEqual(r["verdict"], verdict)
                self.assertIn("capture_max_height=540", " ".join(sh.call_args_list[0].args[0]))

    def test_a_frame_s_hdr_signalling_from_showinfo(self) -> None:
        log = "\n".join(
            [
                "[Parsed_showinfo_0 @ 0xaa] n:   0 pts:      0 fmt:p010le s:3840x2160 iskey:1",
                "[Parsed_showinfo_0 @ 0xaa]   side data - Mastering display metadata: has_primaries:1 "
                "has_luminance:1 r(0.6800,0.3200) g(0.2650,0.6900) b(0.1500 0.0600)",
                "[Parsed_showinfo_0 @ 0xaa]   side data - Content light level metadata: "
                "MaxCLL=1000, MaxFALL=400",
                "[Parsed_showinfo_0 @ 0xaa]   color_range:tv color_space:bt2020nc "
                "color_primaries:bt2020 color_trc:smpte2084",
                "frame=    1 fps=0.0 q=-0.0 Lsize=N/A",
            ]
        )
        got = video.frame_signalling(log)
        self.assertEqual(len(got), 3)
        self.assertTrue(any("smpte2084" in line for line in got))
        self.assertFalse(any("fmt:" in line for line in got))

    def test_a_copy_s_rate_is_the_time_over_a_kept_frame(self) -> None:
        for kept, copied, mbs in ((100.0, 50.0, 1244), (50.0, 50.0, None), (0.0, 50.0, None)):
            with self.subTest(kept=kept, copied=copied):
                self.assertEqual(video.copy_mbs("3840x2160", kept, copied), mbs)

    def test_a_release_build_without_the_parameter_is_untested(self) -> None:
        self.param.unlink()
        rec = self.recovery(True, [], "", "pass")
        self.assertEqual(rec["verdict"], "untested")
        self.assertIn(self.param.name, rec["why"])

    def test_an_untested_case_is_never_worse(self) -> None:
        old = [{"suite": "failure", "codec": "h264", "size": "1920x1080", "verdict": "pass"}]
        new = [dict(old[0], verdict="untested")]
        self.assertEqual(video.worse(old, new), [])

    def test_the_parameter_is_written_as_the_failure_s_number(self) -> None:
        self.recovery(False, [], "", "pass")
        self.assertEqual(self.param.read_text(), str(video.FAILURES["fault"]))

    def test_the_verdict(self) -> None:
        fault = ["rk_iommu: Page fault at 0x1000"]
        for takes, kernel, log, after, verdict in (
            (True, fault, "", "pass", "pass"),
            (True, [], "corrupt decoded frame", "pass", "pass"),
            (True, fault, "", "broken", "broken"),
            (True, [], "", "pass", "broken"),
            (False, fault, "", "pass", "broken"),
        ):
            with self.subTest(takes=takes, kernel=kernel, log=log, after=after):
                self.assertEqual(self.recovery(takes, kernel, log, after)["verdict"], verdict)


class HardwareOnlyTest(unittest.TestCase):
    def test_every_hwaccel_refuses_the_cpu_and_says_so_as_a_fallback(self) -> None:
        for engine, eng in video.ENGINES.items():
            decoded = [c for c in video.CODECS if "decode" in eng and eng["decode"](c)]
            for path in ("decode", "scale", "afbc"):
                for codec in decoded if path in eng else []:
                    args = (codec, video.SCALE_LINES[0]) if path == "scale" else (codec,)
                    opts = eng[path](*args) or []
                    if "-hwaccel" not in opts:
                        continue
                    with self.subTest(engine=engine, path=path, codec=codec):
                        self.assertIn("-nosw_fallback", opts)
                        self.assertTrue(re.search(eng["fallback"], "-sw_fallback is off"))


class Pack10BitTest(unittest.TestCase):
    def test_four_samples_fill_five_bytes_the_first_lowest(self) -> None:
        samples = b"".join((v << video.P010_SHIFT).to_bytes(2, "little") for v in (1, 2, 3, 0x3FF))
        word = 1 | 2 << 10 | 3 << 20 | 0x3FF << 30
        self.assertEqual(video.pack_10bit(samples), word.to_bytes(5, "little"))


class FramePerFrameTest(unittest.TestCase):
    """The one-frame-a-frame control: one frame a job, its first field's, judged against the
    two-frame run."""

    SIZE = (4, 2)
    FRAME = 4 * 2 * 3 // 2
    FIRST, SECOND = bytes([10] * FRAME), bytes([200] * FRAME)

    def run_case(self, on_frames: list[bytes], off_jobs: int = 9, drift: bool = False) -> dict:
        root = Path(tempfile.mkdtemp())
        offs = 0

        def sh(cmd: list[str], timeout: float | None = None) -> tuple[int, str, float]:
            out = next((c.split("=", 1)[1] for c in cmd if c.startswith("--stream-to=")), None)
            nonlocal offs
            if out:
                on = any(c.endswith("frame_per_frame=1") for c in cmd)
                frames = on_frames if on else [self.FIRST, self.SECOND] * off_jobs
                if not on:
                    offs += 1
                    if drift and offs == 2:
                        frames = [self.FIRST, bytes([201] * self.FRAME)] * off_jobs
                Path(out).write_bytes(b"".join(frames))
            return 0, "", 0.0

        with (
            mock.patch.object(video, "BOX_DIR", str(root)),
            mock.patch.object(video, "FRAME_PER_FRAME_SIZE", self.SIZE),
            mock.patch.object(video, "sh", sh),
            mock.patch.object(video, "dmesg_lines", return_value=0),
            mock.patch.object(video, "kernel_errors", return_value=[]),
        ):
            return video.frame_per_frame_case("ffmpeg", "/dev/video0")

    def test_first_fields_pass(self) -> None:
        r = self.run_case([self.FIRST] * 9)
        self.assertEqual((r["verdict"], r["frames_off"], r["frames_on"]), ("pass", 18, 9))

    def test_cases_broken(self) -> None:
        for name, frames in (
            ("second field", [self.SECOND] * 9),
            ("two a job", [self.FIRST] * 18),
            ("none", []),
        ):
            with self.subTest(name):
                self.assertEqual(self.run_case(frames)["verdict"], "broken")

    def test_unrepeatable_broken(self) -> None:
        r = self.run_case([self.FIRST] * 9, drift=True)
        self.assertEqual((r["verdict"], r["repeatable"]), ("broken", False))

    def test_psnr(self) -> None:
        self.assertEqual(video.nv12_psnr(b"\x01\x02", b"\x01\x02"), float("inf"))
        self.assertAlmostEqual(video.nv12_psnr(b"\x00", b"\xff"), 0.0)
