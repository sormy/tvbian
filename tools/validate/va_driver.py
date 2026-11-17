#!/usr/bin/env python3
"""The VA-API driver on a box: its build and va-driver/tests/vaapi_test.py, run there.

On the host, after ./build.sh va-driver check, which makes the driver and the clips:
  va_driver.py --box root@<box> --family <family>
The build, the suite and the clips go to a private directory under the box's /var/tmp, the suite
runs as root against Debian's own clients, and the directory goes on exit. Exit 1 on any FAIL.

The report is kept in build/validate/va-driver/<box>/, and its decode speed is held against the
box's previous report: exit 1 too where a client got slower, or spent more CPU a frame.
"""

from __future__ import annotations

import argparse
import re
import subprocess
import sys
import tarfile
from datetime import datetime
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
RESULTS = REPO / "build/validate/va-driver"
SPEED = re.compile(r"^va\.speed\.(\S+) pass: ([\d.]+) fps, ([\d.]+) ms CPU a frame$", re.M)
# run to run noise on a quiet box: past these, a speed line is a regression
FPS_DROP_MAX = 0.10
CPU_RISE_MAX = 0.25
# a copy back in costs a 4K picture 10 ms and more; below this, CPU a frame is noise
CPU_RISE_MIN_MS = 2.0


def remote(
    box: str, command: str, timeout: float | None = None, capture: bool = False
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(SSH + [box, command], text=True, capture_output=capture, timeout=timeout)


def send(box: str, box_dir: str) -> None:
    """The build as driver/, the suite, the clips, in one tar stream: the GPU's link stays a link."""
    untar = subprocess.Popen(SSH + [box, f"tar -x -C {box_dir}"], stdin=subprocess.PIPE)
    assert untar.stdin
    with tarfile.open(fileobj=untar.stdin, mode="w|") as tar:
        tar.add(BUILD / "driver", "driver")
        tar.add(BUILD / "clips", "clips")
        for name in SUITE_FILES:
            tar.add(TESTS / name, name)
    untar.stdin.close()
    if untar.wait() != 0:
        sys.exit(f"could not copy the suite to {box}")


def speeds(report: str) -> dict[str, tuple[float, float]]:
    return {key: (float(fps), float(cpu)) for key, fps, cpu in SPEED.findall(report)}


def slower(before: str, after: str) -> list[str]:
    """Each speed line that lost frames a second or gained CPU a frame past the noise."""
    was, now = speeds(before), speeds(after)
    regressions = []
    for key in sorted(was.keys() & now.keys()):
        (fps0, cpu0), (fps1, cpu1) = was[key], now[key]
        if fps1 < fps0 * (1 - FPS_DROP_MAX):
            regressions.append(f"{key}: {fps0} to {fps1} fps")
        if cpu1 > cpu0 * (1 + CPU_RISE_MAX) and cpu1 - cpu0 > CPU_RISE_MIN_MS:
            regressions.append(f"{key}: {cpu0} to {cpu1} ms CPU a frame")
    return regressions


def run_suite(box: str, command: str) -> tuple[int, str]:
    """The suite's lines, shown as they come and kept."""
    suite = subprocess.Popen(SSH + [box, command], stdout=subprocess.PIPE, text=True)
    assert suite.stdout
    lines = []
    for line in suite.stdout:
        print(line, end="", flush=True)
        lines.append(line)
    return suite.wait(timeout=SUITE_TIMEOUT), "".join(lines)


def compare(box: str, report: str) -> int:
    """Keep the report; exit 1 where speed fell against the box's previous one."""
    kept = RESULTS / box.split("@")[-1]
    kept.mkdir(parents=True, exist_ok=True)
    previous = sorted(kept.glob("*.log"))
    (kept / f"{datetime.now():%Y-%m-%d-%H%M%S}.log").write_text(report)
    if not previous:
        print("speed: the first report of this box, nothing to compare")
        return 0
    regressions = slower(previous[-1].read_text(), report)
    for regression in regressions:
        print(f"FAIL va.speed {regression}, against {previous[-1].name}")
    return 1 if regressions else 0


def main() -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--box", required=True, help="the box, as ssh reaches it")
    parser.add_argument(
        "--family", required=True, help="the box's BOARD_FAMILY: the clips its engine refuses"
    )
    args = parser.parse_args()
    for needed in (BUILD / "driver/tvb_drv_video.so", BUILD / "clips"):
        if not needed.exists():
            sys.exit(f"no {needed}: ./build.sh va-driver check first")

    made = remote(args.box, "mktemp -d /var/tmp/tvb-va-driver.XXXXXX", capture=True)
    box_dir = made.stdout.strip()
    if made.returncode != 0 or not box_dir:
        sys.exit(f"could not reach {args.box}")
    try:
        send(args.box, box_dir)
        suite = (
            f"TMPDIR={box_dir} python3 {box_dir}/vaapi_test.py box --driver-dir {box_dir}/driver"
            f" --clips {box_dir}/clips --family {args.family}"
        )
        rc, report = run_suite(args.box, suite)
        regressed = compare(args.box, report)
        return rc or regressed
    finally:
        remote(args.box, f"rm -rf -- {box_dir}", timeout=30)


if __name__ == "__main__":
    sys.exit(main())
