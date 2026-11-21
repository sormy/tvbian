#!/usr/bin/env python3
"""Translate a vendor tree into mainline's dialect, by bases/<source>.translate.conf.

Each vendor node meets its mainline counterpart in mainline's SoC dtsi, as our kernel builds it:
by label, else by unit address under counterpart parents. The SoC's facts, a block's compatible,
wiring and geometry, are mainline's; the board's come from the factory tree. The conf is the vendor
dialect's vocabulary: each vendor property or node not mainline's has one outcome, kept, converted,
dropped with the reason that makes it safe, unsupported, or unresolved, a question for the board's
bring-up. A token the conf does not name is reported, never guessed.

  Usage: translate.py [--report <file>] <source base> <target base> <factory_board.dts> \
      > factory_board_translated.dts
"""

from __future__ import annotations

import argparse
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path

from conversions import NUMBER, REFERENCE, Conversions, gpio, okay, opp_v2, speed_bins, voltage_bins
from dtcx import Base
from dts import Node, Prop, Source, base_name, compatibles, unit, walk
from mainline import Mainline, patched_soc, pin_functions
from vocabulary import (
    BUILT,
    DROPPED,
    MAINLINE,
    UNRESOLVED,
    UNSUPPORTED,
    WITHHOLD,
    WRAPPER,
    Rule,
    Vocabulary,
    fill,
)

OPP_TABLE = "operating-points-v2"
OPP_HZ = re.compile(r"<\s*(\d+)\s*>")

SHELL = ("device_type", "status")  # what a vendor-only node keeps once its contents went
# the devicetree spec's own device types: a node holding one says what it is, as /memory does,
# whose reg the bootloader writes
SPEC_DEVICE_TYPES = ('"memory"', '"cpu"')
Cells = tuple[tuple[int, int], tuple[int, int]]  # (vendor's, mainline's) address and size cells


@dataclass
class Report:
    """What the translation could not decide, one entry a decision with every place it applies:
    the board's questions, and the vocabulary's gaps."""

    entries: dict[tuple[str, str], list[str]] = field(default_factory=dict)
    dormant: bool = False  # reading a node the vendor disabled, or one under it

    def add(self, kind: str, what: str, where: str) -> None:
        if kind == DROPPED and self.dormant:  # what a disabled node carries configures nothing
            return
        if kind == UNRESOLVED and self.dormant:  # a question only once a board enables the node
            kind = "dormant"
        self.entries.setdefault((kind, what), []).append(where or "/")

    def count(self, kind: str) -> int:
        return sum(1 for k, _ in self.entries if k == kind)

    def text(self) -> str:
        return "".join(
            f"{kind} {what}  [{len(places)}: {', '.join(places[:3])}{', ...' if len(places) > 3 else ''}]\n"
            for (kind, what), places in sorted(self.entries.items())
        )


