#!/usr/bin/env python3
"""Each installed browser playing synthetic clips on a box, as a file and through Media Source
Extensions as video sites stream: the frames it presents, by requestVideoFrameCallback, whether the
video engine decoded them, and the decoder WebKit made. Then a call between two peers in one page:
its codec, the frames encoded and received, and whether the box's encoder encoded them.

On the host:
  browser.py run --box root@<box> [--only REGEX] [--browsers falkon-wpe,chromium,...]
                [--falkon-root DIR] [--user NAME] [--demote FEATURE:NONE,...]
The clips are made once by the host's FFmpeg into build/validate/browser/clips; this script and the
clips go to a private directory under the box's /var/tmp, which goes on exit. Falkon plays by
default; Chromium and Firefox, references, when --browsers names them, and only on a GPU with
GLES 3; WPE's MiniBrowser only when named, to debug WebKit without qtwpewebkit. Each browser runs in a headless labwc, the desktop's compositor, at
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
from urllib.parse import parse_qs, urlencode, urlparse

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
# each clip as Media Source Extensions take it, as video sites stream: its video and audio apart, in
# buffers of their own, MP4 in fragments; the types of each, by codec
FRAGMENTED_MP4 = ["-movflags", "+frag_keyframe+empty_moov+default_base_moof"]
MSE_PARTS = {"video": "0:v", "audio": "0:a"}
MSE_TYPES = {
    "vp9": {"video": 'video/webm; codecs="vp9"', "audio": 'audio/webm; codecs="opus"'},
    "h264": {"video": 'video/mp4; codecs="avc1.640033"', "audio": 'audio/mp4; codecs="mp4a.40.2"'},
    "hevc": {
        "video": 'video/mp4; codecs="hvc1.1.6.L153.90"',
        "audio": 'audio/mp4; codecs="mp4a.40.2"',
    },
}
# the GStreamer decoders WebKit makes, named in its log
GST_DECODERS_LOG = "GST_ELEMENT_FACTORY:4"
DECODER = re.compile(
    r'"((?:va|v4l2|v4l2sl|avdec_|vp8|vp9|dav1d|av1|openh264|libde265)[a-z0-9_]*dec)"'
)
WARMUP_S = 5
WINDOW_S = 10
LOAD_TIMEOUT_S = 90
RESULT_MARGIN_S = 30
STOP_TIMEOUT_S = 5
PASS_SHARE = 0.95
ENGINE_IRQS = r"cedrus|vdpu|rkvdec|vdec|esparser|video-codec"
VA_PROFILE = Path("/etc/profile.d/tvb-va-driver.sh")
# WebKit's own browser on WPE: the same engine and media pipeline as Falkon's, drawn without Qt
FALKON = "falkon-wpe"
# WPE's own browser, without qtwpewebkit: to debug, trace and probe WebKit, never a default
MINIBROWSER = "wpe-minibrowser"
MINIBROWSER_PATH = Path("/usr/lib/aarch64-linux-gnu/wpe-webkit-2.0/MiniBrowser")
BROWSERS = (FALKON, "chromium", "firefox", MINIBROWSER)
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
// as a player streams: a piece at a time, a few seconds ahead of the playhead, and what has played
// a while ago removed
const appendPiece = 1 << 20, aheadSeconds = 6;
const append = async (source, part) => {
  const buffer = source.addSourceBuffer(params.get(part + "type"));
  const data = new Uint8Array(await (await fetch(params.get(part))).arrayBuffer());
  const updated = () => new Promise((done, failed) => {
    buffer.addEventListener("updateend", done, {once: true});
    buffer.addEventListener("error", failed, {once: true});
  });
  const pause = ms => new Promise(wait => setTimeout(wait, ms));
  const bufferedAhead = () => buffer.buffered.length
    ? buffer.buffered.end(buffer.buffered.length - 1) - video.currentTime : 0;
  for (let at = 0; at < data.length;) {
    if (bufferedAhead() > aheadSeconds) {
      await pause(100);
      continue;
    }
    if (buffer.buffered.length && buffer.buffered.start(0) < video.currentTime - aheadSeconds) {
      buffer.remove(0, video.currentTime - aheadSeconds);
      await updated();
    }
    try {
      buffer.appendBuffer(data.subarray(at, at + appendPiece));
      await updated();
      at += appendPiece;
    } catch (e) {
      if (e.name !== "QuotaExceededError") throw e;
      await pause(250);
    }
  }
};
if (params.get("video")) {
  video.loop = false;
  const source = new MediaSource();
  video.src = URL.createObjectURL(source);
  source.addEventListener("sourceopen", async () => {
    try {
      await Promise.all([append(source, "video"), append(source, "audio")]);
      source.endOfStream();
    } catch (e) {
      report({error: `MSE: ${e}`});
    }
  });
} else video.src = params.get("src");
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
// the browser's own count of the frames it decoded and dropped, over the same window
const quality = () => video.getVideoPlaybackQuality ? video.getVideoPlaybackQuality()
  : {totalVideoFrames: 0, droppedVideoFrames: 0};
// the stalls: how often, and how long, playback waited for data in the window
let waits = 0, waited = 0, waitingSince = null;
video.addEventListener("waiting", () => {
  if (!measuring || waitingSince !== null) return;
  waits++;
  waitingSince = performance.now();
});
video.addEventListener("playing", () => {
  if (waitingSince === null) return;
  waited += performance.now() - waitingSince;
  waitingSince = null;
});
let firstQuality = null;
let firstClock = 0;
setTimeout(() => { measuring = true; began = performance.now(); firstQuality = quality(); firstClock = video.currentTime; }, WARMUP * 1000);
setTimeout(() => {
  const seconds = (performance.now() - began) / 1000, last = quality();
  report({fps: frames / seconds, media: played / seconds, size: `${video.videoWidth}x${video.videoHeight}`,
    decoded: (last.totalVideoFrames - firstQuality.totalVideoFrames) / seconds,
    dropped: (last.droppedVideoFrames - firstQuality.droppedVideoFrames) / seconds,
    clock: (video.currentTime - firstClock) / seconds, waits, waited: (waited + (waitingSince === null ? 0 : performance.now() - waitingSince)) / 1000});
}, (WARMUP + WINDOW) * 1000);
</script>
""".replace("WARMUP", str(WARMUP_S)).replace("WINDOW", str(WINDOW_S))

