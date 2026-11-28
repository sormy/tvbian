#!/usr/bin/env python3
"""The VA-API driver against Debian's own clients: decode, encode, surface calls.

In the build container, the CPU test engine behind an Xvfb display (./build.sh va-driver check):
    vaapi_test.py unit --driver-dir DIR   the C unit tests, then the rebuilds replayed
    vaapi_test.py host --driver-dir DIR
On a box, the family's engine behind its render node, with the clips made on the host:
    vaapi_test.py clips --out DIR
    vaapi_test.py box --driver-dir DIR --clips DIR [--driver-name tvb|v4l2_request]
        [--device /dev/dri/renderD128]

Every line is "key value"; "FAIL key" or "UNTESTED key" follows one whose check failed or could
not run, as tools/validate/box.py prints them. Python's standard library only.
"""

from __future__ import annotations

import argparse
import contextlib
import grp
import hashlib
import math
import os
import re
import resource
import shutil
import stat
import subprocess
import sys
import tempfile
import time
import urllib.request
from collections.abc import Callable, Iterator
from dataclasses import dataclass
from pathlib import Path

import headers

Line = tuple[str, str]
HERE = Path(__file__).resolve().parent
HOST_DISPLAY = ":9"
CASE_TIMEOUT = 120
FRAMES = 30
SIZE = "640x360"
# not a multiple of any block size: the crop and the padding both get exercised
ODD_SIZE = "642x362"
LOSSY_FLOOR_DB = 50.0
REPORT_PREFIX = "va."
# tvb-va-driver's udev link to the GPU's render node, and the node programs open unless told
VA_LINK = Path("/dev/dri/va")
DRIVER_SUFFIX = "_drv_video.so"
NOTHING_TO_TEST = 77  # the regression suite's exit status for a step this box cannot run
FIRST_RENDER_NODE = Path("/dev/dri/renderD128")
# where a desktop user's surfaces get their own memory, opened to this group by the udev rule
SYSTEM_HEAP = Path("/dev/dma_heap/system")
HEAP_GROUP = "video"
HEAP_MODE = 0o660
# the browsers' VA defaults the package ships, each with a setting it must carry
BROWSER_DEFAULTS = {
    Path("/usr/lib/firefox-esr/defaults/pref/tvb-va-driver.js"): "media.ffmpeg.vaapi.enabled",
    Path("/etc/chromium.d/tvb-va-driver"): "--hardware-video-device-path=/dev/dri/va",
}
# a width whose I420 rows GStreamer writes unpadded
RAW_WIDTH_MULTIPLE = 8
ENCODE_FLOOR_DB = 30.0
ENCODE_FRAMES = 30
JPEG_FRAMES = 5
MPV_USING = "Using hardware decoding (vaapi-copy)"
MPV_ZERO_COPY = "Using hardware decoding (vaapi)"
# Mesa's words for a dma-buf it will not import
GPU_REJECTED = "rejecting image"
# the desktop's compositor, run headless for a client that needs a display
COMPOSITOR = "labwc"
COMPOSITOR_START_S = 10
# per engine, the interrupts that prove the hardware decoded
ENGINE_IRQS = r"cedrus|vdpu|rkvdec|vdec|esparser|jpegd|video-codec"

X264 = ["-c:v", "libx264", "-preset", "veryfast"]
X265 = ["-c:v", "libx265", "-preset", "ultrafast", "-x265-params", "log-level=0"]
VPX9 = ["-c:v", "libvpx-vp9", "-deadline", "realtime", "-cpu-used", "8"]
VPX9_TOOLS = ["-c:v", "libvpx-vp9", "-deadline", "good", "-cpu-used", "4", "-b:v", "2M"]
VPX9_TOOLS += ["-auto-alt-ref", "1", "-lag-in-frames", "10", "-aq-mode", "3", "-tile-columns", "1"]
VPX8 = ["-c:v", "libvpx", "-deadline", "realtime", "-cpu-used", "8"]
MPEG2 = ["-c:v", "mpeg2video", "-q:v", "3", "-bf", "2"]
MPEG4 = ["-c:v", "mpeg4", "-q:v", "3"]
H263_SIZE = "352x288"
FATE = "https://fate-suite.ffmpeg.org/"
# up and down, as a site's player switches; widths whose I420 rows GStreamer writes unpadded, so
# its checksums meet FFmpeg's
SWITCH_SIZES = ("640x360", "1280x720", "640x360")


@dataclass(frozen=True)
class Clip:
    """A synthetic clip, the VA profile that decodes it, and whether it is 10-bit."""

    profile: str
    container: str
    encoder: list[str]
    size: str = SIZE
    ten_bit: bool = False
    frames: int = FRAMES
    # a FATE sample, its path in the suite and its SHA-256, in place of an encode
    fate: str = ""
    sha256: str = ""
    # sizes the clip changes to mid-stream, a key frame and its frames each: a context each in
    # FFmpeg, so its decode is judged, not its rebuilt headers or mapped controls
    switch: tuple[str, ...] = ()


CLIPS: dict[str, Clip] = {
    "h264-high": Clip("H264High", "mp4", X264 + ["-profile:v", "high", "-bf", "2"]),
    "h264-main-cavlc": Clip("H264Main", "mp4", X264 + ["-profile:v", "main", "-coder", "0"]),
    "h264-baseline": Clip("H264ConstrainedBaseline", "mp4", X264 + ["-profile:v", "baseline"]),
    "h264-slices": Clip("H264High", "mp4", X264 + ["-x264-params", "slices=4", "-bf", "3"]),
    "h264-weighted": Clip("H264High", "mp4", X264 + ["-x264-params", "weightb=1:weightp=2"]),
    "h264-scaling": Clip("H264High", "mp4", X264 + ["-x264-params", "cqm=jvt", "-bf", "2"]),
    "h264-mbaff": Clip(
        "H264High", "mp4", X264 + ["-flags", "+ildct+ilme", "-x264-params", "tff=1"]
    ),
    "h264-refs": Clip("H264High", "mp4", X264 + ["-refs", "6", "-bf", "3", "-b_strategy", "2"]),
    "h264-odd": Clip("H264High", "mp4", X264 + ["-bf", "2"], size=ODD_SIZE),
    "h264-high10": Clip(
        "H264High10", "mp4", X264 + ["-profile:v", "high10", "-bf", "2"], ten_bit=True
    ),
    "hevc-main": Clip("HEVCMain", "mp4", X265),
    "hevc-odd": Clip("HEVCMain", "mp4", X265, size=ODD_SIZE),
    "hevc-slices": Clip("HEVCMain", "mp4", X265[:-1] + ["log-level=0:slices=4"]),
    "hevc-scaling": Clip("HEVCMain", "mp4", X265[:-1] + ["log-level=0:scaling-list=default"]),
    "hevc-main10": Clip("HEVCMain10", "mp4", X265, ten_bit=True),
    "vp9-p0": Clip("VP9Profile0", "webm", VPX9),
    "vp9-odd": Clip("VP9Profile0", "webm", VPX9, size=ODD_SIZE),
    "vp9-p2": Clip("VP9Profile2", "webm", VPX9 + ["-profile:v", "2"], ten_bit=True),
    # hidden alt-refs, compound prediction, segmentation, two tile columns
    "vp9-tools": Clip("VP9Profile0", "webm", VPX9_TOOLS, size="1280x720"),
    "vp9-switch": Clip("VP9Profile0", "ivf", VPX9, switch=SWITCH_SIZES),
    "h264-switch": Clip("H264High", "h264", X264 + ["-bf", "2"], switch=SWITCH_SIZES),
    "hevc-switch": Clip("HEVCMain", "hevc", X265, switch=SWITCH_SIZES),
    "vp8": Clip("VP8Version0_3", "webm", VPX8),
    "vp8-odd": Clip("VP8Version0_3", "webm", VPX8, size=ODD_SIZE),
    "mpeg2": Clip("MPEG2Main", "mpg", MPEG2),
    "mpeg2-odd": Clip("MPEG2Main", "mpg", MPEG2, size=ODD_SIZE),
    "mpeg2-interlaced": Clip("MPEG2Main", "mpg", MPEG2 + ["-flags", "+ildct+ilme", "-top", "1"]),
    "jpeg": Clip(
        "JPEGBaseline", "avi", ["-c:v", "mjpeg", "-q:v", "3"], frames=JPEG_FRAMES, size=SIZE
    ),
    "mpeg4-sp": Clip("MPEG4Simple", "mp4", MPEG4),
    "mpeg4-odd": Clip("MPEG4Simple", "mp4", MPEG4, size=ODD_SIZE),
    # resync markers: video packets inside each VOP
    "mpeg4-packets": Clip("MPEG4Simple", "mp4", MPEG4 + ["-ps", "2000"]),
    "mpeg4-asp": Clip("MPEG4AdvancedSimple", "mp4", MPEG4 + ["-bf", "2", "-flags", "+qpel"]),
    "mpeg4-matrix": Clip("MPEG4AdvancedSimple", "mp4", MPEG4 + ["-bf", "1", "-mpeg_quant", "1"]),
    "mpeg4-interlaced": Clip(
        "MPEG4AdvancedSimple", "mp4", MPEG4 + ["-bf", "1", "-flags", "+ildct+ilme"]
    ),
    "h263": Clip("H263Baseline", "h263", ["-c:v", "h263", "-q:v", "3"], size=H263_SIZE),
    # GOB headers: each GOB a run of its own on Cedrus
    "h263-gobs": Clip(
        "H263Baseline", "h263", ["-c:v", "h263", "-q:v", "3", "-ps", "1000"], size=H263_SIZE
    ),
    "vc1-ap": Clip(
        "VC1Advanced",
        "vc1",
        [],
        fate="vc1/SA20021.vc1",
        sha256="99098ebb84a71b3a62d48988d79169843d73dbfd12c620961ab5f1973a9f1b05",
    ),
    "vc1-ap-slices": Clip(
        "VC1Advanced",
        "vc1",
        [],
        fate="vc1/SA10143.vc1",
        sha256="5d4a5dff66ca45f32331810fc7f845ab0600850a0ee97d05db32572bb588222e",
    ),
    "vc1-ap-interlaced": Clip(
        "VC1Advanced",
        "vc1",
        [],
        fate="vc1/ilaced_twomv.vc1",
        sha256="8052c6f2514d7b9e0e6322b4cde440a590cbf6c7e97487336eafa4145ba74d30",
    ),
    "vc1-main": Clip(
        "VC1Main",
        "rcv",
        [],
        fate="vc1/SMM0005.rcv",
        sha256="2de6e6efe960bb0d93b0bfc0229e0b3b1fcdca72eb4b3e290de5f24fafa456f9",
    ),
    "vc1-main-multires": Clip(
        "VC1Main",
        "rcv",
        [],
        fate="vc1/SMM0015.rcv",
        sha256="67baabd762ed35f70cd70c492e83e8744d068a5a567d9b19cc509851bf9f1d44",
    ),
}

