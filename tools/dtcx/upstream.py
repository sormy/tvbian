#!/usr/bin/env python3
"""A board's final tree as an upstream board file: the base dtsi included, and only what the board
changes written, in the labels and macros board.dts already uses.

  Usage: upstream.py [--prove <board.dtb>] [--soc <url>] <source> <target> <board.dts>

The dtsi is the one translate.py completes against: the source's translate.conf soc, with its
kernel patches. A node the dtsi labels is changed by &label { }, one it does not inside its
nearest labelled ancestor's block, so no reference is a path; the board's own nodes are written
whole, except pin groups nothing references; a dtsi device the board lacks is disabled, not
deleted, and one the board disables is only disabled. --prove compiles the result against the
same dtsi and checks with canonical.py that it is board.dtb but for what a view leaves out.
"""

from __future__ import annotations

import argparse
import re
import subprocess
import sys
import tempfile
import textwrap
from dataclasses import dataclass, field
from pathlib import Path

from dtcx import HERE, REPO, Base, fetch
from dts import Node, Prop, Source, compatibles, render, unit, walk
from mainline import FILE_HEADER, dtsi_files, dtsi_history, patched_soc
from references import PINCTRL, muxes
from canonical import Blob, Projection, differences
from semdiff import DTC
from vocabulary import Vocabulary

REFERENCE = re.compile(r"&([\w-]+)")
CONF_PATCH = re.compile(r"^\s*[\w./-]+:(\S+\.patch)$", re.MULTILINE)
CONF_KERNELS = re.compile(r'^KERNELS="([^"]*)"', re.MULTILINE)
QUOTED = re.compile(r'"([^"]+)"')
HEADER = re.compile(r"#include <([^>]+)>")
DEFINE = re.compile(r"^#define\s+(\w+)", re.MULTILINE)
TOKEN = re.compile(r"\b[A-Z_][A-Z0-9_]+\b")
# a value that names one node: &label, or its path as a string
PATH_REFERENCE = re.compile(r'^(?:&([\w-]+)|"(/[^"]*)")$')
PINNED_REPO = re.compile(r"^https://raw\.githubusercontent\.com/([^/]+/[^/]+)/([^/]+)/")
COMMIT = re.compile(r"[0-9a-f]{40}")
SHORT_COMMIT = 12
# each sunxi GPIO controller's label and its first bank's letter
SUNXI_BANKS = {"&pio": "A", "&r_pio": "L"}
# one sunxi GPIO: its controller, bank, pin and flags
SUNXI_GPIO = re.compile(r"(&r_pio|&pio) (\d+) (\d+) (?:\([^)]*\)|[^\s()]+)")
WIDTH = 100
# what our distribution adds, not the board: the crash log's RAM
DISTRIBUTION = {"ramoops"}
# a string a driver matches by value, besides a compatible
RC_MAP = "linux,rc-map-name"


@dataclass
class Setting:
    """What a board file is written against: the dtsi it includes, the base kernel it names, the
    patches that may change either, the dtsi as each patch leaves it, and each header's names."""

    soc_file: str
    base_kernel: str = "mainline"
    patches: list[str] = field(default_factory=list)
    history: list[tuple[str, Node]] = field(default_factory=list)
    defines: dict[str, set[str]] = field(default_factory=dict)


@dataclass
class Demand:
    """What a board's final tree asks of its kernel, by name: the strings drivers and bindings
    match, its vendor properties, and the dtsi changes each patch makes that the tree keeps."""

    strings: set[str] = field(default_factory=set)
    properties: set[str] = field(default_factory=set)
    kept: dict[str, list[str]] = field(default_factory=dict)


INCLUDE_LINE = re.compile(r"^#include\b")
NUMBER_LITERAL = re.compile(r"\b(?:0x[0-9a-fA-F]+|[0-9]+)\b")
# what says how dtc numbered a tree, not what it describes
LAYOUT = {"phandle", "linux,phandle"}


