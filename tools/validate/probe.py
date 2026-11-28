#!/usr/bin/env python3
"""Each option a SoC datasheet lists, probed on the box through the kernel's own interfaces: one
line an option, "works" or "does not work" and what showed it. No verdict: whether a line is
expected on this box is the reader's call, against the SoC's datasheet and the board's board.md.

    python3 probe.py [--area system,video,display,audio,network]     # on the box, as root
"""

from __future__ import annotations

import argparse
import ctypes
import fcntl
import glob
import os
import re
import struct
import subprocess
import sys
from collections.abc import Callable, Iterator
from pathlib import Path

import display
import v4l2_request as v4l2

Line = tuple[str, bool, str]

# V4L2: the buffer types a node lists formats for, and the ioctls asked
OUTPUT_TYPES, CAPTURE_TYPES = (2, 10), (1, 9)
ENUM_FMT_SIZE = 64
ENUM_FMT = v4l2.ioc(v4l2.READ_WRITE, "V", 2, ENUM_FMT_SIZE)
QUERYCAP_SIZE = 104
QUERYCAP = v4l2.ioc(v4l2.READ, "V", 0, QUERYCAP_SIZE)
SELECTION_SIZE = 64
# copies dmatest makes through a DMA engine, each its own buffer
DMATEST_ITERATIONS = 20
DMATEST = Path("/sys/module/dmatest/parameters")
G_SELECTION = v4l2.ioc(v4l2.READ_WRITE, "V", 94, SELECTION_SIZE)
SEL_TGT_CROP = 0
# the coded formats a datasheet names, by the fourcc V4L2 gives each
CODECS = {
    "H.264": ("H264", "S264"),
    "H.264 MVC": ("M264",),
    "HEVC": ("HEVC", "S265"),
    "VP9": ("VP90", "VP9F"),
    "AV1": ("AV1F",),
    "MPEG-1/2": ("MPG1", "MPG2", "MG2S"),
    "MPEG-4, H.263": ("MPG4", "MG4S", "H263"),
    "VP8": ("VP80", "VP8F"),
    "VC-1": ("VC1G", "VC1L"),
    "JPEG": ("JPEG", "MJPG"),
}
# DRM
MODIFIER_VENDOR_ARM = 0x08
FB_MODIFIERS = 1 << 1
TEST_ONLY = display.TEST_ONLY | display.ALLOW_MODESET
CAP_STEREO_3D = 1
MODE_FLAG_3D_MASK = 0x1F << 14
AFBC_WIDTH, AFBC_HEIGHT = 1920, 1088
# modes wider than 4K UHD: clock kHz, horizontal and vertical timings, refresh; DCI 4K is CTA's
# VIC 102, 4096x2304 CVT reduced blanking
WIDE_MODES = [
    (594000, (4096, 4184, 4272, 4400), (2160, 2168, 2178, 2250), 60),
    (604000, (4096, 4144, 4176, 4256), (2304, 2307, 2312, 2366), 60),
]
# ALSA: the rates a datasheet's audio interfaces quote
RATES = (8000, 11025, 12000, 16000, 22050, 24000, 32000, 44100, 48000, 64000, 88200, 96000)
RATES += (176400, 192000)
PROBE_SAMPLES = 64
# a crypto driver that is software or the CPU's own instructions, by its name
SOFTWARE_CRYPTO = re.compile(
    r"generic|-ce\b|-neon|arm64|-lib|cipher_null|-scomp|cprng"
    r"|^(drbg|jitter|cryptd|pkcs|hmac|ecdh|ecdsa|rsa|lzo|lz4|zstd|deflate|zlib)"
    r"|\("
)


def run(cmd: list[str], timeout: float = 20) -> tuple[int, str]:
    try:
        done = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout, check=False)
    except (OSError, subprocess.TimeoutExpired) as error:
        return 1, str(error)
    return done.returncode, done.stdout + done.stderr