# a call: a moving canvas streamed between two peers in the page, H.264 preferred, as a call's
# camera is; after a warm-up, the frames encoded and received in a window, the codec and the encoder
CALL_SIZE = (1280, 720)
CALL_RATE = 30
CALL_PAGE = """<!doctype html><meta charset=utf-8><title>call check</title>
<body style="margin:0;background:#000">
<video id=v muted autoplay playsinline style="width:100vw;height:100vh"></video>
<script>
const params = new URLSearchParams(location.search);
const video = document.getElementById("v");
const report = fields => fetch("/report?" + new URLSearchParams({tag: params.get("tag"), ...fields}));
// the page's own errors; another world's, as a browser's own scripts, come as a bare "Script error."
window.onerror = (message, source, line, column, error) => {
  if (error) report({error: `call: ${error.name}: ${error.message} at ${line}:${column}`});
};
window.onunhandledrejection = event => report({error: `call: ${event.reason}`});
const canvas = Object.assign(document.createElement("canvas"), {width: WIDTH, height: HEIGHT});
// on the CPU, as a camera's frames are: a GPU canvas is read back for each frame sent
const draw = canvas.getContext("2d", {willReadFrequently: true});
let tick = 0;
const paint = () => {
  draw.fillStyle = `hsl(${tick % 360} 60% 35%)`;
  draw.fillRect(0, 0, WIDTH, HEIGHT);
  draw.fillStyle = "#fff";
  draw.font = "96px sans-serif";
  draw.fillText(String(tick++), (tick * 7) % (WIDTH - 300), HEIGHT / 2);
  requestAnimationFrame(paint);
};
paint();
const sender = new RTCPeerConnection(), receiver = new RTCPeerConnection();
// each side's candidates, kept to say why a call never connects
const candidates = {sender: [], receiver: []};
sender.onicecandidate = e => {
  if (e.candidate) candidates.sender.push(e.candidate.candidate), receiver.addIceCandidate(e.candidate);
};
receiver.onicecandidate = e => {
  if (e.candidate) candidates.receiver.push(e.candidate.candidate), sender.addIceCandidate(e.candidate);
};
receiver.ontrack = e => { video.srcObject = new MediaStream([e.track]); };
// the canvas, or with ?camera the box's camera, as a call takes it
const source = async () => params.get("camera")
  ? (await navigator.mediaDevices.getUserMedia({video: {width: {ideal: WIDTH}, height: {ideal: HEIGHT}}}))
    .getVideoTracks()[0]
  : canvas.captureStream(RATE).getVideoTracks()[0];
let track = null;
(async () => {
  try {
    track = await source();
    const transceiver = sender.addTransceiver(track, {direction: "sendonly"});
    const h264 = (RTCRtpSender.getCapabilities("video")?.codecs || [])
      .filter(c => c.mimeType.toLowerCase() === "video/h264");
    if (h264.length && transceiver.setCodecPreferences) transceiver.setCodecPreferences(h264);
    await sender.setLocalDescription();
    await receiver.setRemoteDescription(sender.localDescription);
    await receiver.setLocalDescription();
    await sender.setRemoteDescription(receiver.localDescription);
  } catch (e) {
    report({error: e.name === "NotFoundError" ? "no camera" : `call: ${e}`});
  }
})();
const outbound = async () => {
  const stats = await sender.getStats();
  for (const stat of stats.values())
    if (stat.type === "outbound-rtp" && stat.kind === "video")
      return [stat, stats.get(stat.codecId), stats.get(stat.mediaSourceId)];
  return [null, null, null];
};
let frames = 0, measuring = false, began = 0, first = null, firstSource = null;
const counted = () => { if (measuring) frames++; video.requestVideoFrameCallback(counted); };
video.requestVideoFrameCallback(counted);
let paintedAtStart = 0;
setTimeout(async () => {
  [first, , firstSource] = await outbound(); measuring = true; began = performance.now(); paintedAtStart = tick;
},
  WARMUP * 1000);
setTimeout(async () => {
  const seconds = (performance.now() - began) / 1000;
  const [last, codec, lastSource] = await outbound();
  const ice = `ICE ${sender.iceConnectionState}, candidates ${candidates.sender.length}/` +
    `${candidates.receiver.length}: ${candidates.sender[0] || "none"}`;
  if (!first || !last) return report({error: `no video sent; ${ice}`});
  report({sent: (last.framesEncoded - first.framesEncoded) / seconds, received: frames / seconds,
    painted: (tick - paintedAtStart) / seconds,
    captured: firstSource && lastSource ? (lastSource.frames - firstSource.frames) / seconds : -1,
    codec: codec ? codec.mimeType : "unknown", encoder: last.encoderImplementation || "unknown", ice,
    source: track ? `${track.label} ${track.getSettings().width}x${track.getSettings().height}` +
      ` at ${track.getSettings().frameRate}` : "none"});
}, (WARMUP + WINDOW) * 1000);
</script>
"""
for name, value in {"WIDTH": CALL_SIZE[0], "HEIGHT": CALL_SIZE[1], "RATE": CALL_RATE}.items():
    CALL_PAGE = CALL_PAGE.replace(name, str(value))