class Translator:
    def __init__(self, vocabulary: Vocabulary, factory: Node, mainline: Mainline) -> None:
        self.v = vocabulary
        self.m = mainline
        self.report = Report()
        self.lineage: list[str] = []  # compatibles of the node being read and the nodes above it
        self.labels = {
            label: self.renamed(self.v.labels, label) or label
            for _, node in walk(factory)
            for label in node.labels
        }
        self.matched: set[str] = set()
        self.elsewhere: list[str] = []  # mainline nodes the vendor's labels name at other addresses
        self.regulator_names = {
            p.value.strip('"')
            for _, n in walk(factory)
            for p in n.props
            if p.name == "regulator-name"
        }
        self.written: dict[str, Node] = {}  # mainline path -> the node translated for it
        # (translated, mainline, its path, whether the vendor's node states a status)
        self.completions: list[tuple[Node, Node, str, bool]] = []
        self.shells: set[int] = set()  # vendor-only nodes each of whose contents went elsewhere
        self.pin_groups: set[int] = set()  # the vendor's pin groups, translated
        self.paths: dict[str, str] = {}  # vendor path -> translated path, for aliases
        self.labelled = {label: path for path, node in walk(factory) for label in node.labels}
        # labels another node uses, its pin groups and aliases aside: a block something drives
        self.used = {
            label
            for path, node in walk(factory)
            if path != "/aliases"
            for p in node.props
            if not p.name.startswith("pinctrl-")
            for label in REFERENCE.findall(p.value)
        }
        self.lifted: list[Node] = []  # a wrapper's children, for its parent to take
        self.unscaled: set[str] = set()  # labels of nodes whose OPP table was withheld
        self.placed: dict[int, str] = {}  # a node with a counterpart -> mainline's path for it
        self.aliases: list[tuple[list[Prop], Prop, Rule, list[str], str]] = []
        self.current: Node | None = None  # the vendor node whose properties are being read
        self.token = ""  # the node rule that matched, for the report
        self.scopes: list[str] = []  # the node's vendor compatibles and name, for scoped rules
        self.built: list[tuple[str, Node, str, list[str]]] = []  # (action, vendor node, path, args)
        self.opp_tables: list[tuple[str, str]] = []  # (label, operating-points)
        self.opp_rails: list[tuple[str, str]] = []  # (regulator label, its consumer's OPP table)
        self.low_banks: list[tuple[str, str]] = []  # (pin group label, path): a bank at 1.8 V

    def renamed(self, rules: list[Rule], token: str) -> str:
        """The token as mainline names it: by a rule scoped to a compatible this node or one
        above it has, first."""
        found = self.rule(rules, token, self.lineage)
        return fill(found[0].args[0], found[1]) if found else ""

    def rule(
        self, rules: list[Rule], token: str, scopes: list[str]
    ) -> tuple[Rule, list[str]] | None:
        """The rule for a token: one scoped to this node's compatible or name first."""
        for scoped in (True, False):
            for rule in rules:
                if bool(rule.scope) != scoped or (scoped and rule.scope not in scopes):
                    continue
                numbers = rule.pattern.match(token)
                if numbers is not None:
                    return rule, numbers
        return None

    def relabel(self, text: str) -> str:
        return REFERENCE.sub(lambda m: "&" + self.labels.get(m.group(1), m.group(1)), text)

    def counterpart(self, fnode: Node, parent: str | None) -> str | None:
        """The mainline node this vendor node is: by label, under its counterpart parent, by its
        unique address, or, with no address, by its unique name; never one whose compatible says
        it is another block."""
        name = self.renamed(self.v.names, base_name(fnode)) or base_name(fnode)
        labelled = [self.m.by_label.get(self.labels[label]) for label in fnode.labels]
        self.elsewhere = [c for c in labelled if c and not self.located(fnode, c)]
        candidates = [c for c in labelled if c not in self.elsewhere]
        candidates.append(self.m.child(parent, name, unit(fnode.name)) if parent else None)
        # no address to meet it by; an OPP row only meets a row of its own table, whose frequencies
        # other tables repeat
        if not unit(fnode.name) and not (parent and self.ladder(self.m.nodes[parent])):
            candidates.append(self.m.named(name))
        elif compatibles(fnode):  # a block's address is unique on the SoC; a memory node's is not
            candidates.append(self.m.at(unit(fnode.name)))
        return next((c for c in candidates if c and self.agrees(fnode, self.m.nodes[c])), None)

    @staticmethod
    def ladder(mnode: Node) -> bool:
        """Whether a mainline node is an OPP table."""
        compatible = mnode.prop("compatible")
        return compatible is not None and "operating-points-v2" in compatible.value

    def located(self, fnode: Node, mpath: str) -> bool:
        """Whether the mainline node a label names sits at the vendor node's address: a label is
        only a name, and the vendor's may name another block."""
        vendor, mainline = unit(fnode.name), unit(self.m.nodes[mpath].name)
        if not vendor or not mainline:
            return True
        return bool({vendor, *reg_starts(fnode)} & {mainline, self.m.absolute.get(mpath)})

    def agrees(self, fnode: Node, mnode: Node) -> bool:
        """Whether a mainline node can be this vendor node: where the vocabulary names the vendor
        compatible's mainline one, the mainline node has it."""
        vendor = compatibles(fnode)
        expected = self.v.compatibles.get(vendor[0]) if vendor else None
        return not expected or bool(set(expected) & set(compatibles(mnode)))

    def node(self, fnode: Node, path: str, mparent: str | None, cells: Cells | None) -> Node | None:
        above, asleep = self.lineage, self.report.dormant
        self.lineage = above + compatibles(fnode)
        status = fnode.prop("status")
        self.report.dormant = asleep or (status is not None and "disable" in status.value)
        try:
            return self.translated(fnode, path, mparent, cells)
        finally:
            self.lineage, self.report.dormant = above, asleep

    def translated(
        self, fnode: Node, path: str, mparent: str | None, cells: Cells | None
    ) -> Node | None:
        vendor = compatibles(fnode)
        scopes = vendor + [base_name(fnode)]
        for token in scopes + [fnode.name]:
            found = self.rule(self.v.nodes, token, [])
            self.token = found[0].text if found else token
            if found and found[0].action in BUILT:
                self.built.append((found[0].action, fnode, path, found[0].args))
                return None
            if found and found[0].action == WRAPPER:
                for child in fnode.children:
                    out = self.node(child, f"{path}/{child.name}", mparent, cells)
                    self.lifted += [out] if out else []
                return None
            if found and found[0].action == "unused-by":
                flag = fnode.prop(found[0].args[0])
                if flag is not None and flag.value.strip("<>") not in ("0", "0x0", "0x00"):
                    self.report.add(UNRESOLVED, f"node {self.token}", path)
                return None
            if found and found[0].action in (DROPPED, UNRESOLVED, UNSUPPORTED):
                self.report.add(found[0].action, f"node {self.token}", path)
                return None
            if found:
                break
        if okay(fnode):
            for token in scopes:
                found = self.rule(self.v.also, token, [])
                if found:
                    self.built.append((found[0].action, fnode, path, found[0].args))
                    break
        mpath = self.counterpart(fnode, mparent) if path else "/"
        if mpath is None and self.elsewhere:
            self.report.add(UNRESOLVED, f"label at another address: {self.elsewhere[0]}", path)
            return None
        mnode = self.m.nodes.get(mpath) if mpath else None
        if mpath:
            self.matched.add(mpath)
        if mnode is None and vendor and vendor[0] not in self.v.compatibles:
            self.report.add("unknown", f"compatible {vendor[0]}", path)
            return None
        if mnode is not None:
            name, labels = mnode.name, list(mnode.labels)
        else:
            name = self.renamed(self.v.names, base_name(fnode)) or base_name(fnode)
            address = unit(fnode.name) or self.address(fnode)
            if self.v.pin_group and fnode.prop(self.v.pin_group):
                name = "-".join([name, variant(address), "pins"] if address else [name, "pins"])
                name = name.replace("_", "-")  # mainline's pin group names
            elif address:
                name += address if name.endswith("-") else f"@{address}"
            labels = [self.labels[label] for label in fnode.labels if self.labels[label] != "-"]
        above = self.paths.get(path.rsplit("/", 1)[0] or "/", "")
        self.paths[path or "/"] = (
            mpath if mnode is not None and mpath else f"{above.rstrip('/')}/{name}" if path else "/"
        )
        props = self.props(fnode, path, scopes, mnode, cells)
        mainline_cells = self.v.cells.get(base_name(fnode))
        inner = (vendor_cells(fnode), mainline_cells) if mainline_cells else None
        lifted, self.lifted = self.lifted, []
        children = [self.node(c, f"{path}/{c.name}", mpath, inner) for c in fnode.children]
        children = [c for c in children if c is not None] + self.lifted
        self.lifted = lifted
        if mpath in self.written:
            self.merge(self.written[mpath], props, children, path)
            return None
        out = Node(name, labels, [], props, children)
        if mnode is None and self.v.pin_group and fnode.prop(self.v.pin_group):
            self.pin_groups.add(id(out))
        if mnode is None and not children and all(p.name in SHELL for p in props):
            if not any(p.name == "device_type" and p.value in SPEC_DEVICE_TYPES for p in props):
                self.shells.add(id(out))
        if mnode is not None and mpath:
            self.placed[id(out)] = mpath
            self.written[mpath] = out
            self.completions.append((out, mnode, mpath, fnode.prop("status") is not None))
        return out

    def merge(self, out: Node, props: list[Prop], children: list[Node], path: str) -> None:
        """Another vendor node for a block already written, as the vendor splits one block into a
        node a function (the codec and its DAI at one address): its properties added to the
        block's, a property both state with different values a question."""
        for prop in props:
            have = out.prop(prop.name)
            if have is None:
                out.props.append(prop)
            elif have.value != prop.value:
                self.report.add(UNRESOLVED, f"property {prop.name}: two vendor nodes differ", path)
        out.children += children

    def address(self, fnode: Node) -> str:
        """A node with reg and no unit address is named after its first reg cell, as the
        devicetree spec names a node; the vendor's PMIC is pmu, with reg 0x36."""
        reg = fnode.prop("reg")
        first = reg.value.strip("<>").split()[0] if reg and reg.value.startswith("<") else ""
        return f"{int(first, 0):x}" if first and NUMBER.match(first) else ""

    def props(
        self, fnode: Node, path: str, scopes: list[str], mnode: Node | None, cells: Cells | None
    ) -> list[Prop]:
        out: list[Prop] = []
        if mnode is None and compatibles(fnode):
            values = ", ".join(f'"{c}"' for c in self.v.compatibles[compatibles(fnode)[0]])
            out.append(Prop.of("compatible", values))
        self.current, self.scopes = fnode, scopes
        for prop in fnode.props:
            if prop.name == "compatible":
                continue
            found = self.rule(self.v.props, prop.name, scopes)
            if found is None:
                self.report.add("unknown", f"property {prop.name}", path)
                continue
            rule, captures = found
            if rule.action == MAINLINE and mnode is not None:
                continue
            if (
                rule.action == MAINLINE
            ):  # no mainline node states it: the vendor's describes the device
                rule = Rule(rule.pattern, "same")
            if prop.name == "reg" and cells and prop.value and rule.action == "same":
                out.append(self.recelled(prop, cells, path))
                continue
            if prop.name == "ranges" and cells and cells[0] != cells[1] and prop.value:
                self.report.add("unknown", "value of ranges: across cell counts", path)
                continue
            if rule.action == "alias":
                self.aliases.append((out, prop, rule, captures, path))
            else:
                out += self.converted(prop, rule, captures, path)
        return out

    def complete(self, out: Node, mnode: Node, mpath: str, stated: bool) -> None:
        """What mainline's node says and the vendor's does not: properties first, in mainline's
        order; then children the vendor tree has no counterpart for. A vendor "okay" on a node
        mainline enables by default says nothing more; a vendor node with no status is enabled, which
        mainline's disabled default does not override; one whose status a rule dropped leaves
        mainline's."""
        enabled = mnode.prop("status") is None
        out.props = [
            p for p in out.props if not (enabled and p.name == "status" and "okay" in p.value)
        ]
        if not enabled and out.prop("status") is None and not stated:
            out.props.append(Prop.of("status", '"okay"'))  # the vendor's: no status is okay
        have = {p.name for p in out.props}
        out.props = [
            p for p in mnode.props if p.name not in have and not self.withheld(p.name, mnode)
        ] + out.props
        if out.prop(OPP_TABLE) is None and self.withheld(OPP_TABLE, mnode):
            self.unscaled.update(out.labels)
        names = {c.name for c in out.children}
        # an OPP table's rows are the vendor's: a row only mainline's has is a speed this chip's
        # bin was not tested at, but for the rate the device rests at suspended, below them all
        ladder = self.ladder(mnode)
        slowest = min((opp_rate(c) for c in out.children if c.name.startswith("opp-")), default=0)
        for child in mnode.children:
            cpath = f"{'' if mpath == '/' else mpath}/{child.name}"
            if ladder and child.name.startswith("opp-") and not rests(child, slowest):
                continue
            if child.name not in names and cpath not in self.matched:
                out.children.append(self.unmatched(child, cpath))

    def withheld(self, name: str, mnode: Node) -> bool:
        found = self.rule(self.v.props, name, compatibles(mnode) + [base_name(mnode)])
        return found is not None and found[0].action == WITHHOLD

    def unmatched(self, mnode: Node, mpath: str) -> Node:
        """A mainline subtree as mainline writes it, less the nodes vendor nodes met, which move in
        under it: the vendor's GPU at its root, mainline's under a bus the vendor never names."""
        children = [
            self.unmatched(c, f"{mpath}/{c.name}")
            for c in mnode.children
            if f"{mpath}/{c.name}" not in self.matched
        ]
        out = Node(mnode.name, list(mnode.labels), list(mnode.lead), list(mnode.props), children)
        self.placed[id(out)] = mpath
        return out

    def converted(self, prop: Prop, rule: Rule, captures: list[str], path: str) -> list[Prop]:
        statement = [self.relabel(line) for line in prop.statement]
        value = prop.value
        if rule.action in (DROPPED, WITHHOLD) or (rule.action == "none-if-empty" and not value):
            if rule.action == DROPPED:
                self.report.add(DROPPED, f"property {prop.name}", f"{path} = {value}")
            return []
        if rule.action == "none-if-empty" and rule.args == ["same"]:
            return [Prop(prop.name, statement)]
        if rule.action == "none-if-empty":
            self.report.add("unresolved", f"property {rule.text} = {value}", path)
            return []
        if rule.action == UNRESOLVED:
            self.report.add("unresolved", f"property {rule.text}", f"{path} = {value}")
            return []
        if rule.action == "same":
            return [Prop(prop.name, statement)]
        if rule.action == "pinctrl":
            return self.pin_states(prop, path)
        if rule.action == "gpio":
            return [
                Prop.of(prop.name, self.relabel(gpio(value, rule.args[0], "pull" in rule.args)))
            ]
        if rule.action == "opp-v2":
            self.opp_tables.append((rule.args[0], prop.value))
            return [Prop.of("operating-points-v2", f"<&{rule.args[0]}>")]
        if rule.action == "bank-1v8":
            pins = self.current.prop("pinctrl-0") if self.current else None
            for group in REFERENCE.findall(self.relabel(pins.value) if pins else ""):
                self.low_banks.append((group, path))
            return []
        if rule.action == "supply-name":
            if value.strip('"') in self.regulator_names:  # the vendor's lookup finds it
                self.report.add(UNRESOLVED, f"property {rule.text} = {value}", path)
            return []
        if rule.action == "implies":
            return [Prop.of(rule.args[0], " ".join(rule.args[1:]))]
        if rule.action == "opp-range":
            table = self.current.prop("operating-points-v2") if self.current else None
            for rail in REFERENCE.findall(self.relabel(value)):
                for opps in REFERENCE.findall(self.relabel(table.value) if table else ""):
                    self.opp_rails.append((rail, opps))
            return [Prop(prop.name, statement)]
        if rule.action == "alias":
            named = value.strip('"').split('"')[0]
            vendor = self.labelled.get(named[1:], "") if named.startswith("&") else named
            target = self.paths.get(vendor)
            if target is None:  # the node's own outcome, reported or justified, holds for it
                return []
            mnode = self.m.nodes.get(target)
            return [
                Prop.of(
                    prop.name, f"&{mnode.labels[0]}" if mnode and mnode.labels else f'"{target}"'
                )
            ]
        if rule.action == "as":
            name = fill(rule.args[0], captures)
            value = self.revalued(name, self.relabel(value))
            return [Prop.of(name, value)]
        cell = NUMBER.match(value.strip("<>"))
        if cell is None:
            self.report.add("unknown", f"value of {prop.name}: not one number", f"{path} = {value}")
            return []
        number = int(cell.group(1), 0)
        if rule.action == "flag":
            flags = {int(k, 0): f for k, _, f in (a.partition(":") for a in rule.args)}
            if number not in flags:
                self.report.add("unresolved", f"property {prop.name} = {value}", path)
                return []
            flag = flags[number]
            return [] if flag == "-" else [Prop.of(flag)]
        if rule.action == "scale":
            name, step, offset = rule.args[0], int(rule.args[1]), int(rule.args[2])
            unset = {int(a.split(":")[0], 0) for a in rule.args[3:] if a.endswith(":-")}
            if number in unset:
                return []
            return [Prop.of(name, f"<{number * step + offset}>")]
        if rule.action == "bits":
            moves = {int(old): int(new) for old, _, new in (a.partition(":") for a in rule.args)}
            for bit in range(number.bit_length()):
                if number >> bit & 1 and bit not in moves:
                    self.report.add(UNRESOLVED, f"property {prop.name}: vendor bit {bit}", path)
            mapped = sum(1 << new for old, new in moves.items() if number >> old & 1)
            return [Prop.of(prop.name, f"<0x{mapped:02x}>")]
        sys.exit(f"rule for {prop.name}: unknown action {rule.action}")

    def clocks(self, fnode: Node, path: str, name: str) -> list[Prop]:
        """A vendor node's clock references read through the clock vocabulary, for a node mainline
        has no counterpart of to take them from."""
        found = fnode.prop("clocks")
        specs: list[str] = []
        for ref in REFERENCE.findall(found.value if found else ""):
            hit = self.rule(self.v.clocks, ref, [])
            if hit is None:
                self.report.add("unknown", f"clock {ref}", path)
            elif hit[0].action == "as":
                specs.append(" ".join(fill(a, hit[1]) for a in hit[0].args))
        if not specs:
            return []
        names = ", ".join(f'"{name}"' for _ in specs)
        return [
            Prop.of("clocks", ", ".join(f"<{s}>" for s in specs)),
            Prop.of("clock-names", names),
        ]

    def pin_states(self, prop: Prop, path: str) -> list[Prop]:
        """pinctrl-names read with its pinctrl-N: the default state kept, each other state by its
        rule, kept, renamed or dropped, else a question, since whether a mainline driver selects it
        is the driver's to say."""
        if prop.name != "pinctrl-names":
            return []
        names = re.findall(r'"([^"]*)"', prop.value)
        node = self.current
        out: list[Prop] = []
        kept: list[tuple[str, str]] = []
        for index, name in enumerate(names):
            state = node.prop(f"pinctrl-{index}") if node else None
            if state is None or not state.value:
                continue  # a state with no pin groups selects nothing
            value = self.relabel(state.value)
            if name == "default":
                kept.insert(0, (name, value))
            else:
                found = self.rule(self.v.states, name, self.scopes)
                if found is not None and found[0].action == "used-as":
                    if node is not None and self.used & set(node.labels):
                        renamed = found[0].args[0]
                        kept.insert(0 if renamed == "default" else len(kept), (renamed, value))
                elif found is not None and found[0].action in ("same", "as"):
                    renamed = found[0].args[0] if found[0].action == "as" else name
                    at = 0 if renamed == "default" else len(kept)
                    kept.insert(at, (renamed, value))
                else:
                    kind = (
                        DROPPED if found is not None and found[0].action == DROPPED else UNRESOLVED
                    )
                    self.report.add(kind, f"pin state {name}", f"{path} = {value}")
        if not kept or kept[0][0] != "default":
            return out
        out.append(Prop.of("pinctrl-names", ", ".join(f'"{n}"' for n, _ in kept)))
        out += [Prop.of(f"pinctrl-{i}", v) for i, (_, v) in enumerate(kept)]
        return out

    def revalued(self, name: str, value: str) -> str:
        """Each quoted vendor word in a property's value as mainline names it."""

        def swap(word: re.Match[str]) -> str:
            for rule in self.v.values:
                numbers = rule.pattern.match(word.group(1))
                if rule.args[0] == name and numbers is not None:
                    return f'"{fill(rule.args[1], numbers)}"'
            return word.group(0)

        return re.sub(r'"([^"]*)"', swap, value)

    def recelled(self, prop: Prop, cells: Cells, path: str) -> Prop:
        """reg from the vendor's cell counts to mainline's: a cell added in front as zero, a high cell
        dropped where zero; a nonzero one reported, never cut."""
        (vendor_address, vendor_size), (address, size) = cells
        words = prop.value.strip("<>").split()
        keep: list[str] = []
        stride = vendor_address + vendor_size
        for start in range(0, len(words), stride):
            entry = words[start : start + stride]
            fields = ((entry[:vendor_address], address), (entry[vendor_address:], size))
            for field_, target in fields:
                extra = len(field_) - target
                if any(int(h, 0) for h in field_[:extra]):
                    self.report.add("unknown", f"value of {prop.name}: a nonzero high cell", path)
                keep += ["0"] * -extra + field_[max(extra, 0) :]
        return Prop.of(prop.name, f"<{' '.join(keep)}>")


