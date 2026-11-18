#!/usr/bin/env python3
"""Each installed browser playing synthetic clips on a box: the frames it presents, by
requestVideoFrameCallback, and whether the video engine decoded them.

On the host:
  browser.py run --box root@<box> [--only REGEX] [--falkon-root DIR] [--user NAME]
The clips are made once by the host's FFmpeg into build/validate/browser/clips; this script and the
clips go to a private directory under the box's /var/tmp, which goes on exit. Firefox and Chromium
run only on a GPU with GLES 3. Each browser runs in a headless labwc, the desktop's compositor, at
1920x1080, as the user logged into the box unless --user names one. Exit 1 on any FAIL.
"""

from __future__ import annotations

import argparse
import io
import json
import os
import re
import shlex
import shutil
import signal
import tempfile
import subprocess
import sys
import tarfile
import threading
import time
from collections.abc import Buffer, Callable, Iterator
from dataclasses import dataclass
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import BinaryIO
from urllib.parse import parse_qs, urlparse

REPO = Path(__file__).resolve().parents[2]
CLIPS = REPO / "build/validate/browser/clips"
SSH = ["ssh", "-o", "BatchMode=yes", "-o", "ConnectTimeout=10"]
REPORT_PREFIX = "browser."
CLIP_SECONDS = 20
# what a browser shows without dropping: each codec at 1080p60, 4K30 and 4K60
SIZES = {"1080p60": ("1920x1080", 60), "4k30": ("3840x2160", 30), "4k60": ("3840x2160", 60)}
ENCODERS = {
    "vp9": (
        "webm",
        ["-c:v", "libvpx-vp9", "-b:v", "20M", "-deadline", "realtime"]
        + ["-cpu-used", "8", "-row-mt", "1", "-c:a", "libopus"],
    ),
    "h264": ("mp4", ["-c:v", "libx264", "-preset", "ultrafast", "-b:v", "30M", "-c:a", "aac"]),
    "hevc": (
        "mp4",
        ["-c:v", "libx265", "-preset", "ultrafast", "-b:v", "30M", "-tag:v", "hvc1"]
        + ["-x265-params", "log-level=error", "-c:a", "aac"],
    ),
}
KEYFRAME_FRAMES = "120"
WARMUP_S = 5
WINDOW_S = 10
LOAD_TIMEOUT_S = 90
RESULT_MARGIN_S = 30
STOP_TIMEOUT_S = 5
PASS_SHARE = 0.95
ENGINE_IRQS = r"cedrus|vdpu|rkvdec|vdec|esparser"
VA_PROFILE = Path("/etc/profile.d/tvb-va-driver.sh")
# GPU drivers with no GLES 3, which Firefox's and Chromium's renderers need: there they are not run
GLES2_ONLY_DRIVERS = {"lima"}
HEADLESS = {
    "WLR_BACKENDS": "headless",
    "WLR_RENDERER": "gles2",
    "WLR_HEADLESS_OUTPUTS": "1",
    "WLR_LIBINPUT_NO_DEVICES": "1",
    "NO_AT_BRIDGE": "1",
}
FIREFOX_PREFS = {
    "media.ffmpeg.vaapi.enabled": "true",
    "media.hardware-video-decoding.force-enabled": "true",
    "media.autoplay.default": "0",
    "media.autoplay.blocking_policy": "0",
    "browser.shell.checkDefaultBrowser": "false",
    "datareporting.policy.dataSubmissionEnabled": "false",
    "toolkit.telemetry.reportingpolicy.firstRun": "false",
    "browser.aboutwelcome.enabled": "false",
}
# the page: plays ?src muted and looped, and after a warm-up reports the frames presented in a window
PAGE = """<!doctype html><meta charset=utf-8><title>browser check</title>
<body style="margin:0;background:#000">
<video id=v muted autoplay playsinline loop style="width:100vw;height:100vh"></video>
<script>
const params = new URLSearchParams(location.search);
const video = document.getElementById("v");
const report = fields => fetch("/report?" + new URLSearchParams({tag: params.get("tag"), ...fields}));
video.onerror = () => report({error: `code ${video.error.code} ${video.error.message}`});
video.src = params.get("src");
video.play().catch(e => report({error: `play rejected: ${e}`}));
let measuring = false, frames = 0, played = 0, lastMedia = null, began = 0;
const counted = (now, meta) => {
  if (measuring) {
    frames++;
    if (lastMedia !== null && meta.mediaTime > lastMedia) played += meta.mediaTime - lastMedia;
  }
  lastMedia = meta.mediaTime;
  video.requestVideoFrameCallback(counted);
};
if (!video.requestVideoFrameCallback) report({error: "no requestVideoFrameCallback"});
else video.requestVideoFrameCallback(counted);
setTimeout(() => { measuring = true; began = performance.now(); }, WARMUP * 1000);
setTimeout(() => {
  const seconds = (performance.now() - began) / 1000;
  report({fps: frames / seconds, media: played / seconds, size: `${video.videoWidth}x${video.videoHeight}`});
}, (WARMUP + WINDOW) * 1000);
</script>
""".replace("WARMUP", str(WARMUP_S)).replace("WINDOW", str(WINDOW_S))

