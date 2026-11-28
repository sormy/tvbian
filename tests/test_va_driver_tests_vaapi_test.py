from __future__ import annotations

import io
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "va-driver/tests"))
import vaapi_test  # noqa: E402


class BoxTest(unittest.TestCase):
    def test_a_box_without_the_driver_has_nothing_to_test(self) -> None:
        empty = tempfile.mkdtemp()
        out = io.StringIO()
        argv = ["vaapi_test.py", "box", "--driver-dir", empty, "--clips", empty]
        with mock.patch.object(sys, "argv", argv), mock.patch("sys.stdout", out):
            self.assertEqual(vaapi_test.main(), vaapi_test.NOTHING_TO_TEST)
        self.assertIn("tvb_drv_video.so: the driver is not installed", out.getvalue())


class ProbeTest(unittest.TestCase):
    def test_a_missing_probe_reports_its_path(self) -> None:
        probe = Path("/usr/lib/tvb/vaapi-probe")
        setup = vaapi_test.Setup(Path("/usr/lib"), probe, "tvb", "", "", Path("."), Path("."), True)
        with (
            mock.patch.object(Path, "exists", return_value=False),
            mock.patch.object(vaapi_test, "run") as run,
        ):
            self.assertEqual(
                list(vaapi_test.probe_case(setup)),
                [("probe.initialize", f"no {probe}")],
            )
        run.assert_not_called()


if __name__ == "__main__":
    unittest.main()
