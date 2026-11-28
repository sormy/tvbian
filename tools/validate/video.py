#!/usr/bin/env python3
"""Hardware video test matrix: decode, decoder scaling and encode, against FFmpeg's software path.

On the host:
  video.py clips                                   the clip corpus, made by the host's FFmpeg
  video.py run --box root@<box> --engine <engine>  copy, run on the box, save its JSON
  video.py report <run.json>                       the largest passing size per codec
  video.py compare <old.json> <new.json>           what got worse; exits 1 if anything did
On the box, started by run:
  video.py box --engine <engine> --ffmpeg <ffmpeg> --dir <dir>
"""

import argparse
import hashlib
import json
import math
import os
import re
import shutil
import subprocess
import struct
import sys
import time
import urllib.request
from collections.abc import Callable
from dataclasses import dataclass

import v4l2_request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
CORPUS = ROOT / "build" / "validate" / "video" / "clips"
RESULTS = ROOT / "build" / "validate" / "video"
BOX_DIR = "/var/tmp/tvb-validate-video"
FRAMES = 3
# a hardware hang costs a minute at most; past two failing sizes a codec's ladder stops
CASE_TIMEOUT = 60
STOP_AFTER = 2
# portrait at 1080p's area, then past it: a decoder limited by area, not by side
AREA_SIZES = ["1080x1920", "1920x1200"]
LADDER = [
    "1920x1080",
    *AREA_SIZES,
    "2560x1440",
    "3840x2160",
    "4096x2160",
    "4096x2304",
    "4080x4080",
    "5120x2880",
    "6144x3456",
    "7680x4320",
    "8192x4320",
    "8192x8192",
    "16384x8640",
]
# luma PSNR a decode must hold where the format leaves the IDCT's rounding to the decoder
LOSSY_FLOOR_DB = 50.0
# chroma PSNR a lossy decode must hold: 4:1:1 converted to NV12 reads 34 dB, a wrong plane ~10
CHROMA_FLOOR_DB = 30.0
# FFmpeg queues 16 raw frames by default: 1.6 GB at 8192x8192, past a small box's RAM
V4L2_ENCODE_QUEUE = 4
# a V4L2 encoder in separate header mode hands the parameter sets out as a packet of their own
HEADER_PACKETS = 1
SCALE_FLOOR_DB = 30.0
ENCODE_FLOOR_DB = 30.0
SCALE_FROM = "3840x2160"
# the encoder's source layouts, as FFmpeg hands them to V4L2: YUV 4:2:0 and 4:2:2 semi-planar,
# planar and packed, and 32-, 24- and 16-bit RGB; each coded once at this size
ENCODE_INPUTS = ["nv12", "nv21", "yuv420p", "nv16", "yuv422p", "yuyv422", "uyvy422"]
ENCODE_INPUTS += ["bgr0", "rgb0", "0rgb", "0bgr", "bgr24", "rgb24", "rgb565le"]
ENCODE_INPUTS += ["nv24", "nv42", "yuv444p"]
ENCODE_INPUT_SIZE = "1280x720"
# every layout through H.264; one RGB layout through the codecs that signal or range RGB apart
ENCODE_INPUT_CODECS = {"h264": ENCODE_INPUTS, "hevc": ["bgr0"], "mjpeg": ["bgr0"]}
# error concealment: the clip size damaged, and how much of it, from its middle
CONCEAL_SIZE = "1920x1080"
CONCEAL_SPAN = 4096
# the scaled picture's lines asked of SCALE_FROM: a half, a quarter and an eighth
SCALE_LINES = (1080, 540, 270)
AFBC_SIZES = ["1920x1080", "3840x2160"]
TEN_BIT = {"h264p10", "hevc10", "hevc10hdr", "vp9p2"}
# HDR10 as a player gets it: BT.2020, PQ, a 1000-nit mastering display, MaxCLL and MaxFALL
HDR10_X265 = (
    "colorprim=bt2020:transfer=smpte2084:colormatrix=bt2020nc:hdr10=1:repeat-headers=1"
    ":master-display=G(13250,34500)B(7500,3000)R(34000,16000)WP(15635,16450)L(10000000,50)"
    ":max-cll=1000,400"
)
HDR_CODECS = ("hevc10hdr",)
# the engine's deinterlacer is not bwdif: a floor that catches a broken field, not a different filter
DEINTERLACE_FLOOR_DB = 25.0
# a frame per field, then per frame where the deinterlacer offers it; the filter's refusal
DEINTERLACE_RATES = ("field", "frame")
DEINTERLACE_UNOFFERED = r"gives no frame per frame"
PAIRED = "settb=AVTB,setpts=N"
# frame rate: a FRAMES-long run and a longer one, differenced so setup cancels out; the longer one
# grows until it outlasts the short one by FPS_SPAN seconds
FPS_FRAMES = [12, 60]
FPS_SPAN = 1.0
# film's rate: a size the engine runs slower than this is correct but cannot play
PLAYABLE_FPS = 24

# a request the driver refuses still completes: past this, it hung
REQUEST_TIMEOUT_MS = 2000
# a converter's scaler is not FFmpeg's bicubic, but garbage sits near 5 dB
CONVERT_FLOOR_DB = 25.0
# DMSR's edge smoothing against the plain scaler: 54 dB luma measured at 1:1
DMSR_FLOOR_DB = 45.0
# its BT.601 limited-range RGB, 55-70 dB of FFmpeg's; a wrong matrix reads near 20
CSC_FLOOR_DB = 40.0


@dataclass(frozen=True)
class Conversion:
    """A converter case: the controls set, FFmpeg's filter for the same frame, the output format,
    and the PSNR floor, None for byte-exact; changes, where the controls must alter the frame."""

    name: str
    src: str
    dst: str
    ref: str = "null"
    ctrls: tuple[str, ...] = ()
    fourcc: str = "NV12"
    pix_fmt: str = "nv12"
    floor: float | None = None
    src_fourcc: str = "NV12"
    src_pix_fmt: str = "nv12"
    changes: bool = False
    # a full-range YUV source, its output format saying so: v4l2-ctl sets the capture format first,
    # and an output format's colour then overwrites the capture's, as mem2mem has it
    src_full_range: bool = False


# a packed 10-bit source as V4L2 lays it, made from FFmpeg's 16-bit one: four samples in five bytes
PACKED_10BIT = {"NV15": "p010le", "NV20": "p210le"}
SAMPLE_BITS = 10
P010_SHIFT = 6


CONVERT_CASES = [
    Conversion("copy", "1920x1080", "1920x1080"),
    Conversion(
        "up", "1280x720", "1920x1080", "scale=1920:1080:flags=bicubic", floor=CONVERT_FLOOR_DB
    ),
    Conversion(
        "down", "1920x1080", "1280x720", "scale=1280:720:flags=bicubic", floor=CONVERT_FLOOR_DB
    ),
]
# the VDPP's own: its chroma either way round, and 4:4:4 out, its chroma upscaled as FFmpeg's
VDPP_CASES = [
    Conversion(
        "nv21",
        "1920x1080",
        "1920x1080",
        fourcc="NV21",
        pix_fmt="nv21",
        src_fourcc="NV21",
        src_pix_fmt="nv21",
    ),
    Conversion("nv21-to-nv12", "1920x1080", "1920x1080", src_fourcc="NV21", src_pix_fmt="nv21"),
    Conversion(
        "nv24",
        "1920x1080",
        "1920x1080",
        "scale=flags=bicubic",
        fourcc="NV24",
        pix_fmt="nv24",
        floor=CONVERT_FLOOR_DB,
    ),
    Conversion(
        "nv42",
        "1920x1080",
        "1920x1080",
        "scale=flags=bicubic",
        fourcc="NV42",
        pix_fmt="nv42",
        floor=CONVERT_FLOOR_DB,
    ),
    # DMSR smooths edges: the frame changes, and stays near the plain scaler's
    Conversion(
        "dmsr", "1920x1080", "1920x1080", ctrls=("sharpness=1",), floor=DMSR_FLOOR_DB, changes=True
    ),
    Conversion(
        "dmsr-up",
        "1280x720",
        "1920x1080",
        "scale=1920:1080:flags=bicubic",
        ("sharpness=1",),
        floor=CONVERT_FLOOR_DB,
    ),
]
# the RGA's own: mirror, rotation, NV12 to RGB; V4L2's rotation turns clockwise
RGA_CASES = [
    Conversion("hflip", "1920x1080", "1920x1080", "hflip", ("horizontal_flip=1",)),
    Conversion("vflip", "1920x1080", "1920x1080", "vflip", ("vertical_flip=1",)),
    Conversion("rotate-90", "1920x1080", "1080x1920", "transpose=clock", ("rotate=90",)),
    Conversion("rotate-180", "1920x1080", "1920x1080", "hflip,vflip", ("rotate=180",)),
    Conversion("rotate-270", "1920x1080", "1080x1920", "transpose=cclock", ("rotate=270",)),
    Conversion(
        "xrgb",
        "1920x1080",
        "1920x1080",
        "scale=in_color_matrix=bt601:in_range=tv",
        fourcc="XR24",
        pix_fmt="bgr0",
        floor=CSC_FLOOR_DB,
    ),
    # the datasheet's other 32-bit order, either way
    Conversion(
        "xrgb-bx24",
        "1920x1080",
        "1920x1080",
        "scale=in_color_matrix=bt601:in_range=tv",
        fourcc="BX24",
        pix_fmt="0rgb",
        floor=CSC_FLOOR_DB,
    ),
    Conversion(
        "bx24-to-nv12",
        "1920x1080",
        "1920x1080",
        "scale=out_color_matrix=bt601:out_range=tv",
        src_fourcc="BX24",
        src_pix_fmt="0rgb",
        floor=CSC_FLOOR_DB,
    ),
    # a 10-bit decode's frame, packed as the decoder writes it, to 8 bits
    Conversion(
        "nv12-full-to-xrgb",
        "1920x1080",
        "1920x1080",
        "scale=in_color_matrix=bt601:in_range=pc",
        fourcc="XR24",
        pix_fmt="bgr0",
        floor=CSC_FLOOR_DB,
        src_full_range=True,
    ),
    Conversion("nv15", "1920x1080", "1920x1080", floor=CONVERT_FLOOR_DB, src_fourcc="NV15"),
    Conversion("nv20", "1920x1080", "1920x1080", floor=CONVERT_FLOOR_DB, src_fourcc="NV20"),
    # the destination's limit, 4096 a side, and one step past it
    Conversion(
        "dst-4096",
        "2048x1152",
        "4096x2304",
        "scale=4096:2304:flags=bicubic",
        floor=CONVERT_FLOOR_DB,
    ),
    Conversion(
        "dst-past-4096",
        "1920x1080",
        "4608x2592",
        "scale=4608:2592:flags=bicubic",
        floor=CONVERT_FLOOR_DB,
    ),
    # a vertical upscale's source, 2048 wide at most, and one step past it
    Conversion(
        "vup-2048",
        "2048x1152",
        "2048x1536",
        "scale=2048:1536:flags=bicubic",
        floor=CONVERT_FLOOR_DB,
    ),
    Conversion(
        "vup-past-2048",
        "2064x1152",
        "2064x1536",
        "scale=2064:1536:flags=bicubic",
        floor=CONVERT_FLOOR_DB,
    ),
]
# FFmpeg's MJPEG encoder writes no standard sampling but 4:2:0: libjpeg's cjpeg makes the others
CJPEG = "cjpeg"
JPEG_SAMPLINGS = {
    "400": ["-grayscale"],
    "411": ["-sample", "4x1,1x1,1x1"],
    "422": ["-sample", "2x1,1x1,1x1"],
    "444": ["-sample", "1x1,1x1,1x1"],
}
# the interlaced clips in MBAFF: 4:2:0 and 4:2:2
INTERLACED = ("h264i", "h264i422")
# interlaced pictures coded as frames, signalled progressive: the case names their field order
INTERLACED_FRAMES = ("h264i422frame",)
# a deinterlaced frame read back and compared as its own sampling
DEINTERLACE_FORMATS = {
    "h264i": ("nv12", "yuv420p10le"),
    "h264i422": ("nv16", "yuv422p10le"),
    "h264i422frame": ("nv16", "yuv422p10le"),
}
# a variant's codec, as decoders are named
BASE_CODEC = {
    "h264i": "h264",
    "h264i422": "h264",
    "h264i422frame": "h264",
    "h264p10": "h264",
    "h264422": "h264",
    "h264gray": "h264",
    "hevc10": "hevc",
    "hevc10hdr": "hevc",
    "vp9p2": "vp9",
    **{f"mjpeg{sampling}": "mjpeg" for sampling in JPEG_SAMPLINGS},
}