Line = tuple[str, str]


def make_clips() -> None:
    CLIPS.mkdir(parents=True, exist_ok=True)
    for codec, (container, encoder) in ENCODERS.items():
        for tag, (size, rate) in SIZES.items():
            path = CLIPS / f"{codec}-{tag}.{container}"
            if path.exists():
                continue
            video = f"testsrc2=size={size}:rate={rate}:duration={CLIP_SECONDS}"
            subprocess.run(
                ["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i", video]
                + ["-f", "lavfi", "-i", "anullsrc=r=48000:cl=stereo", "-shortest"]
                + ["-pix_fmt", "yuv420p", "-g", KEYFRAME_FRAMES, "-movflags", "+faststart"]
                + encoder
                + [str(path)],
                check=True,
            )


def clip_rate(clip: Path) -> int:
    return SIZES[clip.stem.split("-", 1)[1]][1]


# on the box


class Server(ThreadingHTTPServer):
    """The page, the clips with range requests, and each page's report by its tag."""

    def __init__(self, root: Path) -> None:
        self.root = root
        self.reports: dict[str, dict[str, str]] = {}
        super().__init__(("127.0.0.1", 0), partial(Handler, directory=str(root)))
        threading.Thread(target=self.serve_forever, daemon=True).start()

    def handle_error(self, request: object, client_address: object) -> None:
        pass  # a browser drops a clip's connection whenever it seeks or has enough

    @property
    def port(self) -> int:
        return self.server_address[1]


class Window(io.RawIOBase):
    """A range of a file, read as a whole file."""

    def __init__(self, path: Path, start: int, length: int) -> None:
        super().__init__()
        self.file = path.open("rb")
        self.file.seek(start)
        self.left = length

    def readable(self) -> bool:
        return True

    def readinto(self, buffer: Buffer) -> int:
        read = self.file.readinto(memoryview(buffer)[: self.left]) or 0
        self.left -= read
        return read

    def close(self) -> None:
        self.file.close()
        super().close()


class Handler(SimpleHTTPRequestHandler):
    def log_message(self, format: str, *args: object) -> None:
        pass

    def do_GET(self) -> None:
        url = urlparse(self.path)
        if url.path != "/report":
            return super().do_GET()
        fields = {k: v[0] for k, v in parse_qs(url.query).items()}
        assert isinstance(self.server, Server)
        self.server.reports[fields.pop("tag", "")] = fields
        self.send_response(204)
        self.end_headers()

    def send_head(self) -> BinaryIO | None:
        path = Path(self.translate_path(self.path))
        wanted = re.fullmatch(r"bytes=(\d+)-(\d*)", self.headers.get("Range", ""))
        if not wanted or not path.is_file():
            return super().send_head()
        size = path.stat().st_size
        start = int(wanted.group(1))
        end = min(int(wanted.group(2) or size - 1), size - 1)
        self.send_response(206)
        self.send_header("Content-Type", self.guess_type(str(path)))
        self.send_header("Accept-Ranges", "bytes")
        self.send_header("Content-Range", f"bytes {start}-{end}/{size}")
        self.send_header("Content-Length", str(end - start + 1))
        self.end_headers()
        return io.BufferedReader(Window(path, start, end - start + 1))


@dataclass
class Browser:
    name: str
    command: list[str]
    env: dict[str, str]