def normal(value: str) -> str:
    """A value as dtc compiles it: <a>, <b> is <a b>, a number its value however spelled
    (0x00 is 0), spacing no part of it; quoted strings as written."""
    parts = re.split(r'("[^"]*")', value)
    unquoted = (
        re.sub(
            r"\s+",
            " ",
            NUMBER_LITERAL.sub(
                lambda m: str(int(m.group(0), 16 if m.group(0).startswith("0x") else 10)),
                re.sub(r">\s*,\s*<", " ", p),
            ),
        )
        for p in parts[::2]
    )
    return "".join(x for pair in zip(unquoted, parts[1::2] + [""]) for x in pair).strip()


def controller(node: Node) -> bool:
    return node.prop("gpio-controller") is not None or node.name.startswith("pinctrl")


def pin_group(node: Node, under_pinctrl: bool) -> bool:
    """What a pin controller muxes, at any depth below it, by pins or groups, on itself or in its
    children: a mux child, or the pin groups of a function (Rockchip's i2s1 holding i2s1-sclk), by
    a vendor's own `<vendor>,pins` too."""
    muxing = any(muxes(p.name for p in n.props) for n in (node, *node.children))
    return under_pinctrl and muxing and not compatibles(node)


def key(path: str, values: dict[str, int]) -> str:
    """A path or a node name with each unit address as its number, a macro's evaluated:
    drm-logo@00000000 is drm-logo@0, pd_gpu@RK3528_PD_GPU is pd_gpu@4."""
    return "/".join(spelled(p, values) for p in path.split("/"))


def spelled(name: str, values: dict[str, int]) -> str:
    base, at, address = name.partition("@")
    if not at:
        return name
    parts = [f"{values[p]:x}" if p in values else p for p in address.split(",")]
    return f"{base}@{unit('@' + ','.join(parts))}"


def labelled(node: Node) -> set[str]:
    """The labels of a node and of every node below it."""
    return {label for n in (node, *(x for _, x in walk(node))) for label in n.labels}


def references(node: Node) -> set[str]:
    """Every label node's subtree points to."""
    nodes = [node, *(n for _, n in walk(node))]
    return {label for n in nodes for p in n.props for label in REFERENCE.findall(p.value)}


def empty(node: Node) -> bool:
    return not node.props and not node.children


def disabled(node: Node) -> bool:
    status = node.prop("status")
    return status is not None and "disabled" in status.value


def points_to(prop: Prop | None, labels: set[str]) -> bool:
    return prop is not None and bool(set(REFERENCE.findall(prop.value)) & labels)