CALL_PAGE = CALL_PAGE.replace("WARMUP", str(WARMUP_S)).replace("WINDOW", str(WINDOW_S))
# the GStreamer encoders WebKit makes for a call; va and v4l2 ones run on the box's encoder
ENCODER = re.compile(r'"((?:va|v4l2|x264|openh264|vp8|vp9|mpp|rkmpp)[a-z0-9_]*enc)"')
HARDWARE_ENCODERS = ("va", "v4l2")
# encoders a browser names in its own stats (encoderImplementation) that run on the CPU
SOFTWARE_ENCODERS = ("openh264", "libvpx", "x264", "libaom", "ffmpeg software", "unknown")

Line = tuple[str, str]


def make_clips() -> None:
    (CLIPS / "mse").mkdir(parents=True, exist_ok=True)
    for codec, (container, encoder) in ENCODERS.items():
        for tag, (size, rate) in SIZES.items():
            path = CLIPS / f"{codec}-{tag}.{container}"
            # a file as sites serve one, its index first; the parts as MSE takes them, in fragments
            faststart = ["-movflags", "+faststart"] if container == "mp4" else []
            fragmented = FRAGMENTED_MP4 if container == "mp4" else []
            if not path.exists():
                video = f"testsrc2=size={size}:rate={rate}:duration={CLIP_SECONDS}"
                subprocess.run(
                    ["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i", video]
                    + ["-f", "lavfi", "-i", "anullsrc=r=48000:cl=stereo", "-shortest"]
                    + ["-pix_fmt", "yuv420p", "-g", KEYFRAME_FRAMES]
                    + faststart
                    + encoder
                    + [str(path)],
                    check=True,
                )
            for part, stream in MSE_PARTS.items():
                if not mse_part(path, part).exists():
                    subprocess.run(
                        ["ffmpeg", "-v", "error", "-y", "-i", str(path), "-map", stream]
                        + ["-c", "copy"]
                        + fragmented
                        + [str(mse_part(path, part))],
                        check=True,
                    )


