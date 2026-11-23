#!/usr/bin/env python3
"""The regression suite: every unattended bring-up check, on both kernels, run by each box alone.

From the host, in the repo checkout:

    python3 tools/validate/regression.py run [--profile short|default|extended] \\
        [--kernels own|next|next2|both|all] [--iperf HOST] [--released] BOARD=USER@HOST
    python3 tools/validate/regression.py deploy [--profile short|default|extended] \\
        [--kernels own|next|next2|both|all] [--iperf HOST] [--released] BOARD=USER@HOST
    python3 tools/validate/regression.py collect BOARD=USER@HOST ...
    python3 tools/validate/regression.py report build/validate/regression/<date>

deploy installs the board's kernels, tools and its package built fresh from this tree, checks on
the host what needs the repo (the box runs the repo's tree, its upstream view proves), then copies
the suite to the box with its plan and starts it: onbox.py, run by a systemd unit at every boot,
switches to each kernel of the board's family and its -next, with a guard that brings the default
back if a kernel brings no network up, and runs the profile's steps:

    every profile runs every step: box.py's phases, a soak, display.py, screen.py, video decode,
    dEQP, a panic, an unpinged watchdog and warm reboots. short samples; default runs it all;
    extended soaks longer:

                    short          default            extended
    soak            30 s           2 min              30 min
    s2idle          10 s           20 s               120 s, past the watchdog
    reboots         1              2                  5
    screens         SDR, HDR10     every sink, the ladder
    video sizes     4K             the whole ladder
    dEQP            1/2000         1/500

    --kernels picks the kernels apart from the profile: the family's own, its -next, its -next2
    (mainline beside the vendor kernels), own and next (both, the default), or all three.

--released tests a box as its owner has it: what it lacks of the release's kernels, board package
and tools comes from its own apt, nothing is built, and the checks against this tree are left out.
The host needs only Python, an FFmpeg for the clips, and iperf3 unless --iperf names a server.

run deploys one box, prints its run log as it grows, collects and reports, in one go; several
boxes are several runs at once. collect fetches each box's results, done or not, into
build/validate/regression/<date>/<board>/; report writes report.md there, for a pull request:
every FAIL and UNTESTED line and what moved since each board's last run.
--iperf names the iperf3 server; by default this machine serves, started if it does not yet.
SSH_OPTIONS adds ssh options. Docs: docs/bring-up/regression.md.
"""

from __future__ import annotations

import argparse
import datetime
import fcntl
import hashlib
import json
import os
import re
import shlex
import shutil
import socket
import subprocess
import sys
import tempfile
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path

from box import PROFILES as SCOPES, TEST_TOOLS
from onbox import Step
from gpu import GLES2, SUITE, expectations, suite_toml
from results import Verdicts
from va_driver import slower
from video import worse

ROOT = Path(__file__).resolve().parents[2]
HERE = ROOT / "tools" / "validate"
DEBS = ROOT / "build" / "out" / "debs"
CLIPS = ROOT / "build" / "validate" / "video" / "clips"
RESULTS = ROOT / "build" / "validate" / "regression"
INVENTORY = "inventory."  # box.py's device-class lines, which parity compares
# the VA suite, run against the installed driver, and the session's check, with their clips
VA_SUITE = ROOT / "va-driver" / "tests"
VA_FILES = ("vaapi_test.py", "headers.py")
VA_CLIPS = ROOT / "build" / "out" / "va-driver" / "clips"
DRI_DIR = "/usr/lib/aarch64-linux-gnu/dri"
# the box's clip folders a new run keeps: only changed clips are sent again
CLIP_DIRS = {"video": CLIPS, "va-clips": VA_CLIPS}
BOX_DIR = "/var/lib/tvb-regress"
IPERF_PORT = 5201
COMMAND_S = 600
# how long run waits for a box's run before collecting what there is; how often it asks
RUN_LIMIT_S = {"short": 40 * 60, "default": 120 * 60, "extended": 10 * 3600}
POLL_S = 15  # how often run looks at the boxes: a crash is said within this
ON_BOX = ("onbox.py", "box.py", "display.py", "screen.py", "video.py", "results.py", "known.conf")
# per kernel family: video.py's engine and the Mesa CI GPU nearest the box's
ENGINE = {"sunxi64": "sunxi", "rk35xx": "rkmpp", "meson64": "meson"}
# a series whose kernel reaches the video engines another way than its family's: mainline's V4L2
SERIES_ENGINE = {"-next2": "rkvdec"}
GPU = {"sunxi64": "g52", "rk35xx": "lima", "meson64": "lima"}
PHASES = ("system", "cpu", "storage", "network", "throughput", "display", "audio", "gpu", "input")
PHASES += ("power",)
# each phase's time on the box: its normal duration in the profile, about doubled
PHASE_SECONDS = {"short": 120, "default": 300, "extended": 1200}
PROFILES = ("short", "default", "extended")
# each profile's scope within a test: how long, how many, how much of a sample
REBOOTS = {"short": 1, "default": 2, "extended": 5}
# a family's kernel series: its metapackage's suffix, and its kernel release's
SERIES = {"own": ("", ""), "next": ("-next", ""), "next2": ("-next2", "-next2")}
# which series a run boots, a choice apart from the profile
KERNELS = {
    "own": ("own",),
    "next": ("next",),
    "next2": ("next2",),
    "both": ("own", "next"),
    "all": ("own", "next", "next2"),
}
# display.py's synthetic screens: short, an SDR and an HDR10 one at their first mode; the rest,
# every sink and the rating's ladder of modes
DISPLAY_ARGS = {"short": ["--sinks", "SDR,HDR10", "--no-ladder"], "default": [], "extended": []}
# a box's whole run as it usually takes, boots in it; past it, the report flags the run
BUDGET_MIN = {"short": 12, "default": 40, "extended": 75}  # a kernel's minutes
STEP_SECONDS = {"short": 600, "default": 7200, "extended": 7200}  # display, screen, video, dEQP
DEQP_FRACTION = {"short": 2000, "default": 500, "extended": 500}  # every N'th case
# the video sizes short decodes; the others walk the whole ladder
VIDEO_SIZES = {"short": ("3840x2160",)}