class Upstream:
    """The board's tree against the dtsi's: what each node the board shares with it changes."""

    def __init__(
        self,
        soc: Node,
        board: Source,
        values: dict[str, int] | None = None,
    ) -> None:
        self.values = values or {}  # each header macro's number: a value meets its number
        self.soc = dict(walk(soc)) | {"/": soc}
        self.soc_paths = {self.key(path): path for path in self.soc}  # however spelled -> as is
        self.soc_labels = {label: path for path, n in self.soc.items() for label in n.labels}
        self.board = board
        self.board_nodes = {"/": board.root} | dict(walk(board.root))
        self.board_labels = {label: p for p, n in self.board_nodes.items() for label in n.labels}
        self.labels = set(self.board_labels)  # every label the board's tree holds
        self.blocks: dict[str, Node] = {}  # "/" or "&label" -> its block
        self.added: set[int] = set()  # the nodes the board adds, and theirs
        self.born_empty: set[int] = set()  # those it adds empty, on purpose
        self.droppable: set[int] = set()  # added nodes that go when nothing references them
        self.stands_for: dict[int, Node] = {}  # a block, or a node in one -> the board's node
        self.omitted: list[str] = []  # the distribution's nodes, left out
        self.described: dict[str, Node] = {}  # a dtsi path's key -> the board node describing it
        self.dtsi_of: dict[int, Node] = {}  # a block, or a node in one -> the dtsi's node
        self.deleted: set[int] = set()  # the base's nodes the view deletes, and theirs

    def key(self, path: str) -> str:
        return key(path, self.values)

    def removed(self, mine: Node, at: str) -> list[Node]:
        """The children of the dtsi's node at `at` that the board's node lacks."""
        names = {self.key(c.name) for c in mine.children}
        return [c for c in self.soc[at].children if self.key(c.name) not in names]

    def going(self, child: Node, under_pinctrl: bool, quiet: bool) -> bool:
        """Whether a node the board lacks is deleted: a device whose label the board gives to
        another node, which a disabled node would still hold; or, where the board describes the
        parent, what is not a device, unless a pin group, which dtc drops when nothing selects
        it."""
        moved = bool(labelled(child) & self.labels)
        idle = not compatibles(child) and not pin_group(child, under_pinctrl)
        return moved or (idle and not quiet)

    def block(self, path: str) -> Node:
        """The node to write path's changes in: its own &label block, or nested by name in its
        nearest labelled ancestor's, or the root's."""
        names: list[str] = []
        at = path
        while at != "/" and not self.soc[at].labels:
            at, name = at.rsplit("/", 1)
            at, names = at or "/", [name, *names]
        anchor = "/" if at == "/" else f"&{self.soc[at].labels[0]}"
        node = self.blocks.setdefault(anchor, Node(anchor))
        self.dtsi_of[id(node)] = self.soc[at]
        for name in names:
            child = next((c for c in node.children if c.name == name), None)
            if child is None:
                child = Node(name)
                node.children.append(child)
            node, at = child, f"{at.rstrip('/')}/{name}"
            self.dtsi_of[id(node)] = self.soc[at]
        return node

    def enabled(self, path: str) -> bool:
        """Whether the board's node at path is enabled, itself and under every ancestor."""
        while path:
            if disabled(self.board_nodes[path]):
                return False
            path = path.rsplit("/", 1)[0]
        return not disabled(self.board.root)

    def selected(self) -> set[str]:
        """The labels an enabled board node's pinctrl-N names: the pin groups in use."""
        return {
            label
            for path, node in self.board_nodes.items()
            if self.enabled(path)
            for p in node.props
            if PINCTRL.fullmatch(p.name)
            for label in REFERENCE.findall(p.value)
        }

    def silent(self, met: list[tuple[Node, str]]) -> tuple[set[str], set[str]]:
        """The dtsi paths to write nothing for, off in both trees, and those to write only what
        keeps every reference whole: a node the board disables, a pin group no enabled device
        selects; each with everything below it."""
        selected = self.selected()
        off: set[str] = set()
        quiet: set[str] = set()
        for mine, at in met:
            theirs, parent = self.soc[at], at.rsplit("/", 1)[0] or "/"
            unselected = pin_group(theirs, self.under_pinctrl(at)) and not (
                labelled(mine) & selected
            )
            if (at != "/" and parent in off) or (disabled(mine) and disabled(theirs)):
                off.add(at)
            elif (at != "/" and parent in quiet) or disabled(mine) or unselected:
                quiet.add(at)
        return off, quiet

    def changes(self) -> None:
        """Each change to a node the dtsi has, met by name and unit address however spelled
        (drm-logo@00000000 is drm-logo@0, a macro as its number), but none to a node off in both,
        and to one the board disables or a pin group nothing enabled selects only what keeps the
        references whole: a disabled node describes nothing, nor an unselected group."""
        met = [
            (mine, at)
            for path, mine in self.board_nodes.items()
            if (at := self.soc_paths.get(self.key(path))) is not None
        ]
        off, quiet = self.silent(met)
        going: dict[str, list[Node]] = {}
        for mine, at in [(mine, at) for mine, at in met if at not in off]:
            under = self.under_pinctrl(at)
            going[at] = [c for c in self.removed(mine, at) if self.going(c, under, at in quiet)]
        vanishing = self.cascade(met, going)
        for mine, at in met:
            if at in off:
                self.unpointed(at, vanishing)
                continue
            theirs, hushed = self.soc[at], at in quiet
            if not hushed:
                self.described[self.key(at)] = mine
            props = [
                self.by_label(p)
                for p in mine.props
                if p.name not in LAYOUT and not self.same(p, theirs.prop(p.name))
            ]
            gone = [
                p.name for p in theirs.props if p.name not in LAYOUT and mine.prop(p.name) is None
            ]
            if "status" in gone:  # the dtsi's disabled, the board's no status: okay
                gone.remove("status")
                props.append(Prop.of("status", '"okay"'))
            if hushed:
                kept = {
                    n
                    for n in [p.name for p in props] + gone
                    if points_to(theirs.prop(n), vanishing - self.labels)
                }
                if disabled(mine) and (at == "/" or at.rsplit("/", 1)[0] not in quiet):
                    kept.add("status")
                props = [p for p in props if p.name in kept]
                gone = [n for n in gone if n in kept]
            prefix = "" if at == "/" else at
            added = [
                c for c in mine.children if self.key(f"{prefix}/{c.name}") not in self.soc_paths
            ]
            ours = [c for c in added if set(compatibles(c)) & DISTRIBUTION]
            self.omitted += [f"{prefix}/{c.name}" for c in ours]
            added = [c for c in added if c not in ours]
            if hushed:
                self.droppable |= {id(c) for c in added}
            removed = self.removed(mine, at)
            deleted = going[at]
            # a device the board lacks is disabled, as a board file does; one already off, or
            # under a node the board disables, needs nothing
            devices = [c for c in removed if compatibles(c) and not disabled(c)]
            for child in [] if hushed else [c for c in devices if c not in deleted]:
                self.block(f"{prefix}/{child.name}").props.append(Prop.of("status", '"disabled"'))
            labels = [label for label in mine.labels if label not in theirs.labels]
            if not (props or gone or added or deleted or labels):
                continue
            out = self.block(at)
            self.stands_for[id(out)] = mine
            if not out.lead and out.name.startswith("&"):
                out.lead = list(mine.lead)
            out.labels += labels
            out.props += [Prop(n, [f"/delete-property/ {n};"]) for n in gone]
            out.props += [Prop(c.name, [f"/delete-node/ {c.name};"]) for c in deleted]
            out.props += props
            out.children += added
            self.added |= {id(n) for c in added for n in [c, *(x for _, x in walk(c))]}
            self.born_empty |= {
                id(n) for c in added for n in [c, *(x for _, x in walk(c))] if empty(n)
            }

    def cascade(self, met: list[tuple[Node, str]], going: dict[str, list[Node]]) -> set[str]:
        """The labels that vanish: going's, and a device's the board lacks that points to one, which
        dtc would still resolve, until no deleted node leaves a reference behind. going gains each
        such device in its parent's place."""
        vanishing = {label for gone in going.values() for c in gone for label in labelled(c)}
        while True:
            pointing = [
                (at, c)
                for mine, at in met
                if at in going
                for c in self.removed(mine, at)
                if c not in going[at] and references(c) & vanishing
            ]
            if not pointing:
                self.deleted = {
                    id(n)
                    for gone in going.values()
                    for c in gone
                    for n in [c, *(x for _, x in walk(c))]
                }
                return vanishing
            for at, c in pointing:
                going[at].append(c)
                vanishing |= labelled(c)

    def unpointed(self, at: str, vanishing: set[str]) -> None:
        """A node off in both trees loses each property naming a label that vanishes: dtc resolves
        a disabled node's references too."""
        dangling = [p.name for p in self.soc[at].props if points_to(p, vanishing - self.labels)]
        if dangling:
            out = self.block(at)
            out.props += [Prop(n, [f"/delete-property/ {n};"]) for n in dangling]

    def prune(self) -> None:
        """Each node the board adds that nothing written references, as long as one goes: a pin
        group, which configures no pin unless a device selects it, a disabled node, or one under
        a node the board disables; and any node left empty, but one the board adds empty."""
        # what the base still points to counts as much as what the view writes
        kept = {
            label
            for n in self.soc.values()
            if id(n) not in self.deleted
            for p in n.props
            for label in REFERENCE.findall(p.value)
        }
        while True:
            referenced = set(REFERENCE.findall(self.text())) | kept
            if not any(self.pruned(b, referenced) for b in self.blocks.values()):
                return

    def pruned(self, node: Node, referenced: set[str], under: bool = False) -> bool:
        here = under or controller(self.stands_for.get(id(node), node))
        idle = [
            c
            for c in node.children
            if (
                empty(c)
                and id(c) not in self.born_empty
                or id(c) in self.added
                and (pin_group(c, here) or disabled(c) or id(c) in self.droppable)
            )
            and not labelled(c) & referenced
        ]
        node.children = [c for c in node.children if c not in idle]
        # a kept pin group's children are its own pins, not groups to prune
        nested = [self.pruned(c, referenced, here) for c in node.children if not pin_group(c, here)]
        return bool(idle) or any(nested)

    def under_pinctrl(self, path: str) -> bool:
        """Whether the dtsi's node at path is a pin controller or below one."""
        while path:
            node = self.soc.get(path or "/")
            if node is not None and controller(node):
                return True
            path = path.rsplit("/", 1)[0]
        return False

    def text(self) -> str:
        root = self.blocks.get("/", Node("/"))
        others = [self.blocks[k] for k in sorted(self.blocks) if k != "/"]
        blocks = [b for b in [root, *others] if b.props or b.children or b.labels]
        return "\n\n".join("\n".join(written(b, self.dtsi_of)) for b in blocks)

    def same(self, mine: Prop, theirs: Prop | None) -> bool:
        """The same value however written: a macro as its number, a number however spelled, a
        reference to one node as that node, by label or by path."""
        if theirs is None:
            return False
        targets = self.board_target(mine.value), self.soc_target(theirs.value)
        if targets != (None, None):
            return targets[0] == targets[1]
        return self.number(mine.value) == self.number(theirs.value)

    def board_target(self, value: str) -> str | None:
        """The node a board's path-valued reference names: the dtsi's path for it, or its key
        in the board's tree marked as the board's own."""
        found = PATH_REFERENCE.match(value)
        path = found and (self.board_labels.get(found.group(1) or "") or found.group(2))
        if not path or path not in self.board_nodes:
            return None
        return self.soc_paths.get(self.key(path), f"board {self.key(path)}")

    def soc_target(self, value: str) -> str | None:
        found = PATH_REFERENCE.match(value)
        path = found and (self.soc_labels.get(found.group(1) or "") or found.group(2))
        return self.soc_paths.get(self.key(path)) if path else None

    def by_label(self, prop: Prop) -> Prop:
        """A path-valued reference written as its node's label, as a board file writes one."""
        found = PATH_REFERENCE.match(prop.value)
        target = self.board_nodes.get(found.group(2)) if found and found.group(2) else None
        if target is None or not target.labels:
            return prop
        return Prop(prop.name, [f"{prop.name} = &{target.labels[0]};"], prop.comments)

    def number(self, value: str) -> str:
        return normal(TOKEN.sub(lambda m: str(self.values.get(m.group(0), m.group(0))), value))

    def demand(self, history: list[tuple[str, Node]], text: str) -> Demand:
        """What the final tree asks beyond the base: the compatibles and rc-map names of its
        enabled nodes, their vendor properties, and each dtsi change the view keeps."""
        enabled = [n for p, n in self.board_nodes.items() if self.enabled(p)]
        # one with no vendor prefix is a generic binding, which the base has
        strings = {c for n in enabled for c in compatibles(n) if "," in c}
        strings |= {s for n in enabled if (p := n.prop(RC_MAP)) for s in QUOTED.findall(p.value)}
        properties = {
            p.name
            for n in enabled
            for p in n.props
            if "," in p.name and not p.name.startswith(("linux,", "#"))
        }
        used = set(REFERENCE.findall(text))
        kept = {
            patch: found
            for (_, before), (patch, after) in zip(history, history[1:])
            if (found := self.kept(before, after, used))
        }
        return Demand(strings, properties, kept)

    def kept(self, before: Node, after: Node, used: set[str]) -> list[str]:
        """What a dtsi patch changes that the view keeps: a label it defines that the view uses,
        a node it adds that the board describes, a property it sets or drops there as the board
        has it."""
        if not before.children:
            return ["the dtsi, which it creates"]
        old = {self.key(p): n for p, n in [("/", before), *walk(before)]}
        found: list[str] = []
        for path, node in [("/", after), *walk(after)]:
            was = old.get(self.key(path))
            labels = set(node.labels) - set(was.labels if was else [])
            found += [f"&{label}" for label in node.labels if label in labels & used]
            mine = self.described.get(self.key(path))
            if mine is None:
                continue
            name = f"&{node.labels[0]}" if node.labels else path
            if was is None:
                if self.key(path.rsplit("/", 1)[0] or "/") in old:  # not under a node it adds
                    found.append(name)
                continue
            props = [
                p.name for p in node.props if p.name not in LAYOUT and self.keeps(mine, was, p)
            ]
            props += [p.name for p in was.props if not node.prop(p.name) and not mine.prop(p.name)]
            found += [f"{name} {p}" for p in props]
        return list(dict.fromkeys(found))

    def keeps(self, mine: Node, was: Node, prop: Prop) -> bool:
        """Whether the board's node has the value a patch gives a property."""
        before, board = was.prop(prop.name), mine.prop(prop.name)
        changed = before is None or normal(before.value) != normal(prop.value)
        return changed and board is not None and self.same(board, prop)

    def render(self, setting: Setting) -> str:
        self.changes()
        self.prune()
        body = self.text()
        used = set(TOKEN.findall(body))
        includes = [
            line
            for line in self.board.preamble
            if INCLUDE_LINE.match(line) and used_header(line, setting.defines, used)
        ]
        notice = ["/*", " * Written by tools/dtcx/upstream.py from board.dts: a view, not edited."]
        notice += [f" * Over {setting.base_kernel}."]
        needed = needs(self.demand(setting.history, body), setting.patches)
        if needed:
            notice += [
                " * Needs, beyond it, found by name and so best-effort: each",
                " * patch adding a name the tree uses or a dtsi change it keeps, which may in",
                " * turn need others before it:",
                *(line for n in needed for line in wrapped(n)),
            ]
        if self.omitted:
            notice += [" * Left out, the distribution's, not the board's:"]
            notice += [f" *   {path}" for path in self.omitted]
        head = ["/dts-v1/;", "", *notice, " */", "", f'#include "{setting.soc_file}"', *includes]
        return "\n".join(head) + "\n\n" + body + "\n"


