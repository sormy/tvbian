"""tools/validate/screen.py: where two captures differ, told apart from rounding."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools/validate"))
import screen  # noqa: E402

WIDTH = 64


def frame() -> bytearray:
    return bytearray(WIDTH * 32 * 4)


class WhereTest(unittest.TestCase):
    def test_rounding_is_no_visible_difference(self) -> None:
        a, b = frame(), frame()
        b[(20 * WIDTH + 5) * 4] = 2
        self.assertEqual(
            screen.where(bytes(a), bytes(b), WIDTH), "no pixel off by more than 8, the worst by 2"
        )

    def test_a_wrong_tile_is_found_where_it_is(self) -> None:
        a, b = frame(), frame()
        for y in range(16):
            for x in range(16, 32):
                b[(y * WIDTH + x) * 4 + 1] = 200
        self.assertEqual(
            screen.where(bytes(a), bytes(b), WIDTH),
            "256 pixels off by more than 8, the worst by 200, in 1 tiles over 16x16 at 16,0",
        )


class CompareTest(unittest.TestCase):
    def test_off_by_one_is_the_same_picture_and_off_by_two_is_not(self) -> None:
        a = bytes(1000)
        self.assertEqual(screen.compare(a, bytes([1] * 1000))[0], 1.0)
        self.assertEqual(screen.compare(a, bytes([2] * 1000))[0], 0.0)


if __name__ == "__main__":
    unittest.main()