UNIT = f"""[Unit]
Description=TVBian regression run
After=network-online.target
Wants=network-online.target
[Service]
Type=simple
ExecStart=/usr/bin/python3 {BOX_DIR}/onbox.py step
# a step out of memory fails alone; the run goes on
OOMPolicy=continue
[Install]
WantedBy=multi-user.target
"""
# a kernel that brings no network up gets the default back
GUARD = f"""[Unit]
Description=TVBian regression run: the way back from a kernel with no network
[Service]
Type=oneshot
ExecStart=/bin/sh -c 'sleep 180; ip -4 -o addr show scope global | grep -q inet || \
python3 {BOX_DIR}/onbox.py rollback'
[Install]
WantedBy=multi-user.target
"""
START = f"""set -e
install -m 644 {BOX_DIR}/tvb-regress.service {BOX_DIR}/tvb-regress-guard.service \
/etc/systemd/system/
systemctl daemon-reload
systemctl enable tvb-regress.service tvb-regress-guard.service
systemctl start tvb-regress.service
"""
# the release the box's default entry boots: the entry itself is a position, which installs shift
DEFAULT_RELEASE = (
    "awk '/^default/{d=$2} /^label/{l=$2} /^[[:space:]]*linux/ && l==d"
    ' {sub(/.*vmlinuz-/, "", $2); print $2; exit}\' /boot/extlinux/extlinux.conf'
)
INSTALL = """set -e
export DEBIAN_FRONTEND=noninteractive
# $1: the suite's tools, a list; the rest: package files. apt's index only for a tool missing
tools=$1
shift
missing=$(for t in $tools; do
  dpkg-query -W -f '${Status}\\n' "$t" 2>/dev/null | grep -q 'ok installed' || echo "$t"
done)
[ -z "$missing" ] || apt-get update -qq
[ -n "$missing$*" ] || exit 0
# --reinstall: a local build keeps its version, 0~local, and apt would skip it
apt-get install -y -qq --reinstall $missing "$@"
"""
PACKAGES = "/var/tmp/regress"  # the box's copy of what it was given, kept to skip what is unchanged
# --released: what the box's apt gives the suite beside its tools and the family's kernels
RELEASED = ("deqp",)
RELEASED_HELP = "the release's packages from the box's apt; nothing built"
DEQP_RUN = """cd deqp
EGL_PLATFORM=surfaceless LD_LIBRARY_PATH=/usr/lib/deqp/lib /usr/lib/deqp/deqp-runner suite \
  --suite suite.toml --output results --baseline fails.txt --flakes flakes.txt \
  --skips skips.txt --jobs 4 > runner.log 2>&1
status=$?
tail -20 runner.log
if [ ! -f results/failures.csv ]; then
  echo "FAIL deqp: the runner wrote no results, exit $status"
  exit 1
fi
grep -vE ',(Pass|Skip|ExpectedFail|Flake|KnownFlake)' results/failures.csv | sed 's/^/FAIL deqp /'
"""


def board_family_name(board: str) -> str:
    """The family a board's board.conf names, as the VA suite keys its engines' refusals."""
    conf = (ROOT / "boards" / board / "board.conf").read_text()
    found = re.search(r"^BOARD_FAMILY=(\S+)$", conf, re.MULTILINE)
    return found.group(1) if found else ""


def board_family(board: str) -> str:
    """The kernel family a board's board.conf names."""
    conf = (ROOT / "boards" / board / "board.conf").read_text()
    found = re.search(r"^BOARD_KERNEL=(\S+)$", conf, re.MULTILINE)
    if found is None:
        sys.exit(f"boards/{board}/board.conf names no BOARD_KERNEL")
    return found.group(1)


def kernels(family: str, debs: list[str], which: str = "all") -> list[str]:
    """The family's kernels of the series which names, the newest each metapackage built, as uname
    names them."""
    out = []
    for series in KERNELS[which]:
        meta, release = SERIES[series]
        name = f"linux-image-tvb-{family}{meta}"
        versions = [
            m.group(1) for d in debs if (m := re.fullmatch(rf"{name}_([\d.]+)-[^_]+_arm64\.deb", d))
        ]
        if versions:
            newest = max(versions, key=lambda v: [int(p) for p in v.split(".")])
            out.append(f"{newest}-tvb-{family}{release}")
    return out


def upstream_args(board: str) -> list[str]:
    """upstream.py's arguments for the board's kernel tree, as build-dtb.sh gives them."""
    text = (ROOT / "boards" / board / "board.conf").read_text()
    conf = dict(re.findall(r"^BOARD_KERNEL_DTB_(\w+)=(\S+)$", text, re.MULTILINE))
    base = ["--soc", conf["UPSTREAM"]] if "UPSTREAM" in conf else []
    return [*base, conf["SOURCE"], conf["TARGET"]]