def selected_functions(root: Node, functions: dict[str, set[str]], report: Report) -> None:
    """Each pin function an enabled node's pin state selects, one mainline's pinctrl has on every
    pin of the group: else the node's whole pinctrl lookup fails, its default state with it. A
    name mainline lacks is the vocabulary's to fix; one a pin lacks, the board's to answer."""
    known = set().union(*functions.values()) if functions else set()
    nodes = [root, *(n for _, n in walk(root))]
    groups = {label: n for n in nodes for label in n.labels}
    for path, node in walk(root):
        if not okay(node):
            continue
        for prop in node.props:
            if not re.fullmatch(r"pinctrl-\d+", prop.name):
                continue
            for label in REFERENCE.findall(prop.value):
                group = groups.get(label)
                # sunxi states its function in the group; meson in a mux node under it
                for mux in [group, *group.children] if group else []:
                    function = mux.prop("function")
                    listed = mux.prop("pins") or mux.prop("groups")
                    name = function.value.strip('"') if function else ""
                    if not name:
                        continue
                    if name not in known:
                        report.add("unknown", f"pin function {name} selected by {prop.name}", path)
                        continue
                    pins = re.findall(r'"([^"]+)"', listed.value) if listed else []
                    for pin in [p for p in pins if name not in functions.get(p, set())]:
                        report.add(
                            UNRESOLVED, f"pin function {name} not on {pin}, by {prop.name}", path
                        )


