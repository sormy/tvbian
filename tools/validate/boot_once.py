#!/usr/bin/env python3
"""Boot a kernel once, on the box, as root: its initramfs puts the known-good menu back before root
mounts, so a kernel that hangs from there on comes back on the old one at the watchdog's reset.

    python3 boot_once.py <release>      # then reboot
"""

import os
import re
import subprocess
import sys
from pathlib import Path

MENU = Path("/boot/extlinux/extlinux.conf")
STATE = Path("/var/lib/tvb-boot-once")
HOOKS = Path("/etc/initramfs-tools/scripts")
HOOK = HOOKS / "local-premount/tvb-boot-once"
OLD_HOOK = HOOKS / "local-bottom/tvb-boot-once"
# runs in the initramfs once the root device exists, before it is checked and mounted; a hook sees
# $ROOT as root= gave it, not the init's resolved device and type; its tools are klibc's, no cp
HOOK_SCRIPT = """#!/bin/sh
PREREQ=""
case "$1" in prereqs) echo "$PREREQ"; exit 0 ;; esac
. /scripts/functions
say() { echo "tvb-boot-once: $1" > /dev/kmsg; }
root=/tvb-boot-once
mkdir -p "$root"
dev=$(resolve_device "$ROOT") && fs=$(get_fstype "$dev") && mount -r -t "$fs" "$dev" "$root" ||
	{ say "root not mounted, the menu not restored"; exit 0; }
state="$root/var/lib/tvb-boot-once"
menu="$root/boot/extlinux/extlinux.conf"
if [ -f "$state/pending" ]; then
	if mount -o remount,rw "$dev" "$root" && cat "$state/extlinux.before" > "$menu.new" && sync &&
		mv "$menu.new" "$menu"; then
		rm -f "$state/pending"
		sync
		say "the menu before restored"
	else
		say "the menu not restored"
	fi
fi
umount "$root"
"""


def label_of(menu, release):
    """The label whose kernel is vmlinuz-<release>, or None."""
    label = None
    for line in menu.split("\n"):
        m = re.match(r"^label (\S+)$", line)
        if m:
            label = m.group(1)
        elif label and re.match(rf"^\s*linux /boot/vmlinuz-{re.escape(release)}$", line):
            return label
    return None


def with_default(menu, label):
    """The menu booting label by default; every label kept."""
    out = re.sub(r"^default \S+$", f"default {label}", menu, flags=re.M)
    if re.findall(r"^label (\S+)$", out, re.M) != re.findall(r"^label (\S+)$", menu, re.M):
        raise ValueError("a label was lost")
    if f"default {label}" not in out:
        raise ValueError("the menu has no default line")
    return out


def write_atomically(path, text):
    new = path.with_suffix(path.suffix + ".new")
    with open(new, "w") as f:
        f.write(text)
        f.flush()
        os.fsync(f.fileno())
    os.replace(new, path)


def main():
    release = sys.argv[1]
    menu = MENU.read_text()
    label = label_of(menu, release)
    if label is None:
        sys.exit(f"no label boots {release}")
    STATE.mkdir(parents=True, exist_ok=True)
    write_atomically(STATE / "extlinux.before", menu)
    OLD_HOOK.unlink(missing_ok=True)
    HOOK.parent.mkdir(parents=True, exist_ok=True)
    HOOK.write_text(HOOK_SCRIPT)
    HOOK.chmod(0o755)
    subprocess.run(["update-initramfs", "-u", "-k", release], check=True)
    (STATE / "pending").touch()
    write_atomically(MENU, with_default(menu, label))
    os.sync()
    print(f"{release} boots once as {label}; the menu before comes back before root mounts")


if __name__ == "__main__":
    main()