def changed(old: str, new: str) -> list[str]:
    """box.py lines that differ between two runs, by key: key, old value, new value."""
    before = dict(line.split(" ", 1) for line in old.splitlines() if " " in line)
    after = dict(line.split(" ", 1) for line in new.splitlines() if " " in line)
    return [
        f"{key}: {before.get(key, '-')} -> {after.get(key, '-')}"
        for key in sorted(before.keys() | after.keys())
        if before.get(key) != after.get(key)
    ]


def release_order(kernel_dir: Path) -> tuple[int, ...]:
    """A kernel's results folder by its version, as uname names it: 6.1.172 before 6.12.69."""
    return tuple(int(n) for n in re.findall(r"\d+", kernel_dir.name.split("-")[0]))


def short_of(own: str, other: str) -> list[str]:
    """The device classes another kernel offers fewer of than the board's own, from box.py's
    inventory lines: class, both counts, and what only the own kernel names."""

    def counted(text: str) -> dict[str, list[str]]:
        return {
            key.removeprefix(INVENTORY): value.split()
            for key, _, value in (line.partition(" ") for line in text.splitlines())
            if key.startswith(INVENTORY)
        }

    theirs = counted(other)
    out = []
    for device_class, (count, *names) in counted(own).items():
        found, *found_names = theirs.get(device_class, ["0"])
        if int(found) < int(count):
            gone = " ".join(n for n in names if n not in found_names) or "renamed"
            out.append(f"{device_class}: {found} of {count}, {gone}")
    return out


def engine(family: str, release: str) -> str:
    """video.py's engine for a kernel: its series', else its family's."""
    return next((e for s, e in SERIES_ENGINE.items() if release.endswith(s)), ENGINE[family])


def steps(profile: str, family: str, iperf: str, board_family_name: str) -> list[Step]:
    """The plan's steps for each kernel, in order: a name, a command run in BOX_DIR, its time.
    Every profile runs every step but short, which skips conformance; it sets how much of each."""
    soak = SCOPES[profile].soak_s
    phase = ["python3", "box.py", "--profile", profile, "--iperf", iperf, "--suite"]
    out = [Step(name, [*phase, name], PHASE_SECONDS[profile]) for name in PHASES]
    video_box = [
        "python3",
        "video.py",
        "box",
        "--engine",
        "{engine}",
        "--dir",
        f"{BOX_DIR}/video",
    ]
    video = list(video_box)
    if profile in VIDEO_SIZES:  # joined with =: a regex starting with - would read as an option
        video += ["--suite", "decode", f"--only=-({'|'.join(VIDEO_SIZES[profile])})$"]
    long = STEP_SECONDS[profile]
    out.append(Step("soak", [*phase, "soak"], soak + 600))
    display = ["python3", "display.py", *DISPLAY_ARGS[profile]]
    # Composite can leave HDMI writeback unavailable on the vendor kernel.
    out.append(Step("screen", ["python3", "screen.py"], long))
    out.append(Step("display-full", display, long))
    out.append(Step("video", video, long))
    if profile != "short":
        out.append(Step("conformance", [*video_box, "--suite", "conformance"], long))
    va = ["python3", "vaapi_test.py", "box", "--driver-dir", DRI_DIR]
    va += ["--clips", f"{BOX_DIR}/va-clips", "--family", board_family_name]
    out.append(Step("va", va, long))
    out.append(Step("deqp", ["sh", "deqp/run.sh"], long))
    out.append(Step("recovery", [], 0))
    out.append(Step("reboots", [], 0))
    return out


SSH_FAILED = 255  # ssh's own exit status, as opposed to the command's


class Box:
    """A box over ssh: commands, root scripts on stdin, files."""

    def __init__(self, target: str) -> None:
        self.target = target
        self.options = ["-o", "BatchMode=yes", "-o", "ConnectTimeout=10"]
        # the boxes trade addresses and are reflashed: a changed key is expected, not an attack
        self.options += ["-o", "StrictHostKeyChecking=no", "-o", "UserKnownHostsFile=/dev/null"]
        self.options += ["-o", "LogLevel=ERROR"]
        self.options += ["-o", "ServerAliveInterval=10", "-o", "ServerAliveCountMax=3"]
        self.options += shlex.split(os.environ.get("SSH_OPTIONS", ""))

    def raw(
        self, command: str, stdin: bytes = b"", seconds: float = COMMAND_S, check: bool = False
    ) -> bytes:
        """command's output as bytes. ssh failing itself, the box unreachable or refusing, is a
        ConnectionError; with check, so is command failing or not answering in time. Without it,
        a probe: no answer in time is empty."""
        try:
            done = subprocess.run(
                ["ssh", *self.options, self.target, command],
                input=stdin,
                capture_output=True,
                timeout=seconds,
            )
        except subprocess.TimeoutExpired:
            if check:
                raise ConnectionError(f"{self.target}: {command}: no answer in {seconds:.0f} s")
            return b""
        if done.returncode == SSH_FAILED or (check and done.returncode):
            said = (done.stderr or done.stdout).decode(errors="replace").strip().splitlines()
            raise ConnectionError(f"{self.target}: {command}: exit {done.returncode}: {said[-1:]}")
        return done.stdout

    def run(
        self,
        command: str,
        stdin: str | bytes = b"",
        seconds: float = COMMAND_S,
        check: bool = False,
    ) -> str:
        data = stdin.encode() if isinstance(stdin, str) else stdin
        return self.raw(command, data, seconds, check).decode(errors="replace").strip()

    def root(self, script: str, *args: str) -> str:
        """script, run as root: no quoting crosses ssh. Its failure is an error."""
        return self.run(f"sudo -n bash -s {shlex.join(args)} 2>&1", script, check=True)

    def put(self, path: str, data: bytes) -> None:
        folder = shlex.quote(str(Path(path).parent))
        command = f"sudo -n mkdir -p {folder} && sudo -n tee {shlex.quote(path)} > /dev/null"
        self.run(command, data, check=True)