def used_header(line: str, defines: dict[str, set[str]], used: set[str]) -> bool:
    """An include the file needs: one that defines a name it uses; any, unknown."""
    header = HEADER.search(line)
    names = defines.get(header.group(1)) if header else None
    return names is None or bool(names & used)


def written(block: Node, dtsi_of: dict[int, Node]) -> list[str]:
    """A block's lines; dtc takes one label on a &reference, so each one more is a block of its
    own, one line each, under a comment that says the board names the node more than one way."""
    tidy = tidied(block, dtsi_of)
    if not block.name.startswith("&"):
        return render(tidy, 0)
    labels, tidy.labels = tidy.labels, tidy.labels[:1]
    empty = not tidy.props and not tidy.children
    named = sorted(labels if empty else labels[1:])
    lines = [f"/* on this board {block.name[1:]} is also {' and '.join(named)} */"] if named else []
    lines += [f"{label}: {block.name} {{ }};" for label in named]
    return lines if empty else lines + render(tidy, 0)


def tidied(node: Node, dtsi_of: dict[int, Node]) -> Node:
    """A node as a board file writes it, its compiled tree unchanged: what it deletes first, then
    what the dtsi already has, whose place the dtsi fixes, standard properties before vendor ones
    and children by name (aliases by name too), then what is new in the board's order, status
    last, and the children it deletes, which dtc takes only after every property; each sunxi
    GPIO named in a comment, each long table wrapped at its entries."""
    theirs = dtsi_of.get(id(node), Node(""))
    fixed = {p.name for p in theirs.props}
    deletes = [p for p in node.props if p.statement[0].startswith("/delete-node/")]
    erased = [p for p in node.props if p.statement[0].startswith("/delete-property/")]
    kept = [p for p in node.props if p not in deletes + erased and p.name not in LAYOUT]
    by_name = node.name == "aliases"
    ordered = sorted(
        (p for p in kept if p.name in fixed and p.name != "status"),
        key=lambda p: natural(p.name) if by_name else [vendor(p.name)],
    )
    ordered += [p for p in kept if p.name not in fixed and p.name != "status"]
    props = erased + [pinned(p) for p in ordered]
    props += [p for p in kept if p.name == "status"] + deletes
    known = {c.name for c in theirs.children}
    children = sorted((c for c in node.children if c.name in known), key=lambda c: natural(c.name))
    children += [c for c in node.children if c.name not in known]
    return Node(node.name, node.labels, node.lead, props, [tidied(c, dtsi_of) for c in children])


