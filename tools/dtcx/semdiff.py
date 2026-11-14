#!/usr/bin/env python3
"""What a board's new tree changes against its last proven one, by meaning, not text.

  Usage: semdiff.py <proven.dtb> <new.dtb>

Nodes meet across layouts by the CPU address of their registers, through the buses' ranges, so a
vendor's flat node meets mainline's nested one; an addressless node by its path, else its unique
compatible, else its name. Reported: blocks enabled in one tree only, then each block enabled in
both with the properties it drops, adds or changes, and the same for the children it describes
without a compatible of their own (LEDs, endpoints, thermal maps, the root's aliases), met by name.

What it covers is what it reads: a phandle reads as the node it points at, the old tree's as its
counterpart, so renumbering is no difference and a reference moved to another node is, only in a
property references.py, with the dialect a base gives it, knows holds phandles and that decodes;
any other property compares as numbers. An alias reads as the node its path names. Not compared:
a disabled block or anything below it, a pin group no enabled device selects, which configures no
pin, the layout (reg past its address, ranges, #-cells, the memory), phandles and the order of
nodes and properties. Two trees laid out alike compare exactly with canonical.py.
"""

from __future__ import annotations

import re
import subprocess
import sys
from collections.abc import Callable
from dataclasses import dataclass
from functools import cached_property
from pathlib import Path

from dts import Node, Source, compatibles, walk
from references import ENTRIES, PINCTRL, STANDARD, Dialect, cells

DTC = Path(__file__).resolve().parents[2] / "build" / "bin" / "dtc"
# lists whose entries a names property names: compared by name, so an order is no difference
NAMED = {
    "clocks": "clock-names",
    "resets": "reset-names",
    "dmas": "dma-names",
    "phys": "phy-names",
    "pwms": "pwm-names",
    "mboxes": "mbox-names",
    "io-channels": "io-channel-names",
}
NAME = re.compile(r'"([^"]*)"')
NAMED_ENTRY = re.compile(r"^[^:&<\s]+: ")
# what says how a tree is laid out, not what it describes
IGNORED = {"phandle", "linux,phandle", "status", "#address-cells", "#size-cells", "reg", "ranges"}
ALIASES = "/aliases"


def joined(parts: list[int]) -> int:
    """Cells, most significant first, as one number."""
    return int.from_bytes(b"".join(c.to_bytes(4, "big") for c in parts), "big")