def opp_rate(row: Node) -> int:
    """An OPP row's rate in Hz, 0 where it has none."""
    hz = row.prop("opp-hz")
    found = OPP_HZ.search(hz.value) if hz else None
    return int(found.group(1)) if found else 0


def rests(row: Node, slowest: int) -> bool:
    """Whether a mainline OPP row is the suspended device's rate, below every vendor row."""
    return row.prop("opp-suspend") is not None and 0 < opp_rate(row) < slowest


def opp_table_of(node: Node) -> str:
    table = node.prop("operating-points-v2")
    return table.value if table else ""


def unthrottled(root: Node, unscaled: set[str]) -> None:
    """Each cooling map naming a node whose OPP table was withheld, gone: nothing scales it."""
    for _, node in walk(root):
        if node.name == "cooling-maps":
            node.children = [c for c in node.children if not throttles(c, unscaled)]


def throttles(cooling_map: Node, labels: set[str]) -> bool:
    device = cooling_map.prop("cooling-device")
    return device is not None and bool(set(REFERENCE.findall(device.value)) & labels)


def unreferenced(root: Node, shells: set[int]) -> None:
    """Each shell nothing in the finished tree references, gone: it says nothing."""
    text = Source([], root).render()
    referenced = set(REFERENCE.findall(text))
    for _, node in [("/", root), *walk(root)]:
        node.children = [c for c in node.children if not said_nothing(c, shells, referenced)]