def vendor(name: str) -> bool:
    """Whether a property is a vendor's: a prefix and comma, linux's own aside."""
    return "," in name and not name.startswith("linux,")


def natural(name: str) -> list[str | int]:
    """A name's sort key with its numbers as numbers: serial2 before serial10."""
    return [int(p) if p.isdigit() else p for p in re.split(r"(\d+)", name)]


def pinned(prop: Prop) -> Prop:
    """A property of sunxi GPIOs, each one's pin named after it: <&pio 7 6 …> is PH6; none
    where an entry is not plain."""
    inner = normal(prop.value).removeprefix("<").removesuffix(">")
    if "/*" in prop.statement[-1] or not prop.name.endswith(("gpios", "gpio")):
        return prop
    entries = SUNXI_GPIO.findall(inner)
    if not entries or SUNXI_GPIO.sub("", inner).strip():
        return prop
    pins = ", ".join(f"P{chr(ord(SUNXI_BANKS[c]) + int(bank))}{pin}" for c, bank, pin in entries)
    return Prop(
        prop.name, [*prop.statement[:-1], f"{prop.statement[-1]} /* {pins} */"], prop.comments
    )


def wrapped(entry: str) -> list[str]:
    """A header entry in comment lines, the patch first, what it is needed for indented after."""
    patch, _, reasons = entry.partition(": ")
    indent = " *     "
    lines = textwrap.wrap(
        reasons,
        WIDTH,
        initial_indent=indent,
        subsequent_indent=indent,
        break_on_hyphens=False,
        break_long_words=False,
    )
    return [f" *   {patch}:", *lines]


