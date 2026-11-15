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
        ]
        for key, value, expected in cases:
            with self.subTest(key=key, value=value):
                self.assertEqual(box.verdict(key, value), expected)


if __name__ == "__main__":
    unittest.main()