def base_codec(codec: str) -> str:
    return BASE_CODEC.get(codec, codec)


# name: container, encoder arguments, sizes, whether the decode must be bit exact
X265 = ["-preset", "ultrafast", "-x265-params", "log-level=0"]
VPX = ["-deadline", "realtime", "-cpu-used", "8", "-row-mt", "1"]
CODECS = {
    "h264": (
        "mp4",
        ["-pix_fmt", "yuv420p", "-c:v", "libx264", "-preset", "veryfast", "-bf", "2"],
        LADDER,
        True,
    ),
    "h264i": (
        "mp4",
        [
            "-pix_fmt",
            "yuv420p",
            "-c:v",
            "libx264",
            "-preset",
            "veryfast",
            "-flags",
            "+ildct+ilme",
            "-x264-params",
            "tff=1",
        ],
        ["1920x1080"],
        True,
    ),
    "h264i422": (
        "mp4",
        [
            "-pix_fmt",
            "yuv422p",
            "-c:v",
            "libx264",
            "-profile:v",
            "high422",
            "-preset",
            "veryfast",
            "-flags",
            "+ildct+ilme",
            "-x264-params",
            "tff=1",
        ],
        ["1920x1080"],
        True,
    ),
    "h264i422frame": (
        "mp4",
        [
            "-pix_fmt",
            "yuv422p",
            "-c:v",
            "libx264",
            "-profile:v",
            "high422",
            "-preset",
            "veryfast",
            "-x264-params",
            "fake-interlaced=1",
        ],
        ["1920x1080"],
        True,
    ),
    "h264422": (
        "mp4",
        ["-pix_fmt", "yuv422p", "-c:v", "libx264", "-profile:v", "high422", "-preset", "veryfast"],
        ["1920x1080", "3840x2160"],
        True,
    ),
    # x264 writes 4:0:0 full range: its software decode, yuvj420p, takes another swscale path to
    # 10-bit than the hardware's NV12, and the rounding differs
    "h264gray": (
        "mp4",
        ["-pix_fmt", "gray", "-c:v", "libx264", "-preset", "veryfast"],
        ["1920x1080", "3840x2160"],
        False,
    ),
    "h264p10": (
        "mp4",
        [
            "-pix_fmt",
            "yuv420p10le",
            "-c:v",
            "libx264",
            "-profile:v",
            "high10",
            "-preset",
            "veryfast",
        ],
        LADDER,
        True,
    ),
    "hevc": ("mp4", ["-pix_fmt", "yuv420p", "-c:v", "libx265"] + X265, LADDER, True),
    "hevc10": ("mp4", ["-pix_fmt", "yuv420p10le", "-c:v", "libx265"] + X265, LADDER, True),
    "hevc10hdr": (
        "mp4",
        ["-pix_fmt", "yuv420p10le", "-c:v", "libx265", "-preset", "ultrafast"]
        + ["-x265-params", f"log-level=0:{HDR10_X265}"],
        ["3840x2160"],
        True,
    ),
    "vp9": ("webm", ["-pix_fmt", "yuv420p", "-c:v", "libvpx-vp9"] + VPX, LADDER, True),
    "vp9p2": (
        "webm",
        ["-pix_fmt", "yuv420p10le", "-c:v", "libvpx-vp9", "-profile:v", "2"] + VPX,
        LADDER,
        True,
    ),
    "vp8": ("webm", ["-c:v", "libvpx", "-deadline", "realtime", "-cpu-used", "8"], LADDER, True),
    "mpeg1": (
        "mpg",
        ["-c:v", "mpeg1video", "-q:v", "3", "-bf", "2"],
        ["1280x720", "1920x1080", *AREA_SIZES, "2560x1440", "3840x2160"],
        False,
    ),
    "mpeg2": (
        "ts",
        ["-c:v", "mpeg2video", "-q:v", "3", "-bf", "2"],
        [
            "1920x1080",
            *AREA_SIZES,
            "2560x1440",
            "3840x2160",
            "4000x2250",
            "4000x3000",
            "4080x4080",
            "7680x4320",
        ],
        False,
    ),
    "mpeg4": (
        "avi",
        ["-c:v", "mpeg4", "-q:v", "3", "-bf", "2"],
        ["1920x1080", *AREA_SIZES, "2048x2048", "2560x1440", "3840x2160", "4080x2160", "4080x4080"],
        False,
    ),
    "h263": (
        "3gp",
        ["-c:v", "h263", "-q:v", "3"],
        ["176x144", "352x288", "704x576", "1408x1152"],
        False,
    ),
    "mjpeg": (
        "avi",
        ["-pix_fmt", "yuvj420p", "-c:v", "mjpeg", "-q:v", "3"],
        [
            # the decoder's smallest, by the datasheet
            "48x48",
            "1920x1080",
            "3840x2160",
            "4096x4096",
            "6000x4000",
            "6144x4096",
            "6144x5120",
            "6144x6144",
            "8192x8192",
        ],
        False,
    ),
    **{
        f"mjpeg{sampling}": ("jpg", [CJPEG, *flags], ["1920x1080"], False)
        for sampling, flags in JPEG_SAMPLINGS.items()
    },
}

# streams FFmpeg cannot encode, or with features its encoders never use, from its FATE suite:
# name: (codec, FATE path, sha256). Each decodes exact or fails, and twice alike.
FATE = "https://fate-suite.ffmpeg.org/"
CONFORMANCE = {
    "vc1-SA00040.vc1": (
        "vc1",
        "vc1/SA00040.vc1",
        "898035e63cfe0ddb1cc2c8749d7dafdfcc1b12fe5dac7e5b65941e6c4e41c860",
    ),
    "vc1-SA00050.vc1": (
        "vc1",
        "vc1/SA00050.vc1",
        "29cf8bebc87be73a1b7a6169aff4c1c36d8891a20c200da7676560fefe3e461c",
    ),
    "vc1-SA10091.vc1": (
        "vc1",
        "vc1/SA10091.vc1",
        "c60a0da89873b40d7e436f1c29757c6cc71f3c51f2ac2ea8c6bd023762c94b6c",
    ),
    "vc1-SA10143.vc1": (
        "vc1",
        "vc1/SA10143.vc1",
        "5d4a5dff66ca45f32331810fc7f845ab0600850a0ee97d05db32572bb588222e",
    ),
    "vc1-SA20021.vc1": (
        "vc1",
        "vc1/SA20021.vc1",
        "99098ebb84a71b3a62d48988d79169843d73dbfd12c620961ab5f1973a9f1b05",
    ),
    "vc1-ilaced_twomv.vc1": (
        "vc1",
        "vc1/ilaced_twomv.vc1",
        "8052c6f2514d7b9e0e6322b4cde440a590cbf6c7e97487336eafa4145ba74d30",
    ),
}

# a hwaccel that cannot be set up fails the decode: timed, a software fallback would time the CPU
HARDWARE_ONLY = ["-nosw_fallback"]
# FFmpeg's v4l2request device with CAPTURE buffers the CPU caches, for a reader on the CPU
CACHED_DEVICE = ["-init_hw_device", "v4l2request=v:,cacheable=1", "-hwaccel_device", "v"]

# engine: decoder input options per codec (None: not offered), how frames come out, encoders
ENGINES = {
    "sunxi": {
        "decode": lambda c: (
            ["-c:v", "mjpeg_v4l2m2m"]
            if base_codec(c) == "mjpeg"
            else HARDWARE_ONLY + ["-hwaccel", "v4l2request"]
        ),
        "scale": lambda c, lines: [
            *HARDWARE_ONLY,
            "-init_hw_device",
            f"v4l2request=v:,capture_max_height={lines}",
            "-hwaccel",
            "v4l2request",
            "-hwaccel_device",
            "v",
        ],
        "download": "",
        "keep": ["-hwaccel_output_format", "drm_prime"],
        "afbc": lambda c: [
            *HARDWARE_ONLY,
            "-init_hw_device",
            f"v4l2request=v:,afbc={10 if c in TEN_BIT else 8}",
            "-hwaccel",
            "v4l2request",
            "-hwaccel_device",
            "v",
            "-hwaccel_output_format",
            "drm_prime",
        ],
        "afbc_formats": r"\b(AS12|AS01)\b",
        "deinterlace": "deinterlace_v4l2m2m",
        "fallback": r"Failed setup for format|hwaccel initialisation returned error|Failed to get a hw"
        r"|-sw_fallback is off",
        "irq": r"cedrus",
        "encoders": {"h264": "h264_v4l2m2m", "mjpeg": "mjpeg_v4l2m2m"},
        # the decoder asked for its largest frame per coded format
        "device": "cedrus-dec",
        "formats": {
            "h264": "S264",
            "h264i": "S264",
            "h264p10": "S264",
            "hevc": "S265",
            "hevc10": "S265",
            "vp9": "VP9F",
            "vp9p2": "VP9F",
            "vp8": "VP8F",
            "mpeg2": "MG2S",
            "mjpeg": "MJPG",
        },
    },
    "rkmpp": {
        "decode": lambda c: (
            [
                "-c:v",
                base_codec(c) + "_rkmpp",
            ]
            if base_codec(c) not in ("mjpeg", "vc1")
            else None
        ),
        "scale": lambda c, lines: ["-capture_max_height", str(lines)]
        + ENGINES["rkmpp"]["decode"](c),
        "download": "hwdownload,format=nv12,",
        "download_formats": {
            "h264422": "nv16",
            "h264i422": "nv16",
            "h264i422frame": "nv16",
            "h264gray": "gray",
        },
        # NV15 frames cannot be downloaded: 10-bit is checked by frames decoded
        "count_only": {"h264p10", "hevc10", "vp9p2"},
        "field_decode": set(INTERLACED),
        "fallback": r"larger than the hardware|unsupported by MPP|for soc \S+ unsupported|Unknown codec",
        "irq": r"vdpu|rkvdec|jpegd|avsd|rkvenc",
        "encoders": {"h264": "h264_rkmpp", "hevc": "hevc_rkmpp"},
    },
    "meson": {
        "decode": lambda c: [
            "-c:v",
            base_codec(c) + "_v4l2m2m",
        ],
        "scale": lambda c, lines: ["-capture_max_height", str(lines)]
        + ENGINES["meson"]["decode"](c),
        "download": "",
        # 10-bit comes out as 8-bit NV12: checked by frames decoded
        "count_only": {"hevc10", "vp9p2"},
        "fallback": r"Could not find a valid device|can't configure decoder",
        "irq": r"vdec|esparser|venc|hcodec",
        "encoders": {"h264": "h264_v4l2m2m", "hevc": "hevc_v4l2m2m"},
    },
}
# mainline Rockchip: stateless V4L2 decode as on sunxi, through rkvdec; stateful encode, rkvenc
ENGINES["rkvdec"] = {
    **ENGINES["sunxi"],
    # MJPEG is jpegd's, stateful; NV15 frames download unpacked to P010 (FFmpeg 0066)
    "decode": lambda c: (
        ["-c:v", "mjpeg_v4l2m2m"]
        if base_codec(c) == "mjpeg"
        else HARDWARE_ONLY + ["-hwaccel", "v4l2request"]
    ),
    "count_only": set(),
    "cacheable": True,
    # rkvdec writes AFBC non-split, Cedrus split
    "afbc_formats": r"\b(AN68|AN6a)\b",
    "irq": r"video-codec",
    "encoders": {"h264": "h264_v4l2m2m", "hevc": "hevc_v4l2m2m", "mjpeg": "mjpeg_v4l2m2m"},
    "device": "rkvdec",
    # each driver's test parameter: its next job times out (1) or faults on the IOMMU (2)
    "fail_next_job": {
        **dict.fromkeys(("h264", "hevc"), "/sys/module/rockchip_vdec/parameters/fail_next_job"),
        **dict.fromkeys(
            ("mpeg2", "mpeg4", "vp8"), "/sys/module/hantro_vpu/parameters/fail_next_job"
        ),
        "mjpeg": "/sys/module/rockchip_jpegd/parameters/fail_next_job",
    },
    "encoder_fail_next_job": "/sys/module/rockchip_rkvenc/parameters/fail_next_job",
    # VDPU2 hangs on a VOP whose time increment resolution is 0, unless the driver refuses it
    "mpeg4_device": "vpu-dec",
    # rkvenc: H.264 at most 2 macroblocks wide and over 1 high hangs the encoder
    "refused_encodes": {"h264": "32x64"},
    "converter_fail_next_job": {
        "rockchip-vdpp": "/sys/module/rockchip_vdpp/parameters/fail_next_job",
    },
    "converters": {
        "rockchip-vdpp": CONVERT_CASES + VDPP_CASES,
        "rockchip-rga": CONVERT_CASES + RGA_CASES,
    },
    "formats": {
        "h264": "S264",
        "h264i": "S264",
        "h264p10": "S264",
        "hevc": "S265",
        "hevc10": "S265",
    },
}