def mentions(text: str, name: str) -> bool:
    """Whether text names `name` whole: a quoted string, a YAML key or list entry."""
    return re.search(rf"(?<![\w,.#-]){re.escape(name)}(?![\w,.-])", text) is not None


def needs(demand: Demand, patches: list[str]) -> list[str]:
    """Each patch the board file needs beyond its base, with what it needs from it: a dtsi change
    it keeps; a string it writes that drivers or bindings match (a compatible, an rc-map name),
    or a vendor property it sets, that the patch adds outside the dts files."""
    out: list[str] = []
    for patch in dict.fromkeys(patches):
        found = list(demand.kept.get(patch, []))
        for part in re.split(r"(?m)^(?=--- )", (REPO / patch).read_text(errors="replace")):
            header = FILE_HEADER.match(part)
            if header is None or header.group(1).endswith((".dts", ".dtsi")):
                continue
            added = "\n".join(
                line[1:]
                for line in part.splitlines()
                if line.startswith("+") and not line.startswith("+++")
            )
            found += [f'"{s}"' for s in sorted(demand.strings) if mentions(added, s)]
            found += [p for p in sorted(demand.properties) if mentions(added, p)]
        if found:
            out.append(f"{patch}: {', '.join(dict.fromkeys(found))}")
    return out


