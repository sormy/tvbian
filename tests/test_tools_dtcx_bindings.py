"""tools/dtcx/bindings.py: a kernel's bindings with a conf's patches to them applied."""

from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools/dtcx"))
from bindings import BINDINGS, apply, binding_parts  # noqa: E402

BINDING = "properties:\n  reg: true\n"
PATCH = f"""Subject: [PATCH] mixed

--- a/drivers/x.c
+++ b/drivers/x.c
@@ -1 +1 @@
-old
+new
--- a/{BINDINGS}/x.yaml
+++ b/{BINDINGS}/x.yaml
@@ -1,2 +1,3 @@
 properties:
   reg: true
+  clocks: true
"""


class BindingsTest(unittest.TestCase):
    def test_only_a_patch_s_binding_parts_are_taken(self) -> None:
        parts = binding_parts(PATCH)
        self.assertIn(f"+++ b/{BINDINGS}/x.yaml", parts)
        self.assertNotIn("drivers/x.c", parts)

    def test_the_conf_s_binding_changes_land_on_the_kernel_s_bindings(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "kernel" / BINDINGS).mkdir(parents=True)
            (root / "kernel" / BINDINGS / "x.yaml").write_text(BINDING)
            (root / "x.patch").write_text(PATCH)
            (root / "none.patch").write_text("--- a/drivers/y.c\n+++ b/drivers/y.c\n")
            conf = root / "kernel.conf"
            conf.write_text(f'PATCHES="\n  .:{root}/none.patch\n  .:{root}/x.patch\n"\n')
            applied = apply(root / "kernel", conf, root / "out")
            self.assertEqual(applied, [f"{root}/x.patch"])
            yaml = (root / "out" / BINDINGS / "x.yaml").read_text()
            self.assertEqual(yaml, BINDING + "  clocks: true\n")


if __name__ == "__main__":
    unittest.main()
