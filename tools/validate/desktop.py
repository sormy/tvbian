#!/usr/bin/env python3
"""A desktop session on a box: tests/session_check.py run there against the installed package and
the session a user is logged into, with clips mpv plays in it.

On the host:
  desktop.py --box root@<box> [--session desktop]
The clips are made once by the host's FFmpeg into build/validate/desktop/clips; the check and the
clips go to a private directory under the box's /var/tmp, which goes on exit. Exit 1 on any FAIL.
"""

from __future__ import annotations

import argparse
import subprocess
import sys
import tarfile
from pathlib import Path

from va_driver import SSH, remote

REPO = Path(__file__).resolve().parents[2]
CHECK = REPO / "tests/session_check.py"
CLIPS = REPO / "build/validate/desktop/clips"
CHECK_TIMEOUT = 1800
CLIP_SECONDS = 10
ENCODERS = {
    "h264": ["-c:v", "libx264", "-preset", "veryfast"],
    "hevc": ["-c:v", "libx265", "-preset", "ultrafast", "-x265-params", "log-level=error"],
    "vp9": ["-c:v", "libvpx-vp9", "-deadline", "realtime", "-cpu-used", "8", "-row-mt", "1"],
}
SIZES = {
    "1080p60": ("1920x1080", "60"),
    "2160p30": ("3840x2160", "30"),
    "2160p60": ("3840x2160", "60"),
}
# what a session plays without a dropped frame: each codec at 1080p60, 4K30 and 4K60
CLIP_RECIPES = {
    f"{codec}-{tag}": ["-s", size, "-r", rate, *encoder]
    for codec, encoder in ENCODERS.items()
    for tag, (size, rate) in SIZES.items()
}


def make_clips() -> None:
    CLIPS.mkdir(parents=True, exist_ok=True)
    for name, recipe in CLIP_RECIPES.items():
        path = CLIPS / f"{name}.mp4"
        if path.exists():
            continue
        size, rate = recipe[1], recipe[3]
        source = f"testsrc2=size={size}:rate={rate}:duration={CLIP_SECONDS}"
        subprocess.run(
            ["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i", source]
            + ["-pix_fmt", "yuv420p"]
            + recipe[4:]
            + [str(path)],
            check=True,
        )


def send(box: str, box_dir: str) -> None:
    untar = subprocess.Popen(SSH + [box, f"tar -x -C {box_dir}"], stdin=subprocess.PIPE)
    assert untar.stdin
    with tarfile.open(fileobj=untar.stdin, mode="w|") as tar:
        tar.add(CHECK, CHECK.name)
        tar.add(CLIPS, "clips")
    untar.stdin.close()
    if untar.wait() != 0:
        sys.exit(f"could not copy the check to {box}")


def main() -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--box", required=True, help="the box, as ssh reaches it")
    parser.add_argument("--session", default="desktop", help="the session: session/<name>/")
    args = parser.parse_args()
    make_clips()
    made = remote(args.box, "mktemp -d /var/tmp/tvb-desktop.XXXXXX", capture=True)
    box_dir = made.stdout.strip()
    if made.returncode != 0 or not box_dir:
        sys.exit(f"could not reach {args.box}")
    try:
        send(args.box, box_dir)
        check = (
            f"chmod 755 {box_dir} {box_dir}/clips && chmod 644 {box_dir}/clips/* && "
            f"python3 {box_dir}/{CHECK.name} {args.session} --box --clips {box_dir}/clips"
        )
        return remote(args.box, check, timeout=CHECK_TIMEOUT).returncode
    finally:
        remote(args.box, f"rm -rf -- {box_dir}", timeout=30)


if __name__ == "__main__":
    sys.exit(main())