def kernel_patches(soc_patches: str) -> list[str]:
    """The patches the board's kernel applies: its conf's, then each module's built for it."""
    if not soc_patches:
        return []
    family = Path(soc_patches).stem
    modules = [
        conf
        for conf in sorted((REPO / "modules").glob("*.conf"))
        if (kernels := CONF_KERNELS.search(conf.read_text())) and family in kernels.group(1).split()
    ]
    return [
        p for conf in [REPO / soc_patches, *modules] for p in CONF_PATCH.findall(conf.read_text())
    ]


def base_kernel(url: str) -> str:
    """The kernel a dtsi URL pins: its repository and tag or commit."""
    found = PINNED_REPO.match(url)
    if found is None:
        return url
    ref = found.group(2)
    return f"{found.group(1)} at {ref[:SHORT_COMMIT] if COMMIT.fullmatch(ref) else ref}"


def included(files: dict[str, str], base: Base) -> Path:
    """The base's include root, holding every header the dtsi files name besides the base's own,
    fetched once from the same pinned tree."""
    for text in files.values():
        for header in HEADER.findall(text):
            target = base.root / header
            if not target.exists():
                target.parent.mkdir(parents=True, exist_ok=True)
                body = fetch(f"{base.url}/{header}")
                if "\n" not in body.strip() and not body.startswith("/*"):  # a symlink's target
                    body = fetch(f"{base.url}/{Path(header).parent / body.strip()}")
                target.write_text(body)
    return base.root


