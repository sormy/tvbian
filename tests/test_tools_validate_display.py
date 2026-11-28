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


def systemctl(state: str) -> tuple[mock.MagicMock, list[list[str]]]:
    """systemctl answering every unit with state, as is-active prints it."""
    calls: list[list[str]] = []

    def run(command: list[str], **_: object) -> subprocess.CompletedProcess[str]:
        calls.append(command)
        return subprocess.CompletedProcess(command, 0 if state == "active" else 3, f"{state}\n")

    return mock.MagicMock(side_effect=run), calls


class DisplayFreeTest(unittest.TestCase):
    def test_a_running_session_is_stopped_for_the_run_and_started_after(self) -> None:
        run, calls = systemctl("active")
        with mock.patch.object(display.subprocess, "run", run):
            with display.display_free():
                stops = [c[2] for c in calls if c[1] == "stop"]
                self.assertEqual(stops, list(display.SESSION_UNITS))
        starts = [c[2] for c in calls if c[1] == "start"]
        self.assertEqual(starts, list(reversed(display.SESSION_UNITS)))

    def test_a_unit_caught_restarting_is_stopped_and_not_brought_back(self) -> None:
        for state in ("activating", "deactivating"):
            with self.subTest(state=state):
                run, calls = systemctl(state)
                with mock.patch.object(display.subprocess, "run", run):
                    with display.display_free():
                        pass
                self.assertEqual(
                    [c[2] for c in calls if c[1] == "stop"], list(display.SESSION_UNITS)
                )
                self.assertEqual([c for c in calls if c[1] == "start"], [])

    def test_a_stopped_session_is_stopped_again_its_queued_restart_cancelled(self) -> None:
        for state in ("inactive", "failed"):
            with self.subTest(state=state):
                run, calls = systemctl(state)
                with mock.patch.object(display.subprocess, "run", run):
                    with display.display_free():
                        pass
                self.assertEqual(
                    [c[2] for c in calls if c[1] == "stop"], list(display.SESSION_UNITS)
                )
                self.assertEqual([c for c in calls if c[1] == "start"], [])

    def test_a_failing_run_still_brings_the_session_back(self) -> None:
        run, calls = systemctl("active")
        with mock.patch.object(display.subprocess, "run", run):
            with self.assertRaises(RuntimeError), display.display_free():
                raise RuntimeError("a check crashed")
        self.assertEqual(calls[-1], ["systemctl", "start", display.SESSION_UNITS[0]])


class CrtcBackOnTest(unittest.TestCase):
    def box(self, active: int) -> SimpleNamespace:
        props = {"ACTIVE": (1, active, None), "MODE_ID": (2, 0, None), "CRTC_ID": (3, 0, None)}
        drm = SimpleNamespace(props=lambda *_: props, blob=mock.Mock(return_value=77))
        box = SimpleNamespace(drm=drm, crtc=10, hdmi_connector=20, mode=b"mode")
        box.prop = lambda obj, kind, name: props[name][0]
        return box

    def test_an_off_crtc_gets_the_run_s_mode_back_in_the_commit(self) -> None:
        box, changes = self.box(active=0), {}
        self.assertEqual(display.Box.crtc_back_on(box, changes), 77)
        self.assertEqual(changes, {10: {2: 77, 1: 1}, 20: {3: 10}})

    def test_an_on_crtc_is_left_alone(self) -> None:
        box, changes = self.box(active=1), {}
        self.assertIsNone(display.Box.crtc_back_on(box, changes))
        self.assertEqual(changes, {})


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
            mock.patch.object(display, "against", return_value=True),
            mock.patch.object(display, "hdmi_writeback_available", checks.capture),
            mock.patch("builtins.print"),
        ):
            display.main([], False)
        self.assertEqual(
            checks.mock_calls,
            [mock.call.hdmi(True), mock.call.capture(), mock.call.composite(), mock.call.capture()],
        )
        box.check.assert_called_once_with("HDMI writeback after composite", False)