# VA profile and entrypoint, the client's encoder, its output, its frame count
# an encoder takes the best of its codec's profiles the engine offers
H264_ENCODES = {f"H264{p}/EncSlice" for p in ("High", "Main", "ConstrainedBaseline")}
ENCODES: dict[str, tuple[set[str], str, str, int]] = {
    "h264": (H264_ENCODES, "h264_vaapi", "h264", ENCODE_FRAMES),
    "hevc": ({"HEVCMain/EncSlice"}, "hevc_vaapi", "hevc", ENCODE_FRAMES),
    "jpeg": ({"JPEGBaseline/EncPicture"}, "mjpeg_vaapi", "mjpeg", JPEG_FRAMES),
}
TEN_BIT_SURFACES = ["p010le", "nv12"]
# 10-bit clips a client that shows 8-bit alone turns to NV12 by video processing, as mpv does
VPP_CLIPS = ["hevc-main10", "vp9-p2"]
VPP_TO_NV12 = "scale_vaapi=format=nv12,hwdownload,format=nv12,"
# clips a family's engine may refuse, as MPP does: refused, or decoded right, never broken
REFUSED: dict[str, set[str]] = {
    "sunxi-h616": {"mpeg4-interlaced"},
    "rk35xx": {"mpeg2-interlaced", "mpeg4-interlaced"},
}
# clips whose last pictures a family's engine holds until more stream comes: FFmpeg's command line
# syncs each before sending the next, and the driver refuses what the drain cost its references.
# What comes out must be right.
HELD: dict[str, set[str]] = {
    "meson-gxl": {
        "mpeg2",
        "mpeg2-odd",
        "mpeg2-interlaced",
        "mpeg4-sp",
        "mpeg4-odd",
        "mpeg4-packets",
    }
    | {"mpeg4-asp", "mpeg4-matrix", "mpeg4-interlaced", "vc1-ap", "vc1-ap-slices"}
    | {"vc1-ap-interlaced"},
}
# FFmpeg's word that the VA hwaccel refused a stream or a picture
HWACCEL_REFUSED = re.compile(r"Failed to (end picture decode|create decode context)|hwaccel init")
# 4K clips each client decodes as fast as it can: frames a second and CPU time a frame, compared
# run to run by tools/validate/va_driver.py
SPEED_SIZE = "3840x2160"
# long enough that the engine's start-up, taken off, is small beside it
SPEED_FRAMES = 600
# the best of these: other work on a box only ever makes a run slower
SPEED_RUNS = 3
SPEED_CLIPS: dict[str, Clip] = {
    "speed-h264": Clip("H264High", "mp4", X264, size=SPEED_SIZE, frames=SPEED_FRAMES),
    "speed-hevc": Clip("HEVCMain", "mp4", X265, size=SPEED_SIZE, frames=SPEED_FRAMES),
    "speed-vp9": Clip("VP9Profile0", "webm", VPX9, size=SPEED_SIZE, frames=SPEED_FRAMES),
}
# GStreamer's va decoder for each VA profile family: it has none for MPEG-4, H.263 or VC-1
GST_DECODERS = {
    "H264": "vah264dec",
    "HEVC": "vah265dec",
    "VP9": "vavp9dec",
    "VP8": "vavp8dec",
    "MPEG2": "vampeg2dec",
    "JPEG": "vajpegdec",
    "AV1": "vaav1dec",
}
# GStreamer's va encoder and parser for each of ENCODES
GST_ENCODERS = {
    "h264": ("vah264enc", "h264parse"),
    "hevc": ("vah265enc", "h265parse"),
    "jpeg": ("vajpegenc", "jpegparse"),
}
# the clients the suite drives, and the Debian package each comes in
TOOLS = {
    "vainfo": "vainfo",
    "ffmpeg": "ffmpeg",
    "mpv": "mpv",
    "gst-launch-1.0": "gstreamer1.0-tools gstreamer1.0-plugins-bad",
}


@dataclass(frozen=True)
class Setup:
    """Where the driver is and how a client reaches it."""

    driver_dir: Path
    probe: Path
    driver_name: str
    family: str
    device: str
    clips: Path
    work: Path
    on_box: bool

    def env(self, named: bool = True) -> dict[str, str]:
        env = dict(os.environ)
        env["LIBVA_DRIVERS_PATH"] = str(self.driver_dir)
        env["LD_LIBRARY_PATH"] = str(self.driver_dir)
        if named:
            env["LIBVA_DRIVER_NAME"] = self.driver_name
        # GStreamer's va plugin loads only the drivers it knows unless told otherwise
        env["GST_VA_ALL_DRIVERS"] = "1"
        # a registry of its own: one cached by a crashing build holds the va plugin blacklisted
        env["GST_REGISTRY"] = str(self.work / "gst-registry.bin")
        if not self.on_box:
            env["VAAPI_ENGINE"] = "lavc"
            env["DISPLAY"] = self.device
        return env


def run(
    cmd: list[str], env: dict[str, str] | None = None, timeout: int = CASE_TIMEOUT
) -> tuple[int, str]:
    try:
        done = subprocess.run(
            cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, env=env, timeout=timeout
        )
    except subprocess.TimeoutExpired:
        return -1, "timed out"
    except FileNotFoundError:
        return -2, f"no {cmd[0]}"
    return done.returncode, done.stdout.decode(errors="replace")


def last_line(text: str) -> str:
    lines = [line for line in text.strip().splitlines() if line.strip()]
    return lines[-1][:160] if lines else "no output"


# clips


def make_clips(out: Path) -> Iterator[Line]:
    out.mkdir(parents=True, exist_ok=True)
    for name, clip in {**CLIPS, **SPEED_CLIPS}.items():
        path = out / f"{name}.{clip.container}"
        if path.exists():
            continue
        if clip.fate:
            yield f"clip.{name}", fetch(FATE + clip.fate, clip.sha256, path)
            continue
        if clip.switch:
            yield f"clip.{name}", make_switch(clip, path)
            continue
        pix_fmt = "yuv420p10le" if clip.ten_bit else "yuvj420p" if name == "jpeg" else "yuv420p"
        rc, log = run(
            ["ffmpeg", "-nostdin", "-v", "error", "-f", "lavfi"]
            + ["-i", f"testsrc2=size={clip.size}:rate=30", "-frames:v", str(clip.frames)]
            + ["-pix_fmt", pix_fmt]
            + clip.encoder
            + [str(path)]
        )
        yield f"clip.{name}", "made" if rc == 0 else f"failed: {last_line(log)}"


def make_switch(clip: Clip, path: Path) -> str:
    """Each size's frames encoded apart, a key frame first, then joined in one stream: IVF's
    frames, or a raw stream's bytes, each part opening with its own parameter sets."""
    frames: list[bytes] = []
    for i, size in enumerate(clip.switch):
        part = path.with_suffix(f".{i}.{clip.container}")
        rc, log = run(
            ["ffmpeg", "-nostdin", "-v", "error", "-y", "-f", "lavfi"]
            + ["-i", f"testsrc2=size={size}:rate=30", "-frames:v", str(clip.frames)]
            + ["-pix_fmt", "yuv420p"]
            + clip.encoder
            + [str(part)]
        )
        if rc != 0:
            return f"failed: {last_line(log)}"
        frames += ivf_frames(part) if clip.container == "ivf" else [part.read_bytes()]
        part.unlink()
    joined = ivf(frames, b"VP90", clip.switch[0]) if clip.container == "ivf" else b"".join(frames)
    path.write_bytes(joined)
    return "made"


def fetch(url: str, sha256: str, path: Path) -> str:
    try:
        with urllib.request.urlopen(url, timeout=CASE_TIMEOUT) as response:
            data = response.read()
    except OSError as error:
        return f"no clip: {url}: {error}"
    if hashlib.sha256(data).hexdigest() != sha256:
        return f"failed: {url} is not the sample pinned"
    path.write_bytes(data)
    return "made"


# vainfo


