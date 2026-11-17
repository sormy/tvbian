#!/usr/bin/env python3
"""Enabled devices that claim the same registers: one physical block described twice.

  Usage: devices.py [--all] <board.dtb>...

A tree can compile, prove its upstream view and pass every binding schema while it describes a
block twice, as when a vendor tree's root node and an imported dtsi's node name one SRAM: each is
valid alone, and the kernel probes the block twice. Each enabled node's register windows are read
as the CPU sees them, through the buses' ranges. Two nodes, neither holding the other, are one
block described twice when the first window of each is the same, or they overlap with a compatible
in common;
under such a pair, its children's pairs are not repeated. Exits 1 on any.

Different devices sharing registers is common and works: a clock in a syscon's window, an IOMMU
inside its master's, a bus's window holding another block, a vendor HDMI node mapping a GPIO
bank's window as its second. --all lists those too, for review,
without failing on them. The memory, and what reserved-memory carves out of it, describe no device.
"""

from __future__ import annotations

import sys
from pathlib import Path

from dts import compatibles
from semdiff import Tree


def describes_device(path: str) -> bool:
    top = path.split("/")[1]
    return top not in ("memory", "reserved-memory") and not top.startswith("memory@")


def holds(path: str, other: str) -> bool:
    return path == other or other.startswith(f"{path}/")


def lineage(path: str) -> list[str]:
    """The path and its ancestors, the root excluded."""
    parts = path.split("/")
    return ["/".join(parts[:i]) for i in range(len(parts), 1, -1)]


def overlaps(tree: Tree) -> tuple[list[str], list[str]]:
    """Blocks described twice, and other devices that share registers."""
    claims = sorted(
        (start, start + size, path, index == 0)
        for path in tree.nodes
        if path != "/" and describes_device(path) and tree.enabled(path)
        for index, (start, size) in enumerate(tree.registers(path))
        if size
    )
    twice: dict[tuple[str, str], str] = {}
    shared: dict[tuple[str, str], str] = {}
    for i, (start, end, path, first) in enumerate(claims):
        for other_start, other_end, other, other_first in claims[i + 1 :]:
            if other_start >= end:
                break
            if holds(path, other) or holds(other, path):
                continue
            pair = (min(path, other), max(path, other))
            window = f"{max(start, other_start):#x}-{min(end, other_end) - 1:#x}"
            same = first and other_first and (start, end) == (other_start, other_end)
            common = set(compatibles(tree.nodes[path])) & set(compatibles(tree.nodes[other]))
            (twice if same or common else shared)[
                pair
            ] = f"{pair[0]} and {pair[1]} both claim {window}"
    reported = [
        line
        for (a, b), line in sorted(
            twice.items(), key=lambda item: len(item[0][0]) + len(item[0][1])
        )
        if not any(
            (x, y) in twice and (x, y) != (a, b) for x in lineage(a) for y in lineage(b) if x < y
        )
        and not any(
            (y, x) in twice and (y, x) != (a, b) for x in lineage(a) for y in lineage(b) if y < x
        )
    ]
    return reported, list(shared.values())


def main() -> None:
    args = sys.argv[1:]
    review = "--all" in args
    dtbs = [a for a in args if a != "--all"]
    if not dtbs:
        sys.exit(__doc__)
    failed = False
    for dtb in dtbs:
        twice, shared = overlaps(Tree.load(Path(dtb)))
        for line in twice:
            print(f"{dtb}: described twice: {line}")
        for line in shared if review else []:
            print(f"{dtb}: shared: {line}")
        failed |= bool(twice)
    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    main()
