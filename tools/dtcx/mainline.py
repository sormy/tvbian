"""Mainline's SoC dtsi as our kernel builds it, indexed for meeting vendor nodes."""

from __future__ import annotations

import hashlib
import re
import subprocess
import sys
import tempfile
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit

from dtcx import REPO, Base, fetch
from dts import Deletion, Node, Source, unit, walk

KERNEL_PATCH = re.compile(r"^\s*\.:(\S+\.patch)$", re.MULTILINE)
SUNXI_PIN = re.compile(r"SUNXI_PINCTRL_PIN\((\w),\s*(\d+)\)")
SUNXI_FUNCTION = re.compile(r'SUNXI_FUNCTION(?:_IRQ_BANK)?\([^,]+,\s*"([^"]+)"')
# a dtsi's own include, at the top or inside a node, where cpp splices it
LOCAL_INCLUDE = re.compile(r'^[ \t]*#include "([^"]+)"[^\n]*$', re.MULTILINE)
# a file's part of a patch, its --- and +++ lines, a timestamp after either
FILE_HEADER = re.compile(r"--- [^\n]+\n\+\+\+ b/(\S+)")
# a meson pinctrl driver's function and the pin groups it can mux
MESON_FUNCTION = re.compile(r"static const char \* const (\w+)_groups\[\] = \{([^}]*)\}")


class Mainline:
    """The dtsi's nodes by path, and by label."""

    def __init__(self, source: Source) -> None:
        self.nodes = dict(walk(source.root)) | {"/": source.root}
        self.by_label = {label: p for p, n in self.nodes.items() for label in n.labels}
        self.absolute = {p: a for p in self.nodes if (a := self.cpu_address(p)) is not None}

    def at(self, address: str) -> str | None:
        """The one node at this address, wherever mainline puts it: a block's address is unique on
        the SoC, as its unit address or as the CPU sees it through its buses' ranges. None where no
        node, or more than one, has it."""
        found = [
            p
            for p, n in self.nodes.items()
            if address and address in (unit(n.name), self.absolute.get(p))
        ]
        return found[0] if len(found) == 1 else None

    def cpu_address(self, path: str) -> str | None:
        """A node's unit address through each bus's ranges up to the root, in hex."""
        address = unit(self.nodes[path].name).split(",")[0]
        if not address or not re.fullmatch(r"[0-9a-f]+", address):
            return None
        value = int(address, 16)
        parent = path.rsplit("/", 1)[0]
        while parent:
            translated = through(
                self.nodes[parent], self.nodes[parent.rsplit("/", 1)[0] or "/"], value
            )
            if translated is None:
                return None
            value, parent = translated, parent.rsplit("/", 1)[0]
        return f"{value:x}"

    def named(self, name: str) -> str | None:
        """The one node of this name anywhere: a node moved, with no address to meet it by."""
        found = [p for p, n in self.nodes.items() if p != "/" and n.name == name]
        return found[0] if len(found) == 1 else None

    def child(self, parent: str, name: str, address: str) -> str | None:
        """parent's child at this unit address, else of this name."""
        prefix = "" if parent == "/" else parent
        under = [
            (p, n) for p, n in self.nodes.items() if p != "/" and p.rsplit("/", 1)[0] == prefix
        ]
        at = [p for p, n in under if address and unit(n.name) == address]
        named = [p for p, n in under if n.name.split("@")[0] == name]
        return at[0] if len(at) == 1 else named[0] if len(named) == 1 else None


def through(bus: Node, above: Node, address: int) -> int | None:
    """An address on bus as above sees it, by bus's ranges; itself where ranges is empty."""
    ranges = bus.prop("ranges")
    if ranges is None:
        return None
    cells = [int(c, 0) for c in re.findall(r"0x[0-9a-fA-F]+|\d+", ranges.value)]
    if not cells:
        return address
    child, parent, size = (
        cell_count(bus, "#address-cells", 2),
        cell_count(above, "#address-cells", 2),
        cell_count(bus, "#size-cells", 1),
    )
    stride = child + parent + size
    for start in range(0, len(cells) - stride + 1, stride):
        entry = cells[start : start + stride]
        base, target, length = (
            number(entry[:child]),
            number(entry[child : child + parent]),
            number(entry[child + parent :]),
        )
        if base <= address < base + length:
            return address - base + target
    return None