def offered(setup: Setup) -> tuple[set[str], str]:
    """The driver's profile/entrypoint pairs, as vainfo prints them."""
    rc, log = run(["vainfo"] + display_args(setup), env=setup.env())
    pairs = set(re.findall(r"VAProfile(\w+)\s*:\s*VAEntrypoint(\w+)", log))
    return {f"{profile}/{entrypoint}" for profile, entrypoint in pairs}, log


def display_args(setup: Setup) -> list[str]:
    if setup.on_box:
        return ["--display", "drm", "--device", setup.device]
    return ["--display", "x11"]


def vainfo(setup: Setup, offers: set[str], log: str) -> Iterator[Line]:
    vendor = re.search(r"Driver version: (.*)", log)
    yield "vainfo.vendor", vendor.group(1) if vendor else f"failed: {last_line(log)}"
    yield "vainfo.offers", " ".join(sorted(offers)) if offers else "failed: none"
    if setup.on_box:
        rc, by_node = run(["vainfo"] + display_args(setup), env=setup.env(named=False))
        found = re.search(r"Driver version: (.*)", by_node)
        yield "vainfo.by-node-name", (
            f"pass: {found.group(1)}" if found else f"failed: {last_line(by_node)}"
        )


def node_driver(node: Path) -> str:
    return Path(f"/sys/class/drm/{node.name}/device/driver").resolve().name


def node_case(setup: Setup) -> Iterator[Line]:
    """/dev/dri/va is the render node of the GPU the driver is named for, and the first one."""
    if not VA_LINK.is_symlink():
        yield "node.va-link", "failed: no /dev/dri/va: tvb-va-driver's udev rule did not run"
        return
    node = VA_LINK.resolve()
    driver = node_driver(node)
    # the build links the driver under its GPU's DRM name beside its own
    gpus = {p.name.removesuffix(DRIVER_SUFFIX) for p in setup.driver_dir.glob(f"*{DRIVER_SUFFIX}")}
    gpus.discard(setup.driver_name)
    if not node.name.startswith("renderD") or driver not in gpus:
        yield "node.va-link", f"failed: {node.name} is {driver}'s, not {' or '.join(sorted(gpus))}'s"
        return
    rc, log = run(["vainfo", "--display", "drm", "--device", str(VA_LINK)], env=setup.env(False))
    found = re.search(r"Driver version: (.*)", log)
    yield "node.va-link", (
        f"pass: {node.name}, {found.group(1)}" if found else (f"failed: {last_line(log)}")
    )
    first = FIRST_RENDER_NODE.resolve()
    yield "node.first-render", (
        "pass"
        if first == node
        else f"failed: {first.name} is {node_driver(first)}'s, a display driver's render node"
    )


def package_case() -> Iterator[Line]:
    """What the installed package sets up beside the driver: the heap, the browsers' defaults."""
    if not SYSTEM_HEAP.exists():
        yield "package.heap", "unsupported: no system heap"
    else:
        info = SYSTEM_HEAP.stat()
        group = grp.getgrgid(info.st_gid).gr_name
        mode = stat.S_IMODE(info.st_mode)
        yield "package.heap", (
            "pass"
            if group == HEAP_GROUP and mode & HEAP_MODE == HEAP_MODE
            else f"failed: {group} {mode:o}, not {HEAP_GROUP} {HEAP_MODE:o}"
        )
    for path, setting in BROWSER_DEFAULTS.items():
        key = f"package.{path.name}"
        if not path.exists():
            yield key, f"failed: no {path}"
        else:
            yield key, "pass" if setting in path.read_text() else f"failed: no {setting}"


# decode


def irq_count() -> int:
    with contextlib.suppress(OSError):
        lines = Path("/proc/interrupts").read_text().splitlines()
        return sum(
            sum(int(n) for n in line.split()[1:] if n.isdigit())
            for line in lines
            if re.search(ENGINE_IRQS, line)
        )
    return 0


def decode_args(setup: Setup) -> list[str]:
    return ["-hwaccel", "vaapi", "-hwaccel_output_format", "vaapi", "-hwaccel_device", setup.device]


def framemd5(cmd: list[str], env: dict[str, str]) -> tuple[list[str], str]:
    rc, out = run(cmd + ["-f", "framemd5", "-"], env=env)
    return re.findall(r"(?:\d+,\s*){5}([0-9a-f]{32})$", out, re.M), out


def refusal_case(setup: Setup, key: str, path: Path) -> Iterator[Line]:
    """A clip the engine cannot decode: the driver refuses it, and no picture comes out of it.

    Judged by the pictures out, not the engine's interrupts: other work on a shared box moves those.
    """
    frames, log = framemd5(
        ["ffmpeg", "-nostdin", "-hide_banner", "-v", "error"]
        + decode_args(setup)
        + ["-i", str(path)],
        setup.env(),
    )
    refused = HWACCEL_REFUSED.search(log)
    yield key, (
        "pass: refused"
        if refused and not frames
        else f"failed: {len(frames)} pictures out, {'refused' if refused else 'not refused'}"
    )


def psnr_y(setup: Setup, decoded: list[str], chain: str, clip: Path, sample: str) -> float | None:
    return psnr_and_log(setup, decoded, chain, clip, sample)[0]


def psnr_and_log(
    setup: Setup, decoded: list[str], chain: str, clip: Path, sample: str
) -> tuple[float | None, str]:
    """Luma PSNR of the decoded input, through the chain, against the clip's software decode."""
    # one timebase for both, as psnr pairs pictures by time and the inputs' timebases differ
    pace = "settb=AVTB,setpts=N"
    graph = f"[0:v]{chain}format={sample},{pace}[a];[1:v]format={sample},{pace}[b];[a][b]psnr"
    rc, log = run(
        ["ffmpeg", "-nostdin", "-hide_banner"]
        + decoded
        + ["-i", str(clip), "-filter_complex", graph, "-f", "null", "-"],
        env=setup.env(),
    )
    found = re.search(r"PSNR y:(inf|[\d.]+)", log)
    if not found:
        return None, log
    return float("inf") if found.group(1) == "inf" else float(found.group(1)), log


def decode_case(setup: Setup, name: str, clip: Clip, offers: set[str]) -> Iterator[Line]:
    path = setup.clips / f"{name}.{clip.container}"
    key = f"decode.{name}"
    if f"{clip.profile}/VLD" not in offers:
        yield key, "unoffered"
        return
    if not path.exists():
        yield key, "no clip"
        return
    if name in REFUSED.get(setup.family, set()):
        refusal = list(refusal_case(setup, key, path))
        if refusal[0][1] == "pass: refused":
            yield from refusal
            return
    if name in HELD.get(setup.family, set()):
        yield from held_case(setup, key, path)
        return
    sample = sample_format(clip)
    base = ["ffmpeg", "-nostdin", "-hide_banner", "-v", "error"]
    software = software_frames(setup, path, sample)
    irqs = irq_count()
    # a 10-bit config's surfaces are P010, or NV12 for a client that asks it
    hardware: list[str] = []
    log = download = ""
    for surface_format in TEN_BIT_SURFACES if clip.ten_bit else ["nv12"]:
        download = f"hwdownload,format={surface_format}"
        hardware, log = framemd5(
            base
            + decode_args(setup)
            + ["-i", str(path), "-vf", f"{download},format={sample}", "-noautoscale"],
            setup.env(),
        )
        if hardware:
            break
    engine_ran = not setup.on_box or irq_count() > irqs
    decoded = decode_args(setup) + ["-i", str(path)]
    yield key, judged(
        hardware,
        software,
        engine_ran,
        log,
        lambda: psnr_y(setup, decoded, f"{download},", path, sample),
    )


def sample_format(clip: Clip) -> str:
    return "yuv420p10le" if clip.ten_bit else "yuv420p"


def software_frames(setup: Setup, path: Path, sample: str) -> list[str]:
    # one thread, as the test engine runs: FFmpeg's MPEG-4 decoder predicts interlaced B-VOPs
    # otherwise when frame-threaded
    # -noautoscale: each picture at its own size, as a switch clip changes it
    frames, _ = framemd5(
        ["ffmpeg", "-nostdin", "-hide_banner", "-v", "error", "-threads", "1"]
        + ["-i", str(path), "-pix_fmt", sample, "-noautoscale"],
        setup.env(),
    )
    return frames


def vpp_case(setup: Setup, offers: set[str]) -> Iterator[Line]:
    """A 10-bit decode turned to NV12 on its surfaces, against the clip's software decode."""
    for name in VPP_CLIPS:
        clip = CLIPS[name]
        path = setup.clips / f"{name}.{clip.container}"
        key = f"vpp.{name}"
        if f"{clip.profile}/VLD" not in offers or "None/VideoProc" not in offers:
            yield key, "unoffered"
            continue
        decoded = decode_args(setup) + ["-i", str(path)]
        y, log = psnr_and_log(setup, decoded, VPP_TO_NV12, path, "yuv420p")
        if y is None:
            yield key, f"failed: {last_line(log)}"
        else:
            yield key, f"{'pass' if y >= LOSSY_FLOOR_DB else 'failed'}: Y PSNR {y} dB"


def judged(
    hardware: list[str],
    software: list[str],
    engine_ran: bool,
    log: str,
    psnr: Callable[[], float | None],
) -> str:
    """A decode's verdict: identical to software, or close enough by luma PSNR."""
    if not hardware:
        return f"failed: no frames: {last_line(log)}"
    if len(hardware) != len(software):
        return f"failed: {len(hardware)} of {len(software)} frames"
    if not engine_ran:
        return "failed: decoded, but the engine's interrupts did not move"
    if hardware == software:
        return f"pass: {len(hardware)} of {len(software)} identical"
    y = psnr()
    verdict = "pass" if y is not None and y >= LOSSY_FLOOR_DB else "failed"
    return f"{verdict}: {len(hardware)} frames, Y PSNR {y} dB"