def unselected(root: Node, groups: set[int]) -> None:
    """Each vendor pin group nothing in the finished tree references, gone: it configures no pin,
    and the vendor's template lists groups for blocks the board has not got. A node that held only
    such groups goes with them; one written empty stays."""
    referenced = set(REFERENCE.findall(Source([], root).render()))

    def emptied(node: Node) -> bool:
        held = bool(node.children)
        node.children = [
            c
            for c in node.children
            if (id(c) not in groups or set(c.labels) & referenced) and not emptied(c)
        ]
        return held and not node.children and not node.props

    emptied(root)


def variant(address: str) -> str:
    """A pin group's vendor unit as the letter the vendor's labels give it (uart1_pins_a is
    uart1@0): mainline's pinctrl schema allows no part of a pin group's name that is digits only."""
    number = int(address, 16)
    return chr(ord("a") + number) if number < 26 else address


def said_nothing(node: Node, shells: set[int], referenced: set[str]) -> bool:
    """A shell still empty once the conversions ran, and referenced by nothing."""
    empty = not node.children and all(p.name in SHELL for p in node.props)
    return id(node) in shells and empty and not set(node.labels) & referenced


def reg_starts(node: Node) -> set[str]:
    """Where a node's registers start, read as one cell or as two: its reg holds the truth when
    the vendor's unit address does not (its GIC is @03020000, its registers at 0x3021000)."""
    reg = node.prop("reg")
    first = (reg.value.strip("<>").split() if reg and reg.value.startswith("<") else [])[:2]
    if not first or not all(NUMBER.match(c) for c in first):
        return set()
    numbers = [int(c, 0) for c in first]
    return {f"{numbers[0]:x}", f"{numbers[0] << 32 | numbers[-1]:x}"}