def read(path: str) -> str:
    try:
        return Path(path).read_text().strip()
    except OSError:
        return ""


# ---- system


def system() -> Iterator[Line]:
    summary = read("/sys/kernel/debug/pm_genpd/pm_genpd_summary").splitlines()
    domains = [line.split() for line in summary if re.match(r"^\S+\s+(on|off)", line)]
    on = [d[0] for d in domains if d[1] == "on"]
    yield "power domains", bool(domains), f"{len(domains)} domains, on: {' '.join(on) or 'none'}"
    clocks = read("/sys/kernel/debug/clk/clk_summary").splitlines()
    plls = [c.split() for c in clocks if re.match(r"^\s*pll_\S+\s", c)]
    yield "PLLs", bool(plls), " ".join(f"{p[0]} {int(p[4]) // 1000000} MHz" for p in plls)
    channels = glob.glob("/sys/class/dma/dma*chan*")
    busy = sum(read(f"{c}/in_use") == "1" for c in channels)
    yield "DMA channels", bool(channels), f"{len(channels)} channels, {busy} in use"
    yield dma_memcpy()
    # CEC registers an rc device too: an IR receiver is one offering an IR protocol
    receivers = [
        rc for rc in sorted(glob.glob("/sys/class/rc/rc*")) if read(f"{rc}/protocols") != "[cec]"
    ]
    for rc in receivers:
        driver = os.path.basename(os.path.realpath(f"{rc}/device/driver"))
        yield f"IR receiver {os.path.basename(rc)}", True, f"{driver}: {read(f'{rc}/protocols')}"
    if not receivers:
        yield "IR receiver", False, "no rc device with an IR protocol"
    yield from crypto()
    rng = read("/sys/class/misc/hw_random/rng_current")
    yield "RNG", bool(rng) and rng != "none", rng or "none"
    watchdogs = sorted(glob.glob("/sys/class/watchdog/watchdog*"))
    drivers = [os.path.basename(os.path.realpath(f"{w}/device/driver")) for w in watchdogs]
    yield "watchdog", bool(watchdogs), " ".join(drivers) or "none"
    pci = sorted(os.path.basename(d) for d in glob.glob("/sys/bus/pci/devices/*"))
    yield "PCIe", bool(pci), " ".join(pci) or "no device"
    spi = sorted(os.path.basename(d) for d in glob.glob("/sys/class/spi_master/*"))
    yield "SPI controllers", bool(spi), " ".join(spi) or "none"
    buses = sorted(glob.glob("/sys/bus/i2c/devices/i2c-*"))
    devices = (os.path.basename(c) for c in glob.glob("/sys/bus/i2c/devices/*"))
    clients = [c for c in devices if re.match(r"^\d+-[0-9a-f]{4}$", c)]
    yield "I2C", bool(buses), f"{len(buses)} buses, clients: {' '.join(sorted(clients)) or 'none'}"


def dma_memcpy() -> Line:
    """Memory to memory through a DMA engine, by the kernel's dmatest: its copies and their
    failures, from its summary."""
    if run(["modprobe", "dmatest"])[0]:
        return "DMA memcpy", False, "no dmatest module"
    try:
        (DMATEST / "iterations").write_text(str(DMATEST_ITERATIONS))
        (DMATEST / "channel").write_text("")
        (DMATEST / "run").write_text("1")
        (DMATEST / "wait").read_text()
        log = run(["dmesg"])[1]
    finally:
        run(["modprobe", "-r", "dmatest"])
    summaries = re.findall(r"(\S+): summary (\d+) tests, (\d+) failures", log)
    if not summaries:
        return "DMA memcpy", False, "dmatest ran no channel: none takes memcpy"
    channel, tests, failures = summaries[-1]
    return "DMA memcpy", failures == "0", f"{channel}: {tests} copies, {failures} failed"