def luma_by_pts(
    setup: Setup, decode: list[str], path: Path, chain: str, size: int
) -> dict[str, bytes]:
    """Each picture's luma, keyed by its timestamp, as showinfo saw it go out."""
    raw = setup.work / "luma.raw"
    raw.unlink(missing_ok=True)
    rc, log = run(
        ["ffmpeg", "-nostdin", "-hide_banner", "-v", "info"]
        + decode
        + [
            "-i",
            str(path),
            "-vf",
            f"{chain}format=gray,showinfo",
            "-f",
            "rawvideo",
            "-y",
            str(raw),
        ],
        env=setup.env(),
    )
    data = raw.read_bytes() if raw.exists() else b""
    stamps = re.findall(r"\bn:\s*\d+\s+pts:\s*(-?\d+)", log)
    return {pts: data[i * size : (i + 1) * size] for i, pts in enumerate(stamps)}


def luma_psnr(a: bytes, b: bytes) -> float:
    squares = sum((x - y) * (x - y) for x, y in zip(a, b))
    return float("inf") if not squares else 10 * math.log10(255 * 255 * len(a) / squares)


def held_case(setup: Setup, key: str, path: Path) -> Iterator[Line]:
    rc, probe = run(
        ["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries", "stream=width,height"]
        + ["-of", "csv=s=x:p=0", str(path)]
    )
    size = re.search(r"(\d+)x(\d+)", probe)
    if not size:
        yield key, f"failed: no size from ffprobe: {last_line(probe)}"
        return
    width, height = int(size.group(1)), int(size.group(2))
    software = luma_by_pts(setup, ["-threads", "1"], path, "", width * height)
    hardware = luma_by_pts(
        setup, decode_args(setup), path, "hwdownload,format=nv12,", width * height
    )
    if not hardware:
        yield key, "failed: no frames"
        return
    unknown = [pts for pts in hardware if pts not in software]
    if unknown:
        yield key, f"failed: pictures at {unknown[:4]} that software never shows"
        return
    worst = min(luma_psnr(hardware[pts], software[pts]) for pts in hardware)
    verdict = "pass" if worst >= LOSSY_FLOOR_DB else "failed"
    yield key, (
        f"{verdict}: {len(hardware)} of {len(software)} out, the rest refused; "
        f"worst Y PSNR {worst:.1f} dB"
    )


# encode


def encode_case(setup: Setup, name: str, offers: set[str], rate: list[str]) -> Iterator[Line]:
    wanted, encoder, extension, frames = ENCODES[name]
    key = f"encode.{name}{'.cbr' if rate else ''}"
    if not wanted & offers:
        yield key, "unoffered"
        return
    out = setup.work / f"{name}{'-cbr' if rate else ''}.{extension}"
    source = f"testsrc2=size={SIZE}:rate=30"
    rc, log = run(
        ["ffmpeg", "-nostdin", "-hide_banner", "-v", "error", "-y"]
        + ["-init_hw_device", f"vaapi=va:{setup.device}", "-filter_hw_device", "va"]
        + ["-f", "lavfi", "-i", source, "-frames:v", str(frames)]
        + ["-vf", "format=nv12,hwupload", "-c:v", encoder]
        + rate
        + [str(out)],
        env=setup.env(),
    )
    if rc != 0 and "RC mode" in log:
        yield key, "unoffered: the engine takes no such rate control"
        return
    if rc != 0 or not out.exists():
        yield key, f"failed: {last_line(log)}"
        return
    count, y = compare_with_source(out, source, frames, setup.work)
    passed = count == frames and y >= ENCODE_FLOOR_DB
    verdict = "pass" if passed else "failed"
    yield key, f"{verdict}: {count} of {frames} frames, Y PSNR {y} dB, {out.stat().st_size} bytes"
    rc, size = run(
        ["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries", "stream=width,height"]
        + ["-of", "csv=p=0:s=x", str(out)]
    )
    size = size.strip()
    yield f"{key}.size", "pass: " + size if size == SIZE else f"failed: {size}, asked {SIZE}"


def compare_with_source(encoded: Path, source: str, frames: int, work: Path) -> tuple[int, float]:
    """Frames decoded back, and their luma PSNR against the source, both as raw pictures."""
    decoded, original = work / "decoded.yuv", work / "original.yuv"
    raw = ["-pix_fmt", "yuv420p", "-f", "rawvideo", "-y"]
    width, height = (int(n) for n in SIZE.split("x"))
    crop = ["-vf", f"crop={width}:{height}:0:0"]
    run(["ffmpeg", "-nostdin", "-v", "error", "-i", str(encoded)] + crop + raw + [str(decoded)])
    run(
        ["ffmpeg", "-nostdin", "-v", "error", "-f", "lavfi", "-i", source]
        + ["-frames:v", str(frames)]
        + raw
        + [str(original)]
    )
    count = decoded.stat().st_size // (width * height * 3 // 2) if decoded.exists() else 0
    yuv = ["-f", "rawvideo", "-pix_fmt", "yuv420p", "-s", SIZE]
    rc, log = run(
        ["ffmpeg", "-nostdin", "-hide_banner"]
        + yuv
        + ["-i", str(decoded)]
        + yuv
        + ["-i", str(original), "-filter_complex", "psnr", "-f", "null", "-"]
    )
    found = re.search(r"PSNR y:([\d.]+|inf)", log)
    return count, (
        float("inf")
        if found and found.group(1) == "inf"
        else float(found.group(1)) if found else 0.0
    )


# clients