class NotStarted(Exception):
    """What the host lacks to start a box's run."""


@dataclass
class Deployment:
    """One box's run: what it is checked against on the host, and what it is given."""

    board: str
    box: Box
    profile: str
    iperf: str  # the iperf3 server, as the box reaches it
    inputs: list[str] = field(default_factory=list)  # "<what> <sha256>" of each thing installed

    def host_checks(self) -> list[str]:
        """boot.md O7 and conversion.md V4, which need the repo, as box.py writes lines."""
        repo = hashlib.md5((ROOT / "boards" / self.board / "board.dtb").read_bytes()).hexdigest()
        on_box = self.box.run("md5sum /usr/lib/tvb/board.dtb").split(" ")[0]
        same = on_box == repo
        lines = [f"tree.repo {'same' if same else f'differs, box {on_box[:8]}'}"]
        lines += [] if same else ["FAIL tree.repo"]
        board = ROOT / "boards" / self.board
        prove = [sys.executable, str(ROOT / "tools/dtcx/upstream.py"), "--prove"]
        prove += [str(board / "board.dtb"), *upstream_args(self.board), str(board / "board.dts")]
        proof = subprocess.run(prove, capture_output=True, text=True, cwd=ROOT).stderr.strip()
        verdict = proof.splitlines()[-1].strip() if proof else "no output"
        lines.append(f"tree.upstream {verdict}")
        lines += [] if verdict.startswith("0 differences") else ["FAIL tree.upstream"]
        return lines

    def install(self, releases: list[str]) -> str:
        """The kernels' packages, the board's own package built fresh from this tree, and the
        suite's tools: each sent and installed only when the box lacks that very file."""
        board = max(DEBS.glob(f"tvb-{self.board}_*.deb"), key=lambda d: d.stat().st_mtime)
        names = [d.name for d in DEBS.glob("*.deb")]
        families = self.box.run("dpkg-query -W -f '${Package}\\n' 'tvb-*-modules-*'").split()
        wanted = [
            n
            for n in names
            for r in releases
            if n.startswith(f"linux-image-{r}_")
            or any(n.startswith(f"{f.split('-modules-')[0]}-modules-{r}_") for f in families)
        ]
        if missing := [
            r for r in releases if not any(n.startswith(f"linux-image-{r}_") for n in wanted)
        ]:
            raise NotStarted(f"no linux-image package for {', '.join(missing)} in {DEBS}")
        wanted += [board.name, *[d.name for d in sorted(DEBS.glob("ffmpeg9_*_arm64.deb"))[-1:]]]
        # what every box gets, from this tree as the board's package is
        wanted += [d.name for d in sorted(DEBS.glob("tvb-base_*.deb"))[-1:]]
        wanted += [d.name for d in sorted(DEBS.glob("deqp_*_arm64.deb"))[-1:]]
        # the VA driver, ours where built
        wanted += [d.name for d in sorted(DEBS.glob("tvb-va-driver_*_arm64.deb"))[-1:]]
        tree = ROOT / "boards" / self.board / "board.dtb"
        self.inputs = [f"{n.split('_')[0]} {sha(DEBS / n)}" for n in wanted]
        self.inputs.append(f"board.dtb {sha(tree)}")
        listing = f"mkdir -p {PACKAGES} && cd {PACKAGES} && sha256sum * 2>/dev/null || true"
        held = dict(line.split()[::-1] for line in self.box.run(listing, check=True).splitlines())
        stale = [n for n in held if n.removesuffix(".installed") not in wanted]
        if stale:
            self.box.run(f"cd {PACKAGES} && rm -f {shlex.join(stale)}", check=True)
        changed = [n for n in wanted if held.get(n) != full_sha(DEBS / n)]
        for name in changed:
            self.box.run(f"cat > {PACKAGES}/{name}", (DEBS / name).read_bytes(), 1800, True)
        todo = [n for n in wanted if n in changed or f"{n}.installed" not in held]
        tools = sorted(TEST_TOOLS - {"ffmpeg9"})
        said = self.box.root(INSTALL, " ".join(tools), *[f"{PACKAGES}/{n}" for n in todo])
        if todo:
            marks = " ".join(f"{shlex.quote(n)}.installed" for n in todo)
            self.box.run(f"cd {PACKAGES} && touch {marks}", check=True)
        last = (said.splitlines() or [""])[-1]
        return f"{len(todo)} of {len(wanted)} packages, {len(changed)} sent; {last}"

    def install_released(self, which: str) -> list[str]:
        """The family's kernels, the board's package and the suite's tools from the box's own apt,
        where it lacks them; the kernels as uname names them, from their metapackages."""
        family = board_family(self.board)
        metas = [f"linux-image-tvb-{family}{SERIES[s][0]}" for s in KERNELS[which]]
        self.box.root(INSTALL, " ".join([*metas, f"tvb-{self.board}", *TEST_TOOLS, *RELEASED]))
        depends = self.box.run(f"dpkg-query -W -f '${{Depends}}\\n' {shlex.join(metas)}")
        return re.findall(r"^linux-image-(\S+)", depends, re.MULTILINE)

    def bundle(self, releases: list[str], host_lines: list[str], default: str) -> None:
        """The suite, its plan, its units and the host's checks, into BOX_DIR, replacing any
        earlier run's; its clips kept, and only those that changed sent. default: the release to
        boot by default after the run."""
        family = board_family(self.board)
        kept = " ".join(f"! -name {d}" for d in CLIP_DIRS)
        keep = f"sudo -n find {BOX_DIR} -mindepth 1 -maxdepth 1 {kept} -exec rm -rf {{}} +"
        self.box.run(f"sudo -n mkdir -p {BOX_DIR}/video && {keep}", check=True)
        for name in ON_BOX:
            self.box.put(f"{BOX_DIR}/{name}", (HERE / name).read_bytes())
        for name in VA_FILES:
            self.box.put(f"{BOX_DIR}/{name}", (VA_SUITE / name).read_bytes())
        self.sync_clips("va-clips")
        plan = {
            "board": self.board,
            "kernels": releases,
            "steps": [
                asdict(s)
                for s in steps(self.profile, family, self.iperf, board_family_name(self.board))
            ],
            "reboots": REBOOTS[self.profile],
            "engines": {release: engine(family, release) for release in releases},
            "default": default,
        }
        self.box.put(f"{BOX_DIR}/plan.json", json.dumps(plan, indent=1).encode())
        self.box.put(f"{BOX_DIR}/tvb-regress.service", UNIT.encode())
        self.box.put(f"{BOX_DIR}/tvb-regress-guard.service", GUARD.encode())
        self.box.put(f"{BOX_DIR}/results/host.txt", ("\n".join(host_lines) + "\n").encode())
        clips = json.loads((CLIPS / "manifest.json").read_text())["clips"]
        listing = f"cd {BOX_DIR}/video && sudo -n sha256sum * 2>/dev/null || true"
        held = dict(line.split()[::-1] for line in self.box.run(listing, check=True).splitlines())
        sizes = VIDEO_SIZES.get(self.profile)
        for name, clip in sorted(clips.items()):
            if sizes is None or any(f"-{size}." in name for size in sizes):
                if held.get(name) != clip["sha256"]:
                    self.box.put(f"{BOX_DIR}/video/{name}", (CLIPS / name).read_bytes())
        self.box.put(f"{BOX_DIR}/video/manifest.json", (CLIPS / "manifest.json").read_bytes())
        self.deqp(family)

    def sync_clips(self, folder: str) -> None:
        """A clip folder on the box made like the host's: only the clips that differ sent."""
        local = CLIP_DIRS[folder]
        listing = f"sudo -n mkdir -p {BOX_DIR}/{folder} && cd {BOX_DIR}/{folder} && "
        listing += "sudo -n sha256sum * 2>/dev/null || true"
        held = dict(line.split()[::-1] for line in self.box.run(listing, check=True).splitlines())
        for clip in sorted(local.iterdir()):
            if held.get(clip.name) != full_sha(clip):
                self.box.put(f"{BOX_DIR}/{folder}/{clip.name}", clip.read_bytes())

    def deqp(self, family: str) -> None:
        """Mesa CI's lists for the box's GPU, the suite and the script that runs it."""
        version = self.box.run("dpkg-query -W -f '${Version}' libgbm1").split("-")[0]
        gpu = GPU[family]
        for kind in ("fails", "flakes", "skips"):
            self.box.put(f"{BOX_DIR}/deqp/{kind}.txt", expectations(version, gpu, kind).encode())
        toml = suite_toml(GLES2 if gpu == "lima" else SUITE, DEQP_FRACTION[self.profile])
        self.box.put(f"{BOX_DIR}/deqp/suite.toml", toml.encode())
        self.box.put(f"{BOX_DIR}/deqp/run.sh", DEQP_RUN.encode())


