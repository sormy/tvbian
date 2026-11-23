"""tools/validate/box.py: soak jobs end with the soak, and each rule fails what it should."""

from __future__ import annotations

import subprocess
import sys
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools/validate"))
import box  # noqa: E402


class SoakJobTest(unittest.TestCase):
    def job(self, script: str) -> subprocess.Popen[str]:
        return subprocess.Popen(["sh", "-c", script], text=True, start_new_session=True)

    def test_a_job_past_the_soak_is_stopped_and_ran_its_course(self) -> None:
        job = self.job("sleep 100")
        with mock.patch.object(box, "SOAK_GRACE_S", 0.2):
            self.assertEqual(box.ended(job), 0)
        self.assertIsNotNone(job.poll())

    def test_a_job_that_failed_keeps_its_status(self) -> None:
        self.assertEqual(box.ended(self.job("exit 3")), 3)


class InputTest(unittest.TestCase):
    def test_a_plugged_in_keyboard_is_not_the_board_s(self) -> None:
        for device, usb in [
            ("/sys/devices/platform/soc/5311000.usb/usb4/4-1/4-1:1.0/0003:046D:C534.0001", True),
            ("/sys/devices/platform/soc/5100000.usb/musb-hdrc.2.auto/usb1/1-1/1-1:1.1", True),
            ("/sys/devices/platform/gpio-keys", False),
            ("/sys/devices/platform/soc/7040000.ir/rc/rc0", False),
        ]:
            with self.subTest(device=device):
                self.assertEqual(box.on_usb(device), usb)


class NetworkTest(unittest.TestCase):
    def test_a_usb_adapter_is_not_the_board_s(self) -> None:
        devices = {
            "/sys/class/net/end0/device": "/sys/devices/platform/soc/5020000.ethernet",
            "/sys/class/net/wlan0/device": "/sys/devices/platform/soc/4021000.mmc/mmc_host/mmc1",
            "/sys/class/net/enx00e04c/device": "/sys/devices/platform/soc/5200000.usb/usb1/1-1",
        }
        found = [f"{d.rsplit('/', 1)[0]}/phydev" for d in devices]
        with (
            mock.patch.object(box.glob, "glob", return_value=found),
            mock.patch.object(box.os.path, "realpath", side_effect=devices.__getitem__),
        ):
            self.assertEqual(box.board_nets("phydev"), ["end0", "wlan0"])


class VerdictTest(unittest.TestCase):
    def test_each_rule_fails_what_it_should(self) -> None:
        cases = [
            ("fio.seq.read", "87.8 MB/s 87 IOPS", None),
            ("fio.seq.read", "failed", "FAIL"),
            ("fio.seq.read", "failed, error 5", "FAIL"),
            ("wifi.reload", "default: 3 s", None),
            ("wifi.reload", "unload failed", "FAIL"),
            ("wifi.reload", "address lost", "FAIL"),
            ("wifi.region.DE", "DE", None),
            ("wifi.region.DE", "98, not taken", "FAIL"),
            ("suspend.s2idle", "same boot, slept, 22 s for 20", None),
            ("suspend.s2idle", "same boot, did not sleep, 0 s for 20", "FAIL"),
            ("cpu.load", "failed, stress-ng exit 1", "FAIL"),
            ("soak.jobs", "0 0 0", None),
            ("soak.jobs", "0 1 0", "FAIL"),
            ("wifi.up.mbits", "failed: no address on wlan0", "FAIL"),
            ("fio", "no fio", "UNTESTED"),
            ("soak.server", "failed: plex not answering after 30 s", "FAIL"),
            ("mmc.errors", "0", None),
            ("mmc.errors", "1: mmc2: error -110 whilst initialising MMC card", "FAIL"),
            ("usb.hubs.external", "1", None),  # a hub plugged in or on the board: the reader judges
        ]
        for key, value, expected in cases:
            with self.subTest(key=key, value=value):
                self.assertEqual(box.verdict(key, value), expected)


if __name__ == "__main__":
    unittest.main()


class IommuLinesTest(unittest.TestCase):
    def test_an_iommu_shared_with_its_master_is_left_out(self) -> None:
        interrupts = """           CPU0       CPU1
 24:          0          0     GICv2 127 Level     ff740800.iommu
 37:     153921          0     GICv2 141 Level     ff847e00.iommu, ff840000.vop
 62:          5          0     GICv2 121 Level     gpmmu
 70:        900          0     GICv2 150 Edge      ff8d0000.hdmi
"""
        lines = box.iommu_lines(interrupts)
        self.assertEqual([l.split(":")[0].strip() for l in lines], ["24", "62"])
