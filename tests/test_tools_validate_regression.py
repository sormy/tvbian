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
import results  # noqa: E402
from regression import (  # noqa: E402
    PROFILES,
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
    def test_every_profile_runs_every_step(self) -> None:
        names = {p: [s.name for s in steps(p, "sunxi64", "plex")] for p in PROFILES}
        self.assertEqual(names["short"], names["default"])
        self.assertEqual(names["default"], names["extended"])
        for check in ("throughput", "soak", "display-full", "screen", "video", "deqp", "reboots"):
            self.assertIn(check, names["short"])
        self.assertEqual(
            len(names["short"]), len(set(names["short"]))
        )  # onbox.py skips a name done

    def test_the_profile_sets_the_scope(self) -> None:
        def arg(profile: str, step: str, flag: str) -> str:
            command = next(s for s in steps(profile, "rk35xx", "plex") if s.name == step).command
            return next(str(a) for a in command if str(a).startswith(flag))

        self.assertEqual(arg("short", "video", "--only="), "--only=-(3840x2160)$")
        self.assertEqual(arg("default", "video", "--only="), "--only=-(1920x1080|3840x2160)$")
        with self.assertRaises(StopIteration):  # the whole ladder
            arg("extended", "video", "--only")
        soak = {
            p: next(s for s in steps(p, "rk35xx", "plex") if s.name == "soak") for p in PROFILES
        }
        self.assertEqual(
            [soak[p].command[soak[p].command.index("--soak") + 1] for p in PROFILES],
            ["30", "120", "1800"],
        )


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
        self.assertEqual(
            regression.step_seconds(log, "6.1.172-tvb-rk35xx"), [("system", 49), ("video", 1145)]
        )
        self.assertIn("| video | 1145 |", regression.step_table(log, "6.1.172-tvb-rk35xx"))
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

    def test_a_crashed_script_is_its_own_failure(self) -> None:
        found = self.verdicts(
            'cpu.ladder 480\nTraceback (most recent call last):\n  File "box.py", line 3\n'
            "subprocess.TimeoutExpired: Command 'glmark2' timed out after 60 seconds\nexit 1\n"
        )
        self.assertEqual(
            found.fails[0],
            "CRASHED: subprocess.TimeoutExpired: Command 'glmark2' timed out after 60 seconds",
        )

    def test_a_skipped_video_case_is_untested_not_a_check(self) -> None:
        record = '{"suite": "decode", "codec": "av1", "size": "7680x4320", "verdict": "skipped"}'
        found = self.verdicts(f"{record}\nexit 0\n")
        self.assertEqual(
            (found.checks, found.untested), (0, ["video decode av1 7680x4320: skipped"])
        )

    def test_a_step_entry_skips_the_step_and_matches_no_check(self) -> None:
        path = self.dir / "known.conf"
        path.write_text("h96max-h313 6.18* step:recovery  # the watchdog test hangs it\n")
        known = Known.load(path)
        self.assertEqual(
            results.skipped(known, "h96max-h313", "6.18.63-tvb-sunxi64", "recovery"),
            "the watchdog test hangs it",
        )
        self.assertIsNone(results.skipped(known, "h96max-h313", "7.3.4-tvb-sunxi64", "recovery"))
        self.assertIsNone(results.skipped(known, "tanix-tx1-v2", "6.18.63-tvb-sunxi64", "recovery"))
        self.assertFalse(known[0].matches("h96max-h313", "6.18.63-tvb-sunxi64", "recovery: x"))

    def test_a_run_past_its_profile_s_usual_time_is_flagged(self) -> None:
        (self.dir / "host.txt").write_text("profile short\n")
        (self.dir / "run.log").write_text(
            "23:55:00 6.1: booting l1\n00:15:00 done: the default back\n"
        )
        self.assertEqual(regression.over_budget(self.dir), " ⚠ 20 min, short's usual 12")
        (self.dir / "run.log").write_text(
            "10:00:00 6.1: booting l1\n10:08:00 done: the default back\n"
        )
        self.assertEqual(regression.over_budget(self.dir), "")

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

        with (
            mock.patch.object(regression, "RESULTS", results),
            mock.patch.object(Box, "raw", answer),
        ):
            into = regression.fetch(["a=root@up", "down=root@down", "b=root@up2"])
        self.assertNotEqual(into, today)
        self.assertEqual(sorted(p.name for p in into.iterdir()), ["a", "b"])
        self.assertEqual((today / "b" / "run.log").read_text(), "08:00:00 an earlier run\n")


class WatchTest(unittest.TestCase):
    def test_a_crash_ends_the_wait_and_is_said(self) -> None:
        answers = iter(
            ["12:00 6.1: system exit 0, 20 s", "running", "12:01 6.1: cpu exit 1, 2 s", "crashed"]
        )

        def run(
            box: Box,
            command: str,
            stdin: str | bytes = b"",
            seconds: float = 0,
            check: bool = False,
        ) -> str:
            return next(answers)

        out = io.StringIO()
        with (
            mock.patch.object(Box, "run", run),
            mock.patch.object(regression, "POLL_S", 0),
            mock.patch("sys.stdout", out),
        ):
            self.assertEqual(regression.watch("a=root@a", 60), "crashed")
        self.assertEqual(
            out.getvalue().splitlines(),
            ["a: 12:00 6.1: system exit 0, 20 s", "a: 12:01 6.1: cpu exit 1, 2 s", "a: crashed"],
        )


class InstallTest(unittest.TestCase):
    def test_only_what_changed_is_sent_and_installed(self) -> None:
        debs = Path(tempfile.mkdtemp())
        for name, data in (
            ("linux-image-6.1.172-tvb-rk35xx_6.1.172-0~local_arm64.deb", b"kernel"),
            ("tvb-h96max-m2-plus_0~local_arm64.deb", b"board, rebuilt"),
        ):
            (debs / name).write_bytes(data)
        kernel, board = sorted(p.name for p in debs.iterdir())
        held = f"{regression.full_sha(debs / kernel)}  {kernel}\n{'0' * 64}  {kernel}.installed\n"
        held += f"{'1' * 64}  {board}\n{'2' * 64}  old.deb\n"
        box = mock.MagicMock()
        box.run.side_effect = lambda command, *a, **k: held if "sha256sum" in command else ""
        box.root.return_value = "done"
        deployment = regression.Deployment("h96max-m2-plus", box, "short", "plex")
        with mock.patch.object(regression, "DEBS", debs):
            said = deployment.install(["6.1.172-tvb-rk35xx"])
        sent = [c.args[0] for c in box.run.call_args_list if c.args[0].startswith("cat > ")]
        self.assertEqual(sent, [f"cat > {regression.PACKAGES}/{board}"])
        installed = [a for a in box.root.call_args.args if a.endswith(".deb")]
        self.assertEqual(installed, [f"{regression.PACKAGES}/{board}"])
        self.assertTrue(any("rm -f old.deb" in c.args[0] for c in box.run.call_args_list))
        self.assertTrue(said.startswith("1 of 2 packages, 1 sent"))


class StartedTest(unittest.TestCase):
    def test_a_box_whose_build_fails_is_not_started_and_says_why(self) -> None:
        failed = subprocess.CalledProcessError(1, ["build.sh", "board", "a"])
        out = io.StringIO()
        with (
            mock.patch.object(regression, "prepare", side_effect=failed),
            mock.patch.object(regression, "start") as start,
            mock.patch("sys.stdout", out),
        ):
            self.assertFalse(regression.started("short", "a=root@a", "plex"))
        start.assert_not_called()
        self.assertTrue(out.getvalue().startswith("a: not started:"))

    def test_a_fresh_folder_never_reuses_one(self) -> None:
        base = Path(tempfile.mkdtemp()) / "2026-11-14-1904"
        self.assertEqual(regression.fresh(base), base)
        base.mkdir()
        self.assertEqual(regression.fresh(base).name, "2026-11-14-1904-2")


if __name__ == "__main__":
    unittest.main()