def vendor_cells(node: Node) -> tuple[int, int]:
    """The cell counts a node gives its children, the spec's 2 and 1 where it states none."""
    address, size = node.prop("#address-cells"), node.prop("#size-cells")
    return (
        int(address.value.strip("<>"), 0) if address else 2,
        int(size.value.strip("<>"), 0) if size else 1,
    )


def relocated(root: Node, placed: dict[int, str]) -> Node:
    """Each node with a mainline counterpart moved under the node at its mainline parent's path,
    where the vendor put it elsewhere: the GPU at the root, mainline's under /soc."""
    at = {
        path: node for node in [root, *(n for _, n in walk(root))] if (path := placed.get(id(node)))
    }
    at["/"] = root
    for parent in [root, *(n for _, n in walk(root))]:
        for child in list(parent.children):
            target = placed.get(id(child))
            home = at.get(target.rsplit("/", 1)[0] or "/") if target else None
            if home is not None and home is not parent:
                parent.children.remove(child)
                home.children.append(child)
    return root


def translate(
    factory: Source,
    vocabulary: Vocabulary,
    mainline: Mainline,
    base: Base,
    functions: dict[str, set[str]] | None = None,
) -> tuple[Source, Report]:
    translator = Translator(vocabulary, factory.root, mainline)
    root = translator.node(factory.root, "", None, None) or Node("/")
    for props, prop, rule, captures, path in translator.aliases:
        props += translator.converted(prop, rule, captures, path)
    root.name = "/"
    for out, mnode, mpath, stated in translator.completions:  # once every vendor node met its own
        translator.complete(out, mnode, mpath, stated)
    root = relocated(root, translator.placed)
    root.children += [opp_v2(label, value) for label, value in translator.opp_tables]
    for _, table in walk(root):
        speed_bins(table)
        voltage_bins(table)
    conversions = Conversions(
        root, translator.report.add, translator.relabel, translator.clocks, translator.revalued
    )
    for action, fnode, path, args in translator.built:
        conversions.run(action, fnode, path, args)
    conversions.finish()
    rails = list(translator.opp_rails) + [
        (rail, table)
        for rail, consumer in conversions.supplied
        for table in REFERENCE.findall(opp_table_of(conversions.by_label[consumer]))
    ]
    for rail, opps in dict.fromkeys(rails):
        conversions.opp_range(rail, opps)
    for group, path in translator.low_banks:
        conversions.group_bank_1v8(group, path)
    unthrottled(root, translator.unscaled)
    unreferenced(root, translator.shells)
    unselected(root, translator.pin_groups)
    if functions:
        selected_functions(root, functions, translator.report)
    head = [f"/* dt-bindings from {base.source} */"] + [f"#include <{h}>" for h in base.headers]
    return Source(["/dts-v1/;", ""] + head, root), translator.report


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--report", help="write the unresolved and unknown tokens here")
    parser.add_argument(
        "source", help="the factory tree's base, whose bases/<source>.translate.conf to apply"
    )
    parser.add_argument("target", help="the base the translated tree is written against")
    parser.add_argument("factory", help="the factory tree, as dtcx wrote it")
    args = parser.parse_args()

    base = Base.load(args.target)
    factory = Source.parse(Path(args.factory).read_text())
    vocabulary = Vocabulary.load(args.source)
    mainline = Mainline(patched_soc(vocabulary.soc, vocabulary.soc_patches, base))
    functions = pin_functions(vocabulary.pin_functions, base)
    translated, report = translate(factory, vocabulary, mainline, base, functions)
    sys.stdout.write(translated.render())
    if args.report:
        Path(args.report).write_text(report.text())
    counts = ", ".join(
        f"{report.count(k)} {k}" for k in ("unresolved", "dormant", "unsupported", "unknown")
    )
    print(f"  {counts}", file=sys.stderr)


if __name__ == "__main__":
    main()