def mse_part(clip: Path, part: str) -> Path:
    return clip.parent / "mse" / f"{clip.stem}.{part}{clip.suffix}"


def clip_rate(clip: Path) -> int:
    return SIZES[clip.stem.split("-", 1)[1]][1]


# on the box


class Server(ThreadingHTTPServer):
    """The pages, the clips with range requests, and each page's report by its tag; and the decoders
    the run ranks down."""

    def __init__(
        self, root: Path, demote: str = "", gst_debug: str = "", extra_env: str = ""
    ) -> None:
        self.root = root
        self.demote = demote
        self.gst_debug = gst_debug
        # KEY=VALUE,... given to every browser, to try a setting
        self.extra_env = dict(e.split("=", 1) for e in extra_env.split(",") if "=" in e)
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


def browsers(profiles: Path, falkon_root: Path | None, names: frozenset[str]) -> list[Browser]:
    """Each named browser the box has, with a profile of its own under the run's directory."""
    found: list[Browser] = []
    if "firefox" in names and gles3() and shutil.which("firefox-esr"):
        profile = profiles / "firefox"
        profile.mkdir(parents=True, exist_ok=True)
        prefs = "".join(f'user_pref("{k}", {v});\n' for k, v in FIREFOX_PREFS.items())
        (profile / "user.js").write_text(prefs)
        command = ["firefox-esr", "--kiosk", "--no-remote", "--profile", str(profile)]
        found.append(Browser("firefox", command, {"MOZ_ENABLE_WAYLAND": "1"}))
    if "chromium" in names and gles3() and shutil.which("chromium"):
        command = ["chromium", "--ozone-platform=wayland", "--kiosk", "--no-first-run"]
        command += [f"--user-data-dir={profiles / 'chromium'}"]
        command += ["--autoplay-policy=no-user-gesture-required"]
        found.append(Browser("chromium", command, {}))
    if MINIBROWSER in names and MINIBROWSER_PATH.exists():
        found.append(Browser(MINIBROWSER, [str(MINIBROWSER_PATH)], {"GST_DEBUG": GST_DECODERS_LOG}))
    # the packaged Falkon, unless a build's own install root is named
    falkon_root = falkon_root or (Path("/") if shutil.which("falkon") else None)
    if FALKON in names and falkon_root:
        usr = falkon_root / "usr"
        libs = f"{usr}/lib:{usr}/lib/aarch64-linux-gnu"
        env = {
            "QT_QPA_PLATFORM": "wayland",
            "LD_LIBRARY_PATH": libs,
            "FALKON_PLUGIN_PATH": f"{usr}/lib/aarch64-linux-gnu/qt6/plugins/falkon",
            "XDG_DATA_DIRS": f"{usr}/share:/usr/share",
            "XDG_CONFIG_HOME": str(profiles / "falkon/config"),
            "XDG_DATA_HOME": str(profiles / "falkon/data"),
            # one cache for every play: AdBlock's lists compile into it once, as on a user's box
            "XDG_CACHE_HOME": str(profiles.parent / "falkon-cache"),
            "GST_DEBUG": GST_DECODERS_LOG,
        }
        # the camera allowed on every site, as a user would for a call
        settings = profiles / "falkon/config/falkon/profiles/default/settings.ini"
        settings.parent.mkdir(parents=True, exist_ok=True)
        settings.write_text(f"[Site-Settings]\n{FALKON_CAMERA_SETTING}=1\n")
        found.append(Browser(FALKON, [f"{usr}/bin/falkon", "--no-remote"], env))
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


