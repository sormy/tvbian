#!/usr/bin/env python3
"""Two compiled trees, equal but for how dtc numbered their phandles: every node, every property,
every memory reservation, read from the blob itself, not from any text of it.

  Usage: canonical.py [--base <base>] <a.dtb> <b.dtb>

Each property is its bytes, but for the cells references.py proves are phandles, each its
target's path: renumbering is no difference, a reference moved to another node is. A property
that does not decode is its bytes, and if one of its cells is a phandle naming another node in
each tree, it is a difference unless the property is known to hold numbers only: a reference the
model does not know fails the check, it does not pass it. The overlay bookkeeping (__symbols__,
__fixups__, __local_fixups__) is compared as bytes. Not compared: the phandle and linux,phandle
properties themselves, and the order of nodes and properties.
"""

from __future__ import annotations

import argparse
import re
import struct
import sys
from dataclasses import dataclass, field
from pathlib import Path

from dtcx import Base
from references import PINCTRL, STANDARD, Dialect, interrupt_map, muxes

MAGIC = 0xD00DFEED
VERSION = 17  # dtc's, the first with every block's size in the header
BEGIN_NODE, END_NODE, PROP, NOP, END = 1, 2, 3, 4, 9
NUMBERING = ("phandle", "linux,phandle")
METADATA = ("/__symbols__", "/__fixups__", "/__local_fixups__")
HEADER = struct.Struct(">10I")
OKAY = b"okay\0"
# a property as compared: the proven references as tokens, anything else its bytes
Value = tuple[str, ...] | bytes


@dataclass(frozen=True)
class Cells:
    """A property as references.py reads one: its cells, written as dts would."""

    value: str


@dataclass
class Node:
    props: dict[str, bytes] = field(default_factory=dict)

    def prop(self, name: str) -> Cells | None:
        raw = self.props.get(name)
        return Cells(f"<{' '.join(map(str, words(raw)))}>") if raw is not None else None