def cell_count(node: Node, name: str, default: int) -> int:
    found = node.prop(name)
    return int(found.value.strip("<>"), 0) if found else default


def number(cells: list[int]) -> int:
    value = 0
    for cell in cells:
        value = value << 32 | cell
    return value


def patched_soc(url: str, kernel_conf: str, base: Base) -> Source:
    """The dtsi as one tree, as dtc reads it: each dtsi it includes spliced in where the include
    stands, at the top or inside a node, then its root and &label blocks in file order."""
    source = soc_tree(dtsi_files(url, kernel_conf, base), file_name(url))
    numeric_units(source, base.defines())
    return source


def numeric_units(source: Source, defines: dict[str, int]) -> None:
    """Unit addresses written as binding constants are numbers after preprocessing."""
    for _, node in walk(source.root):
        name, separator, address = node.name.partition("@")
        if separator and address in defines:
            node.name = f"{name}@{defines[address]:x}"


def soc_tree(files: dict[str, str], top: str) -> Source:
    """The dtsi files, by name, as one tree; a file not yet written is empty."""

    def spliced(name: str) -> str:
        return LOCAL_INCLUDE.sub(lambda m: spliced(file_name(m.group(1))), files.get(name, ""))

    text = spliced(top)
    root = Node("/")
    if text.strip():
        source = Source.parse(text)
        merge(root, source.root)
        amend(root, source.overlays, top)
    return Source([], root)


def file_name(url: str) -> str:
    return urlsplit(url).path.rsplit("/", 1)[-1]


def sibling(url: str, name: str) -> str:
    """The file named beside url's, at the same revision."""
    parts = urlsplit(url)
    return urlunsplit(parts._replace(path=parts.path.rsplit("/", 1)[0] + "/" + name))


def dtsi_urls(url: str, kernel_conf: str, base: Base) -> dict[str, str]:
    """The dtsi and each dtsi it includes, patched, by file name, with its URL."""
    out = {file_name(url): url}
    for name in LOCAL_INCLUDE.findall(patched(url, kernel_conf, base)):
        out |= dtsi_urls(sibling(url, name), kernel_conf, base)
    return out


def dtsi_files(url: str, kernel_conf: str, base: Base) -> dict[str, str]:
    """The dtsi and each dtsi it includes, patched, by file name: what a board file including it
    compiles against."""
    return {
        name: patched(u, kernel_conf, base) for name, u in dtsi_urls(url, kernel_conf, base).items()
    }


def dtsi_history(url: str, kernel_conf: str, base: Base) -> list[tuple[str, Node]]:
    """The dtsi as one tree before the conf's patches, then after each patch that touches one of
    its files: (patch, root), "" for the first."""
    revised = {
        name: revisions(u, kernel_conf, base)
        for name, u in dtsi_urls(url, kernel_conf, base).items()
    }
    touching_any = {patch for steps in revised.values() for patch, _ in steps[1:]}
    current = {name: steps[0][1] for name, steps in revised.items()}
    out = [("", soc_tree(current, file_name(url)).root)]
    for patch in (p for p in conf_patches(kernel_conf) if p in touching_any):
        for name, steps in revised.items():
            current[name] = next((text for p, text in steps if p == patch), current[name])
        out.append((patch, soc_tree(current, file_name(url)).root))
    return out


def amend(root: Node, overlays: list[Node | Deletion], where: str) -> None:
    """Each &label block merged into the node it names, each /delete-node/ &label; removing it,
    in file order, as dtc reads them."""
    for overlay in overlays:
        label = overlay.label if isinstance(overlay, Deletion) else overlay.name.removeprefix("&")
        parents = {id(c): n for _, n in [("/", root), *walk(root)] for c in n.children}
        labelled = (n for _, n in walk(root) if label in n.labels)
        target = root if label == "/" else next(labelled, None)
        if target is None:
            sys.exit(f"{where}: &{label} names no node")
        if isinstance(overlay, Deletion):
            parents[id(target)].children.remove(target)
        else:
            merge(target, overlay)


