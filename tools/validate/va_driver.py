#!/usr/bin/env python3
"""The VA-API driver on a box: its family's build and va-driver/tests/vaapi_test.py, run there.

On the host, after ./build.sh va-driver check, which makes the builds and the clips:
  va_driver.py --box root@<box> --family <family>
The build, the suite and the clips go to a private directory under the box's /var/tmp, the suite
runs as root against Debian's own clients, and the directory goes on exit. Exit 1 on any FAIL.
"""

from __future__ import annotations

import argparse
import subprocess
import sys
import tarfile
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
BUILD = REPO / "build/out/va-driver"
TESTS = REPO / "va-driver/tests"
SUITE_FILES = ["vaapi_test.py", "headers.py"]
SSH = [
    "ssh",
    "-o", "StrictHostKeyChecking=no",
    "-o", "UserKnownHostsFile=/dev/null",
    "-o", "LogLevel=ERROR",
    "-o", "BatchMode=yes",
    "-o", "ServerAliveInterval=5",
    "-o", "ServerAliveCountMax=3",
]  # fmt: skip
SUITE_TIMEOUT = 3600


def remote(
    box: str, command: str, timeout: float | None = None, capture: bool = False
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(SSH + [box, command], text=True, capture_output=capture, timeout=timeout)


def send(box: str, family: str, box_dir: str) -> None:
    """The build as driver/, the suite, the clips, in one tar stream: the GPU's link stays a link."""
    untar = subprocess.Popen(SSH + [box, f"tar -x -C {box_dir}"], stdin=subprocess.PIPE)
    assert untar.stdin
    with tarfile.open(fileobj=untar.stdin, mode="w|") as tar:
        tar.add(BUILD / family, "driver")
        tar.add(BUILD / "clips", "clips")
        for name in SUITE_FILES:
            tar.add(TESTS / name, name)
    untar.stdin.close()
    if untar.wait() != 0:
        sys.exit(f"could not copy the suite to {box}")


def main() -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--box", required=True, help="the box, as ssh reaches it")
    parser.add_argument("--family", required=True, help="the box's BOARD_FAMILY")
    args = parser.parse_args()
    for needed in (BUILD / args.family / "tvb_drv_video.so", BUILD / "clips"):
        if not needed.exists():
            sys.exit(f"no {needed}: ./build.sh va-driver check first")

    made = remote(args.box, "mktemp -d /var/tmp/tvb-va-driver.XXXXXX", capture=True)
    box_dir = made.stdout.strip()
    if made.returncode != 0 or not box_dir:
        sys.exit(f"could not reach {args.box}")
    try:
        send(args.box, args.family, box_dir)
        suite = (
            f"TMPDIR={box_dir} python3 {box_dir}/vaapi_test.py box --driver-dir {box_dir}/driver"
            f" --clips {box_dir}/clips --family {args.family}"
        )
        return remote(args.box, suite, timeout=SUITE_TIMEOUT).returncode
    finally:
        remote(args.box, f"rm -rf -- {box_dir}", timeout=30)


if __name__ == "__main__":
    sys.exit(main())