@dataclass
class Blob:
    """A flattened tree, as its bytes say: nodes by path, the memory reservations, the boot CPU."""

    nodes: dict[str, Node]
    reservations: list[tuple[int, int]]
    boot_cpu: int

    @staticmethod
    def read(data: bytes) -> Blob:
        """The blob, or ValueError for one malformed: a header out of its bounds, a block cut
        short, a node or property twice, a phandle on two nodes."""
        if len(data) < HEADER.size:
            raise ValueError("shorter than a header")
        (
            magic,
            total,
            structs,
            strings,
            reserved,
            version,
            _,
            boot_cpu,
            strings_size,
            structs_size,
        ) = HEADER.unpack_from(data)
        if magic != MAGIC or version < VERSION:
            raise ValueError(f"not a version {VERSION} flattened device tree")
        if total > len(data) or structs + structs_size > total or strings + strings_size > total:
            raise ValueError("a block past the blob's end")
        reservations: list[tuple[int, int]] = []
        while True:
            at = reserved + 16 * len(reservations)
            if at + 16 > total:
                raise ValueError("the reservations run past the blob's end")
            entry = struct.unpack_from(">QQ", data, at)
            if entry == (0, 0):
                break
            reservations.append(entry)
        nodes: dict[str, Node] = {}
        stack: list[str] = []
        at, end = structs, structs + structs_size
        while at + 4 <= end:
            (token,) = struct.unpack_from(">I", data, at)
            at += 4
            if token == BEGIN_NODE:
                stop = data.index(b"\0", at, end)
                stack.append(data[at:stop].decode())
                at = aligned(stop + 1)
                path = "/" + "/".join(stack[1:])
                if path in nodes:
                    raise ValueError(f"{path} twice")
                nodes[path] = Node()
            elif token == END_NODE:
                if not stack:
                    raise ValueError("a node closed that was never opened")
                stack.pop()
            elif token == PROP:
                if at + 8 > end:
                    raise ValueError(f"a property header cut short at {at - 4}")
                length, offset = struct.unpack_from(">II", data, at)
                if offset >= strings_size or at + 8 + length > end or not stack:
                    raise ValueError(f"a property out of bounds at {at - 4}")
                stop = data.find(b"\0", strings + offset, strings + strings_size)
                if stop < 0:
                    raise ValueError(f"a property name unterminated at {at - 4}")
                name = data[strings + offset : stop].decode()
                props = nodes["/" + "/".join(stack[1:])].props
                if name in props:
                    raise ValueError(f"{name} twice in one node")
                props[name] = data[at + 8 : at + 8 + length]
                at = aligned(at + 8 + length)
            elif token == END:
                if stack:
                    raise ValueError("the tree ends inside a node")
                blob = Blob(nodes, reservations, boot_cpu)
                blob.paths_by_phandle()  # a phandle on two nodes raises
                return blob
            elif token != NOP:
                raise ValueError(f"token {token} at {at - 4}")
        raise ValueError("no end token")

    def paths_by_phandle(self) -> dict[int, str]:
        out: dict[int, str] = {}
        for path, node in self.nodes.items():
            if metadata(path):
                continue
            if any(n in node.props and len(node.props[n]) != 4 for n in NUMBERING):
                raise ValueError(f"{path}: a phandle not one cell")
            handles = {words(node.props[n])[0] for n in NUMBERING if n in node.props}
            if len(handles) > 1:
                raise ValueError(f"{path}: phandle and linux,phandle disagree")
            for handle in handles:
                if handle in out:
                    raise ValueError(f"phandle {handle} on {out[handle]} and {path}")
                out[handle] = path
        return out

    def enabled(self, path: str) -> bool:
        """Enabled itself and under every ancestor: a missing status is okay."""
        while True:
            status = self.nodes[path].props.get("status", OKAY)
            if status not in (OKAY, b"ok\0"):
                return False
            if path == "/":
                return True
            path = parent(path)

    def selected(self, canonical: dict[str, dict[str, Value]]) -> set[str] | None:
        """The pin groups an enabled device's pinctrl-N names; None if one does not decode."""
        out: set[str] = set()
        for path, props in canonical.items():
            for name, value in props.items():
                if not PINCTRL.fullmatch(name) or not self.enabled(path):
                    continue
                if isinstance(value, bytes):
                    return None
                out |= {token[1:] for token in value if token.startswith("&")}
        return out

    def idle(self, path: str, selected: set[str] | None) -> bool:
        """A pin group, or a node within one, no enabled device selects: it configures no pin. A
        hog drives its pin itself; a device below a pin controller is no pin group."""
        if selected is None or "gpio-hog" in self.nodes[path].props:
            return False
        chain: list[str] = []  # the nodes from below the nearest pin controller down to path
        for node_path in [path, *ancestors(path)]:
            if pin_controller(node_path, self.nodes[node_path]):
                break
            chain.append(node_path)
        else:
            return False
        if not chain or any("compatible" in self.nodes[p].props for p in chain):
            return False
        if not any(self.pin_group(p) for p in chain):
            return False
        return not any(s == path or within(s, (path,)) or within(path, (s,)) for s in selected)

    def pin_group(self, path: str) -> bool:
        """What a pin controller muxes, on the node itself or in its children: Rockchip's i2s1
        holds its groups."""
        children = (n for p, n in self.nodes.items() if p != "/" and parent(p) == path)
        return any(muxes(n.props) for n in (self.nodes[path], *children))

    def canonical(self, dialect: Dialect = STANDARD) -> dict[str, dict[str, Value]]:
        """Each node's properties, each phandle the decoder proves as its target's path."""
        paths = self.paths_by_phandle()
        targets = {handle: self.nodes[path] for handle, path in paths.items()}
        out: dict[str, dict[str, Value]] = {}
        for path, node in self.nodes.items():
            hog = "gpio-hog" in node.props
            out[path] = {}
            for name, raw in node.props.items():
                if name in NUMBERING and not metadata(path):
                    continue
                flat = words(raw) if len(raw) % 4 == 0 and not metadata(path) else []
                found: dict[int, int] | None = None
                if flat and name == "interrupt-map":
                    found = interrupt_map(flat, node, targets)
                elif flat:
                    found = dialect.decode(name, flat, targets, hog)
                out[path][name] = (
                    tuple(f"&{paths[c]}" if i in found else str(c) for i, c in enumerate(flat))
                    if found
                    else raw
                )
        return out


