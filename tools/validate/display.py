#!/usr/bin/env python3
"""The display path on a running box: its planes, their composition and pace, its colour stages
and the HDMI output.

Runs on the box, as root, unattended, with HDMI unplugged, since a real screen's EDID gets in the
synthetic ones' way, and nothing else on the display (no compositor, no player):

    python3 display.py

A synthetic HDR10/HLG EDID stands in through debugfs for the run; then the connector meets SDR,
HDR10, HLG and HDR10-and-HLG screens the same way. The connector's own EDID and force state come
back after.

Checks, each skipped where the box lacks what it needs:
  - planes: every plane the CRTC offers, listed (type, zpos, alpha, modifiers, formats), a YUV
    video plane with an interface plane that can sit above it;
  - compose: the interface over the scaled video plane, opaque and transparent, by writeback;
  - planes-all: every plane at once, each in its own cell and zpos, the YUV ones scaled, then a YUV
    plane over another, by writeback;
  - rotation: each transform a plane offers puts a quadrant pattern's colours where it should,
    by writeback, or is refused;
  - lut: a plane's SUNXI_CDC_LUT3D refuses malformed blobs, and tables (identity, a channel mix,
    an inversion switched while active, held across flips, then the tone mappings HDR10 to SDR,
    HLG to SDR, SDR to PQ and HLG to PQ on 64 YUV patches) come back by writeback within two 8-bit
    codes of the same table interpolated trilinearly;
  - sdr2hdr: the CRTC's HDR_EXT_DATA refuses a short blob, then Rockchip's SDR to HDR stage takes
    seven colours to PQ and to HLG within two 8-bit codes of BT.2408's mapping, by writeback;
  - colorop: a plane's SDR-to-PQ and SDR-to-HLG color pipeline against BT.2408's SDR in HDR by
    writeback, and its refusals: part bypassed, a negative coefficient, two planes' pipelines apart;
  - scope: each stage under the interface, the planes it maps: its own alone, or the whole output;
  - pacing: a minute of nonblocking commits, each after the last flip event, the video plane
    scaled and an idle plane in every commit, as a player makes them: none refused;
  - hdmi: SDR, PQ and HLG with max bpc 8 and 10 give the InfoFrames and colorimetry the dw-hdmi
    registers then hold;
  - hdr10plus: the CRTC's HDR10PLUS_VSIF refuses a short payload and a wrong OUI, then a payload,
    a second one and none (HDMI's own VSIF back) switch the dw-hdmi VSIF in place, with no mode set,
    and a mode set keeps it;
  - underruns: the CRTC's TCON underflow count holds still over a static picture;
  - rating: a synthetic HDMI 2.0 screen offering 8K to 720p at 24 to 120 Hz; each mode the driver
    keeps, 10 s at a player's pace with the video at the mode's size, sustained with every flip on
    time, no underrun and nothing new in the kernel log; the verdicts, the largest mode and the
    fastest;
  - sinks: each synthetic screen gets HDR for the EOTFs it lists; what the box sends for the rest
    is recorded, as are the mappings the engine did and those left to the GPU.
Exit 0 all passed, 1 a failure, 77 nothing to check.
"""

import argparse
import contextlib
import ctypes
import errno
import fcntl
import glob
import math
import mmap
import os
import select
import re
import struct
from pathlib import Path
import subprocess
import sys
import time

# ---- DRM uAPI, as drm.h and drm_mode.h lay it out
u32, u64, u16 = ctypes.c_uint32, ctypes.c_uint64, ctypes.c_uint16


def S(name, fields):
    return type(name, (ctypes.Structure,), {"_fields_": fields})


ClientCap = S("ClientCap", [("capability", u64), ("value", u64)])
CardRes = S(
    "CardRes",
    [
        ("fbs", u64),
        ("crtcs", u64),
        ("connectors", u64),
        ("encoders", u64),
        ("count_fbs", u32),
        ("count_crtcs", u32),
        ("count_connectors", u32),
        ("count_encoders", u32),
        ("min_w", u32),
        ("max_w", u32),
        ("min_h", u32),
        ("max_h", u32),
    ],
)
ModeInfo = S(
    "ModeInfo",
    [
        ("clock", u32),
        ("hdisplay", u16),
        ("hsync_start", u16),
        ("hsync_end", u16),
        ("htotal", u16),
        ("hskew", u16),
        ("vdisplay", u16),
        ("vsync_start", u16),
        ("vsync_end", u16),
        ("vtotal", u16),
        ("vscan", u16),
        ("vrefresh", u32),
        ("flags", u32),
        ("type", u32),
        ("name", ctypes.c_char * 32),
    ],
)
Crtc = S(
    "Crtc",
    [
        ("set_connectors", u64),
        ("count_connectors", u32),
        ("crtc_id", u32),
        ("fb_id", u32),
        ("x", u32),
        ("y", u32),
        ("gamma_size", u32),
        ("mode_valid", u32),
        ("mode", ModeInfo),
    ],
)
Connector = S(
    "Connector",
    [
        ("encoders", u64),
        ("modes", u64),
        ("props", u64),
        ("prop_values", u64),
        ("count_modes", u32),
        ("count_props", u32),
        ("count_encoders", u32),
        ("encoder_id", u32),
        ("connector_id", u32),
        ("connector_type", u32),
        ("connector_type_id", u32),
        ("connection", u32),
        ("mm_width", u32),
        ("mm_height", u32),
        ("subpixel", u32),
        ("pad", u32),
    ],
)
PlaneRes = S("PlaneRes", [("planes", u64), ("count_planes", u32)])
Plane = S(
    "Plane",
    [
        ("plane_id", u32),
        ("crtc_id", u32),
        ("fb_id", u32),
        ("possible_crtcs", u32),
        ("gamma_size", u32),
        ("count_format_types", u32),
        ("format_types", u64),
    ],
)
ObjProps = S(
    "ObjProps",
    [("props", u64), ("values", u64), ("count_props", u32), ("obj_id", u32), ("obj_type", u32)],
)
Property = S(
    "Property",
    [
        ("values", u64),
        ("enum_blobs", u64),
        ("prop_id", u32),
        ("flags", u32),
        ("name", ctypes.c_char * 32),
        ("count_values", u32),
        ("count_enum_blobs", u32),
    ],
)
PropEnum = S("PropEnum", [("value", u64), ("name", ctypes.c_char * 32)])
CreateBlob = S("CreateBlob", [("data", u64), ("length", u32), ("blob_id", u32)])
GetBlob = S("GetBlob", [("blob_id", u32), ("length", u32), ("data", u64)])
BlobId = S("BlobId", [("blob_id", u32)])
CreateDumb = S(
    "CreateDumb",
    [
        ("height", u32),
        ("width", u32),
        ("bpp", u32),
        ("flags", u32),
        ("handle", u32),
        ("pitch", u32),
        ("size", u64),
    ],
)
MapDumb = S("MapDumb", [("handle", u32), ("pad", u32), ("offset", u64)])
FbId = S("FbId", [("fb_id", u32)])
DestroyDumb = S("DestroyDumb", [("handle", u32)])
FbCmd2 = S(
    "FbCmd2",
    [
        ("fb_id", u32),
        ("width", u32),
        ("height", u32),
        ("pixel_format", u32),
        ("flags", u32),
        ("handles", u32 * 4),
        ("pitches", u32 * 4),
        ("offsets", u32 * 4),
        ("modifier", u64 * 4),
    ],
)
Atomic = S(
    "Atomic",
    [
        ("flags", u32),
        ("count_objs", u32),
        ("objs", u64),
        ("count_props", u64),
        ("props", u64),
        ("values", u64),
        ("reserved", u64),
        ("user_data", u64),
    ],
)


def iowr(nr, struct_type):
    return (3 << 30) | (ctypes.sizeof(struct_type) << 16) | (ord("d") << 8) | nr


IOCTL = {
    "cap": iowr(0x0D, ClientCap),
    "res": iowr(0xA0, CardRes),
    "crtc": iowr(0xA1, Crtc),
    "connector": iowr(0xA7, Connector),
    "planes": iowr(0xB5, PlaneRes),
    "plane": iowr(0xB6, Plane),
    "props": iowr(0xB9, ObjProps),
    "property": iowr(0xAA, Property),
    "blob": iowr(0xBD, CreateBlob),
    "unblob": iowr(0xBE, BlobId),
    "getblob": iowr(0xAC, GetBlob),
    "dumb": iowr(0xB2, CreateDumb),
    "map": iowr(0xB3, MapDumb),
    "addfb2": iowr(0xB8, FbCmd2),
    "rmfb": iowr(0xAF, FbId),
    "destroy-dumb": iowr(0xB4, DestroyDumb),
    "atomic": iowr(0xBC, Atomic),
}
CAP_ATOMIC, CAP_WRITEBACK = 3, 5
OBJ_CRTC, OBJ_CONNECTOR, OBJ_PLANE = 0xCCCCCCCC, 0xC0C0C0C0, 0xEEEEEEEE
CONNECTOR_HDMIA, CONNECTOR_WRITEBACK = 11, 18
PAGE_FLIP_EVENT, TEST_ONLY, NONBLOCK, ALLOW_MODESET = 0x1, 0x100, 0x200, 0x400
PROP_IMMUTABLE = 0x4
# set where a plane has them, as a YUV plane without COLOR_ENCODING takes BT.709
OPTIONAL_PLANE_PROPS = {"COLOR_ENCODING", "COLOR_RANGE", "EOTF", "zpos"}
# dw-hdmi's input video mapping and colour depth registers
TX_INVID0, VP_PR_CD = 0x0200, 0x0801
# max bpc 10 on a 4:2:0-capable screen: 10-bit RGB where it fits HDMI 2.0, 10-bit YCbCr 4:2:0 at
# 4K60 where 10-bit RGB would need 742.5 MHz; (AVI format, TX_INVID0, VP_PR_CD)
DEEP_COLOUR_CASES = [(1920, ("RGB", 0x03, 0x50)), (3840, ("YCbCr 4:2:0", 0x0B, 0x50))]
# a colour away from both ends, and the CRTC gamma curves it goes through
GAMMA_SIGNAL = (105, 174, 49)
GAMMA_TABLES = (
    ("identity", lambda v: v),
    ("inversion", lambda v: 1 - v),
    ("square", lambda v: v * v),
)
# a window's region plane, by the vendor's name: Esmart0-win1 is Esmart0-win0's region 1
REGION_NAME = re.compile(r"^(.*-win)([1-9])$")
REGION_RGBS = [(200, 40, 40), (40, 200, 40), (40, 40, 200), (200, 200, 40)]
# DRM's 3D frame packing mode flag; dw-hdmi's vendor InfoFrame payload, active lines and the
# payload frame packing sends: HDMI_Video_Format 3D, 3D_Structure 0
MODE_FLAG_3D_MASK, MODE_FLAG_3D_FRAME_PACKING = 0x1F << 14, 1 << 14
CAP_STEREO_3D = 1
# DRM's plane color pipelines: their client cap, the colorop object, PQ 125's 1.0 in nits, and
# S31.32's one and sign
CAP_COLOR_PIPELINE, OBJ_COLOROP = 7, 0xFAFAFAFA
PQ_125_UNIT_NITS = 80
S31_32_ONE, S31_32_SIGN = 1 << 32, 1 << 63
# a plane's SDR-to-HDR pipeline, then its last curve by target
SDR_TO_HDR = ("Gamma 2.2", "3x4 Matrix", "Multiplier")
HDR_CURVES = {"PQ": "PQ 125 Inverse EOTF", "HLG": "HLG Inverse EOTF"}
FC_VSDPAYLOAD0, FC_VSDPAYLOAD1, FC_INVACTV0, FC_INVACTV1 = 0x1032, 0x1033, 0x1005, 0x1006
FRAME_PACKING_PAYLOAD = (0x40, 0x00)
# dw-hdmi's packetizer: the 4:2:2 packing, 16, 20 or 24 bits
VP_REMAP = 0x0803
# (width at 60 Hz, "color format" asked, max bpc) -> (AVI format, VP_PR_CD depth, VP_REMAP): 4:4:4
# at 10 bits where its TMDS rate fits, 8 at 4K60; 4:2:2 20-bit at the pixel clock, 4K60 included
COLOR_FORMAT_CASES = [
    ((1920, "YUV 4:4:4", 10), ("YCbCr 4:4:4", 5, 0)),
    ((1920, "YUV 4:4:4", 8), ("YCbCr 4:4:4", 4, 0)),
    ((1920, "YUV 4:2:2", 10), ("YCbCr 4:2:2", 0, 1)),
    ((3840, "YUV 4:2:2", 10), ("YCbCr 4:2:2", 0, 1)),
    ((3840, "YUV 4:4:4", 10), ("YCbCr 4:4:4", 4, 0)),
    ((3840, "RGB", 10), ("RGB", 4, 0)),
]
# dw-hdmi's audio: I2S lanes enabled, AVI-style channel count, sample packet layout
AUD_CONF0, FC_AUDICONF0, FC_AUDSCONF = 0x3100, 0x1025, 0x1063
# (channels, Hz) to a screen taking 8-channel LPCM: stereo, 5.1, 7.1, and 7.1 at the top rate
HDMI_AUDIO_CASES = [(2, 48000), (6, 48000), (8, 48000), (8, 192000)]
PLAY_SECONDS = 3
PLAY_SLACK = 0.3
# where the driver picks the bus format itself, the check is judged; elsewhere recorded
DEEP_COLOUR_HDMI = b"rockchip,rk3528-dw-hdmi"
# what an atomic check answers for a state the driver cannot show
REFUSED = {errno.EINVAL, errno.ERANGE}
# the pattern's quadrants, (column, row)
QUADRANT_RGB = {
    (0, 0): (200, 40, 40),
    (1, 0): (40, 200, 40),
    (0, 1): (40, 40, 200),
    (1, 1): (200, 200, 40),
}
# a transform: whether it swaps the source's sides, and where each source quadrant lands on screen;
# DRM's rotations turn counter-clockwise
ROTATIONS = {
    "rotate-0": (False, {(0, 0): (0, 0), (1, 0): (1, 0), (0, 1): (0, 1), (1, 1): (1, 1)}),
    "rotate-180": (False, {(0, 0): (1, 1), (1, 0): (0, 1), (0, 1): (1, 0), (1, 1): (0, 0)}),
    "reflect-x": (False, {(0, 0): (1, 0), (1, 0): (0, 0), (0, 1): (1, 1), (1, 1): (0, 1)}),
    "reflect-y": (False, {(0, 0): (0, 1), (1, 0): (1, 1), (0, 1): (0, 0), (1, 1): (1, 0)}),
    "rotate-90": (True, {(0, 0): (0, 1), (1, 0): (0, 0), (0, 1): (1, 1), (1, 1): (1, 0)}),
    "rotate-270": (True, {(0, 0): (1, 0), (1, 0): (1, 1), (0, 1): (0, 0), (1, 1): (0, 1)}),
}
PLANE_TYPES = {0: "overlay", 1: "primary", 2: "cursor"}
# AFBC: Arm's 16x16 superblock layout, no YTR or split; a 16-byte header a superblock, then its 16
# 4x4 sub-blocks, size code 1 for one stored uncompressed
AFBC_16X16 = 0x08 << 56 | 1
AFBC_SIDE, AFBC_BLOCK, AFBC_HEADER_BYTES, AFBC_UNCOMPRESSED = 256, 16, 16, 1
# lines of it shown, as a player crops 1080 from 1088: not a whole number of superblocks
AFBC_CROPPED_LINES = 240
FB_MODIFIERS = 1 << 1
PACING_SECONDS = 60
# a session's units, in the order they let the display go: the display manager, then the seat
# daemon, which keeps DRM master on the card with no session
SESSION_UNITS = ("greetd.service", "seatd.service")
RUNG_SECONDS = 10
# Kernel log lines that only a screen absent from the bus raises, not a box falling behind.
NO_SCREEN_NOISE = re.compile(r"scdc|ddc|i2c|edid|hpd|hot.?plug|phy", re.I)
# Kernel log lines from buses and radios off the display path: a rung falls on its own lines only.
OFF_PATH_NOISE = re.compile(r"usb\d*-port|\bSKW|wlan\d|\bmmc\d|Bluetooth", re.I)
PLANE_STATE_LINE = re.compile(r"^plane\[(\d+)\]: (\S+)", re.M)
EBUSY = 16
XRGB8888, ARGB8888, NV12, P010 = 0x34325258, 0x34325241, 0x3231564E, 0x30313050
RGB888, RGB565 = 0x34324752, 0x36314752
PACKED_BPP = {RGB888: 24, RGB565: 16}
# the writeback's YCbCr of an RGB output, measured: no property says it
WRITEBACK_RGB_TO_YUV = 601
LUT_POINTS = 17
TOLERANCE = 2
# a 5-bit channel read back: half a step of the 8-bit code it stands for
RGB565_TOLERANCE = TOLERANCE + 255 // 31 // 2