def listening() -> bool:
    with socket.socket() as probe:
        return probe.connect_ex(("127.0.0.1", IPERF_PORT)) == 0


def serve_iperf() -> None:
    """This machine as the iperf3 server, unless something already listens: another box's run may
    have started it a moment before."""
    if not listening() and subprocess.run(["iperf3", "-s", "-D", "-p", str(IPERF_PORT)]).returncode:
        time.sleep(1)
        if not listening():
            raise NotStarted(f"no iperf3 server on port {IPERF_PORT} here")


def address_towards(host: str) -> str:
    """This machine's IPv4 address on its route to host: IPv4, which a reloaded radio has back
    before IPv6."""
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as probe:
        probe.connect((socket.gethostbyname(host), 9))  # UDP: no packet is sent
        return probe.getsockname()[0]


def start(profile: str, spec: str, iperf: str | None, which: str, released: bool) -> None:
    """One box: its packages installed fresh, the suite bundled, the run started. Without an
    iperf3 server named, this machine serves, at its address on the route to the box. A released
    box runs no tree of this checkout's: the checks against it are left out."""
    board, _, target = spec.partition("=")
    box = Box(target)
    iperf = iperf or address_towards(target.rpartition("@")[2])
    deployment = Deployment(board, box, profile, iperf)
    default = box.run(DEFAULT_RELEASE).strip()
    if released:
        releases = deployment.install_released(which)
        host_lines = [f"profile {profile}"]
    else:
        debs = [d.name for d in DEBS.glob("*.deb")]
        releases = kernels(board_family(board), debs, which)
        if not releases:
            raise NotStarted(f"no {which} {board_family(board)} kernel package in {DEBS}")
        print(f"{board}: install {deployment.install(releases)}")
        host_lines = [f"profile {profile}", *deployment.host_checks()]
    host_lines += [f"# input {i}" for i in deployment.inputs]
    deployment.bundle(releases, host_lines, default)
    failed = [line for line in host_lines if line.startswith("FAIL")]
    print(f"{board}: host checks {'; '.join(failed) or 'pass'}")
    Box(target).root(START)
    print(f"{board}: {profile} started on {', '.join(releases)}")