def browsers(profiles: Path, falkon_root: Path | None) -> list[Browser]:
    """Each browser the box has, with a profile of its own under the run's directory."""
    found: list[Browser] = []
    if gles3() and shutil.which("firefox-esr"):
        profile = profiles / "firefox"
        profile.mkdir(parents=True, exist_ok=True)
        prefs = "".join(f'user_pref("{k}", {v});\n' for k, v in FIREFOX_PREFS.items())
        (profile / "user.js").write_text(prefs)
        command = ["firefox-esr", "--kiosk", "--no-remote", "--profile", str(profile)]
        found.append(Browser("firefox", command, {"MOZ_ENABLE_WAYLAND": "1"}))
    if gles3() and shutil.which("chromium"):
        command = ["chromium", "--ozone-platform=wayland", "--kiosk", "--no-first-run"]
        command += [f"--user-data-dir={profiles / 'chromium'}"]
        command += ["--autoplay-policy=no-user-gesture-required"]
        found.append(Browser("chromium", command, {}))
    if falkon_root:
        usr = falkon_root / "usr"
        libs = f"{usr}/lib:{usr}/lib/aarch64-linux-gnu"
        env = {
            "QT_QPA_PLATFORM": "wayland",
            "LD_LIBRARY_PATH": libs,
            "FALKON_PLUGIN_PATH": f"{usr}/lib/aarch64-linux-gnu/qt6/plugins/falkon",
            "XDG_DATA_DIRS": f"{usr}/share:/usr/share",
            "XDG_CONFIG_HOME": str(profiles / "falkon/config"),
            "XDG_DATA_HOME": str(profiles / "falkon/data"),
            "XDG_CACHE_HOME": str(profiles / "falkon/cache"),
        }
        found.append(Browser("falkon-wpe", [f"{usr}/bin/falkon", "--no-remote"], env))
    return found


def gles3() -> bool:
    drivers = {p.resolve().name for p in Path("/sys/class/drm").glob("renderD*/device/driver")}
    return bool(drivers - GLES2_ONLY_DRIVERS)


def logged_in_user() -> str | None:
    listing = subprocess.run(["pgrep", "-x", "labwc"], capture_output=True, text=True).stdout
    owners = [Path(f"/proc/{pid}").owner() for pid in listing.split()]
    return next((o for o in owners if o != "root"), None)


def irq_count() -> int:
    lines = Path("/proc/interrupts").read_text().splitlines()
    engine = [line for line in lines if re.search(ENGINE_IRQS, line)]
    return sum(int(n) for line in engine for n in line.split()[1:] if n.isdigit())


def wait_for(ready: Callable[[], bool], seconds: float) -> bool:
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        if ready():
            return True
        time.sleep(0.5)
    return False


def play(server: Server, user: str, home: Path, browser: Browser, clip: Path) -> str:
    """One clip in one browser: its report against the clip's rate, and the engine's interrupts."""
    tag = f"{browser.name}-{clip.stem}"
    url = f"http://127.0.0.1:{server.port}/page.html?tag={tag}&src=clips/{clip.name}"
    runtime = home / f"runtime-{tag}"
    runtime.mkdir(mode=0o700)
    shutil.chown(runtime, user)
    env = {**HEADLESS, **browser.env, "XDG_RUNTIME_DIR": str(runtime), "HOME": f"/home/{user}"}
    shell = f'[ -f {VA_PROFILE} ] && . {VA_PROFILE}; exec "$@"'
    command = ["runuser", "-u", user, "--", "env", "-u", "DBUS_SESSION_BUS_ADDRESS"]
    command += [f"{k}={v}" for k, v in env.items()]
    command += ["sh", "-c", shell, "sh", "dbus-run-session", "--", "labwc", "-s"]
    command += [shlex.join(browser.command + [url])]
    log = (home / f"{tag}.log").open("w")
    irqs = irq_count()
    process = subprocess.Popen(command, stdout=log, stderr=log, start_new_session=True)
    try:
        reported = wait_for(
            lambda: tag in server.reports, LOAD_TIMEOUT_S + WARMUP_S + WINDOW_S + RESULT_MARGIN_S
        )
    finally:
        stop(process)
        log.close()
    if not reported:
        return f"failed: the page never reported; {last_line(home / f'{tag}.log')}"
    report = server.reports[tag]
    if "error" in report:
        return f"failed: {report['error']}"
    fps, media = float(report["fps"]), float(report["media"])
    measured = f"{fps:.1f} fps, {media:.2f}x, {report['size']}"
    if irq_count() == irqs:
        return f"failed: {measured}, but the video engine's interrupts did not move"
    if fps < clip_rate(clip) * PASS_SHARE or media < PASS_SHARE:
        return f"failed: {measured}"
    return f"pass: {measured}"


