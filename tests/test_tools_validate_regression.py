"""tools/validate/regression.py: which kernels, which boot entry, what moved."""

from __future__ import annotations

import datetime
import io
import json
import subprocess
import sys
import tarfile
import tempfile
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools/validate"))
import regression  # noqa: E402
from regression import (  # noqa: E402
    Box,
    Known,
    Verdicts,
    board_family,
    duration,
    first_line,
    inputs,
    changed,
    kernels,
    steps,
    upstream_args,
    video_records,
    video_table,
)


class KernelsTest(unittest.TestCase):
    def test_the_family_s_and_its_next_newest_each(self) -> None:
        debs = [
            "linux-image-tvb-sunxi64_6.18.62-0~local_arm64.deb",
            "linux-image-tvb-sunxi64_6.18.63-0~local_arm64.deb",
            "linux-image-tvb-sunxi64-next_7.3.10-0~local_arm64.deb",
            "linux-image-tvb-sunxi64-next_7.3.4-0~local_arm64.deb",
            "linux-image-tvb-meson64_6.18.63-0~local_arm64.deb",
            "linux-image-6.18.63-tvb-sunxi64_6.18.63-0~local_arm64.deb",
        ]
        self.assertEqual(kernels("sunxi64", debs), ["6.18.63-tvb-sunxi64", "7.3.10-tvb-sunxi64"])

    def test_a_family_without_next_runs_one(self) -> None:
        debs = ["linux-image-tvb-rk35xx_6.1.172-0~local_arm64.deb"]
        self.assertEqual(kernels("rk35xx", debs), ["6.1.172-tvb-rk35xx"])

    def test_a_board_s_family_from_its_conf(self) -> None:
        self.assertEqual(board_family("h96max-m20"), "meson64")

    def test_upstream_s_arguments_with_the_board_s_own_base(self) -> None:
        args = upstream_args("h96max-rk3528")
        self.assertEqual(args[0], "--soc")
        self.assertTrue(args[1].endswith("rk3528-evb2-ddr3-v10.dts"))
        self.assertEqual(args[2:], ["kernel-rk3528-vendor-6.1", "kernel-rk3528-vendor-6.1"])

    def test_upstream_s_arguments_on_the_bases_own(self) -> None:
        self.assertEqual(
            upstream_args("h96max-m20"), ["kernel-gxl-vendor-4.9", "kernel-gxl-mainline-6.18"]
        )


class StepsTest(unittest.TestCase):
    def test_short_is_a_smoke_test_that_never_waits_on_iperf3(self) -> None:
        plan = steps("short", "rk35xx", "plex")
        names = [s.name for s in plan]
        self.assertNotIn("throughput", names)
        self.assertEqual(names[-2:], ["composite", "video"])
        self.assertIn("--only=-(1920x1080)$", plan[-1].command)

    def test_default_samples_the_video_sizes(self) -> None:
        plan = steps("default", "rk35xx", "plex")
        names = [s.name for s in plan]
        self.assertEqual(names[-2:], ["composite", "video"])
        self.assertIn("throughput", names)
        self.assertNotIn("soak", names)
        only = [a for a in plan[-1].command if str(a).startswith("--only=")]
        self.assertEqual(only, ["--only=-(1920x1080|3840x2160|4096x2160|7680x4320)$"])

    def test_extended_walks_the_whole_ladder(self) -> None:
        video = next(s for s in steps("extended", "sunxi64", "plex") if s.name == "video")
        self.assertFalse([a for a in video.command if str(a).startswith("--only")])

    def test_no_profile_names_a_step_twice(self) -> None:
        """onbox.py skips a name it has done: a second step under it would never run."""
        for profile in ("short", "default", "extended"):
            names = [s.name for s in steps(profile, "sunxi64", "plex")]
            self.assertEqual(len(names), len(set(names)), profile)

    def test_extended_adds_the_long_and_the_rebooting_steps(self) -> None:
        names = [s.name for s in steps("extended", "sunxi64", "plex")]
        for long in ("soak", "display-full", "screen", "deqp", "recovery", "reboots"):
            self.assertIn(long, names)
        self.assertEqual(names[-2:], ["recovery", "reboots"])