def prepare(board: str, released: bool) -> None:
    """What the host gives a box, made first: the board's package built fresh unless released,
    the clip corpus brought up to date (cached, so all but free). One process at a time, whichever
    asks: the build container's work volume and the corpus are one each."""
    (ROOT / "build").mkdir(exist_ok=True)
    with (ROOT / "build" / ".regression.lock").open("w") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        stamp, made_of = DEBS / f".tvb-{board}.inputs", board_inputs(board)
        built = list(DEBS.glob(f"tvb-{board}_*.deb"))
        if not released and not (built and stamp.exists() and stamp.read_text() == made_of):
            subprocess.run([str(ROOT / "build.sh"), "board", board], cwd=ROOT, check=True)
            stamp.write_text(made_of)
        subprocess.run([sys.executable, str(HERE / "video.py"), "clips"], cwd=ROOT, check=True)
        subprocess.run(
            [sys.executable, str(VA_SUITE / "vaapi_test.py"), "clips", "--out", str(VA_CLIPS)],
            cwd=ROOT,
            check=True,
        )


def board_inputs(board: str) -> str:
    """What the board's package is made of, hashed: its folder, the packaging scripts and its
    U-Boot as built."""
    files = [p for d in (ROOT / "boards" / board, ROOT / "package") for p in sorted(d.rglob("*"))]
    files += [p for p in (ROOT / "build" / "out" / "uboot" / board).glob("*") if p.is_file()]
    digest = hashlib.sha256()
    for path in (p for p in files if p.is_file()):
        digest.update(str(path.relative_to(ROOT)).encode() + b"\0" + path.read_bytes())
    return digest.hexdigest()


def started(profile: str, spec: str, iperf: str | None, which: str, released: bool) -> bool:
    """The box's run started; when it could not build, install or start, it says why."""
    try:
        if iperf is None:
            serve_iperf()
        prepare(spec.partition("=")[0], released)
        start(profile, spec, iperf, which, released)
        return True
    except (ConnectionError, subprocess.CalledProcessError, NotStarted) as error:
        print(f"{spec.partition('=')[0]}: not started: {error}", flush=True)
        return False


def deploy(args: argparse.Namespace) -> int:
    return 0 if started(args.profile, args.box, args.iperf, args.kernels, args.released) else 1


def collect(args: argparse.Namespace) -> int:
    into = fetch(args.boxes)
    print(f"then: python3 {Path(__file__).relative_to(ROOT)} report {into.relative_to(ROOT)}")
    return 0


def ending(folder: Path) -> str:
    """How a box's collected run ended: done, or not yet."""
    return "done" if (folder / "done").exists() else "**not finished**"


def fetch(boxes: list[str]) -> Path:
    """Each box's results, done or not, into one folder: today's, or a new one when a board
    already has another run there today. A box that does not answer is said and skipped."""
    with tempfile.TemporaryDirectory() as tmp:
        fetched: list[str] = []
        for spec in boxes:
            board, _, target = spec.partition("=")
            command = f"sudo -n tar -C {BOX_DIR}/results -cf - ."
            try:
                archive = Box(target).raw(command, seconds=600, check=True)
            except ConnectionError as error:
                print(f"{board}: nothing collected: {error}")
                continue
            (Path(tmp) / board).mkdir()
            subprocess.run(
                ["tar", "-C", str(Path(tmp) / board), "-xf", "-"], input=archive, check=True
            )
            fetched.append(board)
        into = RESULTS / datetime.date.today().isoformat()
        if any(
            (into / b).exists()
            and first_line(into / b / "run.log") != first_line(Path(tmp) / b / "run.log")
            for b in fetched
        ):  # another run the same day: a folder of its own, never merged into another
            into = fresh(RESULTS / datetime.datetime.now().strftime("%Y-%m-%d-%H%M"))
        for board in fetched:
            out = into / board
            shutil.copytree(Path(tmp) / board, out, dirs_exist_ok=True)
            print(f"{board}: {ending(out)}, into {out}")
    return into


def fresh(folder: Path) -> Path:
    """folder, or folder-2, -3...: the first that does not exist yet."""
    n = 1
    found = folder
    while found.exists():
        n += 1
        found = folder.with_name(f"{folder.name}-{n}")
    return found


def state(box: Box) -> str:
    """A box's run: done, failed (onbox.py's unit died), or running; a box rebooting between
    kernels is running."""
    probe = f"cd {BOX_DIR}/results && test -f done && echo done; "
    probe += "systemctl is-failed -q tvb-regress.service && echo failed"
    return (box.run(probe).split() or ["running"])[0]


def watch(spec: str, seconds: float) -> str:
    """The box's run log as it grows, until its run ends or the time is up; how it ended."""
    board, _, target = spec.partition("=")
    box, seen, deadline = Box(target), 0, time.monotonic() + seconds
    while time.monotonic() < deadline:
        time.sleep(POLL_S)
        try:
            lines = box.run(f"tail -n +{seen + 1} {BOX_DIR}/results/run.log").splitlines()
            now = state(box)
        except ConnectionError:
            continue  # rebooting
        seen += len(lines)
        for line in lines:
            print(f"{board}: {line}", flush=True)
        if now != "running":
            print(f"{board}: {now}", flush=True)
            return now
    print(f"{board}: timed out", flush=True)
    return "timed out"