def last_line(log: Path) -> str:
    lines = log.read_text(errors="replace").strip().splitlines()
    return lines[-1] if lines else "the browser printed nothing"


def stop(process: subprocess.Popen[bytes]) -> None:
    """The browser's whole session: the compositor, the bus and every process they started."""
    os.killpg(process.pid, signal.SIGTERM)
    try:
        process.wait(timeout=STOP_TIMEOUT_S)
    except subprocess.TimeoutExpired:
        os.killpg(process.pid, signal.SIGKILL)
        process.wait()


def check(run_dir: Path, only: str, falkon_root: Path | None, user: str | None) -> Iterator[Line]:
    user = user or logged_in_user()
    if not user:
        yield "user", "UNTESTED: no --user, and nobody is logged into a session"
        return
    (run_dir / "page.html").write_text(PAGE)
    # WebKit's sandbox cannot map a directory under /var/tmp, which it links to /tmp
    home = Path(tempfile.mkdtemp(prefix="tvb-browser-"))
    try:
        yield from play_all(run_dir, home, user, only, falkon_root)
    finally:
        shutil.rmtree(home, ignore_errors=True)


def play_all(
    run_dir: Path, home: Path, user: str, only: str, falkon_root: Path | None
) -> Iterator[Line]:
    shutil.chown(home, user)
    if not browsers(home / "probe", falkon_root):
        yield "browsers", "UNTESTED: no browser installed"
        return
    server = Server(run_dir)
    clips = sorted(c for c in (run_dir / "clips").iterdir() if re.search(only, c.stem))
    for clip in clips:
        # a fresh profile each play: a killed browser leaves its last session to restore
        profiles = home / f"profiles-{clip.stem}"
        for browser in browsers(profiles, falkon_root):
            subprocess.run(["chown", "-R", user, str(profiles)], check=False)
            yield f"{browser.name}.{clip.stem}", play(server, user, home, browser, clip)


def on_box(args: argparse.Namespace) -> int:
    run_dir = Path(args.dir)
    os.chmod(run_dir, 0o755)
    failed = False
    for key, result in check(run_dir, args.only, args.falkon_root, args.user):
        print(f"{REPORT_PREFIX}{key} {result}", flush=True)
        if result.startswith("failed"):
            print(f"FAIL {REPORT_PREFIX}{key}", flush=True)
            failed = True
    return 1 if failed else 0


# on the host


def remote(
    box: str, command: str, capture: bool = False, timeout: float | None = None
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(SSH + [box, command], text=True, capture_output=capture, timeout=timeout)


def from_host(args: argparse.Namespace) -> int:
    make_clips()
    made = remote(args.box, "mktemp -d /var/tmp/tvb-browser.XXXXXX", capture=True)
    box_dir = made.stdout.strip()
    if made.returncode != 0 or not box_dir:
        sys.exit(f"could not reach {args.box}")
    try:
        untar = subprocess.Popen(SSH + [args.box, f"tar -x -C {box_dir}"], stdin=subprocess.PIPE)
        assert untar.stdin
        with tarfile.open(fileobj=untar.stdin, mode="w|") as tar:
            tar.add(__file__, "browser.py")
            tar.add(CLIPS, "clips")
        untar.stdin.close()
        if untar.wait() != 0:
            sys.exit(f"could not copy the check to {args.box}")
        command = f"python3 {box_dir}/browser.py box --dir {box_dir} --only {json.dumps(args.only)}"
        if args.falkon_root:
            command += f" --falkon-root {args.falkon_root}"
        if args.user:
            command += f" --user {args.user}"
        return remote(args.box, command).returncode
    finally:
        remote(args.box, f"rm -rf -- {box_dir}", timeout=60)


def main() -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    sub = parser.add_subparsers(dest="cmd", required=True)
    for name in ("run", "box"):
        p = sub.add_parser(name)
        p.add_argument("--only", default="", help="a regex over <codec>-<size>")
        p.add_argument(
            "--falkon-root",
            type=Path,
            help="Falkon-WPE's install root on the box, its files under usr/",
        )
        p.add_argument("--user", help="who runs the browsers: by default, who is logged in")
    sub.choices["run"].add_argument("--box", required=True, help="the box, as ssh reaches it")
    sub.choices["box"].add_argument("--dir", required=True)
    args = parser.parse_args()
    return from_host(args) if args.cmd == "run" else on_box(args)


if __name__ == "__main__":
    sys.exit(main())