# VA-API through tvb-va-driver, installed: libva finds it by the render node's DRM driver
RENDER_NODE = "/dev/dri/renderD128"
VAAPI_DEVICE = HARDWARE_ONLY + ["-hwaccel", "vaapi", "-hwaccel_device", RENDER_NODE]
ENGINES["vaapi"] = {
    # FFmpeg has no VA-API hwaccel for MPEG-1: it decodes in software
    "decode": lambda c: (
        None if c == "mpeg1" else VAAPI_DEVICE + ["-hwaccel_output_format", "vaapi"]
    ),
    "download": "hwdownload,format=nv12,",
    # a 10-bit picture's surface is P010, or NV12 where the engine narrows: checked by frames
    "count_only": TEN_BIT,
    "fallback": r"Failed setup for format vaapi|hwaccel initialisation returned error"
    r"|Failed to create decode context|Failed to end picture decode|-sw_fallback is off",
    "irq": r"cedrus|vdpu|rkvdec|jpegd|vdec|esparser|venc|hcodec|rkvenc",
    "encoders": {"h264": "h264_vaapi", "hevc": "hevc_vaapi", "mjpeg": "mjpeg_vaapi"},
    # VA encodes surfaces, uploaded; without packed headers a stream has no extradata to mux
    "encode_device": ["-init_hw_device", f"vaapi=va:{RENDER_NODE}", "-filter_hw_device", "va"],
    "encode_input": ["-vf", "format=nv12,hwupload"],
    "encode_raw": True,
    "encode_refused": r"larger than|resolution not supported|No usable encoding profile",
    # every VA engine takes a fixed QP, Cedrus's alone; mjpeg_vaapi reads -global_quality
    "encode_quality": {
        "h264": ["-qp", "20"],
        "hevc": ["-qp", "20"],
        "mjpeg": ["-global_quality", "90"],
    },
}
# the CPU's fastest encoder per codec: a hardware encoder slower than it has no use
CPU_ENCODERS = {
    "h264": ["-c:v", "libx264", "-preset", "ultrafast"],
    "hevc": ["-c:v", "libx265", "-preset", "ultrafast"],
    "mjpeg": ["-c:v", "mjpeg", "-q:v", "3"],
}
# a V4L2 encoder refuses a size it cannot encode, at its format or its buffers
ENCODE_REFUSED = r"larger than|REQBUFS failed: Invalid argument"
ENCODE_SIZES = [
    "1280x720",
    "1920x1080",
    "3840x2160",
    "4096x2304",
    "4096x4096",
    "7680x4320",
    "8192x4320",
    "8192x8192",
    "16384x8640",
]


def sh(cmd, timeout: float | None = CASE_TIMEOUT) -> tuple[int, str, float]:
    """Run a command; its exit code, combined output and wall time."""
    start = time.monotonic()
    try:
        p = subprocess.run(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            errors="replace",
            timeout=timeout,
        )
        return p.returncode, p.stdout, time.monotonic() - start
    except subprocess.TimeoutExpired as e:
        return 124, (e.stdout or "") if isinstance(e.stdout, str) else "", time.monotonic() - start


def pixels(size):
    w, h = size.split("x")
    return int(w) * int(h)


# host: the corpus


def reference_md5(path):
    """The host's software decode of a clip, frame by frame."""
    rc, out, _ = sh(
        [
            "ffmpeg",
            "-v",
            "error",
            "-i",
            str(path),
            "-pix_fmt",
            "yuv420p10le",
            "-f",
            "framemd5",
            "-",
        ],
        timeout=None,
    )
    return md5_lines(out)


def make_clip(source, enc, path):
    """FRAMES of source, encoded by the host's FFmpeg; its exit status."""
    cmd = ["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i", source, "-frames:v", str(FRAMES)]
    return sh(cmd + enc + [str(path)])[0]


def make_jpeg(source, flags, path):
    """One frame of source, encoded by libjpeg's cjpeg with flags; its exit status."""
    ppm = path.with_suffix(".ppm")
    rc = sh(
        ["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i", source, "-frames:v", "1", str(ppm)]
    )[0]
    if not rc:
        rc = sh([CJPEG, *flags, "-outfile", str(path), str(ppm)])[0]
    ppm.unlink(missing_ok=True)
    return rc


def cmd_clips(args):
    """The corpus: each clip encoded by the host's FFmpeg, and its frames as software decodes them.
    A clip is kept while what made it (size, frames, encoder) is the same, and its reference
    decode while the clip's bytes are."""
    if any(enc[0] == CJPEG for _, enc, _, _ in CODECS.values()) and not shutil.which(CJPEG):
        raise SystemExit(f"{CJPEG} not found: libjpeg makes the JPEG samplings FFmpeg cannot")
    CORPUS.mkdir(parents=True, exist_ok=True)
    index = CORPUS / "manifest.json"
    before = json.loads(index.read_text())["clips"] if index.exists() else {}
    manifest = {
        "ffmpeg": sh(["ffmpeg", "-version"])[1].splitlines()[0],
        "frames": FRAMES,
        "clips": {},
    }
    for codec, (ext, enc, sizes, _) in CODECS.items():
        for size in sizes:
            path = CORPUS / f"{codec}-{size}.{ext}"
            source = f"testsrc2=size={size}:rate=30"
            if codec in INTERLACED + INTERLACED_FRAMES:
                source = f"testsrc2=size={size}:rate=60,tinterlace=interleave_top"
            recipe = " ".join([size, str(FRAMES), *enc])
            if codec in INTERLACED + INTERLACED_FRAMES:
                recipe += f" {source}"
            known = before.get(path.name, {})
            if known.get("recipe") != recipe or not path.exists():
                rc = (
                    make_jpeg(source, enc[1:], path)
                    if enc[0] == CJPEG
                    else make_clip(source, enc, path)
                )
                if rc or not path.exists() or not path.stat().st_size:
                    path.unlink(missing_ok=True)
                    print(f"{path.name}: the host's encoder refuses it", file=sys.stderr)
                    continue
            digest = hashlib.sha256(path.read_bytes()).hexdigest()
            if known.get("sha256") == digest and known.get("recipe") == recipe:
                manifest["clips"][path.name] = known
                continue
            manifest["clips"][path.name] = {
                "recipe": recipe,
                "sha256": digest,
                "framemd5": reference_md5(path),
            }
    for name, (codec, fate, digest) in CONFORMANCE.items():
        path = CORPUS / name
        if not path.exists() or hashlib.sha256(path.read_bytes()).hexdigest() != digest:
            urllib.request.urlretrieve(FATE + fate, path)
            if hashlib.sha256(path.read_bytes()).hexdigest() != digest:
                path.unlink()
                raise SystemExit(f"{name}: {FATE + fate} is not the stream pinned")
        known = before.get(name, {})
        manifest["clips"][name] = (
            known
            if known.get("sha256") == digest
            else {"sha256": digest, "framemd5": reference_md5(path)}
        )
    index.write_text(json.dumps(manifest, indent=1))
    print(f"{len(manifest['clips'])} clips in {CORPUS}")


# box: one case at a time

# a framemd5 record; stderr, merged in, can land a log prefix on its line
FRAMEMD5_RECORD = re.compile(r"(?:\d+,\s*){5}([0-9a-f]{32})$")


def md5_lines(out):
    return [m.group(1) for line in out.splitlines() if (m := FRAMEMD5_RECORD.search(line))]


def frames_of(log):
    m = re.findall(r"frame=\s*(\d+)", log)
    return int(m[-1]) if m else 0


def download_filter(eng, codec):
    """The engine's download, in the format the codec's frames come in."""
    fmt = eng.get("download_formats", {}).get(codec)
    return eng["download"].replace("nv12", fmt) if fmt else eng["download"]


def framemd5(ff, opts, clip, download):
    vf = ["-vf", f"{download}format=yuv420p10le"] if download else ["-pix_fmt", "yuv420p10le"]
    rc, out, secs = sh(
        [ff, "-hide_banner", "-nostdin", "-v", "verbose"]
        + opts
        + ["-i", clip]
        + vf
        + ["-f", "framemd5", "-"]
    )
    return md5_lines(out), out


def psnr(ff, opts, clip, download, scale=None):
    left = f"[0:v]{download}format=yuv420p10le,setpts=N[a]"
    right = f"[1:v]{'scale=' + scale.replace('x', ':') + ':flags=area,' if scale else ''}format=yuv420p10le,setpts=N[b]"
    rc, out, _ = sh(
        [ff, "-hide_banner", "-nostdin", "-v", "info"]
        + opts
        + [
            "-i",
            clip,
            "-i",
            clip,
            "-lavfi",
            f"{left};{right};[a][b]psnr=stats_file=-",
            "-f",
            "null",
            "-",
        ]
    )
    return psnr_planes(out)


