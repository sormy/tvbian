"""tools/validate/onbox.py: boot entries, and state that outlives a reboot."""

from __future__ import annotations

import sys
import tempfile
import json
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools/validate"))
import onbox  # noqa: E402

EXTLINUX = """default l1
label l0
	linux /boot/vmlinuz-7.3.4-tvb-sunxi64
label l0r
	linux /boot/vmlinuz-7.3.4-tvb-sunxi64
label l1
	linux /boot/vmlinuz-6.18.63-tvb-sunxi64
"""


class OnboxTest(unittest.TestCase):
    def setUp(self) -> None:
        self.dir = Path(tempfile.mkdtemp())
        onbox.EXTLINUX = self.dir / "extlinux.conf"
        onbox.EXTLINUX.write_text(EXTLINUX)
        onbox.STATE = self.dir / "state.json"

    def test_the_entry_not_its_recovery_twin(self) -> None:
        self.assertEqual(onbox.entry_for("7.3.4-tvb-sunxi64"), "l0")
        self.assertEqual(onbox.entry_for("6.18.63-tvb-sunxi64"), "l1")
        self.assertIsNone(onbox.entry_for("6.18.62-tvb-sunxi64"))

    def test_the_default_set_and_read_back(self) -> None:
        self.assertEqual(onbox.default_entry(), "l1")
        onbox.set_default("l0")
        self.assertEqual(onbox.default_entry(), "l0")

    def test_state_with_nothing_pending_survives_a_save(self) -> None:
        state = onbox.State(default="l1", kernel=1, steps_done=["system"])
        state.save()
        self.assertEqual(onbox.State.load(), state)

    def test_state_with_a_pending_reboot_survives_a_save(self) -> None:
        state = onbox.State(default="l1", kernel=1, steps_done=["system"], recovery=1)
        state.pending = onbox.Pending("panic", "boot-a", 1.5, "")
        with mock.patch.object(onbox.os, "sync") as sync:
            state.save()
        sync.assert_called_once()  # the panic comes next: an unsynced save loops the box
        self.assertEqual(onbox.State.load(), state)

    def test_a_run_boots_the_kernel_it_already_runs(self) -> None:
        """What the run installed is live only after a boot: the first kernel's included."""
        onbox.HERE, onbox.RESULTS = self.dir, self.dir / "results"
        plan = {
            "board": "tanix-tx1-v2",
            "kernels": ["6.18.63-tvb-sunxi64"],
            "steps": [],
            "reboots": 0,
        }
        (self.dir / "plan.json").write_text(json.dumps(plan))
        running = SimpleNamespace(release="6.18.63-tvb-sunxi64")
        with (
            mock.patch.object(onbox.os, "uname", return_value=running),
            mock.patch.object(onbox, "boot_id", return_value="boot-a"),
            mock.patch.object(onbox, "reboot") as reboot,
        ):
            onbox.step()
        reboot.assert_called_once()
        pending = onbox.State.load().pending
        self.assertEqual(pending.kind if pending else None, "switch")
        self.assertEqual(onbox.default_entry(), "l1")

    def gated(self, known: str) -> Path:
        """A plan whose system step fails a check, then a video step that needs it: its folder."""
        onbox.HERE, onbox.RESULTS = self.dir, self.dir / "results"
        (self.dir / "known.conf").write_text(known)
        failing = onbox.Step(
            "system", ["sh", "-c", "echo 'dmesg.errors 3'; echo 'FAIL dmesg.errors'"], 30
        )
        video = onbox.Step("video", ["sh", "-c", "touch ran"], 30, ["system"])
        plan = onbox.Plan("tanix-tx1-v2", ["6.18.63-tvb-sunxi64"], [failing, video], 0)
        out = self.dir / "results" / "6.18.63-tvb-sunxi64"
        onbox.carry_on(plan, onbox.State(), out)
        return out

    def test_a_new_failure_gates_the_steps_that_need_it(self) -> None:
        out = self.gated("")
        self.assertFalse((self.dir / "ran").exists())
        self.assertIn("UNTESTED video", (out / "video.txt").read_text())

    def test_a_known_failure_does_not(self) -> None:
        self.gated("tanix-* * ^system: dmesg\\.errors: 3$  # known\n")
        self.assertTrue((self.dir / "ran").exists())

    def test_a_step_that_reset_the_box_is_failed_not_rerun(self) -> None:
        onbox.HERE, onbox.RESULTS = self.dir, self.dir / "results"
        out = self.dir / "results" / "6.18.63-tvb-sunxi64"
        out.mkdir(parents=True)
        (out / "soak.txt").write_text("soak.minutes 7\n")
        state = onbox.State(pending=onbox.Pending("step", "boot-a", 0.0, "soak"))
        soak = onbox.Step("soak", ["sh", "-c", "touch ran"], 30)
        plan = onbox.Plan("tanix-tx1-v2", ["6.18.63-tvb-sunxi64"], [soak], 0)
        with mock.patch.object(onbox, "boot_id", return_value="boot-b"):
            onbox.ended(state, out)
            self.assertTrue(onbox.carry_on(plan, state, out))
        self.assertFalse((self.dir / "ran").exists())
        self.assertEqual(
            (out / "soak.txt").read_text(), "soak.minutes 7\nFAIL soak: the box reset during it\n"
        )

    def test_a_panic_that_waited_on_a_power_cycle_skips_the_watchdog(self) -> None:
        onbox.PSTORE = self.dir / "pstore"
        for back_s, recovery, tail in [
            (40.0, 1, []),
            (900.0, 2, ["FAIL recovery.panic: no timely reset", "UNTESTED recovery.watchdog"]),
        ]:
            with self.subTest(back_s=back_s):
                out = self.dir / f"back-{back_s:.0f}"
                out.mkdir()
                state = onbox.State(pending=onbox.Pending("panic", "boot-a", 0.0), recovery=1)
                with (
                    mock.patch.object(onbox, "boot_id", return_value="boot-b"),
                    mock.patch.object(onbox, "booted_at", return_value=back_s),
                ):
                    onbox.ended(state, out)
                self.assertEqual(state.recovery, recovery)
                self.assertEqual((out / "recovery.txt").read_text().splitlines()[1:], tail)

    def test_a_crashed_step_ends_the_run_and_nothing_after_it_runs(self) -> None:
        onbox.HERE, onbox.RESULTS = self.dir, self.dir / "results"
        dying = onbox.Step("soak", ["python3", "-c", "raise TimeoutError('glmark2')"], 30)
        after = onbox.Step("video", ["sh", "-c", "touch ran"], 30)
        plan = {"board": "tanix-tx1-v2", "kernels": ["6.18.63-tvb-sunxi64"], "reboots": 0}
        plan["steps"] = [vars(dying), vars(after)]
        (self.dir / "plan.json").write_text(json.dumps(plan))
        (self.dir / "known.conf").write_text("")
        onbox.State(default="l1", booted=True).save()
        with (
            mock.patch.object(onbox, "boot_id", return_value="boot-a"),
            mock.patch.object(onbox, "reboot"),
            mock.patch.object(onbox.subprocess, "run"),
        ):
            onbox.step()
        self.assertFalse((self.dir / "ran").exists())
        self.assertIn("soak: TimeoutError: glmark2", (self.dir / "results" / "crashed").read_text())
        self.assertFalse((self.dir / "results" / "done").exists())

    def test_a_step_known_conf_skips_is_untested_not_run(self) -> None:
        out = self.gated("tanix-* * step:video  # hangs the box until the fix lands\n")
        self.assertFalse((self.dir / "ran").exists())
        self.assertIn(
            "video skipped, known.conf: hangs the box until the fix lands",
            (out / "video.txt").read_text(),
        )


if __name__ == "__main__":
    unittest.main()
