"""Each board tree names its box as "<BOARD_NAME> (<BOARD_PCB>)", from its board.conf."""

from __future__ import annotations

import re
import unittest
from pathlib import Path

BOARDS = Path(__file__).resolve().parents[1] / "boards"
MODEL = re.compile(r'^\s*model = "([^"]*)";', re.MULTILINE)


def conf(path: Path) -> dict[str, str]:
    return {k: v.strip('"') for k, v in re.findall(r"^(BOARD_\w+)=(.*)$", path.read_text(), re.M)}


class ModelTest(unittest.TestCase):
    def test_every_tree_names_the_board_and_its_pcb(self) -> None:
        checked = 0
        for board in sorted(BOARDS.glob("*/board.conf")):
            values = conf(board)
            expected = f"{values['BOARD_NAME']} ({values['BOARD_PCB']})"
            for tree in ("board.dts", "uboot.dts"):
                path = board.parent / tree
                if not path.exists():
                    continue
                found = MODEL.search(path.read_text())
                with self.subTest(str(path)):
                    self.assertIsNotNone(found)
                    self.assertEqual(found.group(1) if found else "", expected)
                checked += 1
        self.assertGreater(checked, 0)


if __name__ == "__main__":
    unittest.main()