@dataclass
class Tree:
    """A compiled tree, decompiled: its nodes by path, their phandles and CPU addresses."""

    nodes: dict[str, Node]

    @staticmethod
    def load(dtb: Path) -> Tree:
        text = subprocess.run(
            [str(DTC), "-q", "-I", "dtb", "-O", "dts", str(dtb)],
            check=True,
            capture_output=True,
            text=True,
        ).stdout
        root = Source.parse(text).root
        nodes = {path: node for path, node in walk(root) if not path.startswith("/__")}
        return Tree(nodes | {"/": root})

    @cached_property
    def selected(self) -> set[int]:
        """The phandles an enabled device's pinctrl-N names: the pin groups in use."""
        return {
            c
            for path, n in self.nodes.items()
            if self.enabled(path)
            for p in n.props
            if PINCTRL.fullmatch(p.name)
            for c in cells(p.value)
        }

    @cached_property
    def selected_paths(self) -> list[str]:
        """The groups in use, and the pin configurations they name: Rockchip's pcfg nodes."""
        handles = self.phandles
        groups = [handles[h] for h in self.selected if h in handles]
        configs = [
            handles[flat[i]]
            for path, node in self.nodes.items()
            if any(path == g or path.startswith(f"{g}/") for g in groups)
            for prop in node.props
            if prop.name in ENTRIES
            for flat in [cells(prop.value)]
            for i in STANDARD.decode(prop.name, flat, self.targets) or {}
        ]
        return groups + configs

    def describes(self, path: str) -> bool:
        """Whether a node describes anything: below a pin controller, only a pin group an enabled
        device selects, a node within one or one holding one (Rockchip's function nodes), since
        an unselected group configures no pin; a hog drives its pin itself."""
        if self.nodes[path].prop("gpio-hog") is not None or not self.under_pin_controller(path):
            return True
        return any(
            s == path or s.startswith(f"{path}/") or path.startswith(f"{s}/")
            for s in self.selected_paths
        )

    def under_pin_controller(self, path: str) -> bool:
        while path.count("/") > 1:
            path = path.rsplit("/", 1)[0]
            node = self.nodes[path]
            if node.prop("gpio-controller") is not None or node.name.startswith("pinctrl"):
                return True
        return False

    def children(self, path: str) -> dict[str, str]:
        """A node's enabled children with no compatible of their own, by name: an LED, an
        endpoint, a thermal map, described as part of their parent."""
        return {
            p.rsplit("/", 1)[1]: p
            for p, n in self.nodes.items()
            if p != "/"
            and (p.rsplit("/", 1)[0] or "/") == path
            and not compatibles(n)
            and self.enabled(p)
            and self.describes(p)
        }

    @cached_property
    def phandles(self) -> dict[int, str]:
        out: dict[int, str] = {}
        for path, node in self.nodes.items():
            for name in ("phandle", "linux,phandle"):
                prop = node.prop(name)
                if prop is not None and cells(prop.value):
                    out[cells(prop.value)[0]] = path
        return out

    def cell_count(self, path: str, name: str) -> int:
        """The #address-cells or #size-cells a node gives its children, the spec's 2 and 1 else."""
        prop = self.nodes[path].prop(name)
        return cells(prop.value)[0] if prop is not None else (2 if "address" in name else 1)

    def address(self, path: str) -> int | None:
        """The node's first register, as the CPU sees it through every bus's ranges."""
        reg = self.nodes[path].prop("reg")
        parent = path.rsplit("/", 1)[0] or "/"
        if reg is None or path == "/" or parent not in self.nodes:
            return None
        reg_cells = cells(reg.value)
        width = self.cell_count(parent, "#address-cells")
        if not reg_cells or len(reg_cells) < width:
            return None
        address = joined(reg_cells[:width])
        while parent != "/":
            ranges = self.nodes[parent].prop("ranges")
            grand = parent.rsplit("/", 1)[0] or "/"
            if ranges is None:
                return None  # a bus with no ranges maps nothing to the CPU
            entries = cells(ranges.value)
            child = self.cell_count(parent, "#address-cells")
            up = self.cell_count(grand, "#address-cells")
            size = self.cell_count(parent, "#size-cells")
            step = child + up + size
            for i in range(0, len(entries) - step + 1, step):
                base = joined(entries[i : i + child])
                to = joined(entries[i + child : i + child + up])
                span = joined(entries[i + child + up : i + step])
                if base <= address < base + span:
                    address = address - base + to
                    break
            parent = grand
        return address

    def enabled(self, path: str) -> bool:
        """Enabled itself and under every ancestor."""
        while path:
            status = self.nodes[path].prop("status") if path in self.nodes else None
            if status is not None and status.value.strip('"') not in ("okay", "ok"):
                return False
            path = path.rsplit("/", 1)[0]
        return True

    def bus(self, path: str) -> bool:
        return "simple-bus" in compatibles(self.nodes[path])

    @cached_property
    def targets(self) -> dict[int, Node]:
        return {h: self.nodes[p] for h, p in self.phandles.items()}

    def value(
        self,
        path: str,
        name: str,
        value: str,
        named: Callable[[str], str],
        dialect: Dialect = STANDARD,
    ) -> str:
        """A property's value with each phandle read as the node it points at, and an alias as
        the node its path names, each node as named gives it; one that does not decode, as
        numbers."""
        aliased = value.strip('"')
        if path == ALIASES and aliased in self.nodes:
            return f"&{named(aliased)}"
        node = self.nodes.get(path)
        hog = node is not None and node.prop("gpio-hog") is not None
        if not dialect.holds(name, hog):
            return " ".join(value.split())
        flat = cells(value)
        found = dialect.decode(name, flat, self.targets, hog) or {}
        out: list[str] = []
        i = 0
        while i < len(flat):
            if i not in found:
                out.append(str(flat[i]))
                i += 1
                continue
            arguments = "".join(f" {c}" for c in flat[i + 1 : i + 1 + found[i]])
            out.append(f"&{named(self.phandles[flat[i]])}{arguments}")
            i += 1 + found[i]
        return ", ".join(out)