class AgainstTest(unittest.TestCase):
    def run_against(self, synthetic: bool) -> tuple[bool, SimpleNamespace, mock.Mock]:
        box = SimpleNamespace(passes=1, failures=0)
        sink_box = SimpleNamespace(passes=2, failures=1, drm=SimpleNamespace(fd=7))
        check = mock.Mock()
        with (
            mock.patch.object(display, "hdr_sink", side_effect=lambda *_: nullcontext(synthetic)),
            mock.patch.object(display, "Box", return_value=sink_box),
            mock.patch.object(display.os, "close") as close,
        ):
            ran = display.against(box, b"edid", check)
        if synthetic:
            close.assert_called_once_with(7)
        return ran, box, check

    def test_results_on_a_synthetic_screen_are_added(self) -> None:
        ran, box, check = self.run_against(True)
        self.assertTrue(ran)
        check.assert_called_once()
        self.assertEqual((box.passes, box.failures), (3, 1))

    def test_nothing_runs_where_no_screen_stands_in(self) -> None:
        ran, box, check = self.run_against(False)
        self.assertFalse(ran)
        check.assert_not_called()
        self.assertEqual((box.passes, box.failures), (1, 0))


class SurroundEdidTest(unittest.TestCase):
    def cta_blocks(self, edid: bytes) -> dict[int, bytes]:
        ext = edid[128:]
        blocks, at = {}, 4
        while at < ext[2]:
            tag, length = ext[at] >> 5, ext[at] & 31
            blocks[tag] = ext[at + 1 : at + 1 + length]
            at += 1 + length
        return blocks

    def test_surround_offers_8_channel_lpcm_on_7_1_speakers(self) -> None:
        edid = display.hdr_edid(display.SINKS["SDR"], surround=True)
        blocks = self.cta_blocks(edid)
        self.assertEqual(blocks[1], bytes([0x0F, 0x7F, 0x07]))
        self.assertEqual(blocks[4], bytes([0x4F, 0x00, 0x00]))
        self.assertEqual([sum(edid[i : i + 128]) & 0xFF for i in (0, 128)], [0, 0])

    def test_stereo_sets_hdmi_video_present_and_3d_present(self) -> None:
        vsdb = self.cta_blocks(display.hdr_edid(display.SINKS["SDR"], stereo=True))[3]
        self.assertEqual(vsdb[:3], bytes([0x03, 0x0C, 0x00]))
        self.assertEqual(vsdb[7:], bytes([0x20, 0x80, 0x00]))
        self.assertEqual(len(self.cta_blocks(display.hdr_edid(display.SINKS["SDR"]))[3]), 8)

    def test_without_surround_there_is_no_audio_block(self) -> None:
        blocks = self.cta_blocks(display.hdr_edid(display.SINKS["SDR"]))
        self.assertNotIn(1, blocks)
        self.assertNotIn(4, blocks)


if __name__ == "__main__":
    unittest.main()


class CapturePixelTest(unittest.TestCase):
    """A writeback capture's pixel, read back by its DRM format's memory layout."""

    def buffer(self, fourcc: int, data: bytes, pitch: int) -> display.Buffer:
        buf = display.Buffer.__new__(display.Buffer)
        buf.format, buf.map, buf.pitch, buf.width, buf.height = fourcc, bytearray(data), pitch, 1, 1
        return buf

    def test_each_format_reads_red(self) -> None:
        for name, fourcc, data, want in (
            ("RGB888, B first in memory", display.RGB888, bytes((40, 40, 200)), (200, 40, 40)),
            (
                "RGB565, little endian",
                display.RGB565,
                (0xC945).to_bytes(2, "little"),
                (206, 40, 41),
            ),
            ("XRGB8888", display.XRGB8888, (0x00C82828).to_bytes(4, "little"), (200, 40, 40)),
        ):
            with self.subTest(name):
                self.assertEqual(self.buffer(fourcc, data, len(data)).pixel(0, 0), want)