def crypto() -> Iterator[Line]:
    """Algorithms a driver serves that is not the CPU's instructions or software: an engine's."""
    served: dict[str, set[str]] = {}
    for entry in read("/proc/crypto").split("\n\n"):
        fields = dict(re.findall(r"^(\w+)\s*:\s*(.*)$", entry, re.M))
        driver = fields.get("driver", "")
        if driver and not SOFTWARE_CRYPTO.search(driver):
            served.setdefault(driver, set()).add(fields.get("name", "?"))
    detail = "; ".join(f"{d}: {' '.join(sorted(n))}" for d, n in sorted(served.items()))
    yield "crypto engine", bool(served), detail or "only the CPU's instructions and software"


# ---- video: every V4L2 node, by what it takes and gives


def fourccs(fd: int, buf_type: int) -> list[str]:
    found = []
    for index in range(64):
        arg = bytearray(struct.pack("<II", index, buf_type) + bytes(ENUM_FMT_SIZE - 8))
        try:
            fcntl.ioctl(fd, ENUM_FMT, arg)
        except OSError:
            break
        found.append(arg[44:48].decode(errors="replace"))
    return found


def video_nodes() -> Iterator[tuple[str, int, str]]:
    for node in sorted(glob.glob("/dev/video*"), key=lambda n: int(n[10:] or 0)):
        try:
            fd = os.open(node, os.O_RDWR | os.O_NONBLOCK)
        except OSError:
            continue
        cap = bytearray(QUERYCAP_SIZE)
        try:
            fcntl.ioctl(fd, QUERYCAP, cap)
        except OSError:
            os.close(fd)
            continue
        yield node, fd, cap[16:48].split(b"\0")[0].decode()
        os.close(fd)


def video() -> Iterator[Line]:
    coded: dict[str, list[str]] = {}
    for node, fd, card in video_nodes():
        takes = sorted({f for t in OUTPUT_TYPES for f in fourccs(fd, t)})
        gives = sorted({f for t in CAPTURE_TYPES for f in fourccs(fd, t)})
        detail = f"{node}: {' '.join(takes)} -> {' '.join(gives)}"
        yield f"{card} formats", bool(takes or gives), detail
        for fourcc in takes + gives:
            coded.setdefault(fourcc, []).append(card)
        if "JPEG" in takes:
            arg = bytearray(struct.pack("<II", 9, SEL_TGT_CROP) + bytes(SELECTION_SIZE - 8))
            try:
                fcntl.ioctl(fd, G_SELECTION, arg)
                yield f"{card} decode crop (ROI)", True, "G_SELECTION crop answered"
            except OSError as error:
                why = f"G_SELECTION crop: {os.strerror(error.errno)}"
                yield f"{card} decode crop (ROI)", False, why
    yield from vendor_media()
    for codec, codes in CODECS.items():
        cards = sorted({c for f in codes for c in coded.get(f, [])})
        yield f"codec {codec}", bool(cards), ", ".join(cards) or f"no node lists {'/'.join(codes)}"


def vendor_media() -> Iterator[Line]:
    """Rockchip's own interfaces, where its kernel has them in place of V4L2."""
    devices = re.findall(
        r"DEVICE\[\s*\d+\]:(\w+?)(?=HW_ID|\s|$)", read("/proc/mpp_service/supports-device")
    )
    if devices:
        yield "MPP devices", True, " ".join(devices)
    if os.path.exists("/dev/rga"):
        yield "RGA", True, "/dev/rga"


# ---- display


def afbc_buffer(box: display.Box, modifier: int) -> int:
    """An AFBC XRGB8888 framebuffer, contents unset: enough for a test-only commit."""
    dumb = box.drm.call(
        "dumb", display.CreateDumb(height=AFBC_HEIGHT * 2, width=AFBC_WIDTH, bpp=32)
    )
    cmd = display.FbCmd2(
        width=AFBC_WIDTH, height=AFBC_HEIGHT, pixel_format=display.XRGB8888, flags=FB_MODIFIERS
    )
    cmd.handles[0], cmd.pitches[0], cmd.modifier[0] = dumb.handle, AFBC_WIDTH * 4, modifier
    return box.drm.call("addfb2", cmd).fb_id


