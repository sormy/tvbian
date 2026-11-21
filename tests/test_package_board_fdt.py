"""package/board-fdt.postinst and .postrm: each kernel's link to the tree it boots."""

import os
import subprocess
import tempfile
import unittest
from pathlib import Path

HOOKS = Path(__file__).resolve().parent.parent / "package"


def hook(name: str, links: Path, version: str) -> subprocess.CompletedProcess[str]:
    env = {**os.environ, "TVB_FDT_LINKS": str(links)}
    command = ["sh", str(HOOKS / f"board-fdt.{name}"), version]
    return subprocess.run(command, env=env, capture_output=True, text=True)


def shipped(root: Path, *trees: str) -> Path:
    """The board package's layout: its trees, and beside them the directory of links."""
    for tree in trees:
        (root / tree).write_bytes(b"")
    return root / "fdt"


class BoardFdtTest(unittest.TestCase):
    def test_a_kernel_links_the_tree_translated_for_it(self) -> None:
        cases = [("7.3.4-tvb-rk35xx-next2", "board-next2.dtb"), ("6.1.172-tvb-rk35xx", "board.dtb")]
        for version, tree in cases:
            with self.subTest(version=version), tempfile.TemporaryDirectory() as tmp:
                links = shipped(Path(tmp), "board.dtb", "board-next2.dtb")
                hook("postinst", links, version)
                hook("postinst", links, version)  # a reinstall relinks in place
                self.assertEqual(os.readlink(links / version / "board.dtb"), f"../../{tree}")

    def test_a_kernel_whose_tree_the_board_lacks_fails_unlinked(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            links = shipped(Path(tmp), "board.dtb")
            result = hook("postinst", links, "7.3.5-tvb-rk35xx-next2")
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("board-next2.dtb", result.stderr)
            self.assertFalse((links / "7.3.5-tvb-rk35xx-next2").exists())

    def test_a_removed_kernel_takes_its_link(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            links = shipped(Path(tmp), "board.dtb")
            hook("postinst", links, "6.12.69-tvb-rk35xx")
            hook("postrm", links, "6.12.69-tvb-rk35xx")
            self.assertFalse((links / "6.12.69-tvb-rk35xx").exists())


if __name__ == "__main__":
    unittest.main()