def psnr_planes(out):
    """The psnr filter's worst luma and worst chroma, and its frame count."""
    per = [
        dict(kv.split(":") for kv in line.split() if ":" in kv)
        for line in out.splitlines()
        if line.startswith("n:")
    ]
    ys = [float(p.get("psnr_y", "inf")) for p in per]
    uvs = [min(float(p.get("psnr_u", "inf")), float(p.get("psnr_v", "inf"))) for p in per]
    return (min(ys) if ys else None), (min(uvs) if uvs else None), len(per)


def irq_count(pattern):
    """The engine's interrupts so far: a case that moves none ran on the CPU."""
    lines = Path("/proc/interrupts").read_text().splitlines()[1:]
    return sum(int(n) for l in lines if re.search(pattern, l) for n in l.split()[1:] if n.isdigit())


def dmesg_lines():
    return sh(["dmesg"])[1].splitlines()


def kernel_errors(before):
    new = dmesg_lines()[len(before) :]
    return [l for l in new if re.search(r"error|fault|timed out|oops|warn", l, re.I)]


def frame_rate(run):
    """Frames a second once running; run(n) times n frames, None if they did not all come out."""
    short = run(FRAMES)
    for n in FPS_FRAMES:
        long_ = None if short is None else run(n)
        if long_ is None:
            return None
        if long_ - short >= FPS_SPAN or n == FPS_FRAMES[-1]:
            return round((n - FRAMES) / (long_ - short), 1) if long_ > short else None


def timed(cmd, frames, spare=0):
    rc, log, secs = sh(cmd)
    return secs if rc == 0 and frames <= frames_of(log) <= frames + spare else None


def repeated(ff, clip, times):
    """The clip back to back in one file, probed once: no end of stream between copies."""
    listing, out = f"{BOX_DIR}/repeat.txt", f"{BOX_DIR}/repeat{os.path.splitext(clip)[1]}"
    Path(listing).write_text(f"file '{clip}'\n" * times)
    sh([ff, "-v", "error", "-y", "-f", "concat", "-safe", "0", "-i", listing, "-c", "copy", out])
    return out