def pairs(old: Tree, new: Tree) -> dict[str, str]:
    """Each old node's counterpart in the new tree."""
    by_address: dict[int, list[str]] = {}
    for path in new.nodes:
        address = new.address(path)
        if address is not None:
            by_address.setdefault(address, []).append(path)
    by_compatible: dict[str, list[str]] = {}
    by_name: dict[str, list[str]] = {}
    for path, node in new.nodes.items():
        for compatible in compatibles(node):
            by_compatible.setdefault(compatible, []).append(path)
        by_name.setdefault(node.name.split("@")[0], []).append(path)
    old_compatibles: dict[str, int] = {}
    for node in old.nodes.values():
        for compatible in compatibles(node):
            old_compatibles[compatible] = old_compatibles.get(compatible, 0) + 1
    options: dict[str, list[str]] = {}
    for path, node in old.nodes.items():
        address = old.address(path)
        candidates = by_address.get(address, []) if address is not None else []
        if not candidates and path in new.nodes:
            candidates = [path]
        if not candidates:
            for compatible in compatibles(node):
                # unique in both: one of several the old tree has is not the new tree's one
                if len(by_compatible.get(compatible, [])) == 1 and old_compatibles[compatible] == 1:
                    candidates = by_compatible[compatible]
                    break
        if not candidates and len(by_name.get(node.name.split("@")[0], [])) == 1:
            candidates = by_name[node.name.split("@")[0]]
        # a bus pairs only with a bus: a device at a bus's base address is not the bus
        candidates = [c for c in candidates if new.bus(c) == old.bus(path)]
        options[path] = candidates
    # one counterpart each, the likest pairs first: a look-alike never takes another's
    ranked = sorted(
        ((likeness(old, path, new, c), path, c) for path, cs in options.items() for c in cs),
        key=lambda t: t[0],
        reverse=True,
    )
    out: dict[str, str] = {}
    taken: set[str] = set()
    for _, path, candidate in ranked:
        if path not in out and candidate not in taken:
            out[path] = candidate
            taken.add(candidate)
    return out


def likeness(old: Tree, path: str, new: Tree, candidate: str) -> tuple[bool, bool, bool]:
    """How alike two nodes at one address are: a compatible shared, the name, the path. A child
    at its parent's base has the parent's address."""
    mine, theirs = old.nodes[path], new.nodes[candidate]
    return (
        bool(set(compatibles(mine)) & set(compatibles(theirs))),
        mine.name.split("@")[0] == theirs.name.split("@")[0],
        path == candidate,
    )


def by_name(props: dict[str, str]) -> dict[str, str]:
    """Each named list as its entries by name, its names property folded into it."""
    out = dict(props)
    for listed, naming in NAMED.items():
        if listed not in out or naming not in out:
            continue
        names, entries = NAME.findall(out[naming]), out[listed].split(", ")
        if len(names) == len(entries):
            out[listed] = ", ".join(sorted(f"{n}: {e}" for n, e in zip(names, entries)))
            del out[naming]
    return out


def same(before: str, after: str) -> bool:
    """Equal, or one a list by_name named and the other the same entries unnamed; two named
    lists only as named, so a clock swapped under its unchanged name is a difference."""
    if before == after:
        return True
    lists = [value.split(", ") for value in (before, after)]
    if sum(all(NAMED_ENTRY.match(e) for e in entries) for entries in lists) != 1:
        return False
    first, second = ([NAMED_ENTRY.sub("", e) for e in entries] for entries in lists)
    return sorted(first) == sorted(second)


