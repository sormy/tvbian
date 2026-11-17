"""extras/: an upstream release's own build.sh stamps the inputs extras/build.sh hands it.

The plan finds a published package by its X-Tvb-Inputs: a control without it reads as never
published, and the extra rebuilds every run.
"""

from __future__ import annotations

import re
import unittest
from pathlib import Path

EXTRAS = Path(__file__).resolve().parents[1] / "extras"


def own_builds() -> list[Path]:
    return sorted(EXTRAS.glob("*/build.sh"))


class ExtrasInputsTest(unittest.TestCase):
    def test_the_driver_hands_its_inputs_on(self) -> None:
        driver = (EXTRAS / "build.sh").read_text()
        self.assertRegex(driver, r'INPUTS=\$\(bash /repo/release/inputs\.sh extra "\$NAME"')
        self.assertRegex(driver, r'exec bash "\$EXTRA/build\.sh" "\$PACKAGE_VERSION" "\$INPUTS"')

    def test_every_own_build_stamps_them(self) -> None:
        self.assertTrue(own_builds(), "no extra builds itself: the test reads nothing")
        for build in own_builds():
            with self.subTest(build.parent.name):
                script = build.read_text()
                self.assertRegex(script, r"(?m)^INPUTS=\$2$")
                stamps = re.findall(r"(?m)^(?:XB-)?X-Tvb-Inputs: (.*)$", script)
                self.assertEqual(stamps, ["$INPUTS"])


if __name__ == "__main__":
    unittest.main()