@dataclass
class Opened:
    """A page's report, if it made one, the browser's log, and the decode engine's interrupts."""

    report: dict[str, str] | None
    log: str
    engine_irqs: int


def open_page(
    server: Server,
    user: str,
    home: Path,
    browser: Browser,
    tag: str,
    page: str,
    query: dict[str, str],
    until: Callable[[], bool] | None = None,
) -> Opened:
    """A page in the browser, in a headless labwc, until it reports (or until() holds) or the time
    runs out."""
    url = f"http://127.0.0.1:{server.port}/{page}?{urlencode({'tag': tag, **query})}"
    runtime = home / f"runtime-{tag}"
    runtime.mkdir(mode=0o700)
    shutil.chown(runtime, user)
    env = {**HEADLESS, **browser.env, "XDG_RUNTIME_DIR": str(runtime), "HOME": f"/home/{user}"}
    env["TVB_DEMOTE"] = server.demote
    env |= server.extra_env
    if server.gst_debug and "GST_DEBUG" in env:
        env["GST_DEBUG"] += f",{server.gst_debug}"
    # --demote ranks decoders down after the profile ranks its own, to try another
    shell = f'[ -f {VA_PROFILE} ] && . {VA_PROFILE}; [ -z "$TVB_DEMOTE" ] || '
    shell += 'export GST_PLUGIN_FEATURE_RANK="$GST_PLUGIN_FEATURE_RANK,$TVB_DEMOTE"; exec "$@"'
    command = ["runuser", "-u", user, "--", "env", "-u", "DBUS_SESSION_BUS_ADDRESS"]
    command += [f"{k}={v}" for k, v in env.items()]
    command += ["sh", "-c", shell, "sh", "dbus-run-session", "--", "labwc", "-s"]
    command += [shlex.join(browser.command + [url])]
    log_path = home / f"{tag}.log"
    log = log_path.open("w")
    irqs = irq_count()
    process = subprocess.Popen(command, stdout=log, stderr=log, start_new_session=True)
    try:
        wait_for(
            until or (lambda: tag in server.reports),
            LOAD_TIMEOUT_S + WARMUP_S + WINDOW_S + RESULT_MARGIN_S,
        )
    finally:
        stop(process)
        log.close()
    # kept beside the run, for a run on the box itself to read after
    logs = server.root / "logs"
    logs.mkdir(exist_ok=True)
    shutil.copy(log_path, logs / log_path.name)
    return Opened(server.reports.get(tag), log_path.read_text(errors="replace"), irq_count() - irqs)


