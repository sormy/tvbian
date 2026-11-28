"""tools/validate/regression.py: which kernels, which boot entry, what moved."""

from __future__ import annotations

import datetime
import hashlib
import argparse
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
import box  # noqa: E402
import regression  # noqa: E402
import results  # noqa: E402
from results import Known  # noqa: E402
from regression import (  # noqa: E402
    PROFILES,
    Box,
    Verdicts,
    board_family,
    duration,
    first_line,
    inputs,
    changed,
    kernels,
    release_order,
    short_of,
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

    def test_the_kernels_option_picks_its_series(self) -> None:
        debs = [
            "linux-image-tvb-rk35xx_6.1.172-0~local_arm64.deb",
            "linux-image-tvb-rk35xx-next_6.12.69-0~local_arm64.deb",
            "linux-image-tvb-rk35xx-next2_7.3.4-0~local_arm64.deb",
        ]
        own, nxt, next2 = "6.1.172-tvb-rk35xx", "6.12.69-tvb-rk35xx", "7.3.4-tvb-rk35xx-next2"
        expected = {
            "own": [own],
            "next": [nxt],
            "next2": [next2],
            "both": [own, nxt],
            "all": [own, nxt, next2],
        }
        for which, releases in expected.items():
            with self.subTest(which=which):
                self.assertEqual(kernels("rk35xx", debs, which), releases)
        self.assertEqual(kernels("rk35xx", debs[:1], "next"), [])  # none: refused

    def test_a_kernel_s_video_engine_is_its_series_else_its_family_s(self) -> None:
        cases = [
            ("6.1.172-tvb-rk35xx", "rkmpp"),
            ("6.12.69-tvb-rk35xx", "rkmpp"),
            ("7.3.4-tvb-rk35xx-next2", "rkvdec"),
        ]
        for release, expected in cases:
            with self.subTest(release=release):
                self.assertEqual(regression.engine("rk35xx", release), expected)
        video = [
            s for s in regression.steps("short", "rk35xx", "plex", "rk35xx") if s.name == "video"
        ]
        self.assertIn("{engine}", video[0].command)

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
    @staticmethod
    def deb(control: dict[str, bytes], data: dict[str, bytes]) -> bytes:
        def tar(files: dict[str, bytes]) -> bytes:
            out = io.BytesIO()
            with tarfile.open(fileobj=out, mode="w:gz") as t:
                for name, body in files.items():
                    info = tarfile.TarInfo(f"./{name}")
                    info.size = len(body)
                    t.addfile(info, io.BytesIO(body))
            return out.getvalue()

        def member(name: str, body: bytes) -> bytes:
            head = f"{name:<16}{0:<12}{0:<6}{0:<6}{100644:<8}{len(body):<10}`\n".encode()
            return head + body + (b"\n" if len(body) % 2 else b"")

        return b"!<arch>\n" + b"".join(
            member(n, b)
            for n, b in (
                ("debian-binary", b"2.0\n"),
                ("control.tar.gz", tar(control)),
                ("data.tar.gz", tar(data)),
            )
        )

    def test_a_deb_s_md5sums_are_its_own_or_those_dpkg_writes(self) -> None:
        sums = b"d41d8cd98f00b204e9800998ecf8427e  usr/bin/x\n"
        written = f"{hashlib.md5(b'hi').hexdigest()}  usr/bin/x\n".encode()
        for control, expected in (
            ({"control": b"Package: x\n", "md5sums": sums}, sums),
            ({"control": b"Package: x\n"}, written),
        ):
            with self.subTest(own="md5sums" in control), tempfile.TemporaryDirectory() as d:
                path = Path(d) / "x_1_all.deb"
                path.write_bytes(self.deb(control, {"usr/bin/x": b"hi"}))
                self.assertEqual(regression.deb_md5sums(path), hashlib.sha256(expected).hexdigest())

    def test_the_system_step_outlasts_its_cooling_wait(self) -> None:
        self.assertEqual(regression.COOLING_S, box.COOL_WAIT_S)
        for profile in PROFILES:
            with self.subTest(profile=profile):
                system = next(
                    s for s in steps(profile, "rk35xx", "plex", "r69-1") if s.name == "system"
                )
                self.assertGreater(system.seconds, box.COOL_WAIT_S)

    def test_every_profile_runs_every_step_but_short_conformance(self) -> None:
        names = {p: [s.name for s in steps(p, "sunxi64", "plex", "sunxi-h616")] for p in PROFILES}
        self.assertEqual(names["short"], [n for n in names["default"] if n != "conformance"])
        self.assertEqual(names["default"], names["extended"])
        self.assertIn("conformance", names["default"])
        for check in ("throughput", "soak", "display-full", "screen", "video", "va"):
            self.assertIn(check, names["short"])
        for check in ("deqp", "reboots"):
            self.assertIn(check, names["short"])
        self.assertEqual(
            len(names["short"]), len(set(names["short"]))
        )  # onbox.py skips a name done

    def test_the_profile_sets_the_scope(self) -> None:
        def arg(profile: str, step: str, flag: str) -> str:
            command = next(
                s for s in steps(profile, "rk35xx", "plex", "rk35xx") if s.name == step
            ).command
            return next(str(a) for a in command if str(a).startswith(flag))

        self.assertEqual(arg("short", "video", "--only="), "--only=-(3840x2160)$")
        for whole in ("default", "extended"):  # the whole ladder
            with self.assertRaises(StopIteration):
                arg(whole, "video", "--only")
        soak = {
            p: next(s for s in steps(p, "rk35xx", "plex", "rk35xx") if s.name == "soak")
            for p in PROFILES
        }
        # box.py soaks for its profile's time; the step allows that and its margin
        self.assertEqual([soak[p].seconds for p in PROFILES], [630, 720, 2400])
        self.assertEqual(
            [soak[p].command[soak[p].command.index("--profile") + 1] for p in PROFILES],
            list(PROFILES),
        )


class ChangedTest(unittest.TestCase):
    def test_lines_that_moved_appeared_or_went(self) -> None:
        old = "kernel 6.18.63\nmmc.errors 0\nbt.scan.devices 21\nrtc sun6i\n"
        new = "kernel 6.18.63\nmmc.errors 2\nbt.scan.devices 21\ngpu.glmark2 120\n"
        self.assertEqual(
            changed(old, new),
            ["gpu.glmark2: - -> 120", "mmc.errors: 0 -> 2", "rtc: sun6i -> -"],
        )


class ParityTest(unittest.TestCase):
    def test_a_kernel_short_of_the_own_names_the_class_and_what_went(self) -> None:
        own = "kernel 6.1\ninventory.bluetooth 1 hci0\ninventory.leds 2 power link\n"
        cases = (
            ("inventory.bluetooth 1 hci0\ninventory.leds 2 power lan\n", []),
            ("inventory.bluetooth 0\ninventory.leds 3 a b c\n", ["bluetooth: 0 of 1, hci0"]),
            ("inventory.leds 1 power\n", ["bluetooth: 0 of 1, hci0", "leds: 1 of 2, link"]),
            ("inventory.bluetooth 1 hci0\ninventory.leds 1 lan\n", ["leds: 1 of 2, power link"]),
        )
        for other, expected in cases:
            with self.subTest(other=other):
                self.assertEqual(short_of(own, other), expected)

    def test_the_own_kernel_is_the_lowest_version(self) -> None:
        names = ["7.3.5-tvb-rk35xx-next2", "6.12.69-tvb-rk35xx", "6.1.172-tvb-rk35xx"]
        ordered = sorted((Path(n) for n in names), key=release_order)
        self.assertEqual(ordered[0].name, "6.1.172-tvb-rk35xx")


class ReportTest(unittest.TestCase):
    def test_a_measure_against_another_marks_a_move_the_worse_way(self) -> None:
        for now, then, better, shown in [
            (100.0, 120.0, "up", "120 (-17% WORSE)"),
            (100.0, 95.0, "up", "95 (+5%)"),
            (70.0, 60.0, "down", "60 (+17% WORSE)"),
            (70.0, 60.0, "", "60 (+17%)"),
            (70.0, None, "up", "-"),
        ]:
            with self.subTest(better=better, then=then):
                self.assertEqual(regression.against(now, then, better), shown)

    def test_a_measure_is_its_line_s_first_number_and_absent_where_not_taken(self) -> None:
        folder = Path(tempfile.mkdtemp())
        (folder / "cpu.txt").write_text(
            "cpu.load.c 59.4 max over 60 s\ncpu.load.slowest.khz 1416000\n"
        )
        self.assertEqual(regression.measured(folder, "cpu", "cpu.load.c"), 59.4)
        self.assertIsNone(regression.measured(folder, "cpu", "ddr.rate"))
        self.assertIsNone(regression.measured(folder, "gpu", "glmark2.score"))
        self.assertEqual(regression.shown(1416000.0), "1416000")

    def test_lines_sharing_a_reason_are_one_and_a_line_alone_stays_whole(self) -> None:
        lines = [
            "video: video decode h264 16384x8640: past this box's memory, needs 2430 MB",
            "video: video decode hevc 8192x8192: past this box's memory, needs 1152 MB",
            "display-full: lut: no plane with SUNXI_CDC_LUT3D, or no writeback connector",
            "power: suspend",
        ]
        self.assertEqual(
            regression.grouped(lines),
            [
                "video: past this box's memory, 2 cases: decode h264 16384x8640, decode hevc 8192x8192",
                "display-full: lut: no plane with SUNXI_CDC_LUT3D, or no writeback connector",
                "power: suspend",
            ],
        )

    def test_a_step_s_start_is_its_end_less_its_seconds_over_midnight_too(self) -> None:
        for end, seconds, start in [("18:52:50", 50, "18:52:00"), ("00:00:30", 90, "23:59:00")]:
            with self.subTest(end=end):
                self.assertEqual(regression.clock_before(end, seconds), start)

    def test_steps_come_from_the_run_log_in_order(self) -> None:
        log = Path(tempfile.mkdtemp()) / "run.log"
        log.write_text(
            "18:51:32 7.3.6-k: booting l0\n18:52:50 7.3.6-k: system exit 1, 50 s\n"
            "18:53:56 7.3.6-k: cpu exit 0, 67 s\n18:54:00 6.1-k: cpu exit 0, 9 s\n"
        )
        self.assertEqual(
            regression.step_runs(log, "7.3.6-k"),
            [("system", 50, "18:52:50"), ("cpu", 67, "18:53:56")],
        )

    def test_a_step_s_mark_is_its_worst_verdict(self) -> None:
        for found, mark in [
            (Verdicts(5, ["a"], ["b"]), "FAIL 1"),
            (Verdicts(5, [], ["b", "c"]), "UNTESTED 2"),
            (Verdicts(5, [], []), "PASS"),
        ]:
            with self.subTest(mark=mark):
                self.assertEqual(regression.verdict_mark(found), mark)

    def test_the_report_is_ascii_its_glyphs_in_words(self) -> None:
        self.assertEqual(
            regression.ascii_only("✅ ≥ 1920x1080 — 47 °C ·x"), "pass >= 1920x1080 - 47 C ;x"
        )
        self.assertEqual(regression.ascii_only("é"), "?")

    def test_a_command_the_box_prints_no_path_for_is_missing(self) -> None:
        needed = ["fio", "mpv", "vainfo"]
        self.assertEqual(regression.missing_commands(needed, "/usr/bin/vainfo\n"), ["fio", "mpv"])
        self.assertEqual(regression.missing_commands(needed, "/a/fio\n/b/mpv\n/c/vainfo"), [])

    def test_only_the_commands_of_the_steps_in_scope_are_needed(self) -> None:
        self.assertEqual(regression.needed_commands({"storage"}), ["fio"])
        self.assertEqual(regression.needed_commands({"video"}), ["v4l2-ctl"])
        self.assertEqual(regression.needed_commands(set()), [])

    def test_every_command_s_steps_are_regression_steps(self) -> None:
        names = {step.name for step in regression.steps("extended", "", "", "")}
        for command, (_, used) in regression.BOX_COMMANDS.items():
            with self.subTest(command=command):
                self.assertLessEqual(set(used), names)

    def test_probe_options_split_into_on_and_off(self) -> None:
        probe = Path(tempfile.mkdtemp()) / "probe.txt"
        probe.write_text(
            "PROBE system: RNG: works (rng)\nPROBE system: PCIe: does not work (none)\nexit 0\n"
        )
        self.assertEqual(
            regression.on_off_section(probe), "**On, 1:** system: RNG\n\n**Off, 1:** system: PCIe"
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

    def test_a_case_past_the_box_s_memory_says_so_and_is_no_fail(self) -> None:
        case = {"suite": "decode", "codec": "hevc10", "size": "8192x8192", "verdict": "memory"}
        found = self.verdicts(json.dumps(dict(case, why="needs 1440 MB, 900 MB free")) + "\n")
        self.assertEqual(
            (found.checks, found.fails, found.untested),
            (
                0,
                [],
                [
                    "video decode hevc10 8192x8192: past this box's memory, "
                    "needs 1440 MB, 900 MB free"
                ],
            ),
        )

    def test_a_failure_case_without_its_knob_is_untested_and_no_fail(self) -> None:
        case = {"suite": "failure", "codec": "h264", "size": "1920x1080", "verdict": "untested"}
        found = self.verdicts(json.dumps(dict(case, why="no fail_next_job")) + "\n")
        self.assertEqual(
            (found.checks, found.fails, found.untested),
            (0, [], ["video failure h264 1920x1080: untested, no fail_next_job"]),
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
        self.assertIn(
            "| video | PASS | 0 | 19.1 | 09:01:55 | 09:21:00 |",
            regression.steps_section(log, "6.1.172-tvb-rk35xx", self.dir),
        )
        self.assertEqual(duration(log, "6.12.69-tvb-rk35xx"), "1 min")
        self.assertEqual(duration(log, "7.3.4-tvb-sunxi64"), "?")

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

    def test_a_step_entry_skips_the_step_where_it_names(self) -> None:
        path = self.dir / "known.conf"
        path.write_text("h96max-h313 6.18* step:recovery  # the watchdog test hangs it\n")
        known = Known.load(path)
        self.assertEqual(
            results.skipped(known, "h96max-h313", "6.18.63-tvb-sunxi64", "recovery"),
            "the watchdog test hangs it",
        )
        self.assertIsNone(results.skipped(known, "h96max-h313", "7.3.4-tvb-sunxi64", "recovery"))
        self.assertIsNone(results.skipped(known, "tanix-tx1-v2", "6.18.63-tvb-sunxi64", "recovery"))

    def test_a_line_that_is_not_a_step_is_refused(self) -> None:
        path = self.dir / "known.conf"
        path.write_text("r69-1 * ^network: bt\\.find: 0$  # a failure, not a step\n")
        with self.assertRaises(ValueError):
            Known.load(path)

    def test_the_repo_s_known_conf_loads(self) -> None:
        Known.load(Path(regression.__file__).parent / "known.conf")

    def test_a_run_past_its_profile_s_usual_time_is_flagged(self) -> None:
        (self.dir / "host.txt").write_text("profile short\n")
        (self.dir / "run.log").write_text(
            "23:55:00 6.1: booting l1\n00:15:00 done: the default back\n"
        )
        self.assertEqual(regression.over_budget(self.dir), " (slow: 20 min, short's usual 12)")
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
        deployment = regression.Deployment("h96max-m2-plus", box, "short", "plex", frozenset())
        with mock.patch.object(regression, "DEBS", debs):
            said = deployment.install(["6.1.172-tvb-rk35xx"])
        sent = [c.args[0] for c in box.run.call_args_list if c.args[0].startswith("cat > ")]
        self.assertEqual(sent, [f"cat > {regression.PACKAGES}/{board}"])
        installed = [a for a in box.root.call_args.args if a.endswith(".deb")]
        self.assertEqual(installed, [f"{regression.PACKAGES}/{board}"])
        self.assertTrue(any("rm -f old.deb" in c.args[0] for c in box.run.call_args_list))
        self.assertTrue(said.startswith("1 of 2 packages, 1 sent"))


class InstallReleasedTest(unittest.TestCase):
    def test_the_kernels_option_picks_the_metapackages_their_kernels_from_apt(self) -> None:
        depends = {
            "linux-image-tvb-rk35xx": "linux-image-6.1.172-tvb-rk35xx (= 6.1.172-7), tvb-aic8800-modules",
            "linux-image-tvb-rk35xx-next": "linux-image-6.12.69-tvb-rk35xx (= 6.12.69-7)",
            "linux-image-tvb-rk35xx-next2": "linux-image-7.3.4-tvb-rk35xx-next2 (= 7.3.4-1)",
        }
        for which, metas in (
            ("own", ["linux-image-tvb-rk35xx"]),
            ("next", ["linux-image-tvb-rk35xx-next"]),
            ("both", list(depends)[:2]),
            ("next2", ["linux-image-tvb-rk35xx-next2"]),
        ):
            with self.subTest(which=which):
                box = mock.MagicMock()
                box.run.return_value = "\n".join(depends[m] for m in metas)
                deployment = regression.Deployment(
                    "h96max-rk3528", box, "short", "plex", frozenset()
                )
                releases = deployment.install_released(which)
                wanted = box.root.call_args.args[1].split()
                self.assertEqual(wanted[: len(metas)], metas)
                self.assertIn("tvb-h96max-rk3528", wanted)
                kernels = [depends[m].split()[0].removeprefix("linux-image-") for m in metas]
                self.assertEqual(releases, kernels)


class PrepareTest(unittest.TestCase):
    def test_released_builds_nothing_and_still_makes_the_clips(self) -> None:
        with (
            mock.patch.object(regression, "ROOT", Path(tempfile.mkdtemp())),
            mock.patch.object(regression.subprocess, "run") as run,
        ):
            regression.prepare("h96max-rk3528", released=True)
        self.assertNotIn("build.sh", " ".join(str(c.args[0][0]) for c in run.call_args_list))
        self.assertEqual(run.call_count, 2)  # video.py's clips and the VA suite's


START = argparse.Namespace(
    profile="short",
    box="a=root@a",
    iperf="plex",
    kernels="both",
    released=False,
    enable=[],
    disable=[],
)


class StartedTest(unittest.TestCase):
    def test_a_run_s_steps_are_the_profile_s_less_the_experimental_ones(self) -> None:
        every = {step.name for step in regression.steps("default", "", "", "")}
        self.assertEqual(regression.scope_of("default", [], []), every - {"va"})
        self.assertIn("va", regression.scope_of("default", ["va"], []))
        self.assertNotIn("video", regression.scope_of("default", [], ["video"]))
        self.assertNotIn("conformance", regression.scope_of("short", [], []))

    def test_a_step_no_run_has_is_refused_by_name(self) -> None:
        with self.assertRaisesRegex(ValueError, "no step vidoe"):
            regression.scope_of("default", [], ["vidoe"])

    def test_a_box_whose_build_fails_is_not_started_and_says_why(self) -> None:
        failed = subprocess.CalledProcessError(1, ["build.sh", "board", "a"])
        out = io.StringIO()
        with (
            mock.patch.object(regression, "preflight"),
            mock.patch.object(regression, "prepare", side_effect=failed),
            mock.patch.object(regression, "start") as start,
            mock.patch("sys.stdout", out),
        ):
            self.assertFalse(regression.started(START))
        start.assert_not_called()
        self.assertTrue(out.getvalue().startswith("a: not started:"))

    def test_a_box_lacking_a_tool_is_refused_before_anything_is_built(self) -> None:
        lacking = regression.NotStarted("the box lacks fio: apt install fio")
        out = io.StringIO()
        with (
            mock.patch.object(regression, "preflight", side_effect=lacking),
            mock.patch.object(regression, "prepare") as prepare,
            mock.patch("sys.stdout", out),
        ):
            self.assertFalse(regression.started(START))
        prepare.assert_not_called()
        self.assertIn("apt install fio", out.getvalue())

    def test_a_box_answering_as_another_board_is_refused(self) -> None:
        box = mock.Mock()
        box.raw.return_value = b"h96max-m20\n"
        with mock.patch.object(regression, "Box", return_value=box):
            with self.assertRaisesRegex(regression.NotStarted, "answers as h96max-m20, not r69-1"):
                regression.preflight("root@cnc", "plex", set(), "r69-1")

    def test_an_address_unlike_another_run_s_is_a_failure(self) -> None:
        now, last = Path(tempfile.mkdtemp()), Path(tempfile.mkdtemp())
        (now / "network.txt").write_text(
            "addr.wlan0 8a:00:33:d3:75:46 type 0\naddr.eth0 c4:2a type 0\n"
        )
        (last / "network.txt").write_text(
            "addr.wlan0 8a:00:33:65:64:b6 type 0\naddr.eth0 c4:2a type 0\n"
        )
        self.assertEqual(
            regression.moved_addresses(now, {"the last run": last, "the own kernel": None}),
            ["network: addr.wlan0 8a:00:33:d3:75:46, 8a:00:33:65:64:b6 in the last run"],
        )

    def test_another_pvtm_level_than_the_own_kernel_s_is_a_failure(self) -> None:
        now, own = Path(tempfile.mkdtemp()), Path(tempfile.mkdtemp())
        (now / "cpu.txt").write_text("pvtm.cpu 1543 L5\npvtm.gpu 812 L2\n")
        (own / "cpu.txt").write_text("pvtm.cpu 1543 L4\npvtm.gpu 812 L2\n")
        self.assertEqual(
            regression.pvtm_moved(now, own), ["cpu: pvtm.cpu L5, L4 on the own kernel"]
        )
        self.assertEqual(regression.pvtm_moved(now, None), [])

    def test_a_kernel_s_recorded_board_is_its_system_step_s(self) -> None:
        folder = Path(tempfile.mkdtemp())
        self.assertEqual(regression.identity_of(folder), "")
        (folder / "system.txt").write_text("kernel 7.3.6\nidentity.id r69-1\n")
        self.assertEqual(regression.identity_of(folder), "r69-1")

    def test_a_fresh_folder_never_reuses_one(self) -> None:
        base = Path(tempfile.mkdtemp()) / "2026-11-14-1904"
        self.assertEqual(regression.fresh(base), base)
        base.mkdir()
        self.assertEqual(regression.fresh(base).name, "2026-11-14-1904-2")


class ProbeTableTest(unittest.TestCase):
    def test_every_probe_line_is_shown_and_the_ones_not_working_counted(self) -> None:
        with tempfile.TemporaryDirectory() as root:
            lines = ["PROBE video: codec VC-1: does not work (none)"]
            lines += ["PROBE system: RNG: works (rk)"]
            (Path(root) / "probe.txt").write_text("\n".join(lines + ["exit 0"]))
            table = regression.probe_table(Path(root))
        self.assertIn("probe: 1 options work, 1 do not", table)
        self.assertIn("    video: codec VC-1: does not work (none)", table)
        self.assertNotIn("exit 0", table)

    def test_no_probe_output_is_no_table(self) -> None:
        with tempfile.TemporaryDirectory() as root:
            self.assertEqual(regression.probe_table(Path(root)), "")


if __name__ == "__main__":
    unittest.main()