def off(props: dict[str, Value]) -> bool:
    """A device as a projection writes one that is off: its status alone, not okay."""
    return props.keys() == {"status"} and props["status"] not in (OKAY, b"ok\0")


def parent(path: str) -> str:
    return path.rsplit("/", 1)[0] or "/"


def ancestors(path: str) -> list[str]:
    out: list[str] = []
    while path != "/":
        path = parent(path)
        out.append(path)
    return out


def within(path: str, roots: tuple[str, ...]) -> bool:
    """Whether path is one of roots or below one."""
    return any(path == root or path.startswith(f"{root.rstrip('/')}/") for root in roots)


def pin_controller(path: str, node: Node) -> bool:
    return "gpio-controller" in node.props or path.rsplit("/", 1)[-1].startswith("pinctrl")


def metadata(path: str) -> bool:
    """Whether a node is the overlay bookkeeping or within it."""
    return within(path, METADATA)


def shown(value: Value) -> str:
    """A value as dts writes it, for a reader: references, strings, cells, or bytes."""
    if isinstance(value, tuple):
        return " ".join(value)
    parts = value[:-1].split(b"\0") if value.endswith(b"\0") else []
    if parts and all(p and p.isascii() and p.decode().isprintable() for p in parts):
        return ", ".join(f'"{p.decode()}"' for p in parts)
    if value and len(value) % 4 == 0:
        return f"<{' '.join(f'{c:#x}' for c in words(value))}>"
    return f"[{value.hex(' ')}]"


def aligned(at: int) -> int:
    return (at + 3) & ~3


def words(raw: bytes) -> list[int]:
    return [int.from_bytes(raw[i : i + 4], "big") for i in range(0, len(raw) - 3, 4)]


@dataclass(frozen=True)
class Projection:
    """What a view of a tree leaves out on purpose, and nothing else: a disabled device's
    contents (it says only that the device is off), a pin group no enabled device selects
    (it configures no pin), the distribution's own nodes, and the labels. A missing status is
    okay, and a unit address its value however spelled: drm-logo@00000000 is drm-logo@0."""

    omitted: tuple[str, ...] = ()

    def of(self, blob: Blob, canonical: dict[str, dict[str, Value]]) -> dict[str, dict[str, Value]]:
        selected = blob.selected(canonical)
        out: dict[str, dict[str, Value]] = {}
        for path, props in canonical.items():
            if metadata(path) or within(path, self.omitted) or blob.idle(path, selected):
                continue
            spelled = unit_spelled(path)
            if spelled in out:
                raise ValueError(f"{path} and another node spell one unit address, {spelled}")
            if not blob.enabled(path):
                if path == "/" or blob.enabled(parent(path)):  # its own status, the reason kept
                    out[spelled] = {"status": props["status"]}
                continue
            out[spelled] = {
                n: aliased(v) if path == "/aliases" else respelled(v)
                for n, v in props.items()
                if n != "status"
            }
        return out


def aliased(value: Value) -> Value:
    """An alias, the path of its node with each unit address as its value."""
    if isinstance(value, tuple) or not value.endswith(b"\0"):
        return value
    return unit_spelled(value[:-1].decode()).encode() + b"\0"