def display_card():
    """The DRM card with connectors: a GPU loaded first takes card0."""
    names = sorted(Path("/sys/class/drm").glob("card*-*"))
    return f"/dev/dri/{names[0].name.split('-')[0]}" if names else "/dev/dri/card0"


class Drm:
    def __init__(self, path):
        self.fd = os.open(path, os.O_RDWR)
        self.prop_ids = {}

    def call(self, name, arg):
        fcntl.ioctl(self.fd, IOCTL[name], arg)
        return arg

    def ids(self, count):
        return (u32 * max(count, 1))()

    def props(self, obj, kind):
        p = self.call("props", ObjProps(obj_id=obj, obj_type=kind))
        ids, values = self.ids(p.count_props), (u64 * max(p.count_props, 1))()
        self.call(
            "props",
            ObjProps(
                props=ctypes.addressof(ids),
                values=ctypes.addressof(values),
                count_props=p.count_props,
                obj_id=obj,
                obj_type=kind,
            ),
        )
        result = {}
        for i in range(p.count_props):
            prop = self.call("property", Property(prop_id=ids[i]))
            result[prop.name.decode()] = (ids[i], values[i], prop)
        return result

    def enums(self, prop):
        """An enum or bitmask property's names, each to its value or, for a bitmask, its bit."""
        enums = (PropEnum * prop.count_enum_blobs)()
        self.call(
            "property",
            Property(
                prop_id=prop.prop_id,
                enum_blobs=ctypes.addressof(enums),
                count_enum_blobs=prop.count_enum_blobs,
            ),
        )
        return {e.name.decode(): e.value for e in enums}

    def enum_value(self, prop, name):
        return self.enums(prop)[name]

    def blob(self, data):
        buffer = ctypes.create_string_buffer(data, len(data))
        return self.call(
            "blob", CreateBlob(data=ctypes.addressof(buffer), length=len(data))
        ).blob_id

    def unblob(self, blob_id):
        self.call("unblob", BlobId(blob_id=blob_id))

    def getblob(self, blob_id):
        length = self.call("getblob", GetBlob(blob_id=blob_id)).length
        data = ctypes.create_string_buffer(length)
        self.call("getblob", GetBlob(blob_id=blob_id, length=length, data=ctypes.addressof(data)))
        return data.raw

    def prop_range(self, prop):
        values = (u64 * 2)()
        self.call(
            "property",
            Property(prop_id=prop.prop_id, values=ctypes.addressof(values), count_values=2),
        )
        return values[0], values[1]

    def wait_flip(self, timeout=1.0):
        """True once a page-flip event arrives on the card."""
        ready, _, _ = select.select([self.fd], [], [], timeout)
        return bool(ready) and len(os.read(self.fd, 4096)) > 0

    def commit(self, changes, flags=ALLOW_MODESET):
        """changes: {object id: {property id: value}}; an error comes back as its errno."""
        objs = list(changes)
        counts = (u32 * len(objs))(*[len(changes[o]) for o in objs])
        flat = [(p, v) for o in objs for p, v in changes[o].items()]
        props = (u32 * len(flat))(*[p for p, _ in flat])
        values = (u64 * len(flat))(*[v & (2**64 - 1) for _, v in flat])
        objarr = (u32 * len(objs))(*objs)
        try:
            self.call(
                "atomic",
                Atomic(
                    flags=flags,
                    count_objs=len(objs),
                    objs=ctypes.addressof(objarr),
                    count_props=ctypes.addressof(counts),
                    props=ctypes.addressof(props),
                    values=ctypes.addressof(values),
                ),
            )
            return 0
        except OSError as error:
            return error.errno