def run(args: argparse.Namespace) -> int:
    """One box: deployed, watched until its run ends, collected and reported. Several boxes are
    several runs at once, one process each: the iperf3 server takes one at a time, the others wait
    their turn, so no box measures another's traffic."""
    if not started(args.profile, args.box, args.iperf, args.kernels, args.released):
        return 1
    ended = watch(args.box, RUN_LIMIT_S[args.profile])
    report(argparse.Namespace(dir=str(fetch([args.box]))))
    return 0 if ended == "done" else 1


def full_sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def sha(path: Path) -> str:
    """A file's content, short: a rebuilt package keeps its version, 0~local, not its hash."""
    return full_sha(path)[:12]


def inputs(host: Path) -> dict[str, str]:
    """What a run installed, name to hash, from its host.txt."""
    out: dict[str, str] = {}
    for line in host.read_text().splitlines() if host.exists() else []:
        words = line.split()
        if words[:2] == ["#", "input"] and len(words) == 4:
            out[words[2]] = words[3]
    return out


def changed_inputs(board: str, run: Path) -> str:
    """Which of a board's inputs differ from its run before this one, for the report."""
    earlier = sorted(p for p in RESULTS.glob(f"*/{board}/host.txt") if p.parents[1].name < run.name)
    now = inputs(run / board / "host.txt")
    if not earlier or not now:
        return ""
    before = inputs(earlier[-1])
    moved = sorted(n for n in now.keys() | before.keys() if now.get(n) != before.get(n))
    since = earlier[-1].parents[1].name
    return f"Inputs changed since {since}: {', '.join(moved) or 'none'}.\n" if before else ""


def first_line(path: Path) -> str:
    """A run log's first line: when, and on which kernel, its run began."""
    return path.read_text().split("\n", 1)[0] if path.exists() else ""


def last_run(board: str, kernel: str, before: Path) -> Path | None:
    """The board's newest earlier results for this kernel."""
    found = sorted(
        p.parent
        for p in RESULTS.glob(f"*/{board}/{kernel}/system.txt")
        if p.parents[2].name < before.name
    )
    return found[-1] if found else None


def step_seconds(log: Path, kernel: str) -> list[tuple[str, int]]:
    """Each of a kernel's steps and its seconds, in run order, from the run log; boots, reboots
    and recovery not counted, as a box without an RTC logs no true time for them."""
    text = log.read_text() if log.exists() else ""
    found = re.findall(rf"^\S+ {re.escape(kernel)}: (\S+) exit .*, (\d+) s$", text, re.M)
    return [(step, int(seconds)) for step, seconds in found]


def duration(log: Path, kernel: str) -> str:
    """A kernel's minutes of steps."""
    steps = step_seconds(log, kernel)
    return f"{sum(s for _, s in steps) // 60} min" if steps else "?"


def step_table(log: Path, kernel: str) -> str:
    """The kernel's steps and their seconds, folded: where its minutes went."""
    steps = step_seconds(log, kernel)
    if not steps:
        return ""
    rows = "\n".join(f"| {step} | {seconds} |" for step, seconds in steps)
    table = f"| Step | s |\n| --- | ---: |\n{rows}"
    return f"\n<details><summary>steps, {duration(log, kernel)}</summary>\n\n{table}\n</details>"


def wall_minutes(log: Path) -> int | None:
    """A box's whole run, its log's first line to its last: boots and reboots in it."""
    stamps = re.findall(r"^(\d\d):(\d\d):(\d\d) ", log.read_text() if log.exists() else "", re.M)
    if len(stamps) < 2:
        return None
    first, last = (int(h) * 3600 + int(m) * 60 + int(s) for h, m, s in (stamps[0], stamps[-1]))
    return (last - first) % 86400 // 60  # past midnight the clock starts over


def over_budget(board_dir: Path) -> str:
    """A run far past its profile's usual time is a finding in itself: say so."""
    host = board_dir / "host.txt"
    profile = (
        next((l.split()[1] for l in host.read_text().splitlines() if l.startswith("profile ")), "")
        if host.exists()
        else ""
    )
    took = wall_minutes(board_dir / "run.log")
    log = (board_dir / "run.log").read_text() if (board_dir / "run.log").exists() else ""
    booted = len(set(re.findall(r"^\S+ (\S+): booting", log, re.M))) or 1
    budget = BUDGET_MIN[profile] * booted if profile in BUDGET_MIN else None
    if not (took and budget and took > budget):
        return ""
    return f" ⚠ {took} min, {profile}'s usual {budget}"


def profiles(run: Path) -> str:
    found = {
        line.split()[1]
        for host in run.glob("*/host.txt")
        for line in host.read_text().splitlines()
        if line.startswith("profile ")
    }
    return ", ".join(sorted(found)) or "?"


def video_lines(folder: Path) -> list[dict[str, object]]:
    """video.py's records for the run: its header, each case's start and verdict, its end."""
    path = folder / "video.txt"
    lines = path.read_text().splitlines() if path.exists() else []
    return [json.loads(line) for line in lines if line.startswith("{")]


def video_records(folder: Path) -> list[dict[str, object]]:
    return [r for r in video_lines(folder) if "suite" in r]


