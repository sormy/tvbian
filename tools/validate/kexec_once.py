#!/usr/bin/env python3
"""Enter a kernel by kexec, on the box, as root: the boot menu never changes, so any reset, the
watchdog's or a power cycle's, boots the menu's default again.

    python3 kexec_once.py <release> [word ...]   # loads it from the menu's entry, then jumps
Each word is added to the entry's command line, for this boot alone.

The kernel gets its entry's own tree, with what U-Boot adds to a tree it boots taken from the
running one: the memory, the serial number, each Ethernet address.
"""

import shutil
import subprocess
import sys
from pathlib import Path

MENU = Path("/boot/extlinux/extlinux.conf")
# the recovery entries repeat a kernel's lines with an `r` label
RECOVERY_SUFFIX = "r"
LIVE_TREE = Path("/proc/device-tree")
KEXEC_TREE = Path("/var/tmp/kexec.dtb")
CELL_BYTES = 4


def entries(menu: str) -> dict[str, dict[str, str]]:
    """Each label's lines: linux, initrd, fdt, append."""
    found: dict[str, dict[str, str]] = {}
    label = None
    for line in menu.splitlines():
        words = line.strip().split(None, 1)
        if words and words[0] == "label":
            label = words[1]
            found[label] = {}
        elif label and len(words) == 2:
            found[label][words[0]] = words[1]
    return found


def entry_of(menu: str, release: str) -> dict[str, str] | None:
    """The entry whose kernel is vmlinuz-<release>, its recovery twin aside; None if none."""
    for label, lines in entries(menu).items():
        if lines.get("linux") == f"/boot/vmlinuz-{release}" and not label.endswith(RECOVERY_SUFFIX):
            return lines
    return None


def kexec_load_command(lines: dict[str, str], tree: Path, extra: list[str]) -> list[str]:
    """kexec_load, not kexec_file_load: on arm64 the latter boots the running kernel's own tree."""
    append = " ".join([lines.get("append", ""), *extra]).strip()
    command = ["kexec", "-c", "-l", lines["linux"], f"--append={append}"]
    if "initrd" in lines:
        command.append(f"--initrd={lines['initrd']}")
    return command + [f"--dtb={tree}"]


def cells(raw: bytes) -> list[str]:
    return [
        f"{int.from_bytes(raw[i : i + CELL_BYTES], 'big'):#x}"
        for i in range(0, len(raw), CELL_BYTES)
    ]


def node_paths(tree: Path) -> list[str]:
    paths, todo = [], ["/"]
    while todo:
        path = todo.pop()
        paths.append(path)
        listed = subprocess.run(
            ["fdtget", "-l", str(tree), path], capture_output=True, text=True, check=True
        )
        todo += [f"{path.rstrip('/')}/{node}" for node in listed.stdout.split()]
    return paths


def boot_fixups(live: Path, paths: list[str]) -> list[tuple[str, str, str, list[str]]]:
    """The running tree's boot-time additions, as fdtput's type, node, property and values; an
    Ethernet address goes to the node of the same name."""
    memory = next(n for n in live.iterdir() if n.name.partition("@")[0] == "memory")
    puts = [
        ("s", "/memory", "device_type", ["memory"]),
        ("x", "/memory", "reg", cells((memory / "reg").read_bytes())),
    ]
    serial = live / "serial-number"
    if serial.exists():
        puts.append(("s", "/", "serial-number", [serial.read_text().rstrip("\0")]))
    for mac in sorted(live.rglob("local-mac-address")):
        target = next((p for p in paths if p.rsplit("/", 1)[-1] == mac.parent.name), None)
        if target:
            puts.append(("bx", target, "local-mac-address", [f"{b:02x}" for b in mac.read_bytes()]))
    return puts


def fdtput_command(tree: Path, kind: str, node: str, prop: str, values: list[str]) -> list[str]:
    """fdtput writing one property, its node made where the tree lacks it."""
    return ["fdtput", "-p", "-t", kind, str(tree), node, prop, *values]


def kexec_watchdog_armed() -> bool:
    out = subprocess.run(
        ["systemctl", "show", "-p", "KExecWatchdogUSec", "--value"], capture_output=True, text=True
    ).stdout.strip()
    return out not in ("", "0", "infinity")


def main() -> None:
    release, extra = sys.argv[1], sys.argv[2:]
    lines = entry_of(MENU.read_text(), release)
    if lines is None or "fdt" not in lines:
        sys.exit(f"no entry boots {release} with its own tree")
    if not shutil.which("fdtput"):
        sys.exit("no fdtput: install device-tree-compiler")
    if not kexec_watchdog_armed():
        sys.exit(
            "systemd stops the watchdog before a kexec: a hang would not reset; set KExecWatchdogSec"
        )
    shutil.copyfile(lines["fdt"], KEXEC_TREE)
    for put in boot_fixups(LIVE_TREE, node_paths(KEXEC_TREE)):
        subprocess.run(fdtput_command(KEXEC_TREE, *put), check=True)
    subprocess.run(kexec_load_command(lines, KEXEC_TREE, extra), check=True)
    print(f"{release} loaded with its own tree; kexec now, the menu unchanged")
    subprocess.Popen(["sh", "-c", "sleep 2; systemctl kexec"], start_new_session=True)


if __name__ == "__main__":
    main()