class ChangedTest(unittest.TestCase):
    def test_lines_that_moved_appeared_or_went(self) -> None:
        old = "kernel 6.18.63\nmmc.errors 0\nbt.scan.devices 21\nrtc sun6i\n"
        new = "kernel 6.18.63\nmmc.errors 2\nbt.scan.devices 21\ngpu.glmark2 120\n"
        self.assertEqual(
            changed(old, new),
            ["gpu.glmark2: - -> 120", "mmc.errors: 0 -> 2", "rtc: sun6i -> -"],
        )


class ResultsTest(unittest.TestCase):
    def setUp(self) -> None:
        self.dir = Path(tempfile.mkdtemp())

    def verdicts(self, text: str) -> Verdicts:
        path = self.dir / "step.txt"
        path.write_text(text)
        return Verdicts.of(path)

    def test_a_skipped_sub_check_in_a_passing_step_is_untested(self) -> None:
        found = self.verdicts("composite.mode 720x576\nSKIP compose: no writeback\nexit 0\n")
        self.assertEqual(
            (found.checks, found.fails, found.untested), (1, [], ["compose: no writeback"])
        )

    def test_the_codec_table_keeps_video_py_s_header(self) -> None:
        head = {"kernel": "6.1.172-tvb-rk35xx", "engine": "rkmpp", "ffmpeg": "ffmpeg 9"}
        case = {
            "verdict": "pass",
            "fps": 60.0,
            "size": "1920x1080",
            "suite": "decode",
            "codec": "h264",
        }
        lines = [head, {"start": ["decode", "h264", "1920x1080"]}, case, {"done": True}]
        (self.dir / "video.txt").write_text("".join(json.dumps(r) + "\n" for r in lines))
        self.assertIn("rkmpp on 6.1.172-tvb-rk35xx", video_table(self.dir))

    def test_a_skipped_step_is_untested_and_a_dead_one_failed(self) -> None:
        skipped = self.verdicts("SKIP composite: no composite connector\nexit 77\n")
        self.assertEqual(skipped.fails, [])
        self.assertEqual(len(skipped.untested), 1)
        dead = self.verdicts("probing\nexit 1\n")
        self.assertEqual(len(dead.fails), 1)

    def test_a_kernel_s_minutes_are_its_own_steps(self) -> None:
        log = self.dir / "run.log"
        log.write_text(
            "09:00:14 6.1.172-tvb-rk35xx: booting l1\n"
            "09:01:27 6.1.172-tvb-rk35xx: system exit 0, 49 s\n"
            "09:21:00 6.1.172-tvb-rk35xx: video exit 0, 1145 s\n"
            "09:23:00 6.12.69-tvb-rk35xx: system exit 0, 60 s\n"
        )
        self.assertEqual(duration(log, "6.1.172-tvb-rk35xx"), "19 min")
        self.assertEqual(duration(log, "6.12.69-tvb-rk35xx"), "1 min")
        self.assertEqual(duration(log, "7.3.4-tvb-sunxi64"), "?")

    def test_a_known_failure_matches_its_boards_kernels_and_check_alone(self) -> None:
        path = self.dir / "known.conf"
        path.write_text(
            "# a comment\n" "h96max-3518*,r69-1 * ^network: bt\\.find: 0$  # needs an advertiser\n"
        )
        [known] = Known.load(path)
        self.assertEqual(known.reason, "needs an advertiser")
        line = "network: bt.find: 0"
        self.assertTrue(known.matches("h96max-3518d", "6.1.172-tvb-rk35xx", line))
        self.assertTrue(known.matches("r69-1", "6.12.69-tvb-rk35xx", line))
        self.assertFalse(known.matches("h96max-h313", "6.18.63-tvb-sunxi64", line))
        self.assertFalse(known.matches("r69-1", "6.1.172-tvb-rk35xx", "network: bt.find: 01"))

    def test_the_repo_s_composite_failure_is_known_in_either_step(self) -> None:
        known = Known.load(Path(regression.__file__).parent / "known.conf")
        for step in ("composite", "display-full"):
            line = f"{step}: composite PAL writeback colour bars LOST, 720x576"
            self.assertTrue(any(k.matches("r69-1", "6.1.172-tvb-rk35xx", line) for k in known))

    def test_a_skipped_video_case_is_untested_not_a_check(self) -> None:
        record = '{"suite": "decode", "codec": "av1", "size": "7680x4320", "verdict": "skipped"}'
        found = self.verdicts(f"{record}\nexit 0\n")
        self.assertEqual(
            (found.checks, found.untested), (0, ["video decode av1 7680x4320: skipped"])
        )

    def test_a_run_is_told_apart_by_its_log_s_first_line(self) -> None:
        log = self.dir / "run.log"
        log.write_text("09:00:14 6.1.172-tvb-rk35xx: booting l1\n09:01:27 later\n")
        self.assertEqual(first_line(log), "09:00:14 6.1.172-tvb-rk35xx: booting l1")
        self.assertEqual(first_line(self.dir / "none.log"), "")

    def test_a_run_s_inputs_from_its_host_lines(self) -> None:
        host = self.dir / "host.txt"
        host.write_text("profile short\n# input tvb-h96max-3518 0123456789ab\n# input: none\nx 1\n")
        self.assertEqual(inputs(host), {"tvb-h96max-3518": "0123456789ab"})
        self.assertEqual(inputs(self.dir / "none.txt"), {})

    def test_video_records_are_the_cases_alone(self) -> None:
        case = '{"verdict": "ok", "size": "1920x1080", "suite": "decode", "codec": "h264"}'
        (self.dir / "video.txt").write_text(f'{case}\n{{"done": true}}\nexit 0\n')
        self.assertEqual([r["codec"] for r in video_records(self.dir)], ["h264"])