def plane_test(box: display.Box, plane: int, fb: int, extra: dict[str, int]) -> int:
    """errno of a test-only commit showing fb full screen on plane with extra properties."""
    props = box.drm.props(plane, display.OBJ_PLANE)
    w, h = box.mode.hdisplay, box.mode.vdisplay
    values = {"FB_ID": fb, "CRTC_ID": box.crtc, "CRTC_X": 0, "CRTC_Y": 0, "CRTC_W": w}
    values |= {"CRTC_H": h, "SRC_X": 0, "SRC_Y": 0, "SRC_W": AFBC_WIDTH << 16}
    values |= {"SRC_H": (AFBC_HEIGHT - 8) << 16} | extra
    return box.drm.commit({plane: {props[k][0]: v for k, v in values.items()}}, TEST_ONLY)


def planes(box: display.Box) -> Iterator[Line]:
    names = display.plane_names()
    for plane in box.planes:
        info = box.plane_info(plane)
        props = info["props"]
        name = names.get(plane, f"plane {plane}")
        rotations = box.drm.enums(props["rotation"][2]) if "rotation" in props else {}
        afbc = [m for m in box.modifiers(props) if m >> 56 == MODIFIER_VENDOR_ARM]
        stages = sorted(p for p in props if re.search(r"EOTF|LUT|HDR|COLOR|CSC|CTM", p))
        detail = f"{info['type']}, {len(info['formats'])} formats, rotation {' '.join(rotations)}"
        yield f"{name}", True, f"{detail}; AFBC modifiers {len(afbc)}; stages {' '.join(stages)}"
        if not afbc or not rotations:
            continue
        fb = afbc_buffer(box, afbc[0])
        for rotation in rotations:
            value = display.rotation_value(rotations, rotation)
            error = plane_test(box, plane, fb, {"rotation": value})
            ok = not error
            yield f"{name} AFBC {rotation}", ok, "test commit taken" if ok else os.strerror(error)
        box.drm.call("rmfb", display.FbId(fb_id=fb))


def wide_modes(box: display.Box) -> Iterator[Line]:
    for clock, h, v, refresh in WIDE_MODES:
        yield custom_mode(box, clock, h, v, refresh)


def custom_mode(box: display.Box, clock: int, h: tuple, v: tuple, refresh: int) -> Line:
    mode = display.ModeInfo(clock=clock, vrefresh=refresh, name=f"{h[0]}x{v[0]}".encode())
    mode.hdisplay, mode.hsync_start, mode.hsync_end, mode.htotal = h
    mode.vdisplay, mode.vsync_start, mode.vsync_end, mode.vtotal = v
    blob = box.drm.blob(bytes(mode))
    crtc = {box.prop(box.crtc, display.OBJ_CRTC, "MODE_ID"): blob}
    error = box.drm.commit({box.crtc: crtc}, TEST_ONLY)
    box.drm.unblob(blob)
    name = f"{h[0]}x{v[0]}@{refresh} on the HDMI CRTC"
    return name, not error, "test commit taken" if not error else os.strerror(error)


def connectors(box: display.Box) -> Iterator[Line]:
    if box.hdmi_connector:
        props = box.drm.props(box.hdmi_connector, display.OBJ_CONNECTOR)
        for prop in ("Content Protection", "HDCP Content Type", "color format", "Colorspace"):
            yield f"HDMI {prop}", prop in props, "property present" if prop in props else "absent"
        box.drm.call("cap", display.ClientCap(capability=CAP_STEREO_3D, value=1))
        stereo = [m for m in box.connector_modes() if m.flags & MODE_FLAG_3D_MASK]
        yield "HDMI 3D modes", bool(stereo), f"{len(stereo)} of the attached screen's modes"
    crtc_props = box.drm.props(box.crtc, display.OBJ_CRTC) if box.crtc else {}
    stages = sorted(p for p in crtc_props if re.search(r"LUT|CTM|HDR|GAMMA", p))
    detail = " ".join(stages) or f"none of {' '.join(sorted(crtc_props))}"
    yield "CRTC colour stages", bool(stages), detail
    for status in sorted(glob.glob("/sys/class/drm/card*-*/status")):
        connector = status.split("/")[-2].split("-", 1)[1]
        yield f"{connector} detect", True, read(status)


