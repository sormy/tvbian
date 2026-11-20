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


if __name__ == "__main__":
    unittest.main()