def video_table(folder: Path) -> str:
    """video.py's codec table for the run: each codec's largest passing size and its limit."""
    records = video_lines(folder)
    head = next((r for r in records if "engine" in r), None)
    cases = [r for r in records if "suite" in r]
    if head is None or not cases:
        return ""
    (folder / "video.json").write_text(json.dumps([head, *cases]))
    done = subprocess.run(
        [sys.executable, str(HERE / "video.py"), "report", str(folder / "video.json")],
        capture_output=True,
        text=True,
    )
    table = (
        done.stdout.strip() if done.returncode == 0 else f"video.py report: {done.stderr.strip()}"
    )
    return f"\n<details><summary>video, codec by codec</summary>\n\n{table}\n</details>"


def phase_text(folder: Path) -> str:
    return "".join(p.read_text() for p in sorted(folder.glob("*.txt")) if p.stem in PHASES)


def report(args: argparse.Namespace) -> int:
    run = Path(args.dir).resolve()
    commit = subprocess.run(
        ["git", "-C", str(ROOT), "describe", "--always", "--dirty"], capture_output=True, text=True
    ).stdout.strip()
    rows, details = [], []
    for board_dir in sorted(p for p in run.iterdir() if p.is_dir()):
        board = board_dir.name
        end = ending(board_dir) + over_budget(board_dir)
        host = Verdicts.of(board_dir / "host.txt")
        moved_inputs = changed_inputs(board, run)
        kernel_dirs = sorted((p for p in board_dir.iterdir() if p.is_dir()), key=release_order)
        own = kernel_dirs[0] / "system.txt" if kernel_dirs else None
        for kernel_dir in kernel_dirs:
            total = Verdicts(host.checks, list(host.fails), list(host.untested))
            for result in sorted(kernel_dir.glob("*.txt")):
                found = Verdicts.of(result)
                total.checks += found.checks
                total.fails += [f"{result.stem}: {x}" for x in found.fails]
                total.untested += [f"{result.stem}: {x}" for x in found.untested]
            kernel = kernel_dir.name
            last = last_run(board, kernel, run)
            if last is not None and video_records(last):
                since = last.parents[1].name
                cases = worse(video_records(last), video_records(kernel_dir))
                total.fails += [f"video: worse than {since}: {case}" for case in cases]
            if last is not None and (last / "va.txt").exists() and (kernel_dir / "va.txt").exists():
                since = last.parents[1].name
                speeds = slower((last / "va.txt").read_text(), (kernel_dir / "va.txt").read_text())
                total.fails += [f"va: slower than {since}: {speed}" for speed in speeds]
            system_txt = kernel_dir / "system.txt"
            if own is not None and own != system_txt and own.exists() and system_txt.exists():
                gaps = short_of(own.read_text(), system_txt.read_text())
                total.fails += [f"parity: short of {own.parent.name}: {gap}" for gap in gaps]
            counts = f"{total.checks} | {len(total.fails)} | {len(total.untested)}"
            minutes = duration(board_dir / "run.log", kernel)
            rows.append(f"| {board} | {kernel} | {end}, {minutes} | {counts} |")
            details += [f"### {board}, {kernel}\n", moved_inputs]
            details += [f"- ❌ {x}" for x in total.fails]
            details += [f"- ❓ {x}" for x in total.untested]
            details.append(step_table(board_dir / "run.log", kernel))
            details.append(video_table(kernel_dir))
            if last is not None:
                moved = [
                    m
                    for m in changed(phase_text(last), phase_text(kernel_dir))
                    if not m.startswith(("exit", "FAIL", "UNTESTED"))
                ]
                summary = f"{len(moved)} lines moved since {last.parents[1].name}"
                body = "\n".join(f"    {m}" for m in moved)
                details.append(f"\n<details><summary>{summary}</summary>\n\n{body}\n</details>")
            details.append("")
    header = [
        f"## Regression {run.name}",
        "",
        f"Commit `{commit}`; profile {profiles(run)}; results in `{run.relative_to(ROOT)}`.",
        "❌ failed and ❓ untested are both not a pass.",
        "",
        "| Board | Kernel | Run | Checks | ❌ | ❓ |",
        "| --- | --- | --- | ---: | ---: | ---: |",
    ]
    (run / "report.md").write_text("\n".join([*header, *rows, "", *details]) + "\n")
    print(run / "report.md")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    sub = parser.add_subparsers(dest="command", required=True)
    begin = sub.add_parser("deploy")
    begin.add_argument("--profile", choices=PROFILES, default="default")
    begin.add_argument("--iperf", metavar="HOST", help="the iperf3 server; default: this machine")
    begin.add_argument(
        "--kernels", choices=KERNELS, default="both", help="the family's own, -next, -next2"
    )
    begin.add_argument("--released", action="store_true", help=RELEASED_HELP)
    begin.add_argument("box", metavar="BOARD=USER@HOST")
    gather = sub.add_parser("collect")
    gather.add_argument("boxes", nargs="+", metavar="BOARD=USER@HOST")
    write = sub.add_parser("report")
    write.add_argument("dir")
    whole = sub.add_parser("run", help="deploy, wait, collect, report")
    whole.add_argument("--profile", choices=PROFILES, default="default")
    whole.add_argument("--iperf", metavar="HOST", help="the iperf3 server; default: this machine")
    whole.add_argument(
        "--kernels", choices=KERNELS, default="both", help="the family's own, -next, -next2"
    )
    whole.add_argument("--released", action="store_true", help=RELEASED_HELP)
    whole.add_argument("box", metavar="BOARD=USER@HOST")
    args = parser.parse_args()
    commands = {"deploy": deploy, "collect": collect, "report": report, "run": run}
    return commands[args.command](args)


if __name__ == "__main__":
    sys.exit(main())