# Falkon's default for the camera on a site it has no setting for; 1 allows
FALKON_CAMERA_SETTING = "f_media_video_capture"
# where Falkon keeps a profile's AdBlock lists, under its profiles' directory
FALKON_ADBLOCK = Path("falkon/config/falkon/profiles/default/adblock")


def warm_falkon(server: Server, user: str, home: Path, falkon_root: Path | None) -> None:
    """Falkon once, until AdBlock's lists, EasyList with them, are compiled: a minute of a core on
    the H313, which would otherwise land in every play's measurement."""
    falkon = next(iter(browsers(home / "profiles-warm", falkon_root, frozenset({FALKON}))), None)
    if not falkon:
        return
    subprocess.run(["chown", "-R", user, str(home)], check=False)
    compiled = Path(falkon.env["XDG_CACHE_HOME"]) / "falkon/qtwpewebkit-content-filters"
    easylist = home / "profiles-warm" / FALKON_ADBLOCK / "easylist.txt"

    def easylist_compiled() -> bool:
        return easylist.exists() and any(
            c.stat().st_mtime > easylist.stat().st_mtime
            for c in compiled.glob("ContentRuleList-adblock-*")
        )

    open_page(
        server,
        user,
        home,
        falkon,
        "falkon-warm",
        "page.html",
        {},
        easylist_compiled,
    )


def play(server: Server, user: str, home: Path, browser: Browser, clip: Path, mse: bool) -> str:
    """One clip in one browser, as a file or through MSE: its report against the clip's rate, the
    engine's interrupts and the decoder WebKit made."""
    tag = f"{browser.name}-{clip.stem}{'-mse' if mse else ''}"
    query = {"src": f"clips/{clip.name}"}
    if mse:
        for part, type in MSE_TYPES[clip.stem.split("-", 1)[0]].items():
            query[part] = f"clips/mse/{mse_part(clip, part).name}"
            query[f"{part}type"] = type
    opened = open_page(server, user, home, browser, tag, "page.html", query)
    if opened.report is None:
        return f"failed: the page never reported; {last_line(opened.log)}"
    if "error" in opened.report:
        return f"failed: {opened.report['error']}"
    fps, media = float(opened.report["fps"]), float(opened.report["media"])
    decoders = "+".join(sorted(set(DECODER.findall(opened.log)))) or "decoder unknown"
    measured = f"{fps:.1f} fps, {media:.2f}x, {opened.report['size']}, {decoders}"
    if "decoded" in opened.report:
        measured += f", {float(opened.report['decoded']):.1f} decoded and "
        measured += f"{float(opened.report['dropped']):.1f} dropped a second"
    if "waits" in opened.report:
        measured += f", clock {float(opened.report['clock']):.2f}x"
        measured += f", {opened.report['waits']} waits for {float(opened.report['waited']):.1f} s"
    if not opened.engine_irqs:
        return f"failed: {measured}, but the video engine's interrupts did not move"
    if fps < clip_rate(clip) * PASS_SHARE or media < PASS_SHARE:
        return f"failed: {measured}"
    return f"pass: {measured}"


