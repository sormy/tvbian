"""A device tree source, kept as written: each property's lines and comments, each node's labels.

Read by translate.py and learn.py; parses what dtcx writes and what a person writes by hand, one
statement or node a line, comments before what they describe.
"""

from __future__ import annotations

import re
import sys
from dataclasses import dataclass, field

from dtcx import STATEMENT_END

NODE_OPEN = re.compile(r"^((?:[\w-]+:\s*)*)([^\s{]+)\s*\{\s*(?:/\*.*\*/)?$")
EMPTY_NODE = re.compile(r"^((?:[\w-]+:\s*)*)([^\s{]+)\s*\{\s*\};$")  # a node on one line: name {};
NODE_CLOSE = "};"
DELETE_NODE = re.compile(r"^/delete-node/\s*&([\w-]+)\s*;$")
# inside a node: one of its properties or children removed, as a property statement
DELETE_INSIDE = re.compile(r"^/delete-(?:property|node)/\s*([^\s;]+)\s*;$")
NAME = re.compile(r"^\s*([#\w,.+?-]+)\s*(?:=|;)")
INDENT = "\t"
COMMENT = re.compile(r"/\*.*?\*/", re.DOTALL)


@dataclass
class Prop:
    name: str
    statement: list[str]  # as written, indent relative to the node
    comments: list[str] = field(default_factory=list)  # the comment lines before it

    @property
    def lines(self) -> list[str]:
        return self.comments + self.statement

    @staticmethod
    def of(name: str, value: str = "") -> Prop:
        """A property written on one line: name = value, or a flag."""
        return Prop(name, [f"{name} = {value};" if value else f"{name};"])

    @property
    def value(self) -> str:
        """What follows the =, on one line, comments out; empty for a flag."""
        text = COMMENT.sub("", " ".join(l.strip() for l in self.statement))
        _, eq, value = text.partition("=")
        return value.strip().rstrip(";").strip() if eq else ""


@dataclass
class Node:
    name: str
    labels: list[str] = field(default_factory=list)
    lead: list[str] = field(default_factory=list)  # comments and flags such as /omit-if-no-ref/
    props: list[Prop] = field(default_factory=list)
    children: list[Node] = field(default_factory=list)

    def prop(self, name: str) -> Prop | None:
        return next((p for p in self.props if p.name == name), None)


@dataclass
class Deletion:
    """A top-level /delete-node/ &label;: the labelled node removed where it stands in the file."""

    label: str


@dataclass
class Source:
    """A device tree source file: what precedes its root, the root, and the blocks after it that
    amend nodes already written, &label { } or /delete-node/ &label; in a dtsi, in file order."""

    preamble: list[str]
    root: Node
    overlays: list[Node | Deletion] = field(default_factory=list)

    @staticmethod
    def parse(text: str) -> Source:
        preamble: list[str] = []
        stack: list[Node] = []
        root: Node | None = None
        overlays: list[Node | Deletion] = []
        pending: list[str] = []
        statement: list[str] = []
        in_comment = False
        for line in text.split("\n"):
            stripped = line.strip()
            depth = len(stack)
            if in_comment or (stripped.startswith("/*") and stack and not statement):
                pending.append(dedent(line, depth))
                in_comment = "*/" not in stripped
                continue
            if statement:
                statement.append(dedent(line, depth))
                if STATEMENT_END.search(line):
                    stack[-1].props.append(Prop(prop_name(statement), statement, pending))
                    pending, statement = [], []
                continue
            deleted = DELETE_NODE.match(stripped)
            if deleted and not stack:
                overlays.append(Deletion(deleted.group(1)))
                continue
            inside = DELETE_INSIDE.match(stripped)
            if inside and stack:
                stack[-1].props.append(Prop(inside.group(1), [stripped], pending))
                pending = []
                continue
            if stripped.startswith("/delete-"):
                sys.exit(f"unsupported: {stripped}")
            if root is None and not stack and stripped != "/ {" and not stripped.startswith("&"):
                preamble.append(line)
                continue
            empty = EMPTY_NODE.match(stripped)
            if empty and stack:
                labels = re.findall(r"([\w-]+):", empty.group(1))
                stack[-1].children.append(Node(empty.group(2), labels, pending))
                pending = []
                continue
            opened = NODE_OPEN.match(stripped)
            if opened:
                node = Node(opened.group(2), re.findall(r"([\w-]+):", opened.group(1)), pending)
                pending = []
                if stack:
                    stack[-1].children.append(node)
                elif root is None and node.name == "/" and not overlays:
                    root = node
                else:
                    overlays.append(node)
                stack.append(node)
            elif stripped == NODE_CLOSE:
                stack.pop()
            elif not stack:
                continue  # between top-level blocks
            elif stripped.startswith(("//", "/omit-if-no-ref/")):
                pending.append(dedent(line, depth))
            elif stripped:
                statement = [dedent(line, depth)]
                if STATEMENT_END.search(line):
                    stack[-1].props.append(Prop(prop_name(statement), statement, pending))
                    pending, statement = [], []
        if root is None and not overlays:
            sys.exit("no root node")
        while preamble and not preamble[-1].strip():
            preamble.pop()
        return Source(preamble, root or Node("/"), overlays)

    def render(self) -> str:
        blocks = [
            ([f"/delete-node/ &{node.label};"] if isinstance(node, Deletion) else render(node, 0))
            for node in [self.root, *self.overlays]
        ]
        return "\n".join(self.preamble + [""] + ["\n".join(b) for b in blocks]) + "\n"


def dedent(line: str, depth: int) -> str:
    return line[depth:] if line.startswith(INDENT * depth) else line.lstrip("\t")


def prop_name(statement: list[str]) -> str:
    found = NAME.match(statement[0])
    return found.group(1) if found else statement[0].strip()


def render(node: Node, depth: int) -> list[str]:
    pad = INDENT * depth
    labels = "".join(f"{label}: " for label in node.labels)
    out = [pad + line for line in node.lead] + [f"{pad}{labels}{node.name} {{"]
    out += [pad + INDENT + line for prop in node.props for line in prop.lines]
    for child in node.children:
        if node.props or child is not node.children[0]:
            out.append("")
        out += render(child, depth + 1)
    return out + [pad + NODE_CLOSE]


def walk(node: Node, path: str = "") -> list[tuple[str, Node]]:
    """Every node below `node` with its path, parents before children, in source order."""
    out: list[tuple[str, Node]] = []
    for child in node.children:
        child_path = f"{path}/{child.name}"
        out.append((child_path, child))
        out += walk(child, child_path)
    return out


def compatibles(node: Node) -> list[str]:
    found = node.prop("compatible")
    # the Amlogic BSP writes "amlogic, name"; the space is no part of the name
    return [re.sub(r",\s+", ",", c) for c in re.findall(r'"([^"]+)"', found.value)] if found else []


def base_name(node: Node) -> str:
    return node.name.split("@")[0]


def unit(name: str) -> str:
    """A unit address as mainline writes it: hex, no prefix, no leading zeros."""
    _, at, address = name.partition("@")
    if not at:
        return ""
    return ",".join(re.sub(r"^(0x)?0*(?=[0-9a-fA-F])", "", p).lower() for p in address.split(","))