@dataclass
class Comparison:
    """Two trees, each old node met with its counterpart. A reference reads as the node it points
    at: in the old tree as its counterpart, so one moved to another node is a difference."""

    old: Tree
    new: Tree
    dialect: Dialect = STANDARD

    @cached_property
    def matched(self) -> dict[str, str]:
        """pairs(), and a node it leaves alone met by name below its parent's counterpart."""
        out = pairs(self.old, self.new)
        taken = set(out.values())
        for path in sorted(self.old.nodes, key=lambda p: p.count("/")):
            parent, _, name = path.rpartition("/")
            if path in out or (parent or "/") not in out:
                continue
            twin = f"{out[parent or '/'].rstrip('/')}/{name}"
            if twin in self.new.nodes and twin not in taken:
                out[path] = twin
                taken.add(twin)
        return out

    def counterpart(self, path: str) -> str:
        return self.matched.get(path, f"{path}, which has no counterpart")

    def compared(self, tree: Tree) -> set[str]:
        """The enabled blocks: the nodes with a compatible."""
        return {p for p, n in tree.nodes.items() if tree.enabled(p) and compatibles(n)}

    def report(self) -> list[str]:
        old_on, new_on = self.compared(self.old), self.compared(self.new)
        out: list[str] = []
        met = {self.matched[p] for p in old_on if p in self.matched}
        for path in sorted(old_on):
            twin = self.matched.get(path)
            if twin is None or twin not in new_on:
                where = f" -> {twin} (disabled)" if twin else " (no counterpart)"
                compatible = compatibles(self.old.nodes[path])
                out.append(f"- enabled before only: {path} {compatible}{where}")
        for path in sorted(new_on - met):
            out.append(f"+ enabled now only: {path} {compatibles(self.new.nodes[path])}")
        for path in sorted(old_on):
            twin = self.matched.get(path)
            if twin is not None and twin in new_on:
                out += self.changed(path, twin) + self.nested(path, twin)
        return out

    def changed(self, path: str, twin: str) -> list[str]:
        """The properties a node drops, adds or changes, and its registers moved: a node met
        by path whose CPU address is another."""
        old, new = self.old, self.new
        was, now = old.address(path), new.address(twin)
        moved = (
            [] if None in (was, now) or was == now else [f"  {twin}: address: {was:#x} -> {now:#x}"]
        )
        before = by_name(
            {
                p.name: old.value(path, p.name, p.value, self.counterpart, self.dialect)
                for p in old.nodes[path].props
            }
        )
        after = by_name(
            {
                p.name: new.value(twin, p.name, p.value, str, self.dialect)
                for p in new.nodes[twin].props
            }
        )
        out = moved
        for name in sorted((set(before) | set(after)) - IGNORED):
            if name not in after:
                out.append(f"  {twin}: dropped {name} = {before[name]}")
            elif name not in before:
                out.append(f"  {twin}: added {name} = {after[name]}")
            elif not same(before[name], after[name]):
                out.append(f"  {twin}: {name}: {before[name]} -> {after[name]}")
        return out

    def nested(self, path: str, twin: str) -> list[str]:
        """The children a pair describes as part of itself, met by name, compared all the way
        down."""
        mine, theirs = self.old.children(path), self.new.children(twin)
        out = [f"- dropped node: {mine[n]}" for n in sorted(mine.keys() - theirs.keys())]
        out += [f"+ added node: {theirs[n]}" for n in sorted(theirs.keys() - mine.keys())]
        for name in sorted(mine.keys() & theirs.keys()):
            out += self.changed(mine[name], theirs[name]) + self.nested(mine[name], theirs[name])
        return out


def report(old: Tree, new: Tree, dialect: Dialect = STANDARD) -> list[str]:
    return Comparison(old, new, dialect).report()


def main() -> None:
    if len(sys.argv) != 3:
        sys.exit(__doc__)
    old, new = Tree.load(Path(sys.argv[1])), Tree.load(Path(sys.argv[2]))
    for line in report(old, new):
        print(line)


if __name__ == "__main__":
    main()