class Buffer:
    handle = fb = 0  # none yet: an allocation that fails leaves nothing to free

    def __init__(self, drm, width, height, fourcc, unpadded=False):
        """unpadded: rows width pixels apart, as a writeback engine without a stride writes them,
        inside the dumb buffer, whose rows are at least as long."""
        self.drm = drm
        yuv = fourcc in (NV12, P010)
        bpp = 16 if fourcc == P010 else 8 if fourcc == NV12 else PACKED_BPP.get(fourcc, 32)
        d = drm.call(
            "dumb", CreateDumb(height=height * 3 // 2 if yuv else height, width=width, bpp=bpp)
        )
        self.handle = d.handle
        pitch = width * bpp // 8 if unpadded else d.pitch
        self.width, self.height, self.pitch, self.format = width, height, pitch, fourcc
        handles, pitches, offsets = (
            [d.handle, d.handle if yuv else 0],
            [pitch, pitch if yuv else 0],
            [0, pitch * height if yuv else 0],
        )
        cmd = FbCmd2(width=width, height=height, pixel_format=fourcc)
        for i in range(2):
            cmd.handles[i], cmd.pitches[i], cmd.offsets[i] = handles[i], pitches[i], offsets[i]
        self.fb = drm.call("addfb2", cmd).fb_id
        offset = drm.call("map", MapDumb(handle=d.handle)).offset
        self.map = mmap.mmap(
            drm.fd, d.size, mmap.MAP_SHARED, mmap.PROT_READ | mmap.PROT_WRITE, offset=offset
        )

    def __del__(self):
        """Its memory back once the check that made it lets it go: without the display's IOMMU every
        buffer is contiguous, and a run's buffers outgrow the CMA pool. A closed card freed it."""
        try:
            if self.fb:
                self.drm.call("rmfb", FbId(fb_id=self.fb))
            if self.handle:
                self.drm.call("destroy-dumb", DestroyDumb(handle=self.handle))
        except OSError:
            pass

    def fill_rgb(self, rgb, alpha=255, rows=None):
        row = struct.pack("<I", alpha << 24 | rgb[0] << 16 | rgb[1] << 8 | rgb[2]) * self.width
        for y in rows or range(self.height):
            self.map[y * self.pitch : y * self.pitch + len(row)] = row

    def fill_quadrants(self, rgbs):
        """XRGB8888, each quadrant one colour: rgbs[(column, row)]."""
        pixel = lambda rgb: struct.pack("<I", 0xFF << 24 | rgb[0] << 16 | rgb[1] << 8 | rgb[2])
        half = self.width // 2
        for qy in (0, 1):
            row = pixel(rgbs[(0, qy)]) * half + pixel(rgbs[(1, qy)]) * (self.width - half)
            for y in range(qy * self.height // 2, (qy + 1) * self.height // 2):
                self.map[y * self.pitch : y * self.pitch + len(row)] = row

    def fill_yuv(self, code):
        """The whole NV12 picture one 8-bit Y'CbCr code."""
        for y in range(self.height):
            self.map[y * self.pitch : y * self.pitch + self.width] = bytes([code[0]]) * self.width
        for y in range(self.height // 2):
            row = (self.height + y) * self.pitch
            self.map[row : row + self.width] = bytes([code[1], code[2]]) * (self.width // 2)

    def fill_patches(self, codes, grid, side):
        """YUV codes, row-major over a grid of square patches; P010 codes are 10-bit."""
        wide = self.format == P010
        pack = (lambda c: struct.pack("<H", c << 6)) if wide else (lambda c: bytes([c]))
        for py in range(grid):
            for y in range(side):
                luma = b"".join(pack(codes[py * grid + px][0]) * side for px in range(grid))
                row = py * side + y
                self.map[row * self.pitch : row * self.pitch + len(luma)] = luma
            for y in range(side // 2):
                chroma = b"".join(
                    (pack(codes[py * grid + px][1]) + pack(codes[py * grid + px][2])) * (side // 2)
                    for px in range(grid)
                )
                row = self.height + py * side // 2 + y
                self.map[row * self.pitch : row * self.pitch + len(chroma)] = chroma

    def pixel(self, x, y, matrix=709):
        """R'G'B' 8-bit; an NV12 capture read as limited range by matrix, BT.709 for a YCbCr output."""
        if self.format == NV12:
            luma = self.map[y * self.pitch + x]
            chroma = (self.height + y // 2) * self.pitch + x // 2 * 2
            codes = (luma, self.map[chroma], self.map[chroma + 1])
            return to8(yuv_to_rgb([c * 4 / 1023 for c in codes], matrix))
        if self.format == RGB888:  # memory order B, G, R
            b, g, r = self.map[y * self.pitch + x * 3 : y * self.pitch + x * 3 + 3]
            return r, g, b
        if self.format == RGB565:
            (value,) = struct.unpack_from("<H", self.map, y * self.pitch + x * 2)
            r, g, b = value >> 11, value >> 5 & 63, value & 31
            return r << 3 | r >> 2, g << 2 | g >> 4, b << 3 | b >> 2
        (value,) = struct.unpack_from("<I", self.map, y * self.pitch + x * 4)
        return value >> 16 & 255, value >> 8 & 255, value & 255


# ---- colour, enough to build tone-mapping tables a display engine applies
def rotation_value(bits, name):
    """A rotation property's value: DRM takes exactly one rotate- bit, a reflection beside it."""
    value = 1 << bits[name]
    return value | 1 << bits["rotate-0"] if name.startswith("reflect-") else value


def pq_eotf(e):
    m1, m2, c1, c2, c3 = 0.1593017578125, 78.84375, 0.8359375, 18.8515625, 18.6875
    p = min(max(e, 0.0), 1.0) ** (1 / m2)
    return (max(p - c1, 0.0) / (c2 - c3 * p)) ** (1 / m1) * 10000


def pq_oetf(nits):
    m1, m2, c1, c2, c3 = 0.1593017578125, 78.84375, 0.8359375, 18.8515625, 18.6875
    y = (max(nits, 0.0) / 10000) ** m1
    return ((c1 + c2 * y) / (1 + c3 * y)) ** m2


def hlg_eotf(e, peak=1000.0):
    a, b, c = 0.17883277, 0.28466892, 0.55991073
    e = [min(max(x, 0.0), 1.0) for x in e]
    lin = [x * x / 3 if x <= 0.5 else (math.exp((x - c) / a) + b) / 12 for x in e]
    luma = 0.2627 * lin[0] + 0.6780 * lin[1] + 0.0593 * lin[2]
    gain = peak * luma**0.2 if luma > 0 else 0.0
    return [gain * x for x in lin]


def bt1886(nits, white=100.0):
    return min(max(nits / white, 0.0), 1.0) ** (1 / 2.4)


def tone(nits, peak=1000.0, white=100.0):
    x = nits / white
    return white * x * (1 + x / (peak / white) ** 2) / (1 + x)


BT2020_TO_709 = ((1.6605, -0.5876, -0.0728), (-0.1246, 1.1329, -0.0083), (-0.0182, -0.1006, 1.1187))
BT709_TO_2020 = (
    (0.627404, 0.329283, 0.043313),
    (0.069097, 0.919540, 0.011362),
    (0.016391, 0.088013, 0.895595),
)
SDR_WHITE = 0.203  # of 1000 nits
# greys, primaries and a mid green: an SDR to HDR stage's checks
SDR2HDR_SIGNALS = (
    (64, 64, 64),
    (128, 128, 128),
    (255, 255, 255),
    (255, 0, 0),
    (0, 255, 0),
    (0, 0, 255),
    (105, 174, 49),
)
KR_KB = {601: (0.299, 0.114), 709: (0.2126, 0.0722), 2020: (0.2627, 0.0593)}


def matrix(m, v):
    return [sum(m[r][c] * v[c] for c in range(3)) for r in range(3)]


def yuv_to_rgb(v, space):
    """Limited-range Y'CbCr, normalized 10-bit codes, to R'G'B' 0..1."""
    kr, kb = KR_KB[space]
    y, u, w = (v[0] * 1023 - 64) / 876, (v[1] * 1023 - 512) / 896, (v[2] * 1023 - 512) / 896
    r, b = y + 2 * (1 - kr) * w, y + 2 * (1 - kb) * u
    return [r, (y - kr * r - kb * b) / (1 - kr - kb), b]


def rgb_to_yuv(rgb, space):
    kr, kb = KR_KB[space]
    r, g, b = [min(max(c, 0.0), 1.0) for c in rgb]
    y = kr * r + (1 - kr - kb) * g + kb * b
    return [
        (y * 876 + 64) / 1023,
        ((b - y) / (2 * (1 - kb)) * 896 + 512) / 1023,
        ((r - y) / (2 * (1 - kr)) * 896 + 512) / 1023,
    ]


def hdr10_to_sdr(v):
    lin = [tone(pq_eotf(c)) for c in yuv_to_rgb(v, 2020)]
    return rgb_to_yuv([bt1886(c) for c in matrix(BT2020_TO_709, lin)], 709)


def hlg_to_sdr(v):
    lin = [tone(c) for c in hlg_eotf(yuv_to_rgb(v, 2020))]
    return rgb_to_yuv([bt1886(c) for c in matrix(BT2020_TO_709, lin)], 709)


def sdr_to_pq(v):
    lin = [100 * min(max(c, 0.0), 1.0) ** 2.4 for c in yuv_to_rgb(v, 709)]
    return rgb_to_yuv([pq_oetf(c) for c in matrix(BT709_TO_2020, lin)], 2020)


def hlg_to_pq(v):
    return rgb_to_yuv([pq_oetf(c) for c in hlg_eotf(yuv_to_rgb(v, 2020))], 2020)


def hlg_oetf(e):
    a, b, c = 0.17883277, 0.28466892, 0.55991073
    return math.sqrt(3 * e) if e <= 1 / 12 else a * math.log(12 * e - b) + c


def sdr_to_hdr(rgb, target):
    """BT.2408's SDR in HDR: gamma 2.2, BT.709 to BT.2020, white at 203 nits of PQ or of a 1000-nit HLG."""
    lin = [SDR_WHITE * c for c in matrix(BT709_TO_2020, [c**2.2 for c in rgb])]
    if target == "PQ":
        return [pq_oetf(c * 1000) for c in lin]
    luma = 0.2627 * lin[0] + 0.6780 * lin[1] + 0.0593 * lin[2]
    gain = luma ** (1 / 1.2 - 1) if luma > 0 else 0.0
    return [hlg_oetf(gain * c) for c in lin]


# ---- Rockchip's VOP2 SDR to HDR stage: struct hdr_extend for its CRTC's HDR_EXT_DATA
# The SDR inverse-gamma segments, as the engine takes them: 137 slopes, the input each segment
# starts at, and the slope index each one changes at.
RK_INV_GAMMA = (
    0,
    49,
    223,
    545,
    1026,
    1677,
    2504,
    3515,
    4715,
    6110,
    7704,
    3959,
    4870,
    5886,
    7007,
    3577,
    4198,
    4874,
    5604,
    6391,
    7235,
    8136,
    4126,
    4609,
    5122,
    5664,
    6235,
    6837,
    7470,
    8133,
    4109,
    4458,
    4822,
    5202,
    5598,
    6010,
    6438,
    6881,
    7342,
    7818,
    3939,
    4187,
    4442,
    4706,
    4978,
    5259,
    5548,
    5845,
    6151,
    6466,
    6789,
    7121,
    7461,
    7810,
    8168,
    4106,
    4290,
    4478,
    4671,
    4868,
    5070,
    5275,
    5486,
    5701,
    5920,
    6144,
    6373,
    6606,
    6843,
    7086,
    7332,
    7584,
    7840,
    8101,
    4067,
    4200,
    4335,
    4473,
    4613,
    4755,
    4900,
    5047,
    5196,
    5348,
    5503,
    5659,
    5818,
    5980,
    6144,
    6310,
    6479,
    6650,
    6823,
    6999,
    7178,
    7359,
    7542,
    7728,
    7916,
    8107,
    4066,
    4162,
    4260,
    4360,
    4460,
    4562,
    4665,
    4769,
    4875,
    4982,
    5090,
    5199,
    5310,
    5422,
    5535,
    5649,
    5765,
    5882,
    6000,
    6120,
    6241,
    6363,
    6486,
    6611,
    6737,
    6864,
    6993,
    7123,
    7254,
    7387,
    7521,
    7656,
    7792,
    7930,
    8069,
    4043,
    4114,
    0,
)
RK_INV_GAMMA_START = (0, 81, 106, 155, 212, 285, 398, 543, 744, 1017, 1024, 0)
RK_INV_GAMMA_CHANGE = (0, 11, 15, 22, 30, 40, 55, 74, 100, 135, 137, 0)
# Per target: the SDR white's log scale and the engine's r and t terms, then sdr2hdr_ctrl (gating,
# and bit 3 for an HLG output) and hdr_mode (SDR2HDR10_USERSPACE, SDR2HLG_USERSPACE).
RK_TARGETS = {
    "PQ": (SDR_WHITE / 10, 1020, 0, 4913, 0x2, 100),
    "HLG": (SDR_WHITE, 850, -171, 4094, 0xA, 101),
}
RK_HDRVIVID_EN = 0x203  # enable, gating, tone-scale bypass
RK_HDR_EXTEND_SIZE = 12428
RK_HDRVIVID_WORDS = 799
RK_WORD = {
    "ctrl": 0,
    "fix": 1,
    "t_fix": 2,
    "csc": 3,
    "hdrvivid": 8,
    "inv_gamma": 365,
    "start": 434,
    "change": 440,
    "smgain": 446,
    "hdr_mode": 510,
}


def rk_sdr2hdr(target):
    white, scale, r_fix, t_fix, ctrl, mode = RK_TARGETS[target]
    regs = [0] * RK_HDRVIVID_WORDS
    q13 = [round(c * 8192) for row in BT709_TO_2020 for c in row] + [0]
    s_fix = -round(math.log10(white) * scale)
    pairs = lambda v: [v[i] | v[i + 1] << 16 for i in range(0, len(v), 2)]
    for name, words in (
        ("ctrl", [ctrl]),
        ("fix", [s_fix & 0xFFF | (r_fix & 0xFFF) << 16]),
        ("t_fix", [t_fix]),
        ("csc", pairs(q13)),
        ("hdrvivid", [RK_HDRVIVID_EN]),
        ("inv_gamma", pairs(RK_INV_GAMMA)),
        ("start", pairs(RK_INV_GAMMA_START)),
        ("change", pairs(RK_INV_GAMMA_CHANGE)),
        ("smgain", [1024 | 1024 << 16] * 64),
        ("hdr_mode", [mode]),
    ):
        regs[RK_WORD[name] : RK_WORD[name] + len(words)] = words
    data = struct.pack(f"<2I{RK_HDRVIVID_WORDS}I", 0, 4 * RK_HDRVIVID_WORDS, *regs)
    return data.ljust(RK_HDR_EXTEND_SIZE, b"\0")


def lattice(f):
    """17^3 nodes, the first component fastest, as 0..1 floats."""
    n = LUT_POINTS - 1
    return [
        f([x / n, y / n, z / n])
        for z in range(LUT_POINTS)
        for y in range(LUT_POINTS)
        for x in range(LUT_POINTS)
    ]


def quantized(nodes):
    """Each node as the hardware keeps it, 10 bits, and the KMS blob carrying it."""
    unorm = [[round(min(max(c, 0.0), 1.0) * 65535) for c in node] for node in nodes]
    blob = b"".join(struct.pack("<4H", *node, 0) for node in unorm)
    return [[round(c * 1023 / 65535) / 1023 for c in node] for node in unorm], blob


def trilinear(nodes, v):
    n = LUT_POINTS - 1
    base, frac = [], []
    for c in v:
        p = min(max(c, 0.0), 1.0) * n
        i = min(int(p), n - 1)
        base.append(i)
        frac.append(p - i)
    out = [0.0, 0.0, 0.0]
    for corner in range(8):
        weight, at = 1.0, []
        for c in range(3):
            bit = corner >> c & 1
            at.append(base[c] + bit)
            weight *= frac[c] if bit else 1 - frac[c]
        node = nodes[(at[2] * LUT_POINTS + at[1]) * LUT_POINTS + at[0]]
        for c in range(3):
            out[c] += weight * node[c]
    return out


def to8(rgb):
    return tuple(round(min(max(c, 0.0), 1.0) * 255) for c in rgb)


def edid_block(data):
    return data + bytes([(-sum(data)) & 0xFF])


# ---- a synthetic screen over whatever the box has: the HDMI connector's EDID through debugfs
EOTF_SDR, EOTF_PQ, EOTF_HLG = 0, 2, 3
SINKS = {
    "SDR": 1 << EOTF_SDR,
    "HDR10": 1 << EOTF_SDR | 1 << EOTF_PQ,
    "HLG": 1 << EOTF_SDR | 1 << EOTF_HLG,
    "HDR10 and HLG": 1 << EOTF_SDR | 1 << EOTF_PQ | 1 << EOTF_HLG,
}


# The rating's modes: name: (CTA VIC, width, height, refresh). 8K and 4K120 need HDMI 2.1, so a box on
# HDMI 2.0 prunes them; 24 Hz is film's rate, 120 Hz frame-sequential 3D's and fast panels'.
LADDER = {
    "8K60": (199, 7680, 4320, 60),
    "8K30": (196, 7680, 4320, 30),
    "4K120": (118, 3840, 2160, 120),
    "4K60": (97, 3840, 2160, 60),
    "4K50": (96, 3840, 2160, 50),
    "4K30": (95, 3840, 2160, 30),
    "4K24": (93, 3840, 2160, 24),
    "1080p120": (63, 1920, 1080, 120),
    "1080p60": (16, 1920, 1080, 60),
    "1080p50": (31, 1920, 1080, 50),
    "1080p24": (32, 1920, 1080, 24),
    "1080i60": (5, 1920, 1080, 60),
    "1080i50": (20, 1920, 1080, 50),
    "720p120": (47, 1280, 720, 120),
    "720p60": (4, 1280, 720, 60),
    "720p50": (19, 1280, 720, 50),
    "576p50": (17, 720, 576, 50),
    "480p60": (3, 720, 480, 60),
    "576i50": (21, 720, 576, 50),
    "480i60": (6, 720, 480, 60),
}
# broadcast's rungs: the 50 Hz family and the interlaced modes, each offered one held, not only the
# largest and fastest
BROADCAST_LADDER = (
    "4K50",
    "1080p50",
    "1080i60",
    "1080i50",
    "720p50",
    "576p50",
    "480p60",
    "576i50",
    "480i60",
)
# Two verdicts from the same runs, each its rungs most demanding first: how large, and how fast.
RESOLUTION_LADDER = ("8K60", "8K30", "4K60", "4K30", "4K24", "1080p60", "1080p24", "720p60")
RATE_LADDER = ("4K120", "1080p120", "720p120", "4K60", "1080p60", "720p60")
# Detailed timings: pixel clock kHz, then active, blank, sync offset, sync width for H and for V.
DTD_4K60 = (594000, 3840, 560, 176, 88, 2160, 90, 8, 10)
DTD_1080P60 = (148500, 1920, 280, 88, 44, 1080, 45, 4, 5)


def dtd(clock, ha, hb, hso, hsw, va, vb, vso, vsw):
    """An EDID detailed timing, 592x301 mm, digital separate sync, +H +V."""
    return struct.pack("<H", clock // 10) + bytes(
        [
            ha & 255,
            hb & 255,
            ha >> 8 << 4 | hb >> 8,
            va & 255,
            vb & 255,
            va >> 8 << 4 | vb >> 8,
            hso & 255,
            hsw & 255,
            (vso & 15) << 4 | vsw & 15,
            hso >> 8 << 6 | hsw >> 8 << 4 | vso >> 4 << 2 | vsw >> 4,
            0x50,
            0x2D,
            0x21,
            0x00,
            0x00,
            0x1E,
        ]
    )


def hdr_edid(
    eotfs=SINKS["HDR10 and HLG"], ladder=False, y420=False, surround=False, ycc=False, stereo=False
):
    """1080p60, or with ladder 4K60 first and every LADDER mode, as an HDMI 2.0 screen; RGB only so a
    writeback can follow the output, BT.2020; HDR static metadata for the EOTF bits beyond SDR, none
    for an SDR screen. With y420 it also takes every mode as YCbCr 4:2:0, 10 bits deep; with ycc,
    YCbCr 4:4:4 and 4:2:2; with surround, 8-channel LPCM to 192 kHz on 7.1 speakers; with stereo,
    HDMI 1.4's 3D_present, its mandatory 3D formats of the modes it lists."""
    base = b"\x00\xff\xff\xff\xff\xff\xff\x00" + struct.pack(">H", 20 << 10 | 22 << 5 | 2)  # TVB
    base += struct.pack("<HIBB", 1, 1, 1, 34) + bytes([1, 3, 0x80, 0x50, 0x2D, 0x78, 0x0A])
    base += (
        bytes([0x0D, 0xC9, 0xA0, 0x57, 0x47, 0x98, 0x27, 0x12, 0x48, 0x4C, 0, 0, 0])
        + b"\x01\x01" * 8
    )
    base += dtd(*(DTD_4K60 if ladder else DTD_1080P60))
    base += b"\x00\x00\x00\xfc\x00" + b"TVB HDR test\n"
    base += (
        b"\x00\x00\x00\xfd\x00"
        + bytes([24, 75, 15, 140, 60 if ladder else 30, 0, 0x0A])
        + b"\x20" * 6
    )
    base += b"\x00\x00\x00\x10\x00" + b"\x00" * 13 + b"\x01"
    vics = [m[0] for m in LADDER.values()] if ladder else [16, 4]
    blocks = bytes([0x40 | len(vics)] + vics)
    vsdb = [0x03, 0x0C, 0x00, 0x10, 0x00, 0x30, 68 if ladder else 0x2D]  # HDMI, 10/12-bit
    vsdb += [0x20, 0x80, 0x00] if stereo else [0x00]  # HDMI_Video_present, 3D_present
    blocks += bytes([0x60 | len(vsdb)] + vsdb)
    if ladder:
        # HDMI 2.0: 600 MHz, SCDC, and 10-bit 4:2:0 where asked
        blocks += bytes([0x67, 0xD8, 0x5D, 0xC4, 0x01, 120, 0x80, 0x01 if y420 else 0x00])
    if surround:
        blocks += bytes([0x23, 0x0F, 0x7F, 0x07])  # LPCM, 8 channels, 32-192 kHz, 16/20/24-bit
        blocks += bytes([0x83, 0x4F, 0x00, 0x00])  # speakers: 7.1
    if y420:
        blocks += bytes([0xE1, 0x0F])  # YCbCr 4:2:0 capability map, no bitmap: every mode
    blocks += bytes([0xE3, 0x05, 0xC0, 0x00])  # BT.2020 RGB and YCC
    if eotfs & ~(1 << EOTF_SDR):
        blocks += bytes([0xE6, 0x06, eotfs, 0x01, 0x78, 0x50, 0x00])  # HDR static, type 1
    # basic audio, and YCbCr 4:4:4 and 4:2:2 where asked
    ext = bytes([0x02, 0x03, 4 + len(blocks), 0x70 if ycc else 0x40]) + blocks
    return edid_block(base) + edid_block(ext + bytes(127 - len(ext)))


def hdmi_sound_card():
    for card in sorted(glob.glob("/proc/asound/card[0-9]*")):
        if "hdmi" in Path(f"{card}/id").read_text().lower():
            return card.removeprefix("/proc/asound/card")
    return None


def play_reading(card, channels, rate, read, timeout=5.0):
    """PLAY_SECONDS of silence, read() once the stream runs: (seconds, aplay's error, read())."""
    started = time.monotonic()
    play = subprocess.Popen(
        ["aplay", "-q", "-D", f"hw:{card},0", "-c", str(channels), "-r", str(rate)]
        + ["-f", "S32_LE", "-d", str(PLAY_SECONDS), "/dev/zero"],
        stderr=subprocess.PIPE,
        text=True,
    )
    status = Path(f"/proc/asound/card{card}/pcm0p/sub0/status")
    while play.poll() is None and time.monotonic() - started < timeout:
        if "RUNNING" in status.read_text():
            break
        time.sleep(0.05)
    seen = read() or {}
    error = play.communicate(timeout=timeout + PLAY_SECONDS)[1].strip().split("\n")[0]
    return time.monotonic() - started, error, seen


def unit_state(unit):
    """systemctl's word for unit: active, activating, inactive, failed and the rest."""
    done = subprocess.run(["systemctl", "is-active", unit], capture_output=True, text=True)
    return done.stdout.strip()


@contextlib.contextmanager
def display_free():
    """The display to ourselves: a running session's compositor holds DRM master, which every
    modeset here needs; the session is back when the run ends."""
    states = {unit: unit_state(unit) for unit in SESSION_UNITS}
    # each stopped whatever it reads: a greeter between its restarts reads inactive with its restart
    # queued, then switches the console's VT mid-run, and the console's client turns every output off
    for unit in SESSION_UNITS:
        subprocess.run(["systemctl", "stop", unit], check=False)
    try:
        yield
    finally:
        # only what ran steadily comes back: a unit caught restarting would loop on through the next run
        for unit in reversed([u for u, s in states.items() if s == "active"]):
            subprocess.run(["systemctl", "start", unit], check=False)


@contextlib.contextmanager
def hdr_sink(edid=None):
    """Gives the HDMI connector a synthetic screen, edid or else the HDR10 and HLG one, over any
    screen attached: the checks then answer for the screen they expect, unattended. True while it
    stands in; the connector's own EDID and force state come back after."""
    found = [
        (d, c)
        for d in glob.glob("/sys/kernel/debug/dri/*/HDMI-A-1")
        for c in glob.glob("/sys/class/drm/card*-HDMI-A-1")
        if os.path.exists(f"{d}/edid_override")
    ]
    if not found:
        yield False
        return
    debugfs, sysfs = found[0]
    if edid is None:
        print("NOTE a synthetic HDR10/HLG EDID stands in for the HDMI screen")
        edid = hdr_edid()
    with open(f"{debugfs}/force") as f:
        force = f.read().strip()
    try:
        with open(f"{debugfs}/edid_override", "wb") as f:
            f.write(edid)
        # a status change, not a write, is what makes 6.12 re-read the EDID
        for state in ("off", "on"):
            with open(f"{sysfs}/status", "w") as f:
                f.write(state)
        settled_mode()
        yield True
    finally:
        with open(f"{debugfs}/edid_override", "w") as f:
            f.write("reset")
        for state in ("off", "on" if force == "on" else "detect"):
            with open(f"{sysfs}/status", "w") as f:
                f.write(state)


def settled_mode(timeout=10.0, steady=1.0):
    """Waits for the active CRTC's mode to hold still: a new EDID moves it after the probe."""
    drm = Drm(display_card())
    last, since, end = None, time.monotonic(), time.monotonic() + timeout
    while time.monotonic() < end:
        res = drm.call("res", CardRes())
        crtcs = drm.ids(res.count_crtcs)
        drm.call("res", CardRes(crtcs=ctypes.addressof(crtcs), count_crtcs=res.count_crtcs))
        modes = [
            (c.mode.hdisplay, c.mode.vdisplay)
            for c in (drm.call("crtc", Crtc(crtc_id=i)) for i in crtcs)
            if c.mode_valid
        ]
        if modes != last:
            last, since = modes, time.monotonic()
        elif modes and time.monotonic() - since >= steady:
            break
        time.sleep(0.1)
    os.close(drm.fd)


def kernel_log():
    """The kernel's warnings and worse, oldest first."""
    result = subprocess.run(
        ["dmesg", "--level=emerg,alert,crit,err,warn"], capture_output=True, text=True
    )
    return result.stdout.splitlines()


def plane_names():
    """Each plane's driver name, by id, from the DRM state in debugfs."""
    names = {}
    for path in glob.glob("/sys/kernel/debug/dri/*/state"):
        with open(path) as f:
            names.update({int(m[1]): m[2] for m in PLANE_STATE_LINE.finditer(f.read())})
    return names


def underrun_count():
    """Underruns so far: sun4i's debugfs counter, Rockchip's per-line POST_BUF_EMPTY in the log, or None
    where the driver reports none."""
    counters = glob.glob("/sys/kernel/debug/dri/*/crtc-*/underruns")
    if counters:
        with open(counters[0]) as f:
            return int(f.read())
    if glob.glob("/sys/bus/platform/drivers/rockchip-vop2"):
        return sum("POST_BUF_EMPTY" in line for line in kernel_log())
    return None


# ---- the box


class AfbcQuadrants(Buffer):
    """An AFBC XRGB8888 square, each quadrant one colour, written as uncompressed sub-blocks: what a
    plane shows of it needs no AFBC encoder to check."""

    def __init__(self, drm, rgbs, modifier=AFBC_16X16):
        self.drm, self.handle, self.fb = drm, 0, 0
        size, blocks = AFBC_SIDE, AFBC_SIDE // AFBC_BLOCK
        header = blocks * blocks * AFBC_HEADER_BYTES
        body = AFBC_BLOCK * AFBC_BLOCK * 4
        d = drm.call("dumb", CreateDumb(height=size * 2, width=size, bpp=32))
        self.handle = d.handle
        offset = drm.call("map", MapDumb(handle=d.handle)).offset
        self.map = mmap.mmap(
            drm.fd, d.size, mmap.MAP_SHARED, mmap.PROT_READ | mmap.PROT_WRITE, offset=offset
        )
        sizes = sum(AFBC_UNCOMPRESSED << (6 * i) for i in range(16)).to_bytes(12, "little")
        for n in range(blocks * blocks):
            bx, by = n % blocks, n // blocks
            rgb = rgbs[(2 * bx // blocks, 2 * by // blocks)]
            start = header + n * body
            self.map[n * AFBC_HEADER_BYTES : (n + 1) * AFBC_HEADER_BYTES] = (
                struct.pack("<I", start) + sizes
            )
            self.map[start : start + body] = struct.pack("<4B", rgb[2], rgb[1], rgb[0], 255) * (
                body // 4
            )
        self.width = self.height = size
        self.pitch, self.format = size * 4, XRGB8888
        cmd = FbCmd2(width=size, height=size, pixel_format=XRGB8888, flags=FB_MODIFIERS)
        cmd.handles[0], cmd.pitches[0], cmd.modifier[0] = d.handle, self.pitch, modifier
        self.fb = drm.call("addfb2", cmd).fb_id


class Box:
    def __init__(self):
        self.drm = Drm(display_card())
        for cap in (CAP_ATOMIC, CAP_WRITEBACK):
            self.drm.call("cap", ClientCap(capability=cap, value=1))
        res = self.drm.call("res", CardRes())
        crtcs, connectors = self.drm.ids(res.count_crtcs), self.drm.ids(res.count_connectors)
        self.drm.call(
            "res",
            CardRes(
                crtcs=ctypes.addressof(crtcs),
                connectors=ctypes.addressof(connectors),
                count_crtcs=res.count_crtcs,
                count_connectors=res.count_connectors,
            ),
        )
        self.crtc = self.index = None
        for i in range(res.count_crtcs):
            c = self.drm.call("crtc", Crtc(crtc_id=crtcs[i]))
            if c.mode_valid and self.crtc is None:
                self.crtc, self.index, self.mode = c.crtc_id, i, c.mode
        self.writeback = self.hdmi_connector = None
        for i in range(res.count_connectors):
            c = self.drm.call("connector", Connector(connector_id=connectors[i]))
            if c.connector_type == CONNECTOR_WRITEBACK:
                self.writeback = c.connector_id
            if c.connector_type == CONNECTOR_HDMIA and c.connection == 1:
                self.hdmi_connector = c.connector_id
        if self.hdmi_connector and res.count_crtcs:
            modes = self.connector_modes()
            shown = self.crtc is not None and any(bytes(m) == bytes(self.mode) for m in modes)
            if not shown:
                # nothing set a mode, or the screen changed under it (fbcon follows a hotplug on 6.1, not 6.12):
                # the preferred one, on the active CRTC, else the first the HDMI encoder takes; the
                # active one may be another output's, composite's on the RK3528
                active = [] if self.index is None else [self.index]
                error = None
                for i in active + [i for i in range(res.count_crtcs) if i not in active]:
                    self.crtc, self.index = crtcs[i], i
                    error = self.set_mode(modes[0]) if modes else None
                    if not error:
                        break
                if not modes or error:
                    print(f"RECORD hdmi: no mode set ({len(modes)} modes, errno {error})")
                    self.crtc = self.index = None
        pr = self.drm.call("planes", PlaneRes())
        ids = self.drm.ids(pr.count_planes)
        self.drm.call(
            "planes", PlaneRes(planes=ctypes.addressof(ids), count_planes=pr.count_planes)
        )
        names = plane_names()
        self.planes, self.region_planes = [], []
        for i in range(pr.count_planes):
            p = self.drm.call("plane", Plane(plane_id=ids[i]))
            if self.crtc is not None and p.possible_crtcs & 1 << self.index:
                # a region shows only with its window: the regions check alone composes it
                region = REGION_NAME.match(names.get(p.plane_id, ""))
                (self.region_planes if region else self.planes).append(p.plane_id)
        self.lut_planes = [
            p for p in self.planes if "SUNXI_CDC_LUT3D" in self.drm.props(p, OBJ_PLANE)
        ]
        self.bypass_color_pipelines()
        self.failures = self.passes = 0
        self.maps = set()
        self.synthetic_sink = False
        self.video_plane = self.ui_plane = None

    def prop(self, obj, kind, name):
        return self.drm.props(obj, kind)[name][0]

    def bypass_color_pipelines(self):
        """Every plane's color pipeline to bypass, as a program before may have left one set: a
        commit from a client that cannot see it is refused. The capability goes again after, as
        it hides the planes' legacy color properties."""
        try:
            self.drm.call("cap", ClientCap(capability=CAP_COLOR_PIPELINE, value=1))
        except OSError:
            return
        changes = {}
        for plane in self.planes + self.region_planes:
            prop = self.drm.props(plane, OBJ_PLANE).get("COLOR_PIPELINE")
            if prop and prop[1]:
                changes[plane] = {prop[0]: 0}
        if changes:
            self.drm.commit(changes, ALLOW_MODESET)
        self.drm.call("cap", ClientCap(capability=CAP_COLOR_PIPELINE, value=0))

    def check(self, name, ok, detail=""):
        print(f"{'PASS' if ok else 'FAIL'} {name} {detail}".rstrip())
        self.passes += ok
        self.failures += not ok
        return ok

    def show(self, plane, buffer, lut, encoding=None, capture=None, crtc=None):
        """Only this plane on the CRTC, full screen; with a capture buffer, waits for its writeback."""
        width, height = self.mode.hdisplay, self.mode.vdisplay
        extra = {} if lut is None else {"SUNXI_CDC_LUT3D": lut}
        if encoding is not None:
            extra.update(COLOR_ENCODING=encoding, COLOR_RANGE="YCbCr limited range")
        rect = (0, 0, width if buffer.format == XRGB8888 else height, height)
        return self.compose([(plane, buffer, rect, extra)], capture, crtc)

    def compose(self, layers, capture=None, crtc=None, flags=ALLOW_MODESET, objects=None):
        """layers: (plane, buffer, (x, y, w, h), {property: value or enum name}); every other plane off.
        A plane's EOTF goes back to SDR, its rotation to none, its color pipeline to bypass, unless
        a layer sets it; objects: other objects' {property id: value}, as colorops'."""
        changes = {
            p: {self.prop(p, OBJ_PLANE, "FB_ID"): 0, self.prop(p, OBJ_PLANE, "CRTC_ID"): 0}
            for p in self.planes + self.region_planes
            if p not in [layer[0] for layer in layers]
        }
        for plane, buffer, (x, y, w, h), extra in layers:
            props = self.drm.props(plane, OBJ_PLANE)
            values = {
                "FB_ID": buffer.fb,
                "CRTC_ID": self.crtc,
                "SRC_X": 0,
                "SRC_Y": 0,
                "SRC_W": buffer.width << 16,
                "SRC_H": buffer.height << 16,
                "CRTC_X": x,
                "CRTC_Y": y,
                "CRTC_W": w,
                "CRTC_H": h,
            }
            if "EOTF" in props:
                values["EOTF"] = 0
            if "rotation" in props:
                values["rotation"] = rotation_value(
                    self.drm.enums(props["rotation"][2]), "rotate-0"
                )
            if "COLOR_PIPELINE" in props:
                values["COLOR_PIPELINE"] = 0
            values.update(extra)
            for name in OPTIONAL_PLANE_PROPS - set(props):
                values.pop(name, None)
            changes[plane] = {
                props[k][0]: self.drm.enum_value(props[k][2], v) if isinstance(v, str) else v
                for k, v in values.items()
            }
        mode_blob = self.crtc_back_on(changes)
        if crtc:
            changes.setdefault(self.crtc, {}).update(
                {self.prop(self.crtc, OBJ_CRTC, k): v for k, v in crtc.items()}
            )
        changes.update(objects or {})
        fence = ctypes.c_int32(-1)
        if capture:
            changes[self.writeback] = {
                self.prop(self.writeback, OBJ_CONNECTOR, "CRTC_ID"): self.crtc,
                self.prop(self.writeback, OBJ_CONNECTOR, "WRITEBACK_FB_ID"): capture.fb,
                self.prop(
                    self.writeback, OBJ_CONNECTOR, "WRITEBACK_OUT_FENCE_PTR"
                ): ctypes.addressof(fence),
            }
        error = self.drm.commit(changes, flags)
        if mode_blob:
            self.drm.unblob(mode_blob)
        if not error and capture:
            ready, _, _ = select.select([fence.value], [], [], 2)
            os.close(fence.value)
            error = 0 if ready else 110
        return error

    def output_state(self):
        """The CRTC and HDMI as the kernel holds them, for a failure to say what it met."""
        active = self.drm.props(self.crtc, OBJ_CRTC)["ACTIVE"][1]
        bound = self.drm.props(self.hdmi_connector, OBJ_CONNECTOR)["CRTC_ID"][1]
        status = next(iter(glob.glob("/sys/class/drm/card*-HDMI-A-1/status")), None)
        seen = Path(status).read_text().strip() if status else "?"
        return f"CRTC {self.crtc} active {active}, HDMI on CRTC {bound}, HDMI {seen}"

    def crtc_back_on(self, changes):
        """The CRTC on again in changes, with the run's mode, where DRM turned it off: freeing the
        framebuffer its primary plane shows does. The mode's blob, to free after the commit; None
        where the CRTC is on."""
        if self.drm.props(self.crtc, OBJ_CRTC)["ACTIVE"][1]:
            return None
        blob = self.drm.blob(bytes(self.mode))
        changes[self.crtc] = {
            self.prop(self.crtc, OBJ_CRTC, "MODE_ID"): blob,
            self.prop(self.crtc, OBJ_CRTC, "ACTIVE"): 1,
        }
        connector = self.prop(self.hdmi_connector, OBJ_CONNECTOR, "CRTC_ID")
        changes[self.hdmi_connector] = {connector: self.crtc}
        return blob

    def plane_info(self, plane):
        p = self.drm.call("plane", Plane(plane_id=plane))
        fourccs = self.drm.ids(p.count_format_types)
        self.drm.call(
            "plane",
            Plane(
                plane_id=plane,
                count_format_types=p.count_format_types,
                format_types=ctypes.addressof(fourccs),
            ),
        )
        props = self.drm.props(plane, OBJ_PLANE)
        modifiers = 0
        if "IN_FORMATS" in props and props["IN_FORMATS"][1]:
            blob = self.drm.getblob(props["IN_FORMATS"][1])
            modifiers = struct.unpack_from("<5I", blob)[4]
        zpos = self.drm.prop_range(props["zpos"][2]) if "zpos" in props else (0, 0)
        return {
            "type": PLANE_TYPES.get(props["type"][1], "?"),
            "formats": list(fourccs[: p.count_format_types]),
            "modifiers": modifiers,
            "zpos": zpos,
            "zpos_fixed": "zpos" in props and bool(props["zpos"][2].flags & PROP_IMMUTABLE),
            "alpha": "alpha" in props,
            "props": props,
        }

    def planes_record(self):
        """H20: every plane the CRTC offers, and the video plane and interface plane the checks compose."""
        name = lambda f: struct.pack("<I", f).decode(errors="replace")
        info = {p: self.plane_info(p) for p in self.planes}
        for p, i in info.items():
            print(
                f"PLANE {p} {i['type']} zpos {i['zpos'][0]}..{i['zpos'][1]}{' fixed' if i['zpos_fixed'] else ''} "
                f"alpha {'yes' if i['alpha'] else 'no'} modifiers {i['modifiers']} "
                f"formats {' '.join(name(f) for f in i['formats'])}"
            )
        video = [p for p, i in info.items() if NV12 in i["formats"]]
        if video:
            self.video_plane = video[0]
            ui = [
                p
                for p, i in info.items()
                if p != self.video_plane
                and ARGB8888 in i["formats"]
                and i["zpos"][1] > info[self.video_plane]["zpos"][0]
            ]
            self.ui_plane = ui[0] if ui else None
        self.check(
            "planes: a YUV video plane and an interface plane above it",
            bool(self.video_plane and self.ui_plane),
            f"(video {self.video_plane}, interface {self.ui_plane})",
        )

    def layer_zpos(self, plane, level):
        """A zpos that puts the plane at level (0 below, 1 above) where it can be set."""
        info = self.plane_info(plane)
        return (
            {}
            if info["zpos_fixed"] or "zpos" not in info["props"]
            else {"zpos": info["zpos"][0] + level}
        )

    def capture_buffer(self):
        """A writeback target the engine takes: full size, or half where it scales its writeback; NV12
        where the output is YCbCr and the engine converts no YCbCr back to RGB."""
        width, height = self.mode.hdisplay, self.mode.vdisplay
        for scale in (1, 2):
            for fourcc in (XRGB8888, ARGB8888, NV12):
                capture = Buffer(self.drm, width // scale, height // scale, fourcc, unpadded=True)
                if not self.show(
                    self.planes[0], Buffer(self.drm, width, height, XRGB8888), None, capture=capture
                ):
                    return capture
        return None

    def video_and_interface(self, video_extra=None, crtc=None, capture=None, ui_rgb=(40, 200, 40)):
        """The video plane scaled to the screen, NV12 BT.709 limited; the interface over its top half,
        transparent below. Returns (error, interface pixel, video pixel, expected video colour)."""
        width, height = self.mode.hdisplay, self.mode.vdisplay
        code = (81, 90, 240)
        video = Buffer(self.drm, 640, 360, NV12)
        video.fill_yuv(code)
        ui = Buffer(self.drm, width, height, ARGB8888)
        ui.fill_rgb(ui_rgb, 255, range(height // 2))
        ui.fill_rgb((0, 0, 0), 0, range(height // 2, height))
        layers = [
            (
                self.video_plane,
                video,
                (0, 0, width, height),
                dict(
                    COLOR_ENCODING="ITU-R BT.709 YCbCr",
                    COLOR_RANGE="YCbCr limited range",
                    **self.layer_zpos(self.video_plane, 0),
                    **(video_extra or {}),
                ),
            ),
            (self.ui_plane, ui, (0, 0, width, height), self.layer_zpos(self.ui_plane, 1)),
        ]
        error = self.compose(layers, capture, crtc)
        want = to8(
            yuv_to_rgb([(code[0] * 4) / 1023, (code[1] * 4) / 1023, (code[2] * 4) / 1023], 709)
        )
        if error or not capture:
            return error, None, None, want
        return (
            0,
            capture.pixel(capture.width // 2, capture.height // 4),
            capture.pixel(capture.width // 2, capture.height * 3 // 4),
            want,
        )

    def compose_check(self):
        """H21: the engine composes the interface over the scaled video plane, alpha and all."""
        if not (self.video_plane and self.ui_plane) or not self.writeback:
            print(
                f"SKIP compose: {'no writeback connector' if self.video_plane and self.ui_plane else 'no video and interface planes'}"
            )
            return
        capture = self.capture_buffer()
        if not capture:
            print("SKIP compose: the writeback takes no capture at this mode")
            return
        error, ui, video, want = self.video_and_interface(capture=capture)
        diff = lambda a, b: max(abs(x - y) for x, y in zip(a, b))
        self.check(
            "compose: interface over the scaled video plane",
            not error and diff(ui, (40, 200, 40)) <= TOLERANCE and diff(video, want) <= TOLERANCE,
            f"(errno {error}, interface {ui}, video {video} want {want})",
        )

    def modifiers(self, props):
        """The format modifiers a plane's IN_FORMATS lists."""
        if "IN_FORMATS" not in props or not props["IN_FORMATS"][1]:
            return []
        blob = self.drm.getblob(props["IN_FORMATS"][1])
        count, offset = struct.unpack_from("<2I", blob, 16)
        return [struct.unpack_from("<Q", blob, offset + 16 + 24 * i)[0] for i in range(count)]

    def regions(self):
        """Each window with region planes by writeback: the window and its regions in turn, each a
        strip below the one before; refused alone, after a gap, beside or above the one before, or
        at another zpos."""
        names = plane_names()
        by_name = {n: p for p, n in names.items() if p in self.planes + self.region_planes}
        windows = {}
        for name, plane in by_name.items():
            m = REGION_NAME.match(name)
            if m and m.group(1) + "0" in by_name:
                windows.setdefault(m.group(1) + "0", {})[int(m.group(2))] = plane
        capture = self.capture_buffer() if self.writeback else None
        if not windows or not capture:
            print("SKIP regions: no region plane, or no writeback capture")
            return
        width, height = self.mode.hdisplay, self.mode.vdisplay
        for window_name, regions in windows.items():
            chain = [by_name[window_name]] + [regions[n] for n in sorted(regions)]
            zpos = self.drm.props(chain[0], OBJ_PLANE)["zpos"][1]
            strip = height // len(chain)
            buffers = []
            for colour in REGION_RGBS[: len(chain)]:
                buffers.append(Buffer(self.drm, width, strip, XRGB8888))
                buffers[-1].fill_rgb(colour)
            layer = lambda n, row, z=zpos, x=0, w=width: (
                chain[n],
                buffers[n],
                (x, row * strip, w, strip),
                {"zpos": z},
            )
            error = self.compose([layer(n, n) for n in range(len(chain))], capture)
            got = [
                capture.pixel(capture.width // 2, (2 * n + 1) * capture.height // (2 * len(chain)))
                for n in range(len(chain))
            ]
            self.check(
                f"regions: {window_name} and its {len(chain) - 1} regions in turn",
                not error and got == REGION_RGBS[: len(chain)],
                f"(errno {error}, strips {got})",
            )
            refusals = {
                "a region alone": [layer(1, 1)],
                "a region after a gap": [layer(0, 0), layer(2, 2)],
                "a region beside its window": [
                    layer(0, 0, w=width // 2),
                    layer(1, 0, x=width // 2, w=width // 2),
                ],
                "a region above its window": [layer(0, 1), layer(1, 0)],
                "a region at another zpos": [layer(0, 0), layer(1, 1, z=zpos + 1)],
            }
            for case, layers in refusals.items():
                error = self.compose(layers, flags=TEST_ONLY | ALLOW_MODESET)
                self.check(
                    f"regions: {window_name} {case} refused", error in REFUSED, f"(errno {error})"
                )

    def writeback_formats(self):
        """Each format the writeback connector lists: a quadrant pattern full screen, captured
        through it, at full size or half where the engine scales its writeback, each quadrant read
        back."""
        if not self.writeback:
            print("SKIP writeback: no writeback connector")
            return
        blob = self.drm.props(self.writeback, OBJ_CONNECTOR)["WRITEBACK_PIXEL_FORMATS"][1]
        data = self.drm.getblob(blob)
        width, height = self.mode.hdisplay, self.mode.vdisplay
        pattern = Buffer(self.drm, width, height, XRGB8888)
        pattern.fill_quadrants(QUADRANT_RGB)
        diff = lambda a, b: max(abs(x - y) for x, y in zip(a, b))
        for (fourcc,) in struct.iter_unpack("<I", data):
            name = fourcc.to_bytes(4, "little").decode()
            tolerance = RGB565_TOLERANCE if fourcc == RGB565 else TOLERANCE
            for scale in (1, 2):
                capture = Buffer(self.drm, width // scale, height // scale, fourcc, unpadded=True)
                error = self.compose(
                    [(self.planes[0], pattern, (0, 0, width, height), {})], capture
                )
                if not error:
                    break
            wrong = [
                (quadrant, seen)
                for quadrant, rgb in QUADRANT_RGB.items()
                if diff(
                    seen := capture.pixel(
                        (2 * quadrant[0] + 1) * capture.width // 4,
                        (2 * quadrant[1] + 1) * capture.height // 4,
                        WRITEBACK_RGB_TO_YUV,
                    ),
                    rgb,
                )
                > tolerance
            ]
            self.check(
                f"writeback: {name}",
                not error and not wrong,
                f"({capture.width}x{capture.height}, errno {error}, wrong {wrong})",
            )

    def rotation(self):
        """Every plane offering rotation, each single transform it lists, a quadrant pattern full
        screen, by writeback: each quadrant's colour where the transform puts it, or refused."""
        capture = self.capture_buffer() if self.writeback else None
        if not capture:
            print("SKIP rotation: no writeback capture at this mode")
            return
        width, height = self.mode.hdisplay, self.mode.vdisplay
        diff = lambda a, b: max(abs(x - y) for x, y in zip(a, b))
        seen = lambda qx, qy: capture.pixel(
            (2 * qx + 1) * capture.width // 4, (2 * qy + 1) * capture.height // 4
        )
        for plane in self.planes:
            props = self.drm.props(plane, OBJ_PLANE)
            if "rotation" not in props:
                continue
            bits = self.drm.enums(props["rotation"][2])
            afbc = AFBC_16X16 in self.modifiers(props)
            kinds = ["linear"] + (["AFBC", "AFBC cropped"] if afbc else [])
            for kind, (name, (turned, moved)) in ((k, r) for k in kinds for r in ROTATIONS.items()):
                if name not in bits:
                    continue
                w, h = (height, width) if turned else (width, height)
                if kind.startswith("AFBC"):
                    pattern = AfbcQuadrants(self.drm, QUADRANT_RGB)
                    if kind == "AFBC cropped":
                        pattern.height = AFBC_CROPPED_LINES
                else:
                    pattern = Buffer(self.drm, w, h, XRGB8888)
                    pattern.fill_quadrants(QUADRANT_RGB)
                label = f"plane {plane} {name}" + ("" if kind == "linear" else f" {kind}")
                error = self.compose(
                    [
                        (
                            plane,
                            pattern,
                            (0, 0, width, height),
                            {"rotation": rotation_value(bits, name)},
                        )
                    ],
                    capture,
                )
                if error in REFUSED:
                    print(f"rotation: {label} refused")
                    continue
                misplaced = [
                    (src, seen(*dst))
                    for src, dst in moved.items()
                    if diff(seen(*dst), QUADRANT_RGB[src]) > TOLERANCE
                ]
                self.check(
                    f"rotation: {label}",
                    not error and not misplaced,
                    f"(errno {error}, misplaced {misplaced})",
                )

    def planes_all(self):
        """H16: every plane on the CRTC at once, each in its own cell at its own zpos, the YUV ones
        scaled up; then a YUV plane over another, by writeback."""
        capture = self.capture_buffer() if self.writeback else None
        if not capture:
            print("SKIP planes-all: no writeback capture at this mode")
            return
        width, height = self.mode.hdisplay, self.mode.vdisplay
        cols = math.ceil(math.sqrt(len(self.planes)))
        cw, ch = width // cols, height // math.ceil(len(self.planes) / cols)
        rgbs = [
            (200, 40, 40),
            (40, 200, 40),
            (40, 40, 200),
            (200, 200, 40),
            (200, 40, 200),
            (40, 200, 200),
        ]
        codes = [(81, 90, 240), (145, 54, 34), (41, 240, 110), (170, 166, 16)]
        sample = lambda x, y: capture.pixel(
            x * capture.width // width, y * capture.height // height
        )
        diff = lambda a, b: max(abs(x - y) for x, y in zip(a, b))

        def layer(plane, i, rect, scale):
            info = self.plane_info(plane)
            extra = {}
            if not info["zpos_fixed"] and "zpos" in info["props"]:
                extra["zpos"] = min(info["zpos"][1], info["zpos"][0] + i)
            if NV12 in info["formats"]:
                code = codes[i % len(codes)]
                buffer = Buffer(self.drm, rect[2] // scale & ~1, rect[3] // scale & ~1, NV12)
                buffer.fill_yuv(code)
                extra.update(COLOR_ENCODING="ITU-R BT.709 YCbCr", COLOR_RANGE="YCbCr limited range")
                return (plane, buffer, rect, extra), to8(
                    yuv_to_rgb([c * 4 / 1023 for c in code], 709)
                )
            fourcc = ARGB8888 if ARGB8888 in info["formats"] else XRGB8888
            buffer = Buffer(self.drm, rect[2], rect[3], fourcc)
            buffer.fill_rgb(rgbs[i % len(rgbs)])
            return (plane, buffer, rect, extra), rgbs[i % len(rgbs)]

        cells = [
            ((i % cols) * cw + 8, (i // cols) * ch + 8, cw - 16 & ~1, ch - 16 & ~1)
            for i in range(len(self.planes))
        ]
        layers, wants = zip(
            *(layer(p, i, rect, 2) for i, (p, rect) in enumerate(zip(self.planes, cells)))
        )
        error = self.compose(list(layers), capture)
        seen = [sample(x + w // 2, y + h // 2) for x, y, w, h in cells] if not error else []
        bad = [
            f"plane {layers[i][0]} {seen[i]} want {wants[i]}"
            for i in range(len(seen))
            if diff(seen[i], wants[i]) > TOLERANCE
        ]
        self.check(
            f"planes-all: {len(self.planes)} planes at once, each in its cell",
            not error and not bad,
            f"(errno {error}{', ' + '; '.join(bad) if bad else ''})",
        )

        video = [p for p in self.planes if NV12 in self.plane_info(p)["formats"]]
        if len(video) < 2:
            print(f"SKIP planes-all: {len(video)} YUV plane, none to stack")
            return
        (under, want_under), (over, want_over) = layer(
            video[0], 0, (0, 0, width, height), 4
        ), layer(video[1], 1, (width // 4, height // 4, width // 2 & ~1, height // 2 & ~1), 2)
        error = self.compose([under, over], capture)
        inner, outer = (
            (sample(width // 2, height // 2), sample(width // 8, height // 8))
            if not error
            else (None, None)
        )
        self.check(
            "planes-all: a YUV plane over another",
            not error
            and diff(inner, want_over) <= TOLERANCE
            and diff(outer, want_under) <= TOLERANCE,
            f"(errno {error}, inner {inner} want {want_over}, outer {outer} want {want_under})",
        )

    def pace(self, seconds, frame_size):
        """Nonblocking commits, each after the last flip event, as a player makes them: the video plane
        full screen from frames of frame_size, the interface over it, an idle plane in every commit.
        """
        width, height = self.mode.hdisplay, self.mode.vdisplay
        frames = [Buffer(self.drm, *frame_size, NV12) for _ in range(2)]
        for i, frame in enumerate(frames):
            frame.fill_yuv((16 + 200 * i, 128, 128))
        ui = Buffer(self.drm, width, height, ARGB8888)
        ui.fill_rgb((40, 200, 40), 255, range(height // 2))
        ui.fill_rgb((0, 0, 0), 0, range(height // 2, height))
        error = self.compose(
            [
                (
                    self.video_plane,
                    frames[0],
                    (0, 0, width, height),
                    dict(
                        COLOR_ENCODING="ITU-R BT.709 YCbCr",
                        COLOR_RANGE="YCbCr limited range",
                        **self.layer_zpos(self.video_plane, 0),
                    ),
                ),
                (self.ui_plane, ui, (0, 0, width, height), self.layer_zpos(self.ui_plane, 1)),
            ]
        )
        fb = self.prop(self.video_plane, OBJ_PLANE, "FB_ID")
        idle = [p for p in self.planes if p not in (self.video_plane, self.ui_plane)][:1]
        commits = refused = failed = late = 0
        end = time.monotonic() + seconds
        while not error and time.monotonic() < end:
            changes = {self.video_plane: {fb: frames[commits % 2].fb}}
            for p in idle:
                changes[p] = {
                    self.prop(p, OBJ_PLANE, "FB_ID"): 0,
                    self.prop(p, OBJ_PLANE, "CRTC_ID"): 0,
                }
            result = self.drm.commit(changes, NONBLOCK | PAGE_FLIP_EVENT)
            commits += 1
            if result == EBUSY:
                refused += 1
                time.sleep(0.004)
            elif result:
                if not failed:
                    print(
                        f"RECORD pacing: commit {commits} failed, errno {result}: {self.output_state()}"
                    )
                failed += 1
            elif not self.drm.wait_flip():
                late += 1
        return {
            "error": error,
            "commits": commits,
            "rate": commits / seconds,
            "refused": refused,
            "failed": failed,
            "late": late,
        }

    def pacing(self):
        """H23: a player's pace for a minute, the video at the mode's size."""
        if not (self.video_plane and self.ui_plane):
            print("SKIP pacing: no video and interface planes")
            return
        r = self.pace(PACING_SECONDS, (self.mode.hdisplay, self.mode.vdisplay))
        self.check(
            f"pacing: {PACING_SECONDS} s of flip-paced nonblocking commits",
            not r["error"] and not r["refused"] and not r["failed"] and not r["late"],
            f"(errno {r['error']}, {r['commits']} commits, {r['rate']:.1f}/s, {r['refused']} refused, "
            f"{r['failed']} failed, {r['late']} without an event)",
        )

    def connector_modes(self):
        c = self.drm.call("connector", Connector(connector_id=self.hdmi_connector))
        modes = (ModeInfo * max(c.count_modes, 1))()
        self.drm.call(
            "connector",
            Connector(
                connector_id=self.hdmi_connector,
                count_modes=c.count_modes,
                modes=ctypes.addressof(modes),
            ),
        )
        return list(modes[: c.count_modes])

    def set_mode(self, mode):
        blob = self.drm.blob(bytes(mode))
        error = self.drm.commit(
            {
                self.crtc: {
                    self.prop(self.crtc, OBJ_CRTC, "MODE_ID"): blob,
                    self.prop(self.crtc, OBJ_CRTC, "ACTIVE"): 1,
                },
                self.hdmi_connector: {
                    self.prop(self.hdmi_connector, OBJ_CONNECTOR, "CRTC_ID"): self.crtc
                },
            }
        )
        if not error:
            self.mode = mode
        return error

    def rating(self):
        """Each LADDER mode the driver offers, at a player's pace with the video at the mode's size:
        sustained when every flip is on time, with no underrun and nothing new in the kernel log. The
        verdicts: the first sustained rung of RESOLUTION_LADDER and of RATE_LADDER."""
        if not (
            self.hdmi_connector and self.crtc is not None and self.video_plane and self.ui_plane
        ):
            print("SKIP rating: no HDMI connector, CRTC with a mode, or video and interface planes")
            return
        offered = self.connector_modes()
        print(
            "RECORD rating: offered "
            + " ".join(sorted({f"{m.hdisplay}x{m.vdisplay}@{m.vrefresh}" for m in offered}))
        )
        sustained, tried = set(), set()
        for name, (_, ha, va, hz) in LADDER.items():
            interlaced = name[-3] == "i"  # 1080i60: the scan is the name's, the timing the same
            mode = next(
                (
                    m
                    for m in offered
                    if (m.hdisplay, m.vdisplay, m.vrefresh) == (ha, va, hz)
                    and bool(m.flags & MODE_INTERLACE) == interlaced
                ),
                None,
            )
            if mode is None:
                print(f"RECORD rating: {name} not offered: the driver pruned it")
                continue
            tried.add(name)
            log, counter = kernel_log(), underrun_count()
            error = self.set_mode(mode)
            time.sleep(0.5)
            r = (
                self.pace(RUNG_SECONDS, (min(ha, 3840), min(va, 2160)))
                if not error
                else {"error": error}
            )
            new = [line for line in kernel_log()[len(log) :]]
            glitches = [
                line
                for line in new
                if not NO_SCREEN_NOISE.search(line) and not OFF_PATH_NOISE.search(line)
            ]
            underruns = None if counter is None else underrun_count() - counter
            ok = (
                not error
                and not r["error"]
                and not r["refused"]
                and not r["failed"]
                and not r["late"]
                and r["rate"] >= 0.95 * mode.vrefresh
                and not glitches
                and not underruns
            )
            detail = (
                f"errno {error}"
                if error
                else f"{r['commits']} commits, {r['rate']:.1f}/s of {mode.vrefresh}, {r['refused']} refused, "
                f"{r['late']} late, {'underruns unmeasured' if underruns is None else f'{underruns} underruns'}, "
                f"{len(glitches)} kernel lines"
            )
            verdict = (
                "not sustained"
                if not ok
                else "kept pace, underruns unmeasured" if underruns is None else "sustained"
            )
            print(f"RECORD rating: {name} {verdict} ({detail})")
            for line in sorted(set(re.sub(r"^\[[ 0-9.]+\] ", "", g) for g in glitches))[:3]:
                print(f"  kernel: {line}")
            if len(new) > len(glitches):
                print(
                    f"  ({len(new) - len(glitches)} lines from the absent screen or off the display path, not counted)"
                )
            if ok:
                sustained.add(name)
        size = next((n for n in RESOLUTION_LADDER if n in sustained), None)
        rate = next((n for n in RATE_LADDER if n in sustained), None)
        unmeasured = (
            " (underruns unmeasured: the driver reports none)" if underrun_count() is None else ""
        )
        print(f"RATING display: largest {size or 'none'}, fastest {rate or 'none'}{unmeasured}")
        self.check(
            "rating: the display sustains a ladder mode", bool(sustained), f"({size}, {rate})"
        )
        offered_broadcast = [n for n in BROADCAST_LADDER if n in tried]
        held = [n for n in offered_broadcast if n in sustained]
        self.check(
            "rating: the display sustains each broadcast mode it offers",
            held == offered_broadcast,
            f"({' '.join(held) or 'none'} of {' '.join(offered_broadcast) or 'none offered'})",
        )

    def scope(self):
        """H24: what each colour stage maps, the interface and an HDR video plane under it."""
        if not (self.video_plane and self.ui_plane) or not self.writeback:
            print(
                f"SKIP scope: {'no writeback connector' if self.video_plane and self.ui_plane else 'no video and interface planes'}"
            )
            return
        capture = self.capture_buffer()
        if not capture:
            print("SKIP scope: the writeback takes no capture at this mode")
            return
        diff = lambda a, b: max(abs(x - y) for x, y in zip(a, b))
        _, ui0, video0, _ = self.video_and_interface(capture=capture)
        if self.video_plane in self.lut_planes:
            nodes, data = quantized(lattice(lambda v: [1 - c for c in v]))
            blob = self.drm.blob(data)
            error, ui, video, _ = self.video_and_interface(
                {"SUNXI_CDC_LUT3D": blob}, capture=capture
            )
            per_plane = not error and diff(ui, ui0) <= TOLERANCE and diff(video, video0) > TOLERANCE
            self.check(
                "scope: SUNXI_CDC_LUT3D maps its plane alone",
                per_plane,
                f"(errno {error}, interface {ui0} -> {ui}, video {video0} -> {video})",
            )
            self.drm.unblob(blob)
        if "HDR_EXT_DATA" in self.drm.props(self.crtc, OBJ_CRTC):
            blob = self.drm.blob(rk_sdr2hdr("PQ"))
            tagged = {"EOTF": 2} if "EOTF" in self.plane_info(self.video_plane)["props"] else {}
            _, _, hdr0, _ = self.video_and_interface(tagged, capture=capture)
            error, ui, hdr, _ = self.video_and_interface(tagged, {"HDR_EXT_DATA": blob}, capture)
            want = to8(sdr_to_hdr([c / 255 for c in (40, 200, 40)], "PQ"))
            mapped = not error and diff(ui, want) <= TOLERANCE
            scope = (
                "per plane, the PQ video plane passing"
                if diff(hdr, hdr0) <= TOLERANCE
                else "the whole output"
            )
            self.check(
                f"scope: HDR_EXT_DATA SDR to PQ maps the interface; scope {scope}",
                mapped,
                f"(errno {error}, interface {ui} want {want}, PQ video {hdr0} -> {hdr})",
            )
            self.drm.unblob(blob)
            self.compose(
                [(self.video_plane, Buffer(self.drm, 64, 64, XRGB8888), (0, 0, 64, 64), {})],
                crtc={"HDR_EXT_DATA": 0},
            )

    def record_maps(self):
        """H25: the mappings the engine did, and those left to the GPU."""
        mappings = ("HDR10 to SDR", "HLG to SDR", "SDR to PQ", "SDR to HLG", "HLG to PQ")
        engine = [m for m in mappings if m in self.maps]
        print(
            f"RECORD maps in the engine: {', '.join(engine) or 'none'}; "
            f"to the GPU: {', '.join(m for m in mappings if m not in engine) or 'none'}"
        )

    def gamma(self):
        """The CRTC's gamma LUT, by writeback: each GAMMA_TABLES curve maps a colour as it says,
        and no table restores it."""
        props = self.drm.props(self.crtc, OBJ_CRTC) if self.crtc is not None else {}
        planes = [p for p in self.planes if XRGB8888 in self.plane_info(p)["formats"]]
        if "GAMMA_LUT" not in props or not self.writeback or not planes:
            print("SKIP gamma: no CRTC GAMMA_LUT, writeback connector or XRGB8888 plane")
            return
        capture = self.capture_buffer()
        if capture is None:
            print("SKIP gamma: the writeback takes no capture")
            return
        rgb = Buffer(self.drm, 256, 256, XRGB8888)
        rgb.fill_rgb(GAMMA_SIGNAL)
        size = props["GAMMA_LUT_SIZE"][1]
        centre = (capture.width // 2, capture.height // 2)
        results = []
        for name, curve in (*GAMMA_TABLES, ("none", None)):
            blob = 0
            if curve is not None:
                entries = [round(curve(i / (size - 1)) * 0xFFFF) for i in range(size)]
                blob = self.drm.blob(b"".join(struct.pack("<4H", e, e, e, 0) for e in entries))
            error = self.drm.commit({self.crtc: {props["GAMMA_LUT"][0]: blob}})
            error = error or self.show(planes[0], rgb, None, capture=capture)
            curve = curve or (lambda v: v)
            want = tuple(round(curve(c / 255) * 255) for c in GAMMA_SIGNAL)
            got = capture.pixel(*centre) if not error else None
            results.append((name, error, got, want))
            if blob:
                self.drm.unblob(blob)
        if all(not error and got == GAMMA_SIGNAL for _, error, got, _ in results):
            print("UNTESTED gamma: tables taken, none in the writeback: it is taken before gamma")
            return
        for name, error, got, want in results:
            self.check(
                f"gamma: {name}",
                not error and max(abs(a - b) for a, b in zip(got, want)) <= TOLERANCE,
                f"got {got} want {want} (errno {error})",
            )

    def lut(self):
        if not self.lut_planes or not self.writeback:
            print("SKIP lut: no plane with SUNXI_CDC_LUT3D, or no writeback connector")
            return
        width, height = self.mode.hdisplay, self.mode.vdisplay
        capture = Buffer(self.drm, width // 2, height // 2, XRGB8888, unpadded=True)
        for plane in self.lut_planes:
            lut_prop = self.prop(plane, OBJ_PLANE, "SUNXI_CDC_LUT3D")
            good = quantized(lattice(lambda v: v))[1]
            for name, data in (("short", good[:-8]), ("reserved", good[:-2] + b"\x01\x00")):
                blob = self.drm.blob(data)
                error = self.drm.commit({plane: {lut_prop: blob}}, TEST_ONLY)
                self.check(f"plane {plane}: a {name} blob refused", error == 22, f"(errno {error})")
                self.drm.unblob(blob)
            error = self.drm.commit({plane: {lut_prop: 0xFFFFFFF0}}, TEST_ONLY)
            self.check(f"plane {plane}: an unknown blob refused", error == 22, f"(errno {error})")

            rgb = Buffer(self.drm, 256, 256, XRGB8888)
            signal = (105, 174, 49)
            rgb.fill_rgb(signal)
            centre = (width // 4, height // 4)
            tables = [
                ("identity", lambda v: v),
                (
                    "channel mix",
                    lambda v: [
                        0.4 * v[0] + 0.2 * v[1] + 0.1 * v[2],
                        0.1 * v[0] + 0.3 * v[1] + 0.4 * v[2],
                        0.2 * v[0] + 0.3 * v[1] + 0.1 * v[2],
                    ],
                ),
                ("inversion, switched while active", lambda v: [1 - c for c in v]),
            ]
            for name, f in tables:
                nodes, data = quantized(lattice(f))
                blob = self.drm.blob(data)
                error = self.show(plane, rgb, blob, capture=capture)
                want = to8(trilinear(nodes, [c / 255 for c in signal]))
                got = capture.pixel(*centre) if not error else None
                self.check(
                    f"plane {plane}: RGB {name}",
                    not error and max(abs(a - b) for a, b in zip(got, want)) <= TOLERANCE,
                    f"got {got} want {want}",
                )
                if name == "channel mix":
                    held = 0
                    for flip in range(60):
                        rgb.fill_rgb(signal)
                        self.show(plane, rgb, blob, capture=capture if flip % 10 == 9 else None)
                        held += (
                            flip % 10 == 9
                            and max(abs(a - b) for a, b in zip(capture.pixel(*centre), want))
                            <= TOLERANCE
                        )
                    self.check(
                        f"plane {plane}: the table held across 60 flips",
                        held == 6,
                        f"({held} of 6 captures)",
                    )
                self.drm.unblob(blob)

            grid, side = 8, 64
            cases = [
                ("HDR10 to SDR", P010, 2020, hdr10_to_sdr, "ITU-R BT.709 YCbCr", 709),
                ("HLG to SDR", P010, 2020, hlg_to_sdr, "ITU-R BT.709 YCbCr", 709),
                ("SDR to PQ", NV12, 709, sdr_to_pq, "ITU-R BT.2020 YCbCr", 2020),
                ("HLG to PQ", P010, 2020, hlg_to_pq, "ITU-R BT.2020 YCbCr", 2020),
            ]
            seed = 12345
            for name, fourcc, _, f, encoding, out_space in cases:
                depth = 1023 if fourcc == P010 else 255
                scale = 4 if fourcc == P010 else 1
                codes = []
                for i in range(grid * grid):
                    if i < 16:
                        codes.append(((16 + i * 219 // 15) * scale, 128 * scale, 128 * scale))
                    else:
                        seed = (seed * 1664525 + 1013904223) & 0xFFFFFFFF
                        codes.append(
                            (
                                (16 + (seed >> 8) % 220) * scale,
                                (40 + (seed >> 12) % 177) * scale,
                                (40 + (seed >> 16) % 177) * scale,
                            )
                        )
                picture = Buffer(self.drm, grid * side, grid * side, fourcc)
                picture.fill_patches(codes, grid, side)
                nodes, data = quantized(lattice(f))
                blob = self.drm.blob(data)
                error = self.show(plane, picture, blob, encoding, capture) or self.show(
                    plane, picture, blob, encoding, capture
                )
                worst, total = 0, 0
                for i, code in enumerate(codes):
                    x = (i % grid * side + side // 2) * height // (grid * side) // 2
                    y = (i // grid * side + side // 2) * height // (grid * side) // 2
                    want = to8(yuv_to_rgb(trilinear(nodes, [c / depth for c in code]), out_space))
                    got = capture.pixel(x, y)
                    error_here = max(abs(a - b) for a, b in zip(got, want))
                    worst, total = max(worst, error_here), total + error_here
                if self.check(
                    f"plane {plane}: {name}, 64 patches",
                    not error and worst <= TOLERANCE,
                    (
                        f"max {worst} mean {total / len(codes):.2f}"
                        if not error
                        else f"(errno {error})"
                    ),
                ):
                    self.maps.add(name)
                self.drm.unblob(blob)
            self.show(plane, rgb, 0)

    def color_pipelines(self):
        """Each plane offering SDR to PQ as a color pipeline: its first colorop, and the chain's ids;
        none where the kernel predates the client cap."""
        try:
            self.drm.call("cap", ClientCap(capability=CAP_COLOR_PIPELINE, value=1))
        except OSError as error:
            if error.errno != errno.EINVAL:
                raise
            return {}
        found = {}
        for plane in self.planes:
            prop = self.drm.props(plane, OBJ_PLANE).get("COLOR_PIPELINE")
            for first in (
                (v for n, v in self.drm.enums(prop[2]).items() if n != "Bypass") if prop else ()
            ):
                chain, op = [], first
                while op:
                    chain.append(op)
                    op = self.drm.props(op, OBJ_COLOROP)["NEXT"][1]
                ops = SDR_TO_HDR + (HDR_CURVES["PQ"],)
                if len(chain) == len(ops) and all(map(self.colorop_offers, chain, ops)):
                    found[plane] = chain
        return found

    def colorop_offers(self, op, name):
        """Whether a colorop offers name: a curve among its curves, or its type."""
        props = self.drm.props(op, OBJ_COLOROP)
        if "CURVE_1D_TYPE" in props:
            return name in self.drm.enums(props["CURVE_1D_TYPE"][2])
        _, value, prop = props["TYPE"]
        return self.drm.enums(prop).get(name) == value

    def sdr_to_hdr(self, chain, target="PQ", matrix=BT709_TO_2020, white=SDR_WHITE, bypass=()):
        """The colorops' {property id: value} for SDR to the target: white in thousands of nits,
        each op of bypass left out."""
        ctm = []
        for row in matrix:
            for c in list(row) + [0]:
                ctm.append(round(abs(c) * S31_32_ONE) | (S31_32_SIGN if c < 0 else 0))
        blob = self.drm.blob(struct.pack("<12Q", *ctm))
        # HLG's 1.0 is its 1000-nit peak
        unit = PQ_125_UNIT_NITS / 1000 if target == "PQ" else 1
        mult = round(white / unit * S31_32_ONE)
        settings = [{}, {"DATA": blob}, {"MULTIPLIER": mult}, {}]
        objects = {}
        for i, (op, extra) in enumerate(zip(chain, settings)):
            props = self.drm.props(op, OBJ_COLOROP)
            values = dict(extra, BYPASS=int(i in bypass))
            if "CURVE_1D_TYPE" in props:
                values["CURVE_1D_TYPE"] = self.drm.enum_value(
                    props["CURVE_1D_TYPE"][2], (SDR_TO_HDR + (HDR_CURVES[target],))[i]
                )
            objects[op] = {props[k][0]: v for k, v in values.items()}
        return objects

    def colorop(self):
        """SDR to PQ and to HLG by a plane's color pipeline, against BT.2408's SDR in HDR by
        writeback; part of it bypassed, a negative coefficient or two planes' whites apart
        refused."""
        pipelines = self.color_pipelines() if self.writeback else {}
        if not pipelines:
            print("SKIP colorop: no plane offers SDR to PQ, or no writeback connector")
            return
        width, height = self.mode.hdisplay, self.mode.vdisplay
        capture = Buffer(self.drm, width, height, ARGB8888, unpadded=True)
        rgb = Buffer(self.drm, 256, 256, XRGB8888)
        plane, chain = next(iter(pipelines.items()))
        on = {"COLOR_PIPELINE": chain[0]}
        layer = lambda p, x: (p, rgb, (x, 0, width // 2, height), on)
        for target, curve in HDR_CURVES.items():
            if not self.colorop_offers(chain[-1], curve):
                print(f"SKIP colorop: the pipeline's last curve lacks {curve}")
                continue
            worst, error = 0, 0
            for signal in SDR2HDR_SIGNALS:
                rgb.fill_rgb(signal)
                objects = self.sdr_to_hdr(chain, target)
                error = error or self.compose(
                    [(plane, rgb, (0, 0, width, height), on)], capture, objects=objects
                )
                want = to8(sdr_to_hdr([c / 255 for c in signal], target))
                got = capture.pixel(width // 2, height // 2)
                worst = max([worst] + [abs(a - b) for a, b in zip(got, want)])
            self.check(
                f"colorop: SDR to {target} at 203 nits, 7 colours",
                not error and worst <= TOLERANCE,
                f"max {worst}" if not error else f"(errno {error})",
            )
        negative = [list(BT709_TO_2020[0]), list(BT709_TO_2020[1]), list(BT709_TO_2020[2])]
        negative[0][1] = -negative[0][1]
        refusals = {
            "part bypassed": [self.sdr_to_hdr(chain, bypass=(3,))],
            "a negative coefficient": [self.sdr_to_hdr(chain, matrix=negative)],
        }
        for case, objects in refusals.items():
            error = self.compose(
                [layer(plane, 0)], objects=objects[0], flags=TEST_ONLY | ALLOW_MODESET
            )
            self.check(f"colorop: {case} refused", error in REFUSED, f"(errno {error})")
        if len(pipelines) < 2:
            print("SKIP colorop: one plane offers SDR to PQ, none to share it")
            return
        (first, a), (second, b) = list(pipelines.items())[:2]
        for case, b_white, refused in (("alike", SDR_WHITE, False), ("whites apart", 0.1, True)):
            objects = {**self.sdr_to_hdr(a), **self.sdr_to_hdr(b, white=b_white)}
            layers = [
                layer(first, 0),
                (second, rgb, (width // 2, 0, width // 2, height), {"COLOR_PIPELINE": b[0]}),
            ]
            error = self.compose(layers, objects=objects, flags=TEST_ONLY | ALLOW_MODESET)
            self.check(
                f"colorop: two planes {case} {'refused' if refused else 'taken'}",
                (error in REFUSED) if refused else not error,
                f"(errno {error})",
            )

    def sdr2hdr(self):
        props = self.drm.props(self.crtc, OBJ_CRTC)
        if "HDR_EXT_DATA" not in props or not self.writeback:
            print("SKIP sdr2hdr: the CRTC lacks HDR_EXT_DATA, or no writeback connector")
            return
        blob = self.drm.blob(rk_sdr2hdr("PQ")[:-4])
        error = self.drm.commit({self.crtc: {props["HDR_EXT_DATA"][0]: blob}}, TEST_ONLY)
        self.check("sdr2hdr: a short HDR_EXT_DATA refused", error == 22, f"(errno {error})")
        self.drm.unblob(blob)
        width, height = self.mode.hdisplay, self.mode.vdisplay
        capture = Buffer(self.drm, width, height, ARGB8888, unpadded=True)
        rgb = Buffer(self.drm, 256, 256, XRGB8888)
        plane = self.planes[0]
        error = self.show(plane, rgb, None, capture=capture)
        if error:
            print(f"SKIP sdr2hdr: baseline RGB writeback refused (errno {error})")
            return
        for target in RK_TARGETS:
            blob = self.drm.blob(rk_sdr2hdr(target))
            worst, error = 0, 0
            for signal in SDR2HDR_SIGNALS:
                rgb.fill_rgb(signal)
                error = error or self.show(
                    plane, rgb, None, capture=capture, crtc={"HDR_EXT_DATA": blob}
                )
                want = to8(sdr_to_hdr([c / 255 for c in signal], target))
                got = capture.pixel(width // 2, height // 2)
                worst = max([worst] + [abs(a - b) for a, b in zip(got, want)])
            if self.check(
                f"sdr2hdr: SDR to {target}, 7 colours",
                not error and worst <= TOLERANCE,
                f"max {worst}" if not error else f"(errno {error})",
            ):
                self.maps.add(f"SDR to {target}")
            self.drm.unblob(blob)
        self.show(plane, rgb, None, crtc={"HDR_EXT_DATA": 0})

    def hdmi_registers(self):
        paths = glob.glob("/sys/kernel/debug/regmap/*.hdmi/registers") + glob.glob(
            "/sys/kernel/debug/regmap/*.hdmi-tx/registers"
        )
        if not paths:
            return None
        with open(paths[0]) as f:
            regs = {
                int(address, 16): int(value, 16)
                for address, value in (line.split(":") for line in f)
            }
        addresses = sorted(regs)
        stride = (
            math.gcd(*(b - a for a, b in zip(addresses, addresses[1:]))) or 1
        )  # 4 at reg-io-width 4
        return {address // stride: value for address, value in regs.items()}

    def hdmi_signal(self, props, eotf, bpc):
        """Sets the output SDR (eotf None) or HDR, reads back what the controller sends:
        (errno, DRM InfoFrame EOTF or None, AVI pixel format, AVI extended colorimetry)."""
        blob = 0
        if eotf is not None:
            # hdr_output_metadata: type 0, then the static type 1 block: EOTF, BT.2020 primaries, D65,
            # 1000 / 0.005 nits, MaxCLL 1000, MaxFALL 400.
            blob = self.drm.blob(
                struct.pack(
                    "<I2B8H4H2x",
                    0,
                    eotf,
                    0,
                    35400,
                    14600,
                    8500,
                    39850,
                    6550,
                    2300,
                    15635,
                    16450,
                    1000,
                    50,
                    1000,
                    400,
                )
            )
        # BT.2020 as YCbCr, or as RGB where the output is RGB; a connector without Colorspace sends its own
        for space in ("Default",) if eotf is None else ("BT2020_YCC", "BT2020_RGB"):
            values = {props["HDR_OUTPUT_METADATA"][0]: blob, props["max bpc"][0]: bpc}
            if "Colorspace" in props:
                values[props["Colorspace"][0]] = self.drm.enum_value(props["Colorspace"][2], space)
            error = self.drm.commit({self.hdmi_connector: values})
            if not error:
                break
        # A forced connector has no hot-plug signal, and Rockchip's dw-hdmi then sets its InfoFrames only
        # as the output comes up: cycle it.
        if not error and self.synthetic_sink:
            active = self.prop(self.crtc, OBJ_CRTC, "ACTIVE")
            error = self.drm.commit({self.crtc: {active: 0}}) or self.drm.commit(
                {self.crtc: {active: 1}}
            )
        time.sleep(1)
        if blob:
            self.drm.unblob(blob)
        regs = self.hdmi_registers()
        sent = regs[0x116A] if regs[0x10E3] & 0x80 else None
        fmt = {0: "RGB", 1: "YCbCr 4:2:2", 2: "YCbCr 4:4:4", 3: "YCbCr 4:2:0"}[regs[0x1019] & 3]
        return error, sent, fmt, regs[0x101B] >> 4 & 7

    def hdmi_props(self, case):
        if not self.hdmi_connector or self.hdmi_registers() is None:
            print(
                f"SKIP {case}: no connected HDMI connector, or no dw-hdmi register map in debugfs"
            )
            return None
        props = self.drm.props(self.hdmi_connector, OBJ_CONNECTOR)
        if not all(k in props for k in ("HDR_OUTPUT_METADATA", "max bpc")):
            print(f"SKIP {case}: the connector lacks HDR_OUTPUT_METADATA or max bpc")
            return None
        return props

    def hdmi_sdr(self, props, bpc):
        values = {props["HDR_OUTPUT_METADATA"][0]: 0, props["max bpc"][0]: bpc}
        if "Colorspace" in props:
            values[props["Colorspace"][0]] = self.drm.enum_value(props["Colorspace"][2], "Default")
        self.drm.commit({self.hdmi_connector: values})

    def hdmi(self):
        props = self.hdmi_props("hdmi")
        if not props:
            return
        bpc_before = props["max bpc"][1]
        low, high = self.drm.prop_range(props["max bpc"][2])
        for eotf, name in ((None, "SDR"), (EOTF_PQ, "PQ"), (EOTF_HLG, "HLG")):
            for bpc in [b for b in (8, 10) if low <= b <= high]:
                error, sent, fmt, ec = self.hdmi_signal(props, eotf, bpc)
                # without Colorspace the colorimetry is the driver's: recorded, not judged
                ok = (
                    not error
                    and sent == eotf
                    and ("Colorspace" not in props or (ec == 6) == (eotf is not None))
                )
                self.check(
                    f"hdmi: {name}, max bpc {bpc}",
                    ok,
                    f"(errno {error}) DRM InfoFrame {'off' if sent is None else 'EOTF %d' % sent}, {fmt}, EC {ec}",
                )
        self.hdmi_sdr(props, bpc_before)

    def deep_colour(self):
        """Max bpc 10 at 1080p60 and 4K60, by dw-hdmi's registers: the format DEEP_COLOUR_CASES
        names, judged where the driver picks it, recorded elsewhere."""
        props = self.hdmi_props("deep colour")
        if not props or self.hdmi_registers() is None:
            print("SKIP deep colour: no HDMI connector, or no dw-hdmi register map in debugfs")
            return
        judged = dt_compatible(DEEP_COLOUR_HDMI) and "hdmi_output_format" not in props
        mode = self.mode
        for width, want in DEEP_COLOUR_CASES:
            modes = [m for m in self.connector_modes() if m.hdisplay == width and m.vrefresh == 60]
            if not modes:
                print(f"SKIP deep colour: no {width}-wide 60 Hz mode offered")
                continue
            self.set_mode(modes[0])
            error, _, fmt, _ = self.hdmi_signal(props, None, 10)
            regs = self.hdmi_registers() or {}
            got = (fmt, regs.get(TX_INVID0, 0), regs.get(VP_PR_CD, 0))
            line = f"{width}-wide 60 Hz, max bpc 10: AVI {fmt}, TX_INVID0 {got[1]:#04x}, "
            line += f"VP_PR_CD {got[2]:#04x}"
            if judged:
                self.check(f"deep colour: {line}", not error and got == want, f"(errno {error})")
            else:
                print(f"RECORD deep colour: {line}")
        self.set_mode(mode)
        self.hdmi_sdr(props, 8)

    def color_format(self):
        """Each COLOR_FORMAT_CASES format asked of a screen taking them all, by dw-hdmi's
        registers; "AUTO" after."""
        props = self.hdmi_props("color format")
        if not props or "color format" not in props:
            print("SKIP color format: the connector lacks the color format property")
            return
        prop, _, enum = props["color format"]
        mode = self.mode
        for (width, asked, bpc), want in COLOR_FORMAT_CASES:
            modes = [m for m in self.connector_modes() if m.hdisplay == width and m.vrefresh == 60]
            if not modes:
                print(f"SKIP color format: no {width}-wide 60 Hz mode offered")
                continue
            self.set_mode(modes[0])
            self.drm.commit({self.hdmi_connector: {prop: self.drm.enum_value(enum, asked)}})
            error, _, fmt, _ = self.hdmi_signal(props, None, bpc)
            regs = self.hdmi_registers() or {}
            got = (fmt, regs.get(VP_PR_CD, 0) >> 4, regs.get(VP_REMAP, 0) & 3)
            self.check(
                f"color format: {asked} at {width}-wide 60 Hz, max bpc {bpc}",
                not error and got == want,
                f"(AVI {got[0]}, depth {got[1]}, 4:2:2 remap {got[2]}, errno {error})",
            )
        self.drm.commit({self.hdmi_connector: {prop: self.drm.enum_value(enum, "AUTO")}})
        self.set_mode(mode)
        self.hdmi_sdr(props, 8)

    def stereo(self):
        """Each frame-packed mode a 3D screen offers: both views and the space between them as one
        frame, and the vendor InfoFrame saying frame packing, by dw-hdmi's registers."""
        if self.hdmi_registers() is None or not self.hdmi_connector:
            print("SKIP stereo: no HDMI connector or dw-hdmi register map")
            return
        self.drm.call("cap", ClientCap(capability=CAP_STEREO_3D, value=1))
        packed = [
            m
            for m in self.connector_modes()
            if m.flags & MODE_FLAG_3D_MASK == MODE_FLAG_3D_FRAME_PACKING
        ]
        if not packed:
            print("SKIP stereo: the driver offers no frame-packed mode")
            return
        mode = self.mode
        for m in packed:
            error = self.set_mode(m)
            regs = self.hdmi_registers() or {}
            lines = regs.get(FC_INVACTV1, 0) << 8 | regs.get(FC_INVACTV0, 0)
            payload = (regs.get(FC_VSDPAYLOAD0), regs.get(FC_VSDPAYLOAD1))
            want = 2 * m.vdisplay + m.vtotal - m.vdisplay
            self.check(
                f"stereo: {m.hdisplay}x{m.vdisplay}@{m.vrefresh} frame packing",
                not error and lines == want and payload == FRAME_PACKING_PAYLOAD,
                f"(errno {error}, {lines} active lines of {want}, payload {payload})",
            )
        self.set_mode(mode)

    def hdmi_audio(self):
        """Against a screen taking 8-channel LPCM: each case plays in real time, and the controller
        takes a lane per channel pair, the channel count, and the multichannel layout past two."""
        card = hdmi_sound_card()
        if card is None or self.crtc is None or self.hdmi_registers() is None:
            print("SKIP hdmi audio: no HDMI sound card, mode, or dw-hdmi register map")
            return
        for channels, rate in HDMI_AUDIO_CASES:
            took, error, regs = play_reading(card, channels, rate, self.hdmi_registers)
            got = (regs.get(AUD_CONF0, 0) & 0xF, regs.get(FC_AUDICONF0, 0) >> 4 & 7)
            got += (regs.get(FC_AUDSCONF, 0) & 1,)
            want = ((1 << math.ceil(channels / 2)) - 1, channels - 1, int(channels > 2))
            self.check(
                f"hdmi audio: {channels} channels at {rate} Hz",
                not error and abs(took - PLAY_SECONDS) <= PLAY_SLACK and got == want,
                f"({took:.2f} s, lanes {got[0]:#x}, CC {got[1]}, layout {got[2]}) {error}",
            )

    def sinks(self, name, eotfs):
        """Against a synthetic screen: HDR sent for each EOTF it lists; what the box does with the rest."""
        props = self.hdmi_props(f"sinks {name}")
        if not props:
            return
        for eotf, signal in ((EOTF_PQ, "PQ"), (EOTF_HLG, "HLG")):
            error, sent, _, _ = self.hdmi_signal(props, eotf, 8)
            if eotfs >> eotf & 1:
                self.check(
                    f"sinks: a {name} screen takes {signal}",
                    not error and sent == eotf,
                    f"(errno {error}, DRM InfoFrame {'off' if sent is None else 'EOTF %d' % sent})",
                )
            else:
                print(
                    f"RECORD sinks: a {name} screen, {signal} asked: errno {error}, DRM InfoFrame "
                    f"{'off' if sent is None else 'EOTF %d' % sent}"
                )
        self.hdmi_sdr(props, 8)

    def hdr10plus(self):
        regs = self.hdmi_registers()
        if not self.hdmi_connector or regs is None:
            print(
                "SKIP hdr10plus: no connected HDMI connector, or no dw-hdmi register map in debugfs"
            )
            return
        props = self.drm.props(self.crtc, OBJ_CRTC)
        if "HDR10PLUS_VSIF" not in props:
            print("SKIP hdr10plus: the CRTC lacks HDR10PLUS_VSIF")
            return
        prop = props["HDR10PLUS_VSIF"][0]
        connector_props = self.drm.props(self.hdmi_connector, OBJ_CONNECTOR)
        bpc = connector_props["max bpc"][0]
        oui = bytes((0x8B, 0x84, 0x90))

        def sent():
            regs = self.hdmi_registers()
            if not regs[0x10B3] & 0x08:
                return None
            return (
                bytes(
                    [regs[0x1029], regs[0x1030], regs[0x1031]]
                    + [regs[0x1032 + i] for i in range(24)]
                ),
                regs[0x102A],
            )

        for name, data in (
            ("short", oui + bytes(23)),
            ("wrong OUI", bytes(3) + bytes(range(1, 25))),
        ):
            blob = self.drm.blob(data)
            error = self.drm.commit({self.crtc: {prop: blob}}, TEST_ONLY)
            self.check(f"hdr10plus: a {name} payload refused", error == 22, f"(errno {error})")
            self.drm.unblob(blob)
        for name, data in (
            ("a payload", oui + bytes(range(1, 25))),
            ("a second payload", oui + bytes(range(64, 88))),
            ("none", None),
        ):
            blob = self.drm.blob(data) if data else 0
            error = self.drm.commit({self.crtc: {prop: blob}}, 0)
            time.sleep(0.2)
            got = sent()
            # none: the slot goes back to HDMI's own VSIF, OUI 0x000c03
            ok = not error and (
                got == (data, 27) if data else got is None or got[0][:3] == bytes((3, 12, 0))
            )
            self.check(
                f"hdr10plus: {name} in place, no mode set",
                ok,
                f"(errno {error}, VSIF {'off' if got is None else got[0][:6].hex() + '..., size %d' % got[1]})",
            )
            if blob:
                self.drm.unblob(blob)
        data = oui + bytes(range(1, 25))
        blob = self.drm.blob(data)
        before = connector_props["max bpc"][1]
        error = self.drm.commit(
            {self.crtc: {prop: blob}, self.hdmi_connector: {bpc: 10 if before != 10 else 8}}
        )
        time.sleep(1)
        got = sent()
        self.check(
            "hdr10plus: kept across a mode set",
            not error and got == (data, 27),
            f"(errno {error}, VSIF {'off' if got is None else 'sent'})",
        )
        self.drm.commit({self.crtc: {prop: 0}, self.hdmi_connector: {bpc: before}})
        self.drm.unblob(blob)

    def underruns(self):
        counters = glob.glob("/sys/kernel/debug/dri/*/crtc-*/underruns")
        if not counters or not self.lut_planes:
            print("SKIP underruns: no underrun counter in debugfs")
            return
        with open(counters[0]) as f:
            first = int(f.read())
        buffer = Buffer(self.drm, 256, 256, XRGB8888)
        buffer.fill_rgb((128, 128, 128))
        self.show(self.lut_planes[0], buffer, 0)
        time.sleep(3)
        with open(counters[0]) as f:
            last = int(f.read())
        self.check("underruns: none over a static picture, 3 s", last == first, f"({last - first})")


# ---- composite: display.md H12's unattended half; the picture itself needs a screen
CONNECTOR_COMPOSITE = 5
MODE_INTERLACE = 0x10
STANDARDS = {576: "PAL", 480: "NTSC"}
BARS = (
    (235, 235, 235),
    (235, 235, 16),
    (16, 235, 235),
    (16, 235, 16),
    (235, 16, 16),
    (16, 16, 235),
)
# a bar comes back as its colour when each channel stays on its side of mid-scale: the composite
# path converts to YCbCr and back, which moves saturated colours by tens of codes
MID_SCALE = 128
ENCODER_WORDS = 16
# the TV encoder's enable bit, by vendor, where its layout is known: (word, bit). Only these
# are read: on the RK3528, reading the TVE's range through /dev/mem hangs the bus
ENCODER_ENABLE = {"allwinner": (0, 0)}


class Composite:
    """Composite-1 forced on; each standard set on a CRTC that takes it, colour bars on a plane read
    back by writeback; the TV encoder's registers while on; the connector forced off after, as the
    image's command line leaves it."""

    def __init__(self, drm):
        self.drm, self.failures, self.passes = drm, 0, 0
        self.mode_set = False
        for cap in (CAP_ATOMIC, CAP_WRITEBACK):
            drm.call("cap", ClientCap(capability=cap, value=1))
        res = drm.call("res", CardRes())
        crtcs, connectors = drm.ids(res.count_crtcs), drm.ids(res.count_connectors)
        drm.call(
            "res",
            CardRes(
                crtcs=ctypes.addressof(crtcs),
                connectors=ctypes.addressof(connectors),
                count_crtcs=res.count_crtcs,
                count_connectors=res.count_connectors,
            ),
        )
        self.crtcs = list(crtcs[: res.count_crtcs])
        self.connector = self.writeback = None
        for i in range(res.count_connectors):
            c = drm.call("connector", Connector(connector_id=connectors[i]))
            if c.connector_type == CONNECTOR_COMPOSITE:
                self.connector = c.connector_id
            if c.connector_type == CONNECTOR_WRITEBACK:
                self.writeback = c.connector_id
        pr = drm.call("planes", PlaneRes())
        ids = drm.ids(pr.count_planes)
        drm.call("planes", PlaneRes(planes=ctypes.addressof(ids), count_planes=pr.count_planes))
        self.planes = [drm.call("plane", Plane(plane_id=ids[i])) for i in range(pr.count_planes)]
        self.encoders = {}  # each standard's encoder registers

    def check(self, name, ok, detail=""):
        print(f"{'PASS' if ok else 'FAIL'} {name} {detail}".rstrip())
        self.passes += ok
        self.failures += not ok

    def prop(self, obj, kind, name):
        return self.drm.props(obj, kind)[name][0]

    def modes(self):
        c = self.drm.call("connector", Connector(connector_id=self.connector))
        modes = (ModeInfo * max(c.count_modes, 1))()
        self.drm.call(
            "connector",
            Connector(
                connector_id=self.connector,
                count_modes=c.count_modes,
                modes=ctypes.addressof(modes),
            ),
        )
        return list(modes[: c.count_modes])

    def changes(self, crtc, mode, plane, bars, capture, fence):
        """The connector on crtc at mode, bars full screen on plane, and the writeback."""
        width, height = mode.hdisplay, mode.vdisplay
        plane_props = self.drm.props(plane, OBJ_PLANE)
        values = {
            "FB_ID": bars.fb,
            "CRTC_ID": crtc,
            "SRC_X": 0,
            "SRC_Y": 0,
            "SRC_W": width << 16,
            "SRC_H": height << 16,
            "CRTC_X": 0,
            "CRTC_Y": 0,
            "CRTC_W": width,
            "CRTC_H": height,
        }
        changes = {
            crtc: {
                self.prop(crtc, OBJ_CRTC, "MODE_ID"): self.drm.blob(bytes(mode)),
                self.prop(crtc, OBJ_CRTC, "ACTIVE"): 1,
            },
            self.connector: {self.prop(self.connector, OBJ_CONNECTOR, "CRTC_ID"): crtc},
            plane: {plane_props[k][0]: v for k, v in values.items()},
        }
        tv_mode = self.drm.props(self.connector, OBJ_CONNECTOR).get("TV mode")
        if tv_mode is not None:  # the standard is the connector's property, not the mode's size
            standard = STANDARDS[mode.vdisplay]
            changes[self.connector][tv_mode[0]] = self.drm.enum_value(tv_mode[2], standard)
        if capture is not None:
            changes[self.writeback] = {
                self.prop(self.writeback, OBJ_CONNECTOR, "CRTC_ID"): crtc,
                self.prop(self.writeback, OBJ_CONNECTOR, "WRITEBACK_FB_ID"): capture.fb,
                self.prop(
                    self.writeback, OBJ_CONNECTOR, "WRITEBACK_OUT_FENCE_PTR"
                ): ctypes.addressof(fence),
            }
        return changes

    def placement(self, mode, bars):
        """The first CRTC and plane the driver takes the connector on, at mode."""
        for index, crtc in enumerate(self.crtcs):
            for plane in self.planes:
                if not plane.possible_crtcs & 1 << index:
                    continue
                changes = self.changes(crtc, mode, plane.plane_id, bars, None, None)
                if not self.drm.commit(changes, TEST_ONLY | ALLOW_MODESET):
                    return crtc, plane.plane_id
        return None

    def standard(self, mode):
        name = STANDARDS.get(mode.vdisplay, f"{mode.hdisplay}x{mode.vdisplay}")
        width, height = mode.hdisplay, mode.vdisplay
        bars = Buffer(self.drm, width, height, XRGB8888)
        side = width // len(BARS)
        for y in range(height):
            row = b"".join(
                struct.pack("<I", 255 << 24 | r << 16 | g << 8 | b) * side for r, g, b in BARS
            )
            bars.map[y * bars.pitch : y * bars.pitch + len(row)] = row
        placed = self.placement(mode, bars)
        if placed is None:
            self.check(f"composite {name}", False, "no CRTC and plane take it")
            return
        crtc, plane = placed
        interlaced = "interlaced" if mode.flags & MODE_INTERLACE else "progressive"
        self.check(f"composite {name}", True, f"{width}x{height} {interlaced} on CRTC {crtc}")
        capture, error, ready = None, 0, False
        start = time.monotonic()
        lines = height // 2 if mode.flags & MODE_INTERLACE else height  # writeback takes a field
        for fourcc, scale in ((XRGB8888, 1), (ARGB8888, 1), (NV12, 1), (XRGB8888, 2), (NV12, 2)):
            if self.writeback is None:
                break
            capture = Buffer(self.drm, width // scale, lines // scale, fourcc, unpadded=True)
            fence = ctypes.c_int32(-1)
            error = self.drm.commit(
                self.changes(crtc, mode, plane, bars, capture, fence), ALLOW_MODESET
            )
            if not error:
                ready = bool(select.select([fence.value], [], [], 2)[0])
                os.close(fence.value)
                break
        if self.writeback is None or error:
            error = self.drm.commit(
                self.changes(crtc, mode, plane, bars, None, None), ALLOW_MODESET
            )
            capture = None
        if error:  # the test commit placed it; the real one must take too
            self.check(f"composite {name} mode set", False, f"the commit failed, error {error}")
        else:
            self.mode_set = True
            print(f"RECORD composite {name} mode set: {(time.monotonic() - start) * 1000:.0f} ms")
        encoder = encoder_registers() if not error else None  # only while the driver powers it
        if self.writeback is None:
            print(f"SKIP composite {name} writeback: no writeback connector")
        elif capture is None:
            self.check(f"composite {name} writeback", False, "every capture format refused")
        else:
            scale = width // capture.width
            seen = [
                capture.pixel((side * i + side // 2) // scale, capture.height // 2)
                for i in range(len(BARS))
            ]
            kept = all(
                (a > MID_SCALE) == (b > MID_SCALE)
                for got, want in zip(seen, BARS)
                for a, b in zip(got, want)
            )
            detail = f"colour bars {'kept' if kept else 'LOST'}, {capture.width}x{capture.height}"
            self.check(
                f"composite {name} writeback",
                ready and kept,
                detail if ready else "no frame in 2 s",
            )
            print(f"RECORD composite {name} writeback bars: {seen}")
        self.drm.commit(
            {
                crtc: {self.prop(crtc, OBJ_CRTC, "ACTIVE"): 0},
                self.connector: {self.prop(self.connector, OBJ_CONNECTOR, "CRTC_ID"): 0},
                plane: {
                    self.prop(plane, OBJ_PLANE, "FB_ID"): 0,
                    self.prop(plane, OBJ_PLANE, "CRTC_ID"): 0,
                },
            },
            ALLOW_MODESET,
        )
        self.detach_writeback()
        if encoder is None:
            print(f"SKIP composite {name} encoder: no TV encoder node, or the output never came on")
            return
        vendor, words = encoder
        if words is None:
            print(
                f"UNTESTED composite {name} encoder: {vendor}'s TVE registers are not read safely"
            )
            return
        self.encoders[name] = words
        print(f"RECORD composite {name} encoder: {' '.join(f'{w:08x}' for w in words)}")
        if vendor in ENCODER_ENABLE:
            word, bit = ENCODER_ENABLE[vendor]
            self.check(f"composite {name} encoder", bool(words[word] >> bit & 1), "enabled")

    def detach_writeback(self):
        """The writeback connector off every CRTC: left bound, the driver refuses the next mode set."""
        if self.writeback is not None:
            self.drm.commit(
                {self.writeback: {self.prop(self.writeback, OBJ_CONNECTOR, "CRTC_ID"): 0}},
                ALLOW_MODESET,
            )

    def run(self):
        if self.connector is None:
            print("SKIP composite: no composite connector")
            return
        self.detach_writeback()
        status = next(iter(glob.glob("/sys/class/drm/card*-Composite-*/status")), None)
        if status:
            Path(status).write_text("on")
        try:
            offered = {
                STANDARDS.get(m.vdisplay): m for m in self.modes() if m.vdisplay in STANDARDS
            }
            self.check("composite modes", bool(offered), " ".join(sorted(k for k in offered if k)))
            for mode in offered.values():
                self.standard(mode)
            if len(self.encoders) > 1:
                programs = {tuple(words) for words in self.encoders.values()}
                self.check(
                    "composite standards",
                    len(programs) == len(self.encoders),
                    "each programs the encoder its own way",
                )
        finally:
            if status:
                Path(status).write_text("off")


def dt_compatible(name):
    """Whether a device tree node is compatible with name."""
    return any(
        name in Path(c).read_bytes().split(b"\0")
        for c in glob.glob("/proc/device-tree/**/compatible", recursive=True)
    )


def encoder_registers():
    """The TV encoder's vendor and first registers, as the tree places it; None without one. Read
    only while the output is on: a block whose power domain is off can stall the bus."""
    for compatible in glob.glob("/proc/device-tree/**/compatible", recursive=True):
        names = Path(compatible).read_bytes().split(b"\0")
        found = [n for n in names if b"tv-encoder" in n or n.endswith(b"-tve")]
        if not found:
            continue
        vendor = found[0].decode().split(",")[0]
        if vendor not in ENCODER_ENABLE:
            return vendor, None
        node = Path(compatible).parent
        cells = int.from_bytes((node.parent / "#address-cells").read_bytes(), "big")
        address = int.from_bytes((node / "reg").read_bytes()[: cells * 4], "big")
        fd = os.open("/dev/mem", os.O_RDONLY | os.O_SYNC)
        try:
            page = address & ~0xFFF
            m = mmap.mmap(fd, 0x1000, mmap.MAP_SHARED, mmap.PROT_READ, offset=page)
            words = struct.unpack_from(f"<{ENCODER_WORDS}I", m, address - page)
            m.close()
        finally:
            os.close(fd)
        return vendor, words
    return None


def hdmi_writeback_available():
    with hdr_sink(hdr_edid()) as synthetic:
        if not synthetic:
            return False
        box = Box()
        try:
            return bool(box.crtc and box.writeback and box.planes and box.capture_buffer())
        finally:
            os.close(box.drm.fd)


def run_composite():
    composite = Composite(Drm(display_card()))
    try:
        composite.run()
    finally:
        os.close(composite.drm.fd)
    return composite


def main(sinks, ladder):
    """HDMI checks and sink variations, then composite and the return to HDMI."""
    with hdr_sink() as synthetic:
        box = run(synthetic)
    if box is None:
        composite = run_composite()
        print(f"{composite.passes} passed, {composite.failures} failed")
        return 1 if composite.failures else 0 if composite.passes else 77

    def rating(sink_box):
        sink_box.video_plane, sink_box.ui_plane = box.video_plane, box.ui_plane
        sink_box.rating()

    if ladder:
        against(box, hdr_edid(ladder=True), rating)
    for name in sinks:
        eotfs = SINKS[name]
        if not against(box, hdr_edid(eotfs), lambda b: b.sinks(name, eotfs)):
            break
    against(box, hdr_edid(SINKS["SDR"], surround=True), Box.hdmi_audio)
    against(box, hdr_edid(ladder=True, y420=True), Box.deep_colour)
    against(box, hdr_edid(SINKS["SDR"], ladder=True, y420=True, ycc=True), Box.color_format)
    against(box, hdr_edid(SINKS["SDR"], ladder=True, stereo=True), Box.stereo)
    hdmi_before = hdmi_writeback_available()
    composite = run_composite()
    box.passes += composite.passes
    box.failures += composite.failures
    if hdmi_before and composite.mode_set:
        box.check("HDMI writeback after composite", hdmi_writeback_available())
    else:
        print("SKIP HDMI writeback after composite: baseline capture or composite mode unavailable")
    print(f"{box.passes} passed, {box.failures} failed")
    return 1 if box.failures else 0 if box.passes else 77


def against(box, edid, check):
    """check(a Box) against the synthetic screen edid, its results added to box's; False where the
    kernel takes no EDID override."""
    with hdr_sink(edid) as synthetic:
        if not synthetic:
            return False
        sink_box = Box()
        sink_box.synthetic_sink = True
        try:
            check(sink_box)
        finally:
            os.close(sink_box.drm.fd)
        box.passes += sink_box.passes
        box.failures += sink_box.failures
        return True


def run(synthetic_sink):
    box = Box()
    box.synthetic_sink = synthetic_sink
    if box.crtc is None:
        print("SKIP: no active CRTC")
        return None
    print(
        f"CRTC {box.crtc} {box.mode.hdisplay}x{box.mode.vdisplay}, LUT planes {box.lut_planes}, writeback {box.writeback}"
    )
    box.planes_record()
    box.gamma()  # first: a gamma table set must leave every plane check after it passing
    box.compose_check()
    box.planes_all()
    box.writeback_formats()
    box.rotation()
    box.regions()
    box.lut()
    box.sdr2hdr()
    box.colorop()
    box.scope()
    box.pacing()
    box.hdmi()
    box.hdr10plus()
    box.underruns()
    box.record_maps()
    os.close(box.drm.fd)
    return box


def composite_only():
    """The composite check alone, for the default profile."""
    composite = run_composite()
    return 1 if composite.failures else 0 if composite.passes else 77


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="the display, unattended")
    parser.add_argument("--sinks", default=",".join(SINKS), help=f"of {', '.join(SINKS)}")
    parser.add_argument("--no-ladder", action="store_true", help="skip the rating's mode ladder")
    with display_free():
        if sys.argv[1:] == ["composite"]:
            sys.exit(composite_only())
        args = parser.parse_args()
        sys.exit(main(args.sinks.split(","), not args.no_ladder))