@contextlib.contextmanager
def headless_wayland() -> Iterator[dict[str, str] | None]:
    """A headless labwc, the desktop's compositor, and the environment a client needs to reach it;
    None where labwc is not installed or does not come up."""
    if not shutil.which(COMPOSITOR):
        yield None
        return
    with tempfile.TemporaryDirectory(prefix="tvb-wayland-") as runtime:
        os.chmod(runtime, 0o700)
        env = dict(os.environ, XDG_RUNTIME_DIR=runtime, WLR_BACKENDS="headless")
        compositor = subprocess.Popen(
            [COMPOSITOR, "-s", "true"],
            env=env,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        try:
            deadline = time.monotonic() + COMPOSITOR_START_S
            while time.monotonic() < deadline and not list(Path(runtime).glob("wayland-[0-9]")):
                time.sleep(0.1)
            sockets = sorted(p.name for p in Path(runtime).glob("wayland-[0-9]"))
            yield dict(XDG_RUNTIME_DIR=runtime, WAYLAND_DISPLAY=sockets[0]) if sockets else None
        finally:
            compositor.terminate()
            compositor.wait()


def mpv_case(setup: Setup, offers: set[str]) -> Iterator[Line]:
    clip = setup.clips / "h264-high.mp4"
    if "H264High/VLD" not in offers:
        yield "mpv.vaapi-copy", "unoffered"
        return
    device = [f"--vaapi-device={setup.device}"] if setup.on_box else []
    rc, log = run(
        ["mpv", "--no-config", "--vo=null", "--ao=null", "--hwdec=vaapi-copy"]
        + device
        + [str(clip)],
        env=setup.env(),
    )
    yield "mpv.vaapi-copy", "pass" if rc == 0 and MPV_USING in log else f"failed: {last_line(log)}"
    if not setup.on_box:
        return
    with headless_wayland() as wayland:
        if wayland is None:
            yield "mpv.vaapi", f"not run: no {COMPOSITOR} to show it on"
            return
        # an odd size: Cedrus pads its rows to a pitch the GPU may not import
        rc, log = run(
            [
                "mpv",
                "--no-config",
                "--hwdec=vaapi",
                "--vo=gpu",
                "--gpu-context=wayland",
                "--ao=null",
            ]
            + ["-v", str(setup.clips / "h264-odd.mp4")],
            env=dict(setup.env(), **wayland),
        )
    rejected = log.count(GPU_REJECTED)
    if rc != 0 or MPV_ZERO_COPY not in log:
        yield "mpv.vaapi", f"failed: {last_line(log)}"
    else:
        yield "mpv.vaapi", (
            "pass" if not rejected else f"failed: the GPU refused {rejected} pictures"
        )


def gst_element(setup: Setup, element: str) -> bool:
    rc, _ = run(["gst-inspect-1.0", element], env=setup.env())
    return rc == 0


# GStreamer's word that a plugin crashed while it registered its elements, so it lists none
GST_PLUGIN_CRASHED = re.compile(r"segmentation fault|blacklisted", re.I)


def gst_plugin_case(setup: Setup) -> Iterator[Line]:
    """GStreamer's va plugin loads with the driver: a crash in its probe hides every element."""
    rc, log = run(["gst-inspect-1.0", "va"], env=setup.env())
    crashed = GST_PLUGIN_CRASHED.search(log)
    yield "gstreamer.va-plugin", f"failed: {crashed.group(0)}" if crashed else "pass"


def gst_decoder(profile: str) -> str | None:
    return next((e for family, e in GST_DECODERS.items() if profile.startswith(family)), None)


def gstreamer_decode_case(setup: Setup, name: str, clip: Clip, offers: set[str]) -> Iterator[Line]:
    """A clip through GStreamer's va decoder, against the same software decode as FFmpeg's."""
    key = f"gstreamer.{name}"
    path = setup.clips / f"{name}.{clip.container}"
    element = gst_decoder(clip.profile)
    if f"{clip.profile}/VLD" not in offers:
        yield key, "unoffered"
        return
    if element is None:
        yield key, "unoffered by GStreamer's va"
        return
    if not gst_element(setup, element):
        yield key, f"no {element}: GStreamer's va lists a driver only on a DRM render node"
        return
    if not path.exists():
        yield key, "no clip"
        return
    if clip.switch:
        yield key, gstreamer_switch(setup, element, path)
        return
    sample = sample_format(clip)
    # GStreamer pads I420 rows to 4 bytes, so raw frames are packed at a width of a multiple of 8;
    # y4menc packs the others, 8-bit progressive alone as FFmpeg reads it
    raw = int(clip.size.split("x")[0]) % RAW_WIDTH_MULTIPLE == 0
    out = setup.work / f"gst-{name}.{'yuv' if raw else 'y4m'}"
    caps = f"video/x-raw,format={'I420_10LE' if clip.ten_bit else 'I420'}"
    sink = ["filesink", f"location={out}"]
    tail = [caps, "!"] + (sink if raw else ["y4menc", "!"] + sink)
    out.unlink(missing_ok=True)
    irqs = irq_count()
    rc, log = run(
        ["gst-launch-1.0", "-q", "filesrc", f"location={path}", "!", "parsebin", "!"]
        + [element, "!", "videoconvert", "!"]
        + tail,
        env=setup.env(),
    )
    engine_ran = not setup.on_box or irq_count() > irqs
    # raw frames carry no range: a JPEG's are full, as FFmpeg reads the clip's
    written = "yuvj420p" if clip.profile.startswith("JPEG") else sample
    decoded = (
        ["-f", "rawvideo", "-pix_fmt", written, "-s", clip.size, "-i", str(out)]
        if raw
        else ["-i", str(out)]
    )
    hardware: list[str] = []
    if rc == 0 and out.exists() and out.stat().st_size:
        hardware, _ = framemd5(
            ["ffmpeg", "-nostdin", "-hide_banner", "-v", "error"] + decoded + ["-pix_fmt", sample],
            setup.env(),
        )
    if name in REFUSED.get(setup.family, set()) and not hardware:
        yield key, "pass: refused"
        return
    software = software_frames(setup, path, sample)
    yield key, judged(
        hardware, software, engine_ran, log, lambda: psnr_y(setup, decoded, "", path, sample)
    )


def gst_checksums(setup: Setup, decoder: str, path: Path) -> tuple[list[str], str]:
    """Each picture's MD5, at its own size, as the decoder hands it out: FFmpeg's framemd5's."""
    rc, log = run(
        ["gst-launch-1.0", "-q", "filesrc", f"location={path}", "!", "parsebin", "!", decoder]
        + ["!", "videoconvert", "!", "video/x-raw,format=I420", "!", "checksumsink", "hash=md5"],
        env=setup.env(),
    )
    return re.findall(r"\b([0-9a-f]{32})\b", log), log


def gstreamer_switch(setup: Setup, element: str, path: Path) -> str:
    """A size change mid-stream: the va decoder's pictures against FFmpeg's software decode."""
    software = software_frames(setup, path, "yuv420p")
    irqs = irq_count()
    hardware, log = gst_checksums(setup, element, path)
    engine_ran = not setup.on_box or irq_count() > irqs
    if not hardware:
        return f"failed: no frames: {last_line(log)}"
    if len(hardware) != len(software):
        return f"failed: {len(hardware)} of {len(software)} frames"
    if not engine_ran:
        return "failed: decoded, but the engine's interrupts did not move"
    differ = sum(h != s for h, s in zip(hardware, software))
    return f"pass: {len(hardware)} identical" if not differ else f"failed: {differ} frames differ"


def gstreamer_encode_case(setup: Setup, name: str, offers: set[str]) -> Iterator[Line]:
    """testsrc2 through GStreamer's va encoder, decoded back by FFmpeg against its source."""
    wanted, _, _, frames = ENCODES[name]
    element, parser = GST_ENCODERS[name]
    key = f"gstreamer.encode.{name}"
    if not wanted & offers:
        yield key, "unoffered"
        return
    if not gst_element(setup, element):
        yield key, f"no {element}: none listed for this driver"
        return
    source = f"testsrc2=size={SIZE}:rate=30"
    raw, out = setup.work / "gst-source.yuv", setup.work / f"gst-{name}.mkv"
    run(
        ["ffmpeg", "-nostdin", "-v", "error", "-y", "-f", "lavfi", "-i", source]
        + ["-frames:v", str(frames), "-pix_fmt", "nv12", "-f", "rawvideo", str(raw)]
    )
    width, height = SIZE.split("x")
    out.unlink(missing_ok=True)
    rc, log = run(
        ["gst-launch-1.0", "-q", "filesrc", f"location={raw}", "!", "rawvideoparse"]
        + [f"width={width}", f"height={height}", "format=nv12", "framerate=30/1", "!"]
        + [element, "!", parser, "!", "matroskamux", "!", "filesink", f"location={out}"],
        env=setup.env(),
    )
    if rc != 0 or not out.exists():
        yield key, f"failed: {last_line(log)}"
        return
    count, y = compare_with_source(out, source, frames, setup.work)
    passed = count == frames and y >= ENCODE_FLOOR_DB
    verdict = "pass" if passed else "failed"
    yield key, f"{verdict}: {count} of {frames} frames, Y PSNR {y} dB, {out.stat().st_size} bytes"


def child_cpu_s() -> float:
    usage = resource.getrusage(resource.RUSAGE_CHILDREN)
    return usage.ru_utime + usage.ru_stime


def timed(cmd: list[str], env: dict[str, str]) -> tuple[int, str, float, float]:
    """A command's exit, its log, and its wall and CPU seconds, its children's included."""
    cpu, start = child_cpu_s(), time.monotonic()
    rc, log = run(cmd, env=env)
    return rc, log, time.monotonic() - start, child_cpu_s() - cpu


def speed(whole: list[str], first: list[str], frames: int, env: dict[str, str]) -> str:
    """The best rate past start-up: the whole clip's cost less its first picture's."""
    best: tuple[float, float] | None = None
    for _ in range(SPEED_RUNS):
        rc, log, wall, cpu = timed(whole, env)
        if rc != 0:
            return f"failed: {last_line(log)}"
        rc, log, start_wall, start_cpu = timed(first, env)
        if rc != 0:
            return f"failed: one picture: {last_line(log)}"
        decoded = frames - 1
        run = (decoded / (wall - start_wall), (cpu - start_cpu) / decoded * 1000)
        best = run if best is None or run[0] > best[0] else best
    assert best is not None
    return f"pass: {best[0]:.1f} fps, {best[1]:.2f} ms CPU a frame"


def speed_case(setup: Setup, name: str, clip: Clip, offers: set[str]) -> Iterator[Line]:
    """Each client decodes the clip to nothing, as fast as the engine and the copies let it."""
    path = setup.clips / f"{name}.{clip.container}"
    codec = name.removeprefix("speed-")
    if f"{clip.profile}/VLD" not in offers:
        yield f"speed.ffmpeg.{codec}", "unoffered"
        yield f"speed.gstreamer.{codec}", "unoffered"
        return
    if not path.exists():
        yield f"speed.ffmpeg.{codec}", "no clip"
        return
    ffmpeg = ["ffmpeg", "-nostdin", "-v", "error"] + decode_args(setup) + ["-i", str(path)]
    yield f"speed.ffmpeg.{codec}", speed(
        ffmpeg + ["-f", "null", "-"],
        ffmpeg + ["-frames:v", "1", "-f", "null", "-"],
        clip.frames,
        setup.env(),
    )
    element = gst_decoder(clip.profile)
    if element is None or not gst_element(setup, element):
        yield f"speed.gstreamer.{codec}", "not run: no GStreamer va decoder for it"
        return
    gst = ["gst-launch-1.0", "-q", "filesrc", f"location={path}", "!", "parsebin", "!", element]
    sink = ["!", "fakesink", "sync=false"]
    yield f"speed.gstreamer.{codec}", speed(
        gst + sink, gst + ["!", "identity", "eos-after=1"] + sink, clip.frames, setup.env()
    )


def probe_case(setup: Setup) -> Iterator[Line]:
    if not setup.probe.exists():
        yield "probe.initialize", f"no {setup.probe}"
        return
    rc, log = run([str(setup.probe), setup.device], env=setup.env())
    for line in log.splitlines():
        key, _, value = line.partition(" ")
        if key.startswith("probe."):
            yield key, value


# the Cedrus mapping: its controls, written out on the host, against FFmpeg's own parse

TRACE_ELEMENT = re.compile(r"\]\s+(\d+)\s+(\S+)\s+([01]+) = (-?\d+)$")
# per picture or per slice, in decode order; the rest once per sequence, compared as a set
MAPPED_SEQUENCES = {
    "first_mb_in_slice",
    "slice_type",
    "idr_pic_id",
    "pic_order_cnt_lsb",
    "slice_qp_delta",
    "disable_deblocking_filter_idc",
    "header_bit_size",
    "picture_coding_type",
    "intra_dc_precision",
    "picture_structure",
    "f_code[0][0]",
    "f_code[1][1]",
    "alternate_scan",
    "slice_segment_address",
    "slice_pic_order_cnt_lsb",
    "collocated_ref_idx",
    "num_entry_point_offsets",
    "entry_point_offset_minus1",
    "frame_type",
    "first_part_size",
    "show_frame",
    "base_q_idx",
    "loop_filter_level",
    "loop_filter_sharpness",
    "header_size_in_bytes",
    "frame_context_idx",
    "refresh_frame_context",
    "segmentation_enabled",
    "PTYPE",
    "PQINDEX",
    "vop_coding_type",
    "intra_dc_vlc_thr",
    "vop_fcode_forward",
    "macroblock_number",
    "quant_scale",
}
SLICE_DATA_ELEMENTS = {"cabac_alignment_one_bit"}
# what Cedrus decodes through the request API: VC-1's Main profile it refuses
MAPPED_PROFILES = (
    "H264", "HEVC", "VP8", "VP9", "MPEG2", "MPEG4", "H263", "VC1Advanced", "VC1Simple",
)  # fmt: skip
H264_SLICE_TYPES = 5


def trace(clip: Path) -> dict[str, list[int]]:
    """FFmpeg's parse of the clip's headers; a slice header's end as header_bit_size."""
    rc, log = run(
        ["ffmpeg", "-nostdin", "-v", "debug", "-i", str(clip), "-c", "copy"]
        + ["-bsf:v", "trace_headers", "-f", "null", "-"]
    )
    values: dict[str, list[int]] = {}
    slice_end = -1
    for line in log.splitlines():
        if "Slice Header" in line or "Packet:" in line:
            if slice_end >= 0:
                values.setdefault("header_bit_size", []).append(slice_end)
            slice_end = 0 if "Slice Header" in line else -1
            continue
        found = TRACE_ELEMENT.search(line)
        if not found:
            continue
        position, name, bits, value = found.groups()
        # one list for every slice's entry points, as the controls carry them
        name = re.sub(r"^(entry_point_offset_minus1)\[\d+\]$", r"\1", name)
        if slice_end >= 0 and name not in SLICE_DATA_ELEMENTS:
            slice_end = max(slice_end, int(position) + len(bits))
        number = int(value) % H264_SLICE_TYPES if name == "slice_type" else int(value)
        values.setdefault(name, []).append(number)
    if slice_end >= 0:
        values.setdefault("header_bit_size", []).append(slice_end)
    return values


def mapping_case(setup: Setup, name: str, clip: Clip) -> Iterator[Line]:
    key = f"mapping.{name}"
    path = setup.clips / f"{name}.{clip.container}"
    dump = setup.work / f"{name}.controls"
    env = dict(setup.env(), VAAPI_ENGINE="v4l2-request", VAAPI_REQUEST_DUMP=str(dump))
    run(
        ["ffmpeg", "-nostdin", "-v", "error"]
        + decode_args(setup)
        + ["-i", str(path), "-f", "null", "-"],
        env=env,
    )
    ours: dict[str, list[int]] = {}
    if dump.exists():
        for line in dump.read_text().splitlines():
            _, field, value = line.split()
            ours.setdefault(field, []).append(int(value))
    if not ours and name in REFUSED["sunxi-h616"]:
        yield key, "pass: refused"
        return
    if not ours:
        yield key, "failed: the request backend wrote no controls"
        return
    reference = (
        parsed_reference(setup, name, clip)
        if clip.profile.startswith(tuple(PARSED_OTHERWISE))
        else trace(path)
    )
    if reference is None:
        yield key, "not run: interlaced, pan-scan or postprocessed pictures, which headers.py does not read"
        return
    for field, values in sorted(ours.items()):
        if field not in reference:
            continue
        expected = reference[field]
        same = values == expected if field in MAPPED_SEQUENCES else set(values) == set(expected)
        if not same:
            yield key, f"failed: {field} {values[:8]} against FFmpeg's {expected[:8]}"
            return
    compared = sorted(field for field in ours if field in reference)
    yield key, f"pass: {len(compared)} fields: {' '.join(compared)}"


def parsed_reference(setup: Setup, name: str, clip: Clip) -> dict[str, list[int]] | None:
    """What headers.py reads from the clip's elementary stream for the codecs FFmpeg cannot trace."""
    path = setup.clips / f"{name}.{clip.container}"
    if clip.profile.startswith("VC1"):
        return headers.vc1_mapping(path.read_bytes())
    codec = "MPEG4" if clip.profile.startswith("MPEG4") else "H263"
    muxer, _, bsf = ELEMENTARY[codec]
    elementary = setup.work / f"{name}.elementary"
    run(
        ["ffmpeg", "-nostdin", "-v", "error", "-y", "-i", str(path), "-c:v", "copy"]
        + bsf
        + ["-f", muxer, str(elementary)]
    )
    data = elementary.read_bytes() if elementary.exists() else b""
    return headers.mpeg4_mapping(data) if codec == "MPEG4" else headers.h263_mapping(data)


# the rebuilds, replayed from captures under the sanitizers, against the clips' own headers

# the clip's elementary stream as the rebuild writes it: muxer, its demuxer, bitstream filter
ELEMENTARY = {
    "H264": ("h264", "h264", ["-bsf:v", "h264_mp4toannexb"]),
    "HEVC": ("hevc", "hevc", ["-bsf:v", "hevc_mp4toannexb"]),
    "VP9": ("ivf", "ivf", ["-bsf:v", "vp9_superframe_split"]),
    "VP8": ("ivf", "ivf", []),
    "MPEG2": ("mpeg2video", "mpegvideo", []),
    "JPEG": ("mjpeg", "mjpeg", []),
    # FFmpeg cannot trace these: headers.py parses the clip itself
    # the VOL from the MP4's extradata ahead of each I-VOP
    "MPEG4": ("m4v", "m4v", ["-bsf:v", "dump_extra=freq=keyframe"]),
    "H263": ("h263", "h263", []),
    "VC1": ("vc1", "vc1", []),
}
# units a rebuild has no reason to carry
UNCARRIED_UNITS = re.compile(
    r"Supplemental|SEI|Access Unit Delimiter|Group of Pictures|User Data|Picture Timing"
    r"|Buffering Period|Recovery Point|Application Data"
)
# elements a profile's syntax leaves out, read as their inferred values
INFERRED = {
    "chroma_format_idc": 1,
    "bit_depth_luma_minus8": 0,
    "bit_depth_chroma_minus8": 0,
    "qpprime_y_zero_transform_bypass_flag": 0,
    "seq_scaling_matrix_present_flag": 0,
    "transform_8x8_mode_flag": 0,
    "pic_scaling_matrix_present_flag": 0,
    "deblocking_filter_override_enabled_flag": 0,
    "pps_deblocking_filter_disabled_flag": 0,
    "pps_beta_offset_div2": 0,
    "pps_tc_offset_div2": 0,
}
# what a rebuild writes otherwise, and why; every other element must match the clip's
REBUILT_OTHERWISE = {
    # High or High 10, level 5.1, one SPS; no cropping: VA has none, the client crops
    "H264": r"profile_idc|constraint_set\d_flag|reserved_zero_2bits|level_idc"
    r"|rbsp_stop_one_bit|rbsp_alignment_zero_bit"
    # VA gives the effective matrices: written out in the PPS, where the clip may fall back
    r"|seq_scaling_\w+|pic_scaling_\w+|delta_scale|second_chroma_qp_index_offset"
    # learned from the first inter slice: the IDR's PPS carries 0 until one comes
    r"|num_ref_idx_l[01]_default_active_minus1"
    r"|seq_parameter_set_id|frame_cropping_flag|frame_crop_\w+_offset"
    # the VUI: a reorder depth of 0 alone
    r"|vui_\w+|aspect_ratio\w*|sar_\w+|overscan\w*|video_signal\w*|video_format|video_full_range_flag"
    r"|colour_\w+|color_\w+|transfer_characteristics|matrix_coefficients|chroma_loc\w+"
    r"|chroma_sample_loc\w+|timing_info_present_flag|num_units_in_tick|time_scale"
    r"|fixed_frame_rate_flag|\w+_hrd_parameters_present_flag|pic_struct_present_flag"
    r"|bitstream_restriction_flag|motion_vectors_over_pic_boundaries_flag|max_bytes_per_pic_denom"
    r"|max_bits_per_mb_denom|log2_max_mv_length_\w+|max_num_reorder_frames|max_dec_frame_buffering"
    # SEI the rebuild has no use for
    r"|last_payload_\w+|payload_\w+|uuid_iso_iec_11578|user_data_\w+|sei_\w+",
    # VA has no deblocking_filter_control_present_flag: always 1, with VA's override and disable
    "HEVC": r"rbsp_stop_one_bit|rbsp_alignment_zero_bit|deblocking_filter_control_present_flag"
    # VA gives the effective lists: written out, where the clip may use the defaults
    r"|\w+_scaling_list_data_present_flag|scaling_list_\w+"
    r"|general_\w+|sub_layer_\w+|vps_\w+|sps_video_parameter_set_id|conformance_window_flag"
    r"|conf_win_\w+_offset|vui_\w+|sps_max_num_reorder_pics\[\d+\]|sps_max_latency_increase_plus1\[\d+\]"
    r"|sps_max_dec_pic_buffering_minus1\[\d+\]|sps_sub_layer_ordering_info_present_flag"
    r"|sps_extension_\w+|pps_extension_\w+|aspect_ratio\w*|sar_\w+|overscan\w*|video_\w+"
    r"|colour_\w+|transfer_characteristics|matrix_coeffs|chroma_loc\w+|chroma_sample_loc\w+"
    r"|neutral_chroma_indication_flag|field_seq_flag|frame_field_info_present_flag"
    r"|default_display_window_flag|bitstream_restriction_flag|\w+_hrd_parameters_present_flag"
    r"|last_payload_\w+|payload_\w+|uuid_iso_iec_11578|user_data_\w+|sei_\w+"
    # short-term sets carried inline in each slice, as VA gives them
    r"|num_short_term_ref_pic_sets|short_term_ref_pic_set_sps_flag|short_term_ref_pic_set_idx"
    r"|inter_ref_pic_set_prediction_flag|delta_idx_minus1|delta_rps_sign|abs_delta_rps_minus1"
    r"|used_by_curr_pic_flag|use_delta_flag|num_negative_pics|num_positive_pics"
    r"|delta_poc_s\d_minus1|used_by_curr_pic_s\d_flag",
    "VP9": r"$^",
    "VP8": r"$^",
    # a 25 Hz Main@High sequence of unknown rate, interlace allowed, low delay; no GOPs
    "MPEG2": r"aspect_ratio_information|frame_rate_code|bit_rate_value|bit_rate_extension"
    r"|vbv_buffer_size_\w+|vbv_delay|constrained_parameters_flag|profile_and_level_indication"
    r"|progressive_sequence|low_delay|frame_rate_extension_\w+|temporal_reference"
    r"|time_code|closed_gop|broken_link|marker_bit|load_\w+_quantiser_matrix|extra_bit_picture"
    r"|full_pel_\w+|\w+_f_code|chroma_420_type|composite_display_flag|user_data\w*"
    r"|video_format|colour_\w+|transfer_characteristics|matrix_coefficients"
    r"|display_\w+_size|sequence_display_extension\w*"
    # VA always loads the luma matrices, the defaults included
    r"|intra_quantiser_matrix|non_intra_quantiser_matrix|extension_start_code_identifier",
    # a DQT and DHT a table: the segment lengths
    "JPEG": r"Lq|Lh|Lp|Ap|Lc|Cm",
}
PARAMETER_UNITS = re.compile(r"Parameter Set|Sequence|Extension|Huffman|Quantization|Frame Header")


def trace_units(
    stream: Path, demuxer: list[str]
) -> tuple[dict[str, list[int]], dict[str, set[int]]]:
    """FFmpeg's parse: per-picture elements in order, parameter-set elements as sets."""
    rc, log = run(
        ["ffmpeg", "-nostdin", "-v", "debug"]
        + demuxer
        + ["-i", str(stream), "-c", "copy", "-bsf:v", "trace_headers", "-f", "null", "-"]
    )
    pictures: dict[str, list[int]] = {}
    parameters: dict[str, set[int]] = {}
    in_parameters = skipped = False
    for line in log.splitlines():
        if "[trace_headers" not in line:
            continue
        found = TRACE_ELEMENT.search(line)
        if not found:
            in_parameters = bool(PARAMETER_UNITS.search(line))
            skipped = bool(UNCARRIED_UNITS.search(line))
            continue
        if skipped:
            continue
        _, name, _, value = found.groups()
        if in_parameters:
            parameters.setdefault(name, set()).add(int(value))
        else:
            pictures.setdefault(name, []).append(int(value))
    return pictures, parameters


def length_prefixed(path: Path) -> list[bytes]:
    data = path.read_bytes()
    units, at = [], 0
    while at + 4 <= len(data):
        size = int.from_bytes(data[at : at + 4], "little")
        units.append(data[at + 4 : at + 4 + size])
        at += 4 + size
    return units


def ivf(frames: list[bytes], fourcc: bytes, size: str) -> bytes:
    width, height = (int(n) for n in size.split("x"))
    header = b"DKIF" + (0).to_bytes(2, "little") + (32).to_bytes(2, "little") + fourcc
    header += width.to_bytes(2, "little") + height.to_bytes(2, "little")
    header += (30).to_bytes(4, "little") + (1).to_bytes(4, "little")
    header += len(frames).to_bytes(4, "little") + bytes(4)
    body = b"".join(
        len(f).to_bytes(4, "little") + i.to_bytes(8, "little") + f for i, f in enumerate(frames)
    )
    return header + body


def ivf_frames(path: Path) -> list[bytes]:
    data = path.read_bytes()
    frames, at = [], 32
    while at + 12 <= len(data):
        size = int.from_bytes(data[at : at + 4], "little")
        frames.append(data[at + 12 : at + 12 + size])
        at += 12 + size
    return frames


def start_code_units(data: bytes) -> list[bytes]:
    """Annex B NAL units, or MPEG-2's start-code units, without their start codes."""
    starts = [m.end() for m in re.finditer(b"\x00\x00\x01", data)]
    ends = [s - 3 for s in starts[1:]] + [len(data)]
    return [data[s:e].rstrip(b"\x00") for s, e in zip(starts, ends)]


def passed_through(
    codec: str, original: bytes, rebuilt: bytes
) -> tuple[list[bytes], list[bytes]] | None:
    """What a rebuild must carry byte for byte: the coded data VA hands over as it came."""
    if codec == "H264":
        return [u for u in start_code_units(original) if u[0] & 0x1F in (1, 5)], [
            u for u in start_code_units(rebuilt) if u[0] & 0x1F in (1, 5)
        ]
    if codec == "MPEG2":
        return [u for u in start_code_units(original) if 0x01 <= u[0] <= 0xAF], [
            u for u in start_code_units(rebuilt) if 0x01 <= u[0] <= 0xAF
        ]
    if codec == "JPEG":
        return [f[f.find(b"\xff\xda") :] for f in original.split(b"\xff\xd8")[1:]], [
            f[f.find(b"\xff\xda") :] for f in rebuilt.split(b"\xff\xd8")[1:]
        ]
    return None


def capture(setup: Setup, clip: Path, out: Path) -> str:
    out.unlink(missing_ok=True)
    rc, log = run(
        ["ffmpeg", "-nostdin", "-v", "error"]
        + decode_args(setup)
        + ["-i", str(clip), "-f", "null", "-"],
        env=dict(setup.env(), VAAPI_CAPTURE=str(out)),
    )
    return "" if out.exists() else f"no capture: {last_line(log)}"


# what the rebuilds write otherwise, for the codecs headers.py parses, and why
PARSED_OTHERWISE = {
    # an Advanced Simple VOL of the version its tools need, low delay, no VBV or fixed rate
    "MPEG4": r"random_accessible_vol|video_object_type_indication|is_object_layer_identifier"
    r"|video_object_layer_verid|video_object_layer_priority|aspect_ratio_info|par_\w+"
    r"|vol_control_parameters|chroma_format|low_delay|vbv_parameters|fixed_vop_\w+"
    r"|newpred_enable|reduced_resolution_vop_enable|bits_per_pixel",
    # VA has no TR: pictures are counted
    "H263": r"temporal_reference",
    # level 4, unknown rates, no display extension or HRD; coded size as the maximum
    "VC1": r"LEVEL|FRMRTQ_POSTPROC|BITRTQ_POSTPROC|DISPLAY_EXT|DISP_\w+|ASPECT_RATIO_FLAG"
    r"|FRAMERATE_FLAG|COLOR_FORMAT_FLAG|HRD_\w+|CODED_SIZE_FLAG|CODED_WIDTH|CODED_HEIGHT"
    # STRUCT_C's reserved bits, as a current encoder sets them
    r"|RES_\w+",
}


def compare_fields(
    codec: str, kind: str, ours: list[headers.Fields], clips: list[headers.Fields]
) -> tuple[str, int]:
    """Each element's distinct values in our headers against the clip's: a failure, or a count."""
    otherwise = re.compile(PARSED_OTHERWISE[codec])
    names = {name for fields in ours + clips for name in fields}
    compared = 0
    for name in sorted(names):
        if otherwise.fullmatch(re.sub(r"\[\d+\]", "", name)):
            continue
        mine = sorted({f[name] for f in ours if name in f})
        theirs = sorted({f[name] for f in clips if name in f})
        if mine != theirs:
            return f"failed: {kind} {name}: {mine[:8]} against the clip's {theirs[:8]}", compared
        compared += 1
    return "", compared


def compare_parsed(codec: str, profile: str, original: bytes, units: list[bytes]) -> str:
    """The rebuilt headers element by element, the coded pictures byte for byte."""
    rebuilt = b"".join(units)
    if codec == "MPEG4":
        theirs, ours = headers.start_code_units(original), headers.start_code_units(rebuilt)
        vol = range(headers.MPEG4_VOL_FIRST, headers.MPEG4_VOL_LAST + 1)
        failure, compared = compare_fields(
            codec, "VOL",
            [headers.mpeg4_vol(p) for c, p in ours if c in vol],
            [headers.mpeg4_vol(p) for c, p in theirs if c in vol],
        )  # fmt: skip
        coded = [[p for c, p in units_ if c == headers.MPEG4_VOP] for units_ in (theirs, ours)]
    elif codec == "H263":
        theirs_h263 = [headers.h263_picture(p) for p in headers.h263_pictures(original)]
        ours_h263 = [headers.h263_picture(u) for u in units]
        failure, compared = compare_fields(
            codec, "picture", [f for f, *_ in ours_h263], [f for f, *_ in theirs_h263]
        )
        coded = [[tuple(data) for _, *data in pictures] for pictures in (theirs_h263, ours_h263)]
    elif profile == "VC1Advanced":
        theirs, ours = headers.start_code_units(original), headers.start_code_units(rebuilt)
        sequences, entry_points = [], []
        for stream in (ours, theirs):
            sequence = [headers.vc1_sequence(p) for c, p in stream if c == headers.VC1_SEQUENCE]
            buckets = sequence[0]["HRD_NUM_LEAKY_BUCKETS"] if sequence else 0
            sequences.append(sequence)
            entry_points.append(
                [
                    headers.vc1_entry_point(p, buckets)
                    for c, p in stream
                    if c == headers.VC1_ENTRY_POINT
                ]
            )
        failure, compared = compare_fields(codec, "sequence", *sequences)
        if not failure:
            failure, more = compare_fields(codec, "entry point", *entry_points)
            compared += more
        coded = [
            [(c, p) for c, p in units_ if c in headers.VC1_PICTURE_UNITS]
            for units_ in (theirs, ours)
        ]
    else:
        struct_c, frames = headers.rcv(original)
        failure, compared = compare_fields(
            codec, "STRUCT_C",
            [headers.vc1_struct_c(u) for u in units],
            [headers.vc1_struct_c(struct_c)],
        )  # fmt: skip
        coded = [frames, [u[4:] for u in units]]
    if failure:
        return failure
    if coded[0] != coded[1]:
        differ = next((i for i, (a, b) in enumerate(zip(*coded)) if a != b), min(map(len, coded)))
        return f"failed: {len(coded[1])} coded pictures, the clip's {len(coded[0])}, differ from {differ}"
    return f"pass: {len(units)} pictures, {compared} elements, every coded picture bit-exact"


def rebuild_case(setup: Setup, unit_dir: Path, name: str, clip: Clip) -> Iterator[Line]:
    key = f"unit.rebuild.{name}"
    codec = next(c for c in ELEMENTARY if clip.profile.startswith(c))
    path = setup.clips / f"{name}.{clip.container}"
    captured, replayed = setup.work / f"{name}.capture", setup.work / f"{name}.replayed"
    original, rebuilt = setup.work / f"{name}.original", setup.work / f"{name}.rebuilt"
    failure = capture(setup, path, captured)
    if failure:
        yield key, f"failed: {failure}"
        return
    rc, log = run([str(unit_dir / "replay"), str(captured), str(replayed)])
    if rc != 0:
        yield key, f"failed: replay: {last_line(log)}"
        return
    muxer, demuxer, bsf = ELEMENTARY[codec]
    run(
        ["ffmpeg", "-nostdin", "-v", "error", "-y", "-i", str(path), "-c:v", "copy"]
        + bsf
        + ["-f", muxer, str(original)]
    )
    if codec in PARSED_OTHERWISE:
        # an RCV file is VC-1's Simple and Main elementary form already
        source = path if clip.container == "rcv" else original
        yield key, compare_parsed(
            codec, clip.profile, source.read_bytes(), length_prefixed(replayed)
        )
        return
    units = length_prefixed(replayed)
    if muxer == "ivf":
        rebuilt.write_bytes(ivf(units, b"VP90" if codec == "VP9" else b"VP80", clip.size))
        if ivf_frames(original) != units:
            yield key, f"failed: {len(units)} frames differ from the clip's"
            return
    else:
        rebuilt.write_bytes(b"".join(units))
    carried = passed_through(codec, original.read_bytes(), rebuilt.read_bytes())
    if carried and carried[0] != carried[1]:
        yield key, f"failed: {len(carried[1])} coded units, the clip's {len(carried[0])}, differ"
        return
    ours, theirs = trace_units(rebuilt, ["-f", demuxer]), trace_units(original, ["-f", demuxer])
    otherwise = re.compile(REBUILT_OTHERWISE[codec])
    compared = 0
    # a parameter set's elements as their sorted distinct values: resent sets count once
    kinds = [
        (ours[0], theirs[0]),
        (
            {name: sorted(values) for name, values in ours[1].items()},
            {name: sorted(values) for name, values in theirs[1].items()},
        ),
    ]
    for kind, (mine, clips) in enumerate(kinds):
        for field in sorted(set(mine) | set(clips)):
            if otherwise.fullmatch(re.sub(r"\[\d+\]", "", field)) or otherwise.fullmatch(field):
                continue
            if field in INFERRED:
                mine.setdefault(field, [INFERRED[field]])
                clips.setdefault(field, [INFERRED[field]])
            if mine.get(field) != clips.get(field):
                what = "parameter set" if kind else "picture"
                yield key, (
                    f"failed: {what} {field}: {str(mine.get(field))[:60]}"
                    f" against the clip's {str(clips.get(field))[:60]}"
                )
                return
            compared += 1
    if not compared:
        yield key, "failed: FFmpeg parsed no headers from either stream"
        return
    yield key, f"pass: {len(units)} pictures, {compared} elements bit-exact"


def unit_suite(setup: Setup, unit_dir: Path) -> Iterator[Line]:
    for test in sorted(unit_dir.glob("test_*")):
        rc, log = run([str(test)])
        reported = [line for line in log.splitlines() if line.startswith("unit.")]
        for line in reported:
            key, _, value = line.partition(" ")
            yield key, value
        if rc != 0 and not any("failed" in line for line in reported):
            yield f"unit.{test.name[5:]}", f"failed: {last_line(log)}"
    for name, clip in CLIPS.items():
        if not clip.switch:
            yield from rebuild_case(setup, unit_dir, name, clip)


# verdicts


def verdict(value: str) -> str | None:
    if value.startswith(("pass", "unoffered", "made")) or not value:
        return None
    if value.startswith(("no ", "not run")):
        return "UNTESTED"
    return "FAIL"


def suite(setup: Setup) -> Iterator[Line]:
    missing = [tool for tool in TOOLS if not shutil.which(tool)]
    for tool in missing:
        yield f"tool.{tool}", f"no {tool}: apt install {TOOLS[tool]}"
    if "vainfo" in missing or "ffmpeg" in missing:
        return
    offers, log = offered(setup)
    yield from vainfo(setup, offers, log)
    if setup.on_box:
        yield from node_case(setup)
        yield from package_case()
    if not offers:
        return
    for name, clip in CLIPS.items():
        yield from decode_case(setup, name, clip, offers)
    yield from vpp_case(setup, offers)
    for name in ENCODES:
        yield from encode_case(setup, name, offers, [])
    yield from encode_case(setup, "h264", offers, ["-b:v", "2M"])
    if "mpv" not in missing:
        yield from mpv_case(setup, offers)
    if "gst-launch-1.0" not in missing:
        yield from gst_plugin_case(setup)
        for name, clip in CLIPS.items():
            yield from gstreamer_decode_case(setup, name, clip, offers)
        for name in ENCODES:
            yield from gstreamer_encode_case(setup, name, offers)
    yield from probe_case(setup)
    if setup.on_box:
        for name, clip in SPEED_CLIPS.items():
            yield from speed_case(setup, name, clip, offers)
    if not setup.on_box:
        for name, clip in CLIPS.items():
            if (
                clip.profile.startswith(MAPPED_PROFILES)
                and name != "h264-high10"
                and not clip.switch
            ):
                yield from mapping_case(setup, name, clip)


def emit(lines: Iterator[Line]) -> int:
    failures = 0
    for case, value in lines:
        # among other suites' lines in one report, these say they are the VA driver's
        key = f"{REPORT_PREFIX}{case}"
        print(f"{key} {value}", flush=True)
        judged = verdict(value) if not key.endswith((".vendor", ".offers")) else None
        if judged:
            print(f"{judged} {key}", flush=True)
            failures += judged == "FAIL"
    return failures


@contextlib.contextmanager
def x_server(display: str) -> Iterator[None]:
    server = subprocess.Popen(
        ["Xvfb", display, "-nolisten", "tcp"],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    try:
        time.sleep(1)
        yield
    finally:
        server.terminate()


def main() -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("mode", choices=["host", "unit", "box", "clips"])
    parser.add_argument("--driver-dir", type=Path, help="where tvb_drv_video.so is")
    parser.add_argument("--clips", type=Path, default=Path("/work/va-driver/clips"))
    parser.add_argument("--driver-name", default="tvb", help="the driver's libva name")
    parser.add_argument("--probe", type=Path, help="va_probe, if not beside the driver")
    parser.add_argument("--out", type=Path, help="clips: where to make them")
    parser.add_argument("--device", default="/dev/dri/renderD128", help="box: the render node")
    parser.add_argument("--family", default="", help="box: the board family, for its refusals")
    args = parser.parse_args()

    if args.mode == "clips":
        return emit(make_clips(args.out or args.clips))
    if not args.driver_dir:
        parser.error("--driver-dir is needed")
    with tempfile.TemporaryDirectory() as work:
        if args.mode == "box":
            driver = args.driver_dir / f"{args.driver_name}{DRIVER_SUFFIX}"
            if not driver.exists():
                print(f"no {driver}: the driver is not installed")
                return NOTHING_TO_TEST
            setup = Setup(
                args.driver_dir,
                args.probe or args.driver_dir / "va_probe",
                args.driver_name,
                args.family,
                args.device,
                args.clips,
                Path(work),
                on_box=True,
            )
            return 1 if emit(suite(setup)) else 0
        if not shutil.which("Xvfb"):
            sys.exit("the host suite needs Xvfb: libva's DRM display needs a render node")
        setup = Setup(
            args.driver_dir,
            args.probe or args.driver_dir / "va_probe",
            args.driver_name,
            "",
            HOST_DISPLAY,
            args.clips,
            Path(work),
            on_box=False,
        )
        with x_server(HOST_DISPLAY):
            failures = emit(make_clips(args.clips))
            if args.mode == "unit":
                failures += emit(unit_suite(setup, args.driver_dir / "unit"))
            else:
                failures += emit(suite(setup))
        return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