def decode_rate(ff, eng, opts, clip, outputs_per_picture=1):
    keep = eng.get("keep", []) if "-hwaccel" in opts else []
    sync = ["-fps_mode", "passthrough"] if outputs_per_picture > 1 else []
    return frame_rate(
        lambda n: timed(
            [ff, "-hide_banner", "-nostdin", "-stats"]
            + opts
            + keep
            + ["-i", repeated(ff, clip, n // FRAMES)]
            + sync
            + ["-f", "null", "-"],
            n * outputs_per_picture,
        )
    )


def encode_rate(ff, codec_args, size):
    src = f"testsrc2=size={size}:rate=30,format=nv12,loop=loop=-1:size={FRAMES}"
    return frame_rate(
        lambda n: timed(
            [
                ff,
                "-hide_banner",
                "-nostdin",
                "-stats",
                "-f",
                "lavfi",
                "-i",
                src,
                "-frames:v",
                str(n),
            ]
            + codec_args
            + ["-f", "null", "-"],
            n,
            HEADER_PACKETS,
        )
    )


def decode_case(ff, engine, codec, size, clip, ref, timed=True):
    eng = ENGINES[engine]
    opts = eng["decode"](codec)
    if opts is None:
        return {"verdict": "unoffered"}
    exact = CODECS[codec][3] if codec in CODECS else True
    before, irqs = dmesg_lines(), irq_count(eng["irq"])
    r = decode_verdict(ff, eng, codec, clip, opts, exact, ref, before)
    if r["verdict"] == "pass" and irq_count(eng["irq"]) == irqs:
        r["verdict"] = "software"
    if r["verdict"] == "pass" and timed:
        r["fps"] = decode_rate(
            ff, eng, opts, clip, 2 if codec in eng.get("field_decode", ()) else 1
        )
    return r


def readback_case(ff, engine, codec, clip, size):
    """video.md C12: a decoded picture read on the CPU, timed as the decode's frames a second kept in
    the device's buffers against copied to memory; the difference is the copy, in MB a second.
    An engine copies by its download filter, or by FFmpeg's own transfer where it keeps frames
    only when asked to."""
    eng = ENGINES[engine]
    opts = eng["decode"](codec)
    if opts is None:
        return {"verdict": "unoffered"}
    keep = eng.get("keep", []) if "-hwaccel" in opts else []
    download = download_filter(eng, codec)
    if download:
        kept_opts, copied_opts = opts + keep, opts + keep + ["-vf", download.rstrip(",")]
    elif keep and not set(keep) <= set(opts):
        kept_opts, copied_opts = opts + keep, opts
    else:
        return {"verdict": "skipped", "why": "the engine's frames are in memory already"}

    def frames_a_second(args):
        before, vf = (
            (args[: args.index("-vf")], args[args.index("-vf") :]) if "-vf" in args else (args, [])
        )
        return frame_rate(
            lambda n: timed(
                [ff, "-hide_banner", "-nostdin", "-stats"]
                + before
                + ["-i", repeated(ff, clip, n // FRAMES)]
                + vf
                + ["-f", "null", "-"],
                n,
            )
        )

    kept, copied = frames_a_second(kept_opts), frames_a_second(copied_opts)
    if not kept or not copied:
        return {"verdict": "broken", "fps_kept": kept, "fps_copied": copied}
    rec = {"verdict": "pass", "fps_kept": kept, "fps": copied}
    rec["readback_mbs"] = copy_mbs(size, kept, copied)
    # against the plain decode: the cached buffers' upkeep is part of their copy's cost
    if eng.get("cacheable"):
        cached = frames_a_second(copied_opts + CACHED_DEVICE)
        exact = frame_hashes(ff, copied_opts, clip) == frame_hashes(
            ff, copied_opts + CACHED_DEVICE, clip
        )
        rec["fps_cached"] = cached
        rec["readback_cached_mbs"] = copy_mbs(size, kept, cached) if cached else None
        rec["cached_exact"] = exact
        if not cached or not exact:
            rec["verdict"] = "broken"
    return rec


def copy_mbs(size, kept, copied):
    """MB a second of an NV12 picture copied: the time a frame copied takes over one kept."""
    width, height = (int(n) for n in size.split("x"))
    extra = 1 / copied - 1 / kept if kept else 0
    return round(width * height * 3 // 2 / extra / 1e6) if extra > 0 else None


def frame_hashes(ff, opts, clip):
    """Each frame's hash as the CPU reads it: a stale cache line would change one."""
    out = sh(
        [ff, "-hide_banner", "-nostdin", "-v", "error"]
        + opts
        + ["-i", clip, "-pix_fmt", "nv12", "-f", "framemd5", "-"]
    )[1]
    return [line.split()[-1] for line in out.splitlines() if line and not line.startswith("#")]


def field_decode_verdict(ff, eng, clip, opts, source_pictures, before):
    """Compare preserved luma fields in the top-first interlaced corpus."""
    prefix = [ff, "-hide_banner", "-nostdin", "-v", "error"]
    output = ["-enc_time_base", "filter", "-fps_mode", "passthrough", "-f", "framemd5", "-"]
    source_filter = "extractplanes=y,setfield=tff,separatefields"
    # Each progressive output contains two fields. Alternate the preserved field.
    preserved = "select='not(mod(n,4))+eq(mod(n,4),3)'"
    sw_rc, sw_log, _ = sh(prefix + ["-i", clip, "-vf", source_filter] + output)
    hw_rc, hw_log, _ = sh(
        prefix
        + opts
        + ["-i", clip, "-vf", f"{eng['download']}{source_filter},{preserved}"]
        + output
    )
    sw, hw = md5_lines(sw_log), md5_lines(hw_log)
    fell_back = bool(re.search(eng["fallback"], hw_log))
    errs = kernel_errors(before)
    ok = not (sw_rc or hw_rc or errs) and len(sw) == 2 * source_pictures > 0 and hw == sw
    return {
        "frames_hw": len(hw),
        "frames_sw": len(sw),
        "checked": "luma fields",
        "identical": ok,
        "fallback": fell_back,
        "kernel": errs[:3],
        "verdict": "refused" if fell_back else "pass" if ok else "broken",
    }


def decode_verdict(ff, eng, codec, clip, opts, exact, ref, before):
    if codec in eng.get("field_decode", ()):
        return field_decode_verdict(ff, eng, clip, opts, len(ref), before)
    sw = ref
    if codec in eng.get("count_only", ()):
        rc, log, _ = sh(
            [ff, "-hide_banner", "-nostdin", "-v", "verbose"]
            + opts
            + ["-i", clip, "-f", "null", "-"]
        )
        n = frames_of(log)
        fell_back = bool(re.search(eng["fallback"], log))
        ok = not fell_back and n == len(sw) and n > 0
        return {
            "frames_hw": n,
            "frames_sw": len(sw),
            "fallback": fell_back,
            "checked": "frames",
            "kernel": kernel_errors(before)[:3],
            "verdict": "refused" if fell_back else "pass" if ok else "broken",
        }
    hw, log = framemd5(ff, opts, clip, download_filter(eng, codec))
    errs = kernel_errors(before)
    fell_back = bool(re.search(eng["fallback"], log))
    r = {"frames_hw": len(hw), "frames_sw": len(sw), "fallback": fell_back, "kernel": errs[:3]}
    if fell_back:
        r["verdict"] = "refused"
    elif not hw or len(hw) != len(sw):
        r["verdict"] = "broken"
    elif hw == sw or (exact and hw == framemd5(ff, [], clip, "")[0]):
        r.update(verdict="pass", identical=True)
    else:
        y, uv, n = psnr(ff, opts, clip, download_filter(eng, codec))
        r.update(identical=False, psnr_y=y, psnr_uv=uv)
        r["verdict"] = "pass" if not exact and lossy_ok(y, uv) else "broken"
    return r


def lossy_ok(y, uv):
    """A lossy decode near the software one: luma to its floor, chroma to its own where measured."""
    return y is not None and y >= LOSSY_FLOOR_DB and (uv is None or uv >= CHROMA_FLOOR_DB)


def conformance_case(decode):
    """A conformance stream decoded twice: a verdict that changes between runs is flaky."""
    rec = decode()
    if rec["verdict"] != "unoffered" and decode()["verdict"] != rec["verdict"]:
        rec["verdict"] = "flaky"
    return rec


def scale_case(ff, engine, codec, clip, lines):
    """The picture the decoder scales to fit lines, against FFmpeg's area scale to the same size:
    a larger one than asked is the decoder's own limit, recorded."""
    eng = ENGINES[engine]
    if eng["decode"](codec) is None:
        return {"verdict": "unoffered"}
    rc, log, _ = sh(
        [ff, "-hide_banner", "-nostdin", "-v", "verbose"]
        + eng["scale"](codec, lines)
        + ["-i", clip, "-frames:v", "1", "-f", "null", "-"]
    )
    if re.search(eng["fallback"], log):
        return {"verdict": "refused"}
    m = re.findall(r"Stream #0:0.*?Video: .*?(\d{3,5}x\d{3,5})", log)
    out = m[-1] if m else None
    if not out:
        return {"verdict": "broken"}
    if out == clip_size(clip):
        return {"verdict": "full", "out": out}
    if codec in eng.get("count_only", ()):
        return {"verdict": "pass", "out": out, "checked": "size"}
    y, uv, n = psnr(ff, eng["scale"](codec, lines), clip, download_filter(eng, codec), scale=out)
    ok = y is not None and y >= SCALE_FLOOR_DB
    return {"verdict": "pass" if ok else "broken", "asked": lines, "out": out, "psnr_y": y}


def damaged(clip):
    """A copy of clip with CONCEAL_SPAN bytes zeroed from its middle."""
    data = bytearray(Path(clip).read_bytes())
    middle = len(data) // 2
    data[middle : middle + CONCEAL_SPAN] = bytes(min(CONCEAL_SPAN, len(data) - middle))
    out = Path(BOX_DIR) / f"damaged-{Path(clip).name}"
    out.write_bytes(data)
    return str(out)


def conceal_case(ff, engine, codec, clip):
    """A clip damaged mid-stream: the hardware decoder goes on as far as the software one, and
    leaves nothing in the kernel log."""
    eng = ENGINES[engine]
    opts = eng["decode"](codec)
    if opts is None:
        return {"verdict": "unoffered"}
    bad = damaged(clip)
    before = dmesg_lines()
    if codec in eng.get("count_only", ()):
        null = ["-i", bad, "-f", "null", "-"]
        _, log, _ = sh([ff, "-hide_banner", "-nostdin", "-v", "verbose"] + opts + null)
        hw = frames_of(log)
    else:
        frames, log = framemd5(ff, opts, bad, download_filter(eng, codec))
        hw = len(frames)
    errs = kernel_errors(before)
    sw = len(framemd5(ff, [], bad, "")[0])
    os.remove(bad)
    r = {"frames_hw": hw, "frames_sw": sw, "kernel": errs[:3]}
    if re.search(eng["fallback"], log):
        return dict(r, verdict="refused")
    return dict(r, verdict="pass" if hw and hw >= sw and not errs else "broken")


FAILURES = {"timeout": 1, "fault": 2}


def provoked(param: Path, failure: str, job: Callable[[], str]) -> tuple[bool, list[str]]:
    """job, run with its driver's test parameter set: whether it failed as asked, and the kernel
    lines it left. The driver clears the parameter as it takes it, then marks the picture an error
    or logs the timeout or fault."""
    before = dmesg_lines()
    param.write_text(str(FAILURES[failure]))
    log = job()
    kernel = kernel_errors(before)
    marked = "corrupt decoded frame" in log or bool(kernel)
    return param.read_text().strip() == "0" and marked, kernel


def recovery(param: Path, failure: str, job: Callable[[], str], after: Callable[[], str]) -> dict:
    """A job made to fail, then the next one right, no reboot. The failure's kernel lines are
    expected, and kept."""
    if not param.exists():
        return {"verdict": "untested", "why": f"no {param.name}: a debug build's knob"}
    failed, kernel = provoked(param, failure, job)
    verdict = after()
    return {
        "failed": failed,
        "after": verdict,
        "kernel": kernel[:3],
        "verdict": "pass" if failed and verdict == "pass" else "broken",
    }


def failure_case(ff, engine, codec, size, clip, ref, failure):
    cmd = [ff, "-hide_banner", "-nostdin", "-v", "warning"] + ENGINES[engine]["decode"](codec)
    return recovery(
        Path(ENGINES[engine]["fail_next_job"][codec]),
        failure,
        lambda: sh(cmd + ["-i", clip, "-f", "null", "-"])[1],
        lambda: decode_case(ff, engine, codec, size, clip, ref, timed=False)["verdict"],
    )


def encoder_failure_case(ff, engine, codec, encoder, failure):
    def encode() -> str:
        return encode_case(ff, engine, codec, encoder, CONCEAL_SIZE, False, timed=False)["verdict"]

    return recovery(Path(ENGINES[engine]["encoder_fail_next_job"]), failure, encode, encode)


def converter_failure_case(ff, device, param, failure):
    def convert() -> str:
        return convert_case(ff, device, CONVERT_CASES[0])["verdict"]

    return recovery(Path(param), failure, convert, convert)


def afbc_case(ff, engine, codec, clip, ref):
    """Frames asked in the decoder's AFBC format: they cannot be downloaded, so every frame decoded,
    the AFBC capture format in the log and a quiet kernel."""
    eng = ENGINES[engine]
    if eng["decode"](codec) is None:
        return {"verdict": "unoffered"}
    before = dmesg_lines()
    rc, log, _ = sh(
        [ff, "-hide_banner", "-nostdin", "-v", "verbose"]
        + eng["afbc"](codec)
        + ["-i", clip, "-f", "null", "-"]
    )
    n, errs = frames_of(log), kernel_errors(before)
    r = {"frames_hw": n, "frames_sw": len(ref), "kernel": errs[:3]}
    if re.search(eng["fallback"], log):
        r["verdict"] = "refused"
    elif rc or n != len(ref) or errs:
        r["verdict"] = "broken"
    else:
        r["verdict"] = "pass" if re.search(eng["afbc_formats"], log) else "linear"
    return r


def frame_signalling(log):
    """A decoded frame's colour signalling and HDR side data, as showinfo prints them."""
    keep = r"color_(range|space|primaries|trc)|mastering display|content light"
    return sorted(
        re.sub(r"^\[[^]]*\] *", "", line).strip()
        for line in log.splitlines()
        if "showinfo" in line and re.search(keep, line, re.IGNORECASE)
    )


def hdr_case(ff, engine, codec, clip):
    """An HDR10 stream decoded in hardware keeps what a player signals the screen with: BT.2020,
    PQ, the mastering display and the light levels, as software decode gives them."""
    eng = ENGINES[engine]
    opts = eng["decode"](codec)
    if opts is None:
        return {"verdict": "unoffered"}
    show = ["-i", clip, "-frames:v", "1", "-vf", "showinfo", "-f", "null", "-"]
    hw_log = sh([ff, "-hide_banner", "-nostdin", "-v", "info"] + opts + show)[1]
    sw_log = sh([ff, "-hide_banner", "-nostdin", "-v", "info"] + show)[1]
    if re.search(eng["fallback"], hw_log):
        return {"verdict": "refused"}
    hw, sw = frame_signalling(hw_log), frame_signalling(sw_log)
    text = " ".join(hw).lower()
    hdr = all(k in text for k in ("smpte2084", "bt2020", "mastering display", "content light"))
    return {
        "signalling": hw,
        "as_software": hw == sw,
        "verdict": "pass" if hdr and hw == sw else "broken",
    }


def deinterlace_case(ff, engine, codec, clip, rate="field"):
    """A frame per field, or per frame, from the engine's deinterlacer, against bwdif's."""
    eng = ENGINES[engine]
    before = dmesg_lines()
    down, compared = DEINTERLACE_FORMATS[codec]
    order = "setfield=tff," if codec in INTERLACED_FRAMES else ""
    per_input = 2 if rate == "field" else 1
    engine_filter = eng["deinterlace"] + ("" if rate == "field" else f"=rate={rate}")
    # bwdif halves its time base at either rate: one base for both, then frames paired in order
    hw = f"[0:v]{order}{engine_filter},hwdownload,format={down},format={compared},{PAIRED}[a]"
    sw = f"[1:v]{order}bwdif=mode=send_{rate},format={compared},{PAIRED}[b]"
    rc, out, _ = sh(
        [ff, "-hide_banner", "-nostdin", "-v", "info"]
        + eng["decode"](codec)
        + eng["keep"]
        + [
            "-i",
            clip,
            "-i",
            clip,
            "-lavfi",
            f"{hw};{sw};[a][b]psnr=stats_file=-",
            "-f",
            "null",
            "-",
        ]
    )
    y, uv, frames = psnr_planes(out)
    errs = kernel_errors(before)
    r = {
        "frames": frames,
        "wanted": per_input * FRAMES,
        "psnr_y": y,
        "psnr_uv": uv,
        "kernel": errs[:3],
    }
    if re.search(eng["fallback"], out):
        r["verdict"] = "refused"
    elif re.search(DEINTERLACE_UNOFFERED, out):
        r["verdict"] = "unoffered"
    else:
        r["verdict"] = (
            "pass"
            if not rc
            and not errs
            and frames >= per_input * FRAMES - 1
            and min(y or 0, uv or 0) >= DEINTERLACE_FLOOR_DB
            else "broken"
        )
    return r


def vop_refusal_case(engine):
    """VDPU2 refuses a VOP with a zero time increment resolution without starting: the request
    completes, both buffers in error, no interrupt."""
    eng = ENGINES[engine]
    found = v4l2_request.find_device(eng["mpeg4_device"])
    if found is None:
        return {"verdict": "unoffered"}
    before, irqs = dmesg_lines(), irq_count(eng["irq"])
    got = v4l2_request.zero_resolution_vop(*found, REQUEST_TIMEOUT_MS)
    started = irq_count(eng["irq"]) != irqs
    ok = got.completed and got.output_error and got.capture_error and not started
    return {
        "completed": got.completed,
        "errors": [got.output_error, got.capture_error],
        "started": started,
        "kernel": kernel_errors(before)[:3],
        "verdict": "pass" if ok else "broken",
    }


def encode_refusal_case(ff, engine, codec, size):
    """An encode the encoder refuses fails, and leaves nothing in the kernel log."""
    encoder = ENGINES[engine]["encoders"][codec]
    before = dmesg_lines()
    rc, log, _ = sh(
        [ff, "-hide_banner", "-nostdin", "-v", "error", "-f", "lavfi"]
        + ["-i", f"testsrc2=size={size}:rate=30", "-frames:v", str(FRAMES)]
        + ["-pix_fmt", "nv12", "-c:v", encoder, "-f", "null", "-"]
    )
    errs = kernel_errors(before)
    return {
        "refused": rc != 0,
        "kernel": errs[:3],
        "verdict": "pass" if rc and not errs else "broken",
    }


def converter_device(name):
    """The video node a V4L2 converter registers as name, or None."""
    for node in sorted(Path("/sys/class/video4linux").glob("video*")):
        if (node / "name").read_text().strip() == name:
            return f"/dev/{node.name}"
    return None


# a deinterlacer's one-frame-a-frame control: frames in, and the PSNR, visually identical, its
# frames keep to the two-frame run's first-field frames and not to the second's
FRAME_PER_FRAME_CTRL = "frame_per_frame"
FRAME_PER_FRAME_SIZE = (1920, 1080)
FRAME_PER_FRAME_INPUTS = 10
FRAME_PER_FRAME_FLOOR = 40.0


def frame_per_frame_devices():
    """Each video node offering the one-frame-a-frame control."""
    found = []
    for node in sorted(Path("/sys/class/video4linux").glob("video*")):
        _, out, _ = sh(["v4l2-ctl", "-d", f"/dev/{node.name}", "-l"])
        if FRAME_PER_FRAME_CTRL in out:
            found.append(f"/dev/{node.name}")
    return found


def nv12_psnr(a: bytes, b: bytes) -> float:
    err = sum((x - y) ** 2 for x, y in zip(a, b)) / max(len(a), 1)
    return math.inf if err == 0 else 10 * math.log10(255 * 255 / err)


def frame_per_frame_case(ff, device):
    """The same interlaced frames with the control off twice, then on: the two off runs alike, a
    stream not leaning on the one before it; on gives one frame a job, each the off run's
    first-field frame, not its second."""
    width, height = FRAME_PER_FRAME_SIZE
    frame = width * height * 3 // 2
    raw = f"{BOX_DIR}/fields-in.nv12"
    sh(
        [ff, "-v", "error", "-y", "-f", "lavfi", "-i", f"testsrc2=size={width}x{height}"]
        + ["-frames:v", str(FRAME_PER_FRAME_INPUTS), "-pix_fmt", "nv12", "-f", "rawvideo", raw]
    )
    before = dmesg_lines()
    runs = []
    for value in (0, 0, 1):
        out = f"{BOX_DIR}/fields-{value}.nv12"
        rc, _, _ = sh(
            ["v4l2-ctl", "-d", device, f"--set-ctrl={FRAME_PER_FRAME_CTRL}={value}"]
            + [
                f"--set-fmt-video-out=width={width},height={height},pixelformat=NV12,field=interlaced-tb"
            ]
            + [f"--set-fmt-video=width={width},height={height},pixelformat=NV12"]
            + ["--stream-out-mmap", "--stream-mmap", f"--stream-from={raw}", f"--stream-to={out}"]
            + [f"--stream-count={3 * FRAME_PER_FRAME_INPUTS}"]
        )
        data = Path(out).read_bytes() if not rc and os.path.exists(out) else b""
        Path(out).unlink(missing_ok=True)
        runs.append([data[i : i + frame] for i in range(0, len(data) - frame + 1, frame)])
    Path(raw).unlink(missing_ok=True)
    two, again, one = runs
    first = [nv12_psnr(f, two[2 * i]) for i, f in enumerate(one) if 2 * i + 1 < len(two)]
    second = [nv12_psnr(f, two[2 * i + 1]) for i, f in enumerate(one) if 2 * i + 1 < len(two)]
    r = {
        "frames_off": len(two),
        "frames_on": len(one),
        "repeatable": two == again,
        "first_field_psnr": round(min(first), 1) if first else None,
        "second_field_psnr": round(max(second), 1) if second else None,
        "kernel": kernel_errors(before)[:3],
    }
    paired = len(two) == 2 * len(one) and bool(first)
    first_kept = paired and min(first) >= FRAME_PER_FRAME_FLOOR > max(second)
    r["verdict"] = "pass" if first_kept and r["repeatable"] else "broken"
    return r


def pack_10bit(samples: bytes) -> bytes:
    """16-bit samples, 10 bits at the top, packed four to five bytes, the first in the low bits."""
    packed = bytearray()
    for i in range(0, len(samples), 8):
        word = 0
        for k, (value,) in enumerate(struct.iter_unpack("<H", samples[i : i + 8])):
            word |= (value >> P010_SHIFT) << (k * SAMPLE_BITS)
        packed += word.to_bytes(5, "little")
    return bytes(packed)


def convert_case(ff, device, case):
    """One frame through a mem2mem converter against FFmpeg's same conversion: byte-exact, or to
    the case's PSNR floor."""
    width, height = (int(n) for n in case.src.split("x"))
    out_width, out_height = (int(n) for n in case.dst.split("x"))
    raw, ref, out = (f"{BOX_DIR}/convert-{n}.raw" for n in ("in", "ref", "out"))
    src_format = f"width={width},height={height},pixelformat={case.src_fourcc}" + (
        ",quantization=full-range" if case.src_full_range else ""
    )
    before = dmesg_lines()
    made = PACKED_10BIT.get(case.src_fourcc, case.src_pix_fmt)
    sh(
        [ff, "-v", "error", "-y", "-f", "lavfi", "-i", f"testsrc2=size={case.src}"]
        + (["-vf", "scale=out_range=pc"] if case.src_full_range else [])
        + ["-frames:v", "1", "-pix_fmt", made, "-f", "rawvideo", raw]
    )
    sh(
        [ff, "-v", "error", "-y", "-f", "rawvideo", "-pix_fmt", made, "-s", case.src]
        + ["-i", raw]
        + ["-vf", f"{case.ref},format={case.pix_fmt}", "-f", "rawvideo", ref]
    )
    if case.src_fourcc in PACKED_10BIT:
        Path(raw).write_bytes(pack_10bit(Path(raw).read_bytes()))
    rc, _, _ = sh(
        ["v4l2-ctl", "-d", device]
        + [f"--set-ctrl={c}" for c in case.ctrls]
        + [f"--set-fmt-video-out={src_format}"]
        + [f"--set-fmt-video=width={out_width},height={out_height},pixelformat={case.fourcc}"]
        + ["--stream-out-mmap", "--stream-mmap", f"--stream-from={raw}", f"--stream-to={out}"]
        + ["--stream-count=1"]
    )
    got = Path(out).read_bytes() if os.path.exists(out) else b""
    want = Path(ref).read_bytes()
    r = {"bytes": len(got), "kernel": kernel_errors(before)[:3]}
    # a frame of another size than asked: S_FMT gave the capture back changed, past a limit
    if got and len(got) != len(want):
        r["verdict"] = "refused"
    elif rc or len(got) != len(want) or (case.changes and got == want):
        r["verdict"] = "broken"
    elif case.floor is None:
        r["verdict"] = "pass" if got == want else "broken"
    else:
        _, scored, _ = sh(
            [ff, "-hide_banner", "-nostdin", "-f", "rawvideo", "-pix_fmt", case.pix_fmt]
            + ["-s", case.dst, "-i", out, "-f", "rawvideo", "-pix_fmt", case.pix_fmt]
            + ["-s", case.dst, "-i", ref, "-lavfi", "psnr", "-f", "null", "-"]
        )
        score = re.search(r"average:([0-9.]+|inf)", scored)
        r["psnr"] = float(score.group(1)) if score else None
        r["verdict"] = "pass" if r["psnr"] is not None and r["psnr"] >= case.floor else "broken"
    for path in (raw, ref, out):
        Path(path).unlink(missing_ok=True)
    return r


def clip_size(clip):
    found = re.search(r"-(\d+x\d+)\.", os.path.basename(clip))
    if found is None:
        raise ValueError(f"no size in the name {clip}")
    return found.group(1)


def encode_case(ff, engine, codec, encoder, size, time_cpu, timed=True, pix_fmt=None):
    eng = ENGINES[engine]
    out = f"{BOX_DIR}/enc.{codec}" if eng.get("encode_raw") else f"{BOX_DIR}/enc.mkv"
    before, irqs = dmesg_lines(), irq_count(eng["irq"])
    src = ["-f", "lavfi", "-i", f"testsrc2=size={size}:rate=30", "-frames:v", str(FRAMES)]
    quality = ["-q:v", "3"] if codec == "mjpeg" else ["-b:v", "40M"]
    quality = eng.get("encode_quality", {}).get(codec, quality)
    rc, log, secs = sh(
        [ff, "-hide_banner", "-nostdin", "-v", "error", "-y"]
        + eng.get("encode_device", [])
        + src
        + (["-pix_fmt", pix_fmt] if pix_fmt else eng.get("encode_input", ["-pix_fmt", "nv12"]))
        + ["-c:v", encoder]
        + (["-num_output_buffers", str(V4L2_ENCODE_QUEUE)] if encoder.endswith("_v4l2m2m") else [])
        + quality
        + [out]
    )
    errs = kernel_errors(before)
    # a v4l2m2m encoder has no CPU fallback, and may free its interrupt on close
    hardware = irq_count(eng["irq"]) != irqs or encoder.endswith("_v4l2m2m")
    if rc or not os.path.exists(out):
        verdict = (
            "unoffered"
            if "Unknown encoder" in log
            else (
                "refused" if re.search(eng.get("encode_refused", ENCODE_REFUSED), log) else "broken"
            )
        )
        return {
            "verdict": verdict,
            "kernel": errs[:3],
            "log": log.strip().splitlines()[-1:] if log.strip() else [],
        }
    got = frames_of(sh([ff, "-hide_banner", "-nostdin", "-i", out, "-f", "null", "-"])[1])
    _, info, _ = sh([ff, "-hide_banner", "-i", out])
    m = re.search(r"Video: .*?(\d{3,5}x\d{3,5})", info)
    # raw frames on both sides, each written as decoded: compared by index, as timestamps may
    # pair them wrong and a constant rate would repeat or drop one
    raw = lambda inp, name: sh(
        [ff, "-v", "error", "-y"]
        + inp
        + [
            "-fps_mode",
            "passthrough",
            "-frames:v",
            str(FRAMES),
            "-vf",
            "scale=out_range=tv,format=yuv420p",
            "-f",
            "rawvideo",
            f"{BOX_DIR}/{name}.yuv",
        ]
    )
    raw(["-i", out], "enc")
    # the source as the encoder was given it: through its pixel format, a 565 or grey loss and all
    picture = src[:-2]
    if pix_fmt:
        picture = ["-f", "lavfi", "-i", f"testsrc2=size={size}:rate=30,format={pix_fmt}"]
    raw(picture, "src")
    rc, cmp_, _ = sh(
        [ff, "-hide_banner", "-nostdin"]
        + [
            a
            for n in ("enc", "src")
            for a in (
                "-f",
                "rawvideo",
                "-pix_fmt",
                "yuv420p",
                "-s",
                size,
                "-i",
                f"{BOX_DIR}/{n}.yuv",
            )
        ]
        + ["-lavfi", "psnr", "-f", "null", "-"]
    )
    for n in ("enc", "src"):
        os.unlink(f"{BOX_DIR}/{n}.yuv")
    y = re.search(r"PSNR y:([\d.inf]+)", cmp_)
    y = float(y.group(1)) if y else None
    uv = [float(c) for c in re.findall(r"[uv]:([\d.inf]+)", cmp_)[:2]]
    uv = min(uv) if len(uv) == 2 else None
    chroma_ok = uv is not None and uv >= CHROMA_FLOOR_DB
    ok = got == FRAMES and m and m.group(1) == size and y is not None and y >= ENCODE_FLOOR_DB
    ok = ok and chroma_ok
    os.unlink(out)
    verdict = ("pass" if hardware else "software") if ok else "broken"
    r = {
        "verdict": verdict,
        "frames": got,
        "out": m.group(1) if m else None,
        "psnr_y": y,
        "psnr_uv": uv,
        "kernel": errs[:3],
    }
    if verdict == "pass" and timed:
        r["fps"] = encode_rate(ff, ["-c:v", encoder] + quality, size)
        r["cpu_fps"] = (
            encode_rate(ff, CPU_ENCODERS[codec], size)
            if time_cpu and codec in CPU_ENCODERS
            else None
        )
    return r


def ladder(sizes, run, emit, start):
    """Each size once, smallest first, stopping after STOP_AFTER failing in a row; past a pass too
    slow to play, untimed, as a larger size is slower still. The largest pass and the first failure
    again, to catch a case that differs run to run."""
    done, misses, timed = {}, 0, True
    for size in sorted(sizes, key=pixels):
        if misses >= STOP_AFTER:
            break
        start(size)
        began = time.monotonic()
        done[size] = run(size, timed)
        done[size]["secs"] = round(time.monotonic() - began, 1)
        passed = done[size]["verdict"] == "pass"
        misses = 0 if passed else misses + 1
        fps = done[size].get("fps")
        if passed and fps is not None and fps < PLAYABLE_FPS:
            timed = False
    passed = [s for s in done if done[s]["verdict"] == "pass"]
    edges = passed[-1:] + [s for s in done if s not in passed][:1]
    for size in edges:
        if run(size, False)["verdict"] != done[size]["verdict"]:
            done[size]["verdict"] = "flaky"
    for size, rec in done.items():
        emit(dict(rec, size=size))


# the picture a player reads back at 4K, by the codecs a 4K player decodes
READBACK_CODECS, READBACK_SIZE = ("h264", "hevc"), "3840x2160"

# a decode's frames in memory at once, FFmpeg's capture pool beyond the references, and what the
# box keeps beside them: 8192x8192 10-bit, 130 MB a frame, ran a 2 GB box out one time in two
FRAMES_HELD = 12
HEADROOM_MB = 512


def needed_mb(codec, size):
    """The memory a decode of codec at size takes, by its 4:2:0 frames, 10-bit ones packed in 5/4."""
    width, height = (int(n) for n in size.split("x"))
    frame = width * height * 3 // 2
    if codec.endswith(("10", "p10", "p2")):
        frame = frame * 5 // 4
    return frame * FRAMES_HELD >> 20


def available_mb():
    meminfo = Path("/proc/meminfo").read_text() if Path("/proc/meminfo").exists() else ""
    found = re.search(r"^MemAvailable:\s+(\d+) kB", meminfo, re.M)
    return int(found.group(1)) >> 10 if found else 1 << 20


def largest(eng, codec):
    """The largest frame the engine's decoder takes for codec, as TRY_FMT clamps a huge one;
    None when the engine does not say or the format is not offered."""
    fourcc = eng.get("formats", {}).get(codec)
    names = Path("/sys/class/video4linux").glob("*/name")
    device = next(
        (n.parent.name for n in names if n.read_text().strip() == eng.get("device")), None
    )
    if fourcc is None or device is None:
        return None
    asked = f"width=65535,height=65535,pixelformat={fourcc}"
    code, out, _ = sh(["v4l2-ctl", "-d", f"/dev/{device}", f"--try-fmt-video-out={asked}"])
    if code:
        raise RuntimeError(f"v4l2-ctl on /dev/{device}: {out.strip()}")
    return clamped(out, fourcc)


def clamped(out, fourcc):
    """The size v4l2-ctl's TRY_FMT gave back, None when the driver swapped the format."""
    size = re.search(r"Width/Height\s*:\s*(\d+)/(\d+)", out)
    if f"'{fourcc}'" not in out or size is None:
        return None
    return int(size[1]), int(size[2])


def cmd_box(args):
    global BOX_DIR
    BOX_DIR = args.dir
    ff, root = args.ffmpeg, Path(args.dir)
    manifest = json.loads((root / "manifest.json").read_text())["clips"]
    only = re.compile(args.only) if args.only else None
    skip = re.compile(args.skip) if args.skip else None
    emit = lambda rec: print(json.dumps(rec), flush=True)

    def runnable(suite, codec, sizes):
        """The sizes to run; a case --skip names, one past the decoder's largest frame or past the
        box's memory, is recorded, not run."""
        free = available_mb()
        most = None if suite == "encode" else largest(ENGINES[args.engine], codec)
        out, past = [], []
        for size in sizes:
            need = needed_mb(codec, size)
            width, height = (int(n) for n in size.split("x"))
            record = {"suite": suite, "codec": codec, "size": size, "verdict": "skipped"}
            if skip and skip.search(f"{suite}:{codec}-{size}"):
                emit(record)
            elif most and (width > most[0] or height > most[1]):
                past.append(size)
            elif need + HEADROOM_MB > free:
                emit(dict(record, verdict="memory", why=f"needs {need} MB, {free} MB free"))
            else:
                out.append(size)
        if most and past:  # the hardware's bound, one line a codec
            above = f"above {most[0]}x{most[1]}"
            why = f"{len(past)} sizes past the driver's limit"
            emit({"suite": suite, "codec": codec, "size": above, "verdict": "skipped", "why": why})
        return out

    emit(
        {
            "kernel": os.uname().release,
            "engine": args.engine,
            "ffmpeg": sh([ff, "-version"])[1].splitlines()[0],
        }
    )
    after = args.after.split(",") if args.after else []
    start = lambda suite, codec: lambda size: emit({"start": [suite, codec, size]})
    for codec, (ext, _, sizes, _) in CODECS.items():
        if f"decode:{codec}" in after:
            continue
        sizes = [
            s
            for s in sizes
            if f"{codec}-{s}.{ext}" in manifest and not (only and not only.search(f"{codec}-{s}"))
        ]
        clip = lambda s: str(root / f"{codec}-{s}.{ext}")
        if "decode" in args.suite:
            ladder(
                runnable("decode", codec, sizes),
                lambda s, timed: decode_case(
                    ff,
                    args.engine,
                    codec,
                    s,
                    clip(s),
                    manifest[f"{codec}-{s}.{ext}"]["framemd5"],
                    timed,
                ),
                lambda rec: emit(dict(rec, suite="decode", codec=codec)),
                start("decode", codec),
            )
        if "hdr" in args.suite and codec in HDR_CODECS:
            for size in sizes:
                start("hdr", codec)(size)
                emit(
                    dict(
                        hdr_case(ff, args.engine, codec, clip(size)),
                        suite="hdr",
                        size=size,
                        codec=codec,
                    )
                )
        if "readback" in args.suite and codec in READBACK_CODECS and READBACK_SIZE in sizes:
            start("readback", codec)(READBACK_SIZE)
            rec = readback_case(ff, args.engine, codec, clip(READBACK_SIZE), READBACK_SIZE)
            emit(dict(rec, suite="readback", codec=codec, size=READBACK_SIZE))
        eng = ENGINES[args.engine]
        if "afbc" in args.suite and "afbc" in eng:
            for size in runnable("afbc", codec, [s for s in sizes if s in AFBC_SIZES]):
                start("afbc", codec)(size)
                emit(
                    dict(
                        afbc_case(
                            ff,
                            args.engine,
                            codec,
                            clip(size),
                            manifest[f"{codec}-{size}.{ext}"]["framemd5"],
                        ),
                        suite="afbc",
                        codec=codec,
                        size=size,
                    )
                )
        if "deinterlace" in args.suite and "deinterlace" in eng and codec in DEINTERLACE_FORMATS:
            for size in runnable("deinterlace", codec, sizes):
                start("deinterlace", codec)(size)
                for rate in DEINTERLACE_RATES:
                    emit(
                        dict(
                            deinterlace_case(ff, args.engine, codec, clip(size), rate),
                            suite="deinterlace",
                            codec=codec if rate == "field" else f"{codec}:{rate}",
                            size=size,
                        )
                    )
        conceal = [CONCEAL_SIZE] if CONCEAL_SIZE in sizes else []
        if "conceal" in args.suite and runnable("conceal", codec, conceal):
            start("conceal", codec)(CONCEAL_SIZE)
            emit(
                dict(
                    conceal_case(ff, args.engine, codec, clip(CONCEAL_SIZE)),
                    suite="conceal",
                    codec=codec,
                    size=CONCEAL_SIZE,
                )
            )
        fails = codec in eng.get("fail_next_job", {}) and runnable("failure", codec, conceal)
        for failure in FAILURES if "failure" in args.suite and fails else ():
            start("failure", codec)(CONCEAL_SIZE)
            emit(
                dict(
                    failure_case(
                        ff,
                        args.engine,
                        codec,
                        CONCEAL_SIZE,
                        clip(CONCEAL_SIZE),
                        manifest[f"{codec}-{CONCEAL_SIZE}.{ext}"]["framemd5"],
                        failure,
                    ),
                    suite="failure",
                    codec=codec,
                    size=CONCEAL_SIZE,
                    failure=failure,
                )
            )
        if "scale" in args.suite and SCALE_FROM in sizes and runnable("scale", codec, [SCALE_FROM]):
            for lines in SCALE_LINES:
                start("scale", codec)(SCALE_FROM)
                emit(
                    dict(
                        scale_case(ff, args.engine, codec, clip(SCALE_FROM), lines),
                        suite="scale",
                        codec=codec if lines == SCALE_LINES[0] else f"{codec}:{lines}",
                        size=SCALE_FROM,
                    )
                )
    if "conformance" in args.suite:
        for name, (codec, _, _) in CONFORMANCE.items():
            if name not in manifest:
                continue
            if not (root / name).exists():
                raise SystemExit(f"{name}: in the manifest, not deployed")
            start("conformance", codec)(name)
            rec = conformance_case(
                lambda: decode_case(
                    ff, args.engine, codec, name, str(root / name), manifest[name]["framemd5"]
                )
            )
            emit(dict(rec, suite="conformance", codec=codec, size=name))
    if "encode" in args.suite:
        for codec, encoder in ENGINES[args.engine]["encoders"].items():
            if f"encode:{codec}" in after:
                continue
            sizes = [s for s in ENCODE_SIZES if not (only and not only.search(f"{codec}-{s}"))]
            # past the first size the hardware wins, the CPU only gets slower
            cpu = {"timed": True}

            def encode(size, timed):
                r = encode_case(ff, args.engine, codec, encoder, size, cpu["timed"], timed)
                if r.get("fps") and r.get("cpu_fps") and r["fps"] > r["cpu_fps"]:
                    cpu["timed"] = False
                return r

            ladder(
                runnable("encode", codec, sizes),
                encode,
                lambda rec: emit(dict(rec, suite="encode", codec=codec)),
                start("encode", codec),
            )
    eng = ENGINES[args.engine]
    if "input" in args.suite:
        for codec, pix_fmts in ENCODE_INPUT_CODECS.items():
            if codec not in eng["encoders"]:
                continue
            for pix_fmt in pix_fmts:
                start("input", codec)(pix_fmt)
                r = encode_case(
                    ff,
                    args.engine,
                    codec,
                    eng["encoders"][codec],
                    ENCODE_INPUT_SIZE,
                    False,
                    timed=False,
                    pix_fmt=pix_fmt,
                )
                emit(dict(r, suite="input", codec=codec, size=pix_fmt))
    if "refusal" in args.suite:
        if "mpeg4_device" in eng:
            start("refusal", "mpeg4")("vop-zero-resolution")
            emit(
                dict(
                    vop_refusal_case(args.engine),
                    suite="refusal",
                    codec="mpeg4",
                    size="vop-zero-resolution",
                )
            )
        for codec, size in eng.get("refused_encodes", {}).items():
            start("refusal", codec)(size)
            emit(
                dict(
                    encode_refusal_case(ff, args.engine, codec, size),
                    suite="refusal",
                    codec=codec,
                    size=size,
                )
            )
    if "failure" in args.suite and "encoder_fail_next_job" in eng:
        for codec, encoder in eng["encoders"].items():
            for failure in FAILURES:
                start("failure", f"enc-{codec}")(CONCEAL_SIZE)
                rec = encoder_failure_case(ff, args.engine, codec, encoder, failure)
                emit(
                    dict(
                        rec,
                        suite="failure",
                        codec=f"enc-{codec}",
                        size=CONCEAL_SIZE,
                        failure=failure,
                    )
                )
    if "failure" in args.suite:
        for name, param in eng.get("converter_fail_next_job", {}).items():
            device = converter_device(name)
            for failure in FAILURES:
                start("failure", name)(CONVERT_CASES[0].name)
                rec = (
                    converter_failure_case(ff, device, param, failure)
                    if device
                    else {"verdict": "unoffered"}
                )
                emit(
                    dict(
                        rec,
                        suite="failure",
                        codec=name,
                        size=CONVERT_CASES[0].name,
                        failure=failure,
                    )
                )
    if "convert" in args.suite:
        for name, cases in eng.get("converters", {}).items():
            device = converter_device(name)
            for case in cases:
                start("convert", name)(case.name)
                rec = convert_case(ff, device, case) if device else {"verdict": "unoffered"}
                emit(dict(rec, suite="convert", codec=name, size=case.name))
    if "fields" in args.suite:
        for device in frame_per_frame_devices():
            start("fields", os.path.basename(device))("1080")
            rec = frame_per_frame_case(ff, device)
            emit(dict(rec, suite="fields", codec=os.path.basename(device), size="1080"))
    emit({"done": True})


# host: run, report, compare


def cmd_run(args):
    global BOX_DIR
    ssh = [
        "ssh",
        "-o",
        "StrictHostKeyChecking=no",
        "-o",
        "UserKnownHostsFile=/dev/null",
        "-o",
        "LogLevel=ERROR",
        "-o",
        "BatchMode=yes",
        "-o",
        "ServerAliveInterval=5",
        "-o",
        "ServerAliveCountMax=3",
        args.box,
    ]
    scp = [
        "scp",
        "-q",
        "-o",
        "StrictHostKeyChecking=no",
        "-o",
        "UserKnownHostsFile=/dev/null",
        "-o",
        "LogLevel=ERROR",
    ]
    BOX_DIR = subprocess.run(
        ssh + ["mktemp -d /var/tmp/tvb-validate-video.XXXXXX"],
        check=True,
        stdout=subprocess.PIPE,
        text=True,
    ).stdout.strip()
    try:
        send = [str(p) for p in CORPUS.glob("*-*.*")] + [str(CORPUS / "manifest.json")]
        if send:
            subprocess.run(scp + send + [f"{args.box}:{BOX_DIR}/"], check=True)
        here = Path(__file__).parent
        subprocess.run(
            scp + [__file__, str(here / "v4l2_request.py"), f"{args.box}:{BOX_DIR}/"], check=True
        )
        records, after = [], []
        RESULTS.mkdir(parents=True, exist_ok=True)
        out = Path(args.out) if args.out else None

        def save(rec):
            nonlocal out
            records.append(rec)
            out = out or RESULTS / f"{args.box.split('@')[-1]}-{records[0]['kernel']}.json"
            out.write_text(json.dumps(records, indent=1))

        while True:
            remote = f"python3 {BOX_DIR}/video.py box --engine {args.engine} --ffmpeg {args.ffmpeg} --dir {BOX_DIR} " f"--suite {args.suite}" + (
                f" --only='{args.only}'" if args.only else ""
            ) + (
                f" --skip='{args.skip}'" if args.skip else ""
            ) + (
                f" --after {','.join(after)}" if after else ""
            )
            p = subprocess.Popen(ssh + [remote], stdout=subprocess.PIPE, text=True)
            started, finished = None, False
            for line in p.stdout or ():
                rec = json.loads(line)
                if "start" in rec:
                    started = rec["start"]
                    continue
                finished = finished or rec.get("done", False)
                if "kernel" in rec and "engine" in rec and records:
                    continue
                save(rec)
                if "suite" in rec:
                    print(
                        f"{rec['suite']:6} {rec['codec']:8} {rec['size']:10} {rec['verdict']:9} "
                        f"{rec.get('fps') or '':>6} {rec.get('cpu_fps') or '':>6} {rec.get('psnr_y') or ''}",
                        flush=True,
                    )
            p.wait()
            if finished or not started:
                break
            # the box went away mid-case: a hang its watchdog reset, or worse; wait for it, go on
            suite, codec, size = started
            save({"suite": suite, "codec": codec, "size": size, "verdict": "hang"})
            print(f"{suite:6} {codec:8} {size:10} hang, waiting for the box", flush=True)
            after.append(f"{suite}:{codec}")
            for _ in range(60):
                time.sleep(10)
                if (
                    subprocess.run(
                        ssh[:-1] + ["-o", "ConnectTimeout=5", args.box, "true"]
                    ).returncode
                    == 0
                ):
                    break
            else:
                sys.exit("the box did not come back")
        print(f"saved {out}")
    finally:
        try:
            subprocess.run(ssh + [f"rm -rf -- {BOX_DIR}"], timeout=10, check=True)
        except (subprocess.SubprocessError, OSError) as error:
            print(f"cleanup needed on box: {BOX_DIR}: {error}", file=sys.stderr)


def load(path):
    records = json.loads(Path(path).read_text())
    return records[0], [r for r in records if "suite" in r]


def cmd_report(args):
    head, cases = load(args.run)
    print(f"{head['engine']} on {head['kernel']}, {head['ffmpeg']}\n")
    for suite in ("decode", "scale", "encode"):
        rows = [c for c in cases if c["suite"] == suite]
        if not rows:
            continue
        useful = "Beats the CPU" if suite == "encode" else f"At {PLAYABLE_FPS} fps"
        print(
            f"## {suite}\n\n| Codec | Largest passing | fps | {useful} | Past it |\n"
            "| --- | --- | --: | --- | --- |"
        )
        for codec in dict.fromkeys(c["codec"] for c in rows):
            mine = sorted((c for c in rows if c["codec"] == codec), key=lambda c: pixels(c["size"]))
            ok = [c for c in mine if c["verdict"] == "pass"]
            best = ok[-1] if ok else None
            past = [c for c in mine if best and pixels(c["size"]) > pixels(best["size"])] or (
                [] if best else mine
            )
            top = mine[-1]["size"] == best["size"] if best else False
            cell = (
                (
                    f"{best['size']} → {best['out']}"
                    if suite == "scale"
                    else ("≥ " if top else "") + best["size"]
                )
                if best
                else "—"
            )
            if best and best.get("checked"):
                cell += f" ({best['checked']} only)"
            reasons = ", ".join(f"{c['size']} {c['verdict']}" for c in past[:3])
            useful = [c["size"] for c in ok if useful_rate(c)]
            print(
                f"| {codec} | {cell} | {(best or {}).get('fps') or ''} | {(useful or ['—'])[-1]} | {reasons} |"
            )
        print()


def useful_rate(c):
    """A decoder plays a film; an encoder beats the CPU. A size past the climb's timing proves
    neither."""
    fps = c.get("fps")
    if fps is None:
        return False
    if c["suite"] == "encode":
        return not c.get("cpu_fps") or fps > c["cpu_fps"]
    return fps >= PLAYABLE_FPS


MARK = {
    "pass": "✅",
    "full": "▢",
    "linear": "▭",
    "refused": "↷",
    "broken": "❌",
    "flaky": "⚠",
    "unoffered": "·",
    "hang": "💥",
    "software": "🖥",
    "skipped": "⏭",
    "memory": "💾",
    "untested": "❓",
}


def cmd_matrix(args):
    """Every case as a grid, one table a suite, to publish in a board's board.md."""
    head, cases = load(args.run)
    print(f"{head['kernel']}, {head['ffmpeg'].split(' Copyright')[0]}\n")
    for suite in ("decode", "scale", "encode", "afbc", "deinterlace"):
        rows = [c for c in cases if c["suite"] == suite]
        if not rows:
            continue
        sizes = sorted({c["size"] for c in rows}, key=pixels)
        print(f"| {suite} | " + " | ".join(sizes) + " |")
        print("| --- |" + " :-: |" * len(sizes))
        for codec in dict.fromkeys(c["codec"] for c in rows):
            got = {c["size"]: c for c in rows if c["codec"] == codec}
            cell = lambda c: (
                ""
                if not c
                else " ".join(
                    [
                        (
                            "🟠"
                            if c["verdict"] == "pass" and c.get("fps") and not useful_rate(c)
                            else MARK[c["verdict"]]
                        )
                    ]
                    + [str(c[k]) for k in ("out", "fps") if c.get(k)]
                    + ([f"/ {c['cpu_fps']}"] if c.get("cpu_fps") else [])
                )
            )
            print(f"| {codec} | " + " | ".join(cell(got.get(s)) for s in sizes) + " |")
        print()
    print(
        "✅ matches software · ❌ broken · ↷ refused, plays on the CPU · ▢ not shrunk, full size · "
        "⚠ differs run to run · 💥 hung the box · ⏭ skipped, known to hang · 💾 not run, past this box's memory · ❓ not run, no debug build · 🖥 decoded on the CPU · · not offered · "
        f"🟠 decodes under {PLAYABLE_FPS} fps, or encodes slower than the CPU · a number: frames a second, "
        "an encoder's against the CPU's"
    )


def key(c):
    return (c["suite"], c["codec"], c["size"])


# how good each verdict is, for telling a run that got worse
RANK = {
    "pass": 3,
    "full": 2,
    "linear": 2,
    "refused": 2,
    "unoffered": 1,
    "flaky": 1,
    "broken": 0,
    "hang": -1,
    "software": 1,
}
# verdicts recorded for a case never run: known to hang, past the memory, or no test knob
NOT_RUN = ("skipped", "memory", "untested")
# verdicts that are a failure at any size: wrong frames, a hang, or no hardware at all
FAILING = {"broken", "hang", "flaky", "software"}


def worse(old, new):
    """Each case of new that did worse than in old: a lower verdict, or 1 dB less luma PSNR."""
    before = {key(c): c for c in old}
    out = []
    for c in new:
        o = before.get(key(c))
        if not o or c["verdict"] in NOT_RUN:
            continue
        if RANK.get(c["verdict"], 0) < RANK.get(o["verdict"], 0):
            out.append(f"{' '.join(key(c))}: {o['verdict']} -> {c['verdict']}")
        elif o.get("psnr_y") and c.get("psnr_y") and c["psnr_y"] < o["psnr_y"] - 1:
            out.append(f"{' '.join(key(c))}: {o['psnr_y']:.1f} -> {c['psnr_y']:.1f} dB")
    return out


def cmd_compare(args):
    _, old = load(args.old)
    _, new = load(args.new)
    worse_cases = worse(old, new)
    print("\n".join(worse_cases) or "nothing worse")
    sys.exit(1 if worse_cases else 0)


def main():
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("clips")
    for name in ("run", "box"):
        p = sub.add_parser(name)
        p.add_argument("--engine", choices=ENGINES, required=True)
        p.add_argument("--ffmpeg", default="ffmpeg9")
        suites = "decode,scale,conceal,failure,encode,input,afbc,deinterlace,refusal,convert,fields,readback,hdr"
        p.add_argument("--suite", default=suites)
        p.add_argument("--only", help="a regex over <codec>-<size>")
        p.add_argument(
            "--skip",
            help="a regex over <suite>:<codec>-<size>: cases known to hang, recorded, not run",
        )
        if name == "run":
            p.add_argument("--box", required=True)
            p.add_argument("--out")
        else:
            p.add_argument("--dir", required=True)
            p.add_argument("--after", help="suite:codec pairs already run, comma-separated")
    sub.add_parser("report").add_argument("run")
    sub.add_parser("matrix").add_argument("run")
    p = sub.add_parser("compare")
    p.add_argument("old")
    p.add_argument("new")
    args = ap.parse_args()
    {
        "clips": cmd_clips,
        "run": cmd_run,
        "box": cmd_box,
        "report": cmd_report,
        "matrix": cmd_matrix,
        "compare": cmd_compare,
    }[args.cmd](args)


if __name__ == "__main__":
    main()