def compiled(text: str, files: dict[str, str], include: Path) -> Path:
    """The board file compiled against the dtsi files, as build-dtb.sh compiles board.dts."""
    tmp = Path(tempfile.mkdtemp())
    for name, body in files.items():
        (tmp / name).write_text(body)
    (tmp / "board.dts").write_text(text)
    cpp = ["cc", "-E", "-nostdinc", "-undef", "-D__DTS__", "-x", "assembler-with-cpp", "-P"]
    done = subprocess.run(
        [*cpp, "-I", str(tmp), "-I", str(include), str(tmp / "board.dts")],
        capture_output=True,
        text=True,
    )
    if done.returncode:
        sys.exit(f"the board file does not preprocess:\n{done.stderr}")
    flat = done.stdout
    dtb = tmp / "board.dtb"
    subprocess.run(
        # -@ as build-dtb.sh: a symbol keeps a node /omit-if-no-ref/ would drop
        [str(DTC), "-q", "-@", "-I", "dts", "-O", "dtb", "-o", str(dtb)],
        input=flat,
        text=True,
        check=True,
    )
    return dtb


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--prove", metavar="DTB", help="the board.dtb the result must describe")
    parser.add_argument("--soc", metavar="URL", help="the base dtsi or board file, for the conf's")
    parser.add_argument(
        "source", help="the factory tree's base, whose translate.conf names the dtsi"
    )
    parser.add_argument("target", help="the base board.dts is written against")
    parser.add_argument("board", help="the board's final tree, board.dts")
    args = parser.parse_args()

    base = Base.load(args.target)
    # a translated tree's dtsi is the one its translation completes against; else its base's
    translated = (
        args.source != args.target and (HERE / "bases" / f"{args.source}.translate.conf").is_file()
    )
    named = Vocabulary.load(args.source) if translated else base
    url = args.soc or named.soc
    if not url:
        sys.exit(f"{args.target} names no soc dtsi")
    soc = patched_soc(url, named.soc_patches, base).root
    files = dtsi_files(url, named.soc_patches, base)
    setting = Setting(
        url.rsplit("/", 1)[-1],
        base_kernel(url),
        kernel_patches(named.soc_patches),
        dtsi_history(url, named.soc_patches, base),
        {h: set(DEFINE.findall((base.root / h).read_text())) for h in base.headers},
    )
    upstream = Upstream(soc, Source.parse(Path(args.board).read_text()), base.defines())
    text = upstream.render(setting)
    sys.stdout.write(text)
    if args.prove:
        view = compiled(text, files, included(files, base))
        lines = differences(
            Blob.read(Path(args.prove).read_bytes()),
            Blob.read(view.read_bytes()),
            base.dialect,
            Projection(tuple(upstream.omitted)),
        )
        print(f"  {len(lines)} differences from {Path(args.prove).name}", file=sys.stderr)
        for line in lines:
            print(line, file=sys.stderr)
        if lines:
            sys.exit(1)


if __name__ == "__main__":
    main()