def display_probe() -> Iterator[Line]:
    """Against the ladder's synthetic screen where the kernel takes one, so 4K modes are offered."""
    if not glob.glob("/dev/dri/card*"):
        yield "DRM", False, "no /dev/dri card"
        return
    with display.display_free(), display.hdr_sink(display.hdr_edid(ladder=True)) as synthetic:
        box = display.Box()
        box.synthetic_sink = synthetic
        if box.crtc is None:
            yield "HDMI CRTC", False, "no mode set"
        else:
            yield from planes(box)
            yield from wide_modes(box)
        yield from connectors(box)
        os.close(box.drm.fd)


# ---- audio


def pcms() -> Iterator[tuple[str, str, str]]:
    """Each PCM: its hw: name, its direction, its card and device name."""
    for line in read("/proc/asound/pcm").splitlines():
        m = re.match(r"(\d+)-(\d+): (.*?) :.*", line)
        if not m:
            continue
        card, device = int(m[1]), int(m[2])
        for direction in ("playback", "capture"):
            if direction in line:
                yield f"hw:{card},{device}", direction, m[3]


def audio() -> Iterator[Line]:
    for pcm, direction, name in pcms():
        tool = "aplay" if direction == "playback" else "arecord"
        stream = "/dev/zero" if direction == "playback" else "/dev/null"
        _, params = run([tool, "-D", pcm, "--dump-hw-params", "-d", "1", stream])
        channels = re.search(r"CHANNELS:\s*(\S.*)", params)
        taken = []
        for rate in RATES:
            cmd = [tool, "-D", pcm, "-r", str(rate), "-c", "2", "-f", "S16_LE"]
            rc, out = run(cmd + ["-s", str(PROBE_SAMPLES), stream])
            # hw: plays a rate it lacks at the nearest, with only a warning
            if not rc and "not accurate" not in out:
                taken.append(str(rate))
        detail = f"channels {channels[1] if channels else '?'}, rates {' '.join(taken) or 'none'}"
        yield f"{name} {direction} ({pcm})", bool(taken), detail


# ---- network


def network() -> Iterator[Line]:
    for iface in sorted(glob.glob("/sys/class/net/*/device")):
        name = iface.split("/")[4]
        _, features = run(["ethtool", "-k", name])
        on = re.findall(r"^(\S+): on$", features, re.M)
        yield f"{name} offloads", bool(on), " ".join(on) or "none on"
        _, settings = run(["ethtool", name])
        wol = re.search(r"Supports Wake-on: (\S+)", settings)
        speeds = re.findall(r"(\d+)base", settings.split("Supported pause")[0])
        yield f"{name} Wake-on-LAN", bool(wol) and wol[1] != "d", wol[1] if wol else "not reported"
        yield f"{name} speeds", bool(speeds), " ".join(sorted(set(speeds), key=int)) or "?"


AREAS: dict[str, Callable[[], Iterator[Line]]] = {
    "system": system,
    "video": video,
    "display": display_probe,
    "audio": audio,
    "network": network,
}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--area", default=",".join(AREAS), help=f"of {', '.join(AREAS)}")
    args = parser.parse_args()
    for area in args.area.split(","):
        for name, works, detail in AREAS[area]():
            print(f"PROBE {area}: {name}: {'works' if works else 'does not work'} ({detail})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