def results_tar(first: str) -> bytes:
    """A box's results as fetch receives them: a run log and its done marker."""
    buffer = io.BytesIO()
    with tarfile.open(fileobj=buffer, mode="w") as tar:
        for name, text in (("run.log", f"{first}\n"), ("done", "now\n")):
            data = text.encode()
            info = tarfile.TarInfo(f"./{name}")
            info.size = len(data)
            tar.addfile(info, io.BytesIO(data))
    return buffer.getvalue()


class BoxTest(unittest.TestCase):
    def test_a_checked_command_that_fails_is_an_error(self) -> None:
        failed = subprocess.CompletedProcess([], 1, b"", b"E: Unable to locate package")
        with mock.patch.object(regression.subprocess, "run", return_value=failed):
            self.assertEqual(Box("root@box").run("apt-get install x"), "")
            with self.assertRaises(ConnectionError):
                Box("root@box").run("apt-get install x", check=True)


class FetchTest(unittest.TestCase):
    def test_one_folder_for_the_batch_and_an_unreachable_box_skipped(self) -> None:
        results = Path(tempfile.mkdtemp())
        today = results / datetime.date.today().isoformat()
        (today / "b").mkdir(parents=True)
        (today / "b" / "run.log").write_text("08:00:00 an earlier run\n")

        def answer(
            box: Box, command: str, stdin: bytes = b"", seconds: float = 0, check: bool = False
        ) -> bytes:
            if box.target == "root@down":
                raise ConnectionError("root@down: no route")
            return results_tar("12:00:00 this run")

        with mock.patch.object(regression, "RESULTS", results), mock.patch.object(
            Box, "raw", answer
        ):
            into = regression.fetch(["a=root@up", "down=root@down", "b=root@up2"])
        self.assertNotEqual(into, today)
        self.assertEqual(sorted(p.name for p in into.iterdir()), ["a", "b"])
        self.assertEqual((today / "b" / "run.log").read_text(), "08:00:00 an earlier run\n")


class StartedTest(unittest.TestCase):
    def test_a_box_whose_build_fails_is_skipped_and_the_next_starts(self) -> None:
        def build(profile: str, spec: str, iperf: str | None) -> None:
            if spec.startswith("a="):
                raise subprocess.CalledProcessError(1, ["build.sh", "board", "a"])

        with mock.patch.object(regression, "start", build):
            self.assertEqual(
                regression.started("short", ["a=root@a", "b=root@b"], "plex"), ["b=root@b"]
            )

    def test_a_fresh_folder_never_reuses_one(self) -> None:
        base = Path(tempfile.mkdtemp()) / "2026-11-14-1904"
        self.assertEqual(regression.fresh(base), base)
        base.mkdir()
        self.assertEqual(regression.fresh(base).name, "2026-11-14-1904-2")


if __name__ == "__main__":
    unittest.main()