def call(server: Server, user: str, home: Path, browser: Browser, camera: bool) -> str:
    """A call in one browser, from a canvas or the box's camera: the frames it encodes and receives
    against the call's rate, its codec, and whether the encoder WebKit made runs on the box's
    encoder."""
    tag = f"{browser.name}-call{'-camera' if camera else ''}"
    opened = open_page(
        server, user, home, browser, tag, "call.html", {"camera": "1"} if camera else {}
    )
    if opened.report is None:
        return f"failed: the page never reported; {last_line(opened.log)}"
    if opened.report.get("error") == "no camera":
        return "UNTESTED: no camera"
    if "error" in opened.report:
        return f"failed: {opened.report['error']}"
    sent, received = float(opened.report["sent"]), float(opened.report["received"])
    codec = opened.report["codec"]
    encoders = sorted(set(ENCODER.findall(opened.log)))
    painted = float(opened.report.get("painted", 0))
    captured = float(opened.report.get("captured", -1))
    measured = f"painted {painted:.1f}, captured {captured:.1f}, sent {sent:.1f} fps, received {received:.1f} fps, {codec}, "
    measured += f"{opened.report.get('ice', '')}, "
    if camera:
        measured += f"camera {opened.report.get('source', 'unknown')}, "
    measured += (
        f"{'+'.join(encoders) or 'no GStreamer encoder'}, encoder {opened.report['encoder']}"
    )
    implementation = opened.report["encoder"].lower()
    on_box = any(e.startswith(HARDWARE_ENCODERS) for e in encoders) or not (
        any(name in implementation for name in SOFTWARE_ENCODERS)
    )
    if codec.lower() != "video/h264" or not on_box:
        return f"failed: {measured}, not H.264 from the box's encoder"
    if min(sent, received) < CALL_RATE * PASS_SHARE:
        return f"failed: {measured}"
    return f"pass: {measured}"


def last_line(log: str) -> str:
    lines = log.strip().splitlines()
    return lines[-1] if lines else "the browser printed nothing"


def stop(process: subprocess.Popen[bytes]) -> None:
    """The browser's whole session: the compositor, the bus and every process they started."""
    os.killpg(process.pid, signal.SIGTERM)
    try:
        process.wait(timeout=STOP_TIMEOUT_S)
    except subprocess.TimeoutExpired:
        os.killpg(process.pid, signal.SIGKILL)
        process.wait()


def check(
    run_dir: Path,
    only: str,
    names: frozenset[str],
    falkon_root: Path | None,
    user: str | None,
    demote: str,
    gst_debug: str,
    extra_env: str,
) -> Iterator[Line]:
    user = user or logged_in_user()
    if not user:
        yield "user", "UNTESTED: no --user, and nobody is logged into a session"
        return
    (run_dir / "page.html").write_text(PAGE)
    (run_dir / "call.html").write_text(CALL_PAGE)
    # WebKit's sandbox cannot map a directory under /var/tmp, which it links to /tmp
    home = Path(tempfile.mkdtemp(prefix="tvb-browser-"))
    try:
        yield from play_all(
            run_dir, home, user, only, names, falkon_root, demote, gst_debug, extra_env
        )
    finally:
        shutil.rmtree(home, ignore_errors=True)


def play_all(
    run_dir: Path,
    home: Path,
    user: str,
    only: str,
    names: frozenset[str],
    falkon_root: Path | None,
    demote: str,
    gst_debug: str,
    extra_env: str,
) -> Iterator[Line]:
    shutil.chown(home, user)
    if not browsers(home / "probe", falkon_root, names):
        yield "browsers", "UNTESTED: no browser installed"
        return
    server = Server(run_dir, demote, gst_debug, extra_env)
    warm_falkon(server, user, home, falkon_root)
    clips = sorted(
        c for c in (run_dir / "clips").iterdir() if c.is_file() and re.search(only, c.stem)
    )
    for clip in clips:
        for mse in (False, True):
            # a fresh profile each play: a killed browser restores its last session, a page that
            # would play beside the next
            profiles = home / f"profiles-{clip.stem}{'-mse' if mse else ''}"
            profiles.mkdir(exist_ok=True)
            # the warm profile's lists: the same text as compiled, not a download and a compile
            warm_lists = home / "profiles-warm" / FALKON_ADBLOCK
            if warm_lists.exists():
                shutil.copytree(warm_lists, profiles / FALKON_ADBLOCK, dirs_exist_ok=True)
            for browser in browsers(profiles, falkon_root, names):
                subprocess.run(["chown", "-R", user, str(profiles)], check=False)
                key = f"{browser.name}.{clip.stem}{'.mse' if mse else ''}"
                yield key, play(server, user, home, browser, clip, mse)
    for camera in (False, True):
        name = f"call{'-camera' if camera else ''}"
        if not re.search(only, name):
            continue
        profiles = home / f"profiles-{name}"
        profiles.mkdir(exist_ok=True)
        for browser in browsers(profiles, falkon_root, names):
            subprocess.run(["chown", "-R", user, str(profiles)], check=False)
            yield f"{browser.name}.{name}", call(server, user, home, browser, camera)


