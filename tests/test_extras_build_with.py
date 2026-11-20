"""extras/build-with.sh: the extras one builds against, and every extra after those it builds against."""

from __future__ import annotations

import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]

# browser builds with toolkit and engine, toolkit with engine; codec stands alone
CONFS = {
    "browser": 'BUILD_WITH="toolkit:libtoolkit0 engine:libengine-dev toolkit:libtoolkit-dev"',
    "codec": "PACKAGE=codec",
    "engine": "PACKAGE=libengine1",
    "toolkit": 'BUILD_WITH="engine:libengine1 engine:libengine-dev"',
}


class BuildWith(unittest.TestCase):
    def setUp(self) -> None:
        self.extras = Path(tempfile.mkdtemp()) / "extras"
        self.addCleanup(shutil.rmtree, self.extras.parent)
        self.extras.mkdir()
        shutil.copy(REPO / "extras/build-with.sh", self.extras)
        for name, conf in CONFS.items():
            (self.extras / name).mkdir()
            (self.extras / name / "extra.conf").write_text(conf + "\n")

    def build_with(self, arg: str) -> list[str]:
        done = subprocess.run(
            ["bash", str(self.extras / "build-with.sh"), arg],
            capture_output=True,
            text=True,
            check=True,
        )
        return done.stdout.split()

    def test_deps_are_the_extras_named_once_each(self) -> None:
        for name, deps in (
            ("browser", ["engine", "toolkit"]),
            ("toolkit", ["engine"]),
            ("codec", []),
        ):
            with self.subTest(name=name):
                self.assertEqual(self.build_with(name), deps)

    def test_order_puts_each_extra_after_those_it_builds_with(self) -> None:
        self.assertEqual(self.build_with("--order"), ["engine", "toolkit", "browser", "codec"])


if __name__ == "__main__":
    unittest.main()
