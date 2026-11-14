#!/usr/bin/env python3
"""A kernel tree's device-tree bindings with a kernel conf's patches to them applied, in the
conf's order: what dt-validate checks a board's tree against.

  Usage: bindings.py <kernel tree> <kernel conf> <out dir>
"""

from __future__ import annotations

import re
import shutil
import subprocess
import sys
from pathlib import Path

from dtcx import REPO

BINDINGS = "Documentation/devicetree/bindings"
CONF_PATCH = re.compile(r"^\s*[\w./-]+:(\S+\.patch)$", re.MULTILINE)
FILE_PART = re.compile(r"(?m)^(?=diff --git |--- a/|--- /dev/null)")


def binding_parts(patch: str) -> str:
    """The parts of a patch that change a binding."""
    return "".join(p for p in FILE_PART.split(patch) if f"+++ b/{BINDINGS}/" in p)


def apply(kernel: Path, conf: Path, out: Path) -> list[str]:
    """out holding kernel's bindings with each binding change conf's patches make; the patches
    applied, by name."""
    shutil.rmtree(out, ignore_errors=True)
    shutil.copytree(kernel / BINDINGS, out / BINDINGS)
    applied: list[str] = []
    for patch in CONF_PATCH.findall(conf.read_text()):
        parts = binding_parts((REPO / patch).read_text(errors="replace"))
        if not parts:
            continue
        done = subprocess.run(
            ["patch", "-p1", "-s", "--forward", "-d", str(out)],
            input=parts,
            capture_output=True,
            text=True,
        )
        if done.returncode:
            sys.exit(f"{patch} does not apply to {kernel}'s bindings:\n{done.stdout}{done.stderr}")
        applied.append(patch)
    return applied


def main() -> None:
    if len(sys.argv) != 4:
        sys.exit(__doc__)
    for patch in apply(Path(sys.argv[1]), Path(sys.argv[2]), Path(sys.argv[3])):
        print(patch)


if __name__ == "__main__":
    main()