def on_box(args: argparse.Namespace) -> int:
    run_dir = Path(args.dir)
    os.chmod(run_dir, 0o755)
    failed = False
    names = frozenset(args.browsers.split(","))
    for key, result in check(
        run_dir,
        args.only,
        names,
        args.falkon_root,
        args.user,
        args.demote,
        args.gst_debug,
        args.env,
    ):
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
        command += f" --browsers {args.browsers}"
        if args.falkon_root:
            command += f" --falkon-root {args.falkon_root}"
        if args.user:
            command += f" --user {args.user}"
        if args.demote:
            command += f" --demote {args.demote}"
        if args.gst_debug:
            command += f" --gst-debug {args.gst_debug}"
        if args.env:
            command += f" --env {shlex.quote(args.env)}"
        returncode = remote(args.box, command).returncode
        logs = CLIPS.parent / "logs" / args.box.split("@")[-1]
        logs.mkdir(parents=True, exist_ok=True)
        fetched = subprocess.run(SSH + [args.box, f"tar -c -C {box_dir} logs"], capture_output=True)
        with tarfile.open(fileobj=io.BytesIO(fetched.stdout)) as tar:
            tar.extractall(logs.parent / "unpacked", filter="data")
        unpacked = logs.parent / "unpacked" / "logs"
        for log in unpacked.glob("*.log"):
            shutil.move(log, logs / log.name)
        shutil.rmtree(logs.parent / "unpacked", ignore_errors=True)
        return returncode
    finally:
        remote(args.box, f"rm -rf -- {box_dir}", timeout=60)


def browser_names(value: str) -> str:
    unknown = set(value.split(",")) - set(BROWSERS)
    if unknown:
        raise argparse.ArgumentTypeError(f"unknown browsers: {','.join(sorted(unknown))}")
    return value


def main() -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    sub = parser.add_subparsers(dest="cmd", required=True)
    for name in ("run", "box"):
        p = sub.add_parser(name)
        p.add_argument("--only", default="", help="a regex over <codec>-<size>, and call")
        p.add_argument(
            "--browsers",
            default=FALKON,
            type=browser_names,
            help=f"which play, comma-separated, of {','.join(BROWSERS)}; Falkon by default",
        )
        p.add_argument("--env", default="", help="KEY=VALUE,... given to every browser, to try one")
        p.add_argument(
            "--gst-debug", default="", help="GStreamer debug categories added for WebKit's browsers"
        )
        p.add_argument(
            "--demote",
            default="",
            help="GStreamer features ranked down for the run, as feature:NONE,...",
        )
        p.add_argument(
            "--falkon-root",
            type=Path,
            help="a Falkon build's install root on the box, its files under usr/; else the packaged",
        )
        p.add_argument("--user", help="who runs the browsers: by default, who is logged in")
    sub.choices["run"].add_argument("--box", required=True, help="the box, as ssh reaches it")
    sub.choices["box"].add_argument("--dir", required=True)
    args = parser.parse_args()
    return from_host(args) if args.cmd == "run" else on_box(args)


if __name__ == "__main__":
    sys.exit(main())