def unit_spelled(path: str) -> str:
    """A path with each unit address as its value: drm-logo@00000000 is drm-logo@0."""
    return re.sub(
        r"@([0-9a-fA-F,]+)(?=/|$)",
        lambda m: (
            "@" + ",".join(f"{int(part, 16):x}" for part in m.group(1).split(","))
            if all(m.group(1).split(","))
            else m.group(0)
        ),
        path,
    )


def respelled(value: Value) -> Value:
    if isinstance(value, bytes):
        return value
    return tuple(f"&{unit_spelled(t[1:])}" if t.startswith("&") else t for t in value)


def differences(
    a: Blob, b: Blob, dialect: Dialect = STANDARD, projection: Projection | None = None
) -> list[str]:
    """Every way b differs from a, renumbering aside, and what a projection leaves out."""
    out: list[str] = []
    if a.reservations != b.reservations:
        out.append(f"reservations: {a.reservations} -> {b.reservations}")
    if a.boot_cpu != b.boot_cpu:
        out.append(f"boot cpu: {a.boot_cpu} -> {b.boot_cpu}")
    mine, theirs = a.canonical(dialect), b.canonical(dialect)
    if projection is not None:
        mine, theirs = projection.of(a, mine), projection.of(b, theirs)
    # projected, a device off on one side and absent on the other describes nothing either way
    out += [
        f"- {p}" for p in sorted(mine.keys() - theirs.keys()) if shown_absent(mine[p], projection)
    ]
    out += [
        f"+ {p}" for p in sorted(theirs.keys() - mine.keys()) if shown_absent(theirs[p], projection)
    ]
    was_at, now_at = a.paths_by_phandle(), b.paths_by_phandle()
    for path in sorted(mine.keys() & theirs.keys()):
        before, after = mine[path], theirs[path]
        for name in sorted(before.keys() | after.keys()):
            was, now = before.get(name), after.get(name)
            if was != now:
                out.append(f"  {path}: {name}: {shown_or_none(was)} -> {shown_or_none(now)}")
            elif isinstance(was, bytes) and numbers_unknown(before, path, name, dialect):
                cell = moved(was, was_at, now_at)
                if cell is not None:
                    out.append(
                        f"  {path}: {name}: {cell:#x} is {was_at.get(cell)} before,"
                        f" {now_at.get(cell)} now: a phandle references.py does not know, or a"
                        " number its base should declare"
                    )
    return out


def shown_absent(props: dict[str, Value], projection: Projection | None) -> bool:
    """Whether a node on one side only is a difference: always, exact; projected, unless off."""
    return projection is None or not off(props)


def numbers_unknown(props: dict[str, Value], path: str, name: str, dialect: Dialect) -> bool:
    """Whether an undecoded value of a node's may hide a phandle: not the bookkeeping, not a
    property known to hold numbers, not a hog's gpios, which are its own controller's pins."""
    hog = name == "gpios" and "gpio-hog" in props
    return not metadata(path) and not dialect.numeric(name) and not hog


def moved(raw: bytes, was_at: dict[int, str], now_at: dict[int, str]) -> int | None:
    """A cell of an undecoded value that is a phandle naming another node in each tree: a
    reference renumbering would have moved, unless the value is numbers or text."""
    if len(raw) % 4 or shown(raw).startswith('"'):
        return None
    return next((c for c in words(raw) if was_at.get(c) != now_at.get(c)), None)


def shown_or_none(value: Value | None) -> str:
    return "(none)" if value is None else shown(value)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base", help="the base whose gpio, ref and quantity names its trees use")
    parser.add_argument("a", type=Path)
    parser.add_argument("b", type=Path)
    args = parser.parse_args()
    dialect = Base.load(args.base).dialect if args.base else STANDARD
    found = differences(Blob.read(args.a.read_bytes()), Blob.read(args.b.read_bytes()), dialect)
    for line in found:
        print(line)
    print(f"  {len(found)} differences, phandle numbering aside", file=sys.stderr)
    sys.exit(1 if found else 0)


if __name__ == "__main__":
    main()