def merge(into: Node, node: Node) -> None:
    """node's labels, properties and children written over into's, as dtc merges a node written
    twice."""
    into.labels += [label for label in node.labels if label not in into.labels]
    for prop in node.props:
        if prop.statement[0].startswith("/delete-property/"):
            into.props = [p for p in into.props if p.name != prop.name]
            continue
        if prop.statement[0].startswith("/delete-node/"):
            into.children = [c for c in into.children if c.name != prop.name]
            continue
        at = next((i for i, p in enumerate(into.props) if p.name == prop.name), None)
        if at is None:
            into.props.append(prop)
        else:
            into.props[at] = prop
    for child in node.children:
        same = next((c for c in into.children if c.name == child.name), None)
        if same is None:
            same = Node(child.name, lead=child.lead)
            into.children.append(same)
        merge(same, child)


def conf_patches(kernel_conf: str) -> list[str]:
    """The patches a kernel conf applies at the kernel tree's root, in order."""
    return KERNEL_PATCH.findall((REPO / kernel_conf).read_text()) if kernel_conf else []


def patched(url: str, kernel_conf: str, base: Base) -> str:
    """The dtsi fetched once from its pinned URL, then each of the kernel conf's patches that
    touches it, applied as kernel/build.sh applies them."""
    return revisions(url, kernel_conf, base)[-1][1]


def revisions(url: str, kernel_conf: str, base: Base) -> list[tuple[str, str]]:
    """A dtsi's text before the kernel conf's patches, empty where one creates it, then after each
    patch that touches it: (patch, text), "" for the first."""
    path = re.sub(r"^.*?/(arch/[^?]+).*$", r"\1", url)
    parts = [
        (p, hunks)
        for p in conf_patches(kernel_conf)
        if (hunks := touching((REPO / p).read_text(), path))
    ]
    created = bool(parts) and parts[0][1].startswith("--- /dev/null")
    out = [("", "" if created else cached(url, base))]
    with tempfile.TemporaryDirectory() as tmp:
        (Path(tmp) / path).parent.mkdir(parents=True)
        if not created:
            (Path(tmp) / path).write_text(out[0][1])
        for patch, hunks in parts:
            cmd = ["patch", "-p1", "--forward", "--batch", "-d", tmp]
            done = subprocess.run(cmd, check=False, input=hunks, capture_output=True, text=True)
            if done.returncode:
                sys.exit(f"{patch} does not apply to {url}:\n{done.stdout}{done.stderr}")
            out.append((patch, (Path(tmp) / path).read_text()))
    return out


def cached(url: str, base: Base) -> str:
    """A pinned URL's text, fetched once."""
    digest = hashlib.sha256(url.encode()).hexdigest()[:12]
    path = base.root.parent / "soc" / digest / file_name(url)
    if not path.exists():
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(fetch(url))
    return path.read_text()


def pin_functions(urls: list[str], base: Base) -> dict[str, set[str]]:
    """Each pin's functions in mainline's sunxi pinctrl drivers, from their pin tables; or each
    pin group's in a meson driver, from its function tables."""
    pins: dict[str, set[str]] = {}
    for url in urls:
        for function, groups in MESON_FUNCTION.findall(cached(url, base)):
            for group in re.findall(r'"([^"]+)"', groups):
                pins.setdefault(group, set()).add(function)
        for entry in cached(url, base).split("SUNXI_PIN(")[1:]:
            pin = SUNXI_PIN.search(entry)
            if pin:
                name = f"P{pin.group(1)}{pin.group(2)}"
                pins.setdefault(name, set()).update(SUNXI_FUNCTION.findall(entry))
    return pins


def touching(patch: str, path: str) -> str:
    """The parts of a patch, git's or plain unified, that change `path`: each file's part opens
    with its --- and +++ lines."""
    parts = re.split(r"(?m)^(?=--- )", patch)
    return "".join(p for p in parts if (m := FILE_HEADER.match(p)) and m.group(1) == path)
