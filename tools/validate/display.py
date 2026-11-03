#!/usr/bin/env python3
"""The display path's colour on a running box: the video plane's 3D LUT and the HDMI output.

Runs on the box, as root, with nothing else on the screen (no compositor, no player):

    python3 display.py

Checks, each skipped where the box lacks what it needs:
  - lut: a plane's SUNXI_CDC_LUT3D refuses malformed blobs, and tables (identity, a channel mix,
    an inversion switched while active, held across flips, then the tone mappings HDR10 to SDR,
    HLG to SDR, SDR to PQ and HLG to PQ on 64 YUV patches) come back by writeback within two 8-bit
    codes of the same table interpolated trilinearly;
  - hdmi: SDR, PQ and HLG with max bpc 8 and 10 give the InfoFrames, colorimetry and pixel format
    the dw-hdmi registers then hold;
  - underruns: the CRTC's TCON underflow count holds still over a static picture.
Exit 0 all passed, 1 a failure, 77 nothing to check.
"""
import ctypes
import fcntl
import glob
import math
import mmap
import os
import select
import struct
import sys
import time

# ---- DRM uAPI, as drm.h and drm_mode.h lay it out
u32, u64, u16 = ctypes.c_uint32, ctypes.c_uint64, ctypes.c_uint16


def S(name, fields):
    return type(name, (ctypes.Structure,), {"_fields_": fields})


ClientCap = S("ClientCap", [("capability", u64), ("value", u64)])
CardRes = S("CardRes", [("fbs", u64), ("crtcs", u64), ("connectors", u64), ("encoders", u64),
                         ("count_fbs", u32), ("count_crtcs", u32), ("count_connectors", u32),
                         ("count_encoders", u32), ("min_w", u32), ("max_w", u32), ("min_h", u32),
                         ("max_h", u32)])
ModeInfo = S("ModeInfo", [("clock", u32), ("hdisplay", u16), ("hsync_start", u16), ("hsync_end", u16),
                           ("htotal", u16), ("hskew", u16), ("vdisplay", u16), ("vsync_start", u16),
                           ("vsync_end", u16), ("vtotal", u16), ("vscan", u16), ("vrefresh", u32),
                           ("flags", u32), ("type", u32), ("name", ctypes.c_char * 32)])
Crtc = S("Crtc", [("set_connectors", u64), ("count_connectors", u32), ("crtc_id", u32), ("fb_id", u32),
                   ("x", u32), ("y", u32), ("gamma_size", u32), ("mode_valid", u32), ("mode", ModeInfo)])
Connector = S("Connector", [("encoders", u64), ("modes", u64), ("props", u64), ("prop_values", u64),
                             ("count_modes", u32), ("count_props", u32), ("count_encoders", u32),
                             ("encoder_id", u32), ("connector_id", u32), ("connector_type", u32),
                             ("connector_type_id", u32), ("connection", u32), ("mm_width", u32),
                             ("mm_height", u32), ("subpixel", u32), ("pad", u32)])
PlaneRes = S("PlaneRes", [("planes", u64), ("count_planes", u32)])
Plane = S("Plane", [("plane_id", u32), ("crtc_id", u32), ("fb_id", u32), ("possible_crtcs", u32),
                     ("gamma_size", u32), ("count_format_types", u32), ("format_types", u64)])
ObjProps = S("ObjProps", [("props", u64), ("values", u64), ("count_props", u32), ("obj_id", u32),
                           ("obj_type", u32)])
Property = S("Property", [("values", u64), ("enum_blobs", u64), ("prop_id", u32), ("flags", u32),
                           ("name", ctypes.c_char * 32), ("count_values", u32), ("count_enum_blobs", u32)])
PropEnum = S("PropEnum", [("value", u64), ("name", ctypes.c_char * 32)])
CreateBlob = S("CreateBlob", [("data", u64), ("length", u32), ("blob_id", u32)])
BlobId = S("BlobId", [("blob_id", u32)])
CreateDumb = S("CreateDumb", [("height", u32), ("width", u32), ("bpp", u32), ("flags", u32),
                               ("handle", u32), ("pitch", u32), ("size", u64)])
MapDumb = S("MapDumb", [("handle", u32), ("pad", u32), ("offset", u64)])
FbCmd2 = S("FbCmd2", [("fb_id", u32), ("width", u32), ("height", u32), ("pixel_format", u32),
                       ("flags", u32), ("handles", u32 * 4), ("pitches", u32 * 4), ("offsets", u32 * 4),
                       ("modifier", u64 * 4)])
Atomic = S("Atomic", [("flags", u32), ("count_objs", u32), ("objs", u64), ("count_props", u64),
                       ("props", u64), ("values", u64), ("reserved", u64), ("user_data", u64)])


def iowr(nr, struct_type):
    return (3 << 30) | (ctypes.sizeof(struct_type) << 16) | (ord("d") << 8) | nr


IOCTL = {"cap": iowr(0x0D, ClientCap), "res": iowr(0xA0, CardRes), "crtc": iowr(0xA1, Crtc),
         "connector": iowr(0xA7, Connector), "planes": iowr(0xB5, PlaneRes), "plane": iowr(0xB6, Plane),
         "props": iowr(0xB9, ObjProps), "property": iowr(0xAA, Property), "blob": iowr(0xBD, CreateBlob),
         "unblob": iowr(0xBE, BlobId), "dumb": iowr(0xB2, CreateDumb), "map": iowr(0xB3, MapDumb),
         "addfb2": iowr(0xB8, FbCmd2), "atomic": iowr(0xBC, Atomic)}
CAP_ATOMIC, CAP_WRITEBACK = 3, 5
OBJ_CRTC, OBJ_CONNECTOR, OBJ_PLANE = 0xCCCCCCCC, 0xC0C0C0C0, 0xEEEEEEEE
CONNECTOR_HDMIA, CONNECTOR_WRITEBACK = 11, 18
TEST_ONLY, ALLOW_MODESET = 0x100, 0x400
XRGB8888, NV12, P010 = 0x34325258, 0x3231564E, 0x30313050
LUT_POINTS = 17
TOLERANCE = 2


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
        self.call("props", ObjProps(props=ctypes.addressof(ids), values=ctypes.addressof(values),
                                    count_props=p.count_props, obj_id=obj, obj_type=kind))
        result = {}
        for i in range(p.count_props):
            prop = self.call("property", Property(prop_id=ids[i]))
            result[prop.name.decode()] = (ids[i], values[i], prop)
        return result

    def enum_value(self, prop, name):
        enums = (PropEnum * prop.count_enum_blobs)()
        self.call("property", Property(prop_id=prop.prop_id, enum_blobs=ctypes.addressof(enums),
                                       count_enum_blobs=prop.count_enum_blobs))
        return next(e.value for e in enums if e.name.decode() == name)

    def blob(self, data):
        buffer = ctypes.create_string_buffer(data, len(data))
        return self.call("blob", CreateBlob(data=ctypes.addressof(buffer), length=len(data))).blob_id

    def unblob(self, blob_id):
        self.call("unblob", BlobId(blob_id=blob_id))

    def commit(self, changes, flags=ALLOW_MODESET):
        """changes: {object id: {property id: value}}; an error comes back as its errno."""
        objs = list(changes)
        counts = (u32 * len(objs))(*[len(changes[o]) for o in objs])
        flat = [(p, v) for o in objs for p, v in changes[o].items()]
        props = (u32 * len(flat))(*[p for p, _ in flat])
        values = (u64 * len(flat))(*[v & (2**64 - 1) for _, v in flat])
        objarr = (u32 * len(objs))(*objs)
        try:
            self.call("atomic", Atomic(flags=flags, count_objs=len(objs), objs=ctypes.addressof(objarr),
                                       count_props=ctypes.addressof(counts), props=ctypes.addressof(props),
                                       values=ctypes.addressof(values)))
            return 0
        except OSError as error:
            return error.errno


class Buffer:
    def __init__(self, drm, width, height, fourcc):
        yuv = fourcc in (NV12, P010)
        bpp = 16 if fourcc == P010 else 8 if fourcc == NV12 else 32
        d = drm.call("dumb", CreateDumb(height=height * 3 // 2 if yuv else height, width=width, bpp=bpp))
        self.width, self.height, self.pitch, self.format = width, height, d.pitch, fourcc
        handles, pitches, offsets = [d.handle, d.handle if yuv else 0], [d.pitch, d.pitch if yuv else 0], \
            [0, d.pitch * height if yuv else 0]
        cmd = FbCmd2(width=width, height=height, pixel_format=fourcc)
        for i in range(2):
            cmd.handles[i], cmd.pitches[i], cmd.offsets[i] = handles[i], pitches[i], offsets[i]
        self.fb = drm.call("addfb2", cmd).fb_id
        offset = drm.call("map", MapDumb(handle=d.handle)).offset
        self.map = mmap.mmap(drm.fd, d.size, mmap.MAP_SHARED, mmap.PROT_READ | mmap.PROT_WRITE, offset=offset)

    def fill_rgb(self, rgb):
        row = struct.pack("<I", rgb[0] << 16 | rgb[1] << 8 | rgb[2]) * self.width
        for y in range(self.height):
            self.map[y * self.pitch:y * self.pitch + len(row)] = row

    def fill_patches(self, codes, grid, side):
        """YUV codes, row-major over a grid of square patches; P010 codes are 10-bit."""
        wide = self.format == P010
        pack = (lambda c: struct.pack("<H", c << 6)) if wide else (lambda c: bytes([c]))
        for py in range(grid):
            for y in range(side):
                luma = b"".join(pack(codes[py * grid + px][0]) * side for px in range(grid))
                row = py * side + y
                self.map[row * self.pitch:row * self.pitch + len(luma)] = luma
            for y in range(side // 2):
                chroma = b"".join((pack(codes[py * grid + px][1]) + pack(codes[py * grid + px][2])) * (side // 2)
                                  for px in range(grid))
                row = self.height + py * side // 2 + y
                self.map[row * self.pitch:row * self.pitch + len(chroma)] = chroma

    def pixel(self, x, y):
        (value,) = struct.unpack_from("<I", self.map, y * self.pitch + x * 4)
        return value >> 16 & 255, value >> 8 & 255, value & 255


# ---- colour, enough to build tone-mapping tables a display engine applies
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
    gain = peak * luma ** 0.2 if luma > 0 else 0.0
    return [gain * x for x in lin]


def bt1886(nits, white=100.0):
    return min(max(nits / white, 0.0), 1.0) ** (1 / 2.4)


def tone(nits, peak=1000.0, white=100.0):
    x = nits / white
    return white * x * (1 + x / (peak / white) ** 2) / (1 + x)


BT2020_TO_709 = ((1.6605, -0.5876, -0.0728), (-0.1246, 1.1329, -0.0083), (-0.0182, -0.1006, 1.1187))
BT709_TO_2020 = ((0.6274, 0.3293, 0.0433), (0.0691, 0.9195, 0.0114), (0.0164, 0.0880, 0.8956))
KR_KB = {709: (0.2126, 0.0722), 2020: (0.2627, 0.0593)}


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
    return [(y * 876 + 64) / 1023, ((b - y) / (2 * (1 - kb)) * 896 + 512) / 1023,
            ((r - y) / (2 * (1 - kr)) * 896 + 512) / 1023]


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


def lattice(f):
    """17^3 nodes, the first component fastest, as 0..1 floats."""
    n = LUT_POINTS - 1
    return [f([x / n, y / n, z / n]) for z in range(LUT_POINTS) for y in range(LUT_POINTS) for x in range(LUT_POINTS)]


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


# ---- the box
class Box:
    def __init__(self):
        self.drm = Drm("/dev/dri/card0")
        for cap in (CAP_ATOMIC, CAP_WRITEBACK):
            self.drm.call("cap", ClientCap(capability=cap, value=1))
        res = self.drm.call("res", CardRes())
        crtcs, connectors = self.drm.ids(res.count_crtcs), self.drm.ids(res.count_connectors)
        self.drm.call("res", CardRes(crtcs=ctypes.addressof(crtcs), connectors=ctypes.addressof(connectors),
                                     count_crtcs=res.count_crtcs, count_connectors=res.count_connectors))
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
        pr = self.drm.call("planes", PlaneRes())
        ids = self.drm.ids(pr.count_planes)
        self.drm.call("planes", PlaneRes(planes=ctypes.addressof(ids), count_planes=pr.count_planes))
        self.planes = []
        for i in range(pr.count_planes):
            p = self.drm.call("plane", Plane(plane_id=ids[i]))
            if self.crtc is not None and p.possible_crtcs & 1 << self.index:
                self.planes.append(p.plane_id)
        self.lut_planes = [p for p in self.planes if "SUNXI_CDC_LUT3D" in self.drm.props(p, OBJ_PLANE)]
        self.failures = self.passes = 0

    def prop(self, obj, kind, name):
        return self.drm.props(obj, kind)[name][0]

    def check(self, name, ok, detail=""):
        print(f"{'PASS' if ok else 'FAIL'} {name} {detail}".rstrip())
        self.passes += ok
        self.failures += not ok

    def show(self, plane, buffer, lut, encoding=None, capture=None):
        """Only this plane on the CRTC, full screen; with a capture buffer, waits for its writeback."""
        width, height = self.mode.hdisplay, self.mode.vdisplay
        changes = {p: {self.prop(p, OBJ_PLANE, "FB_ID"): 0, self.prop(p, OBJ_PLANE, "CRTC_ID"): 0}
                   for p in self.planes if p != plane}
        props = self.drm.props(plane, OBJ_PLANE)
        values = {"FB_ID": buffer.fb, "CRTC_ID": self.crtc, "SRC_X": 0, "SRC_Y": 0, "SRC_W": buffer.width << 16,
                  "SRC_H": buffer.height << 16, "CRTC_X": 0, "CRTC_Y": 0, "CRTC_W": height, "CRTC_H": height,
                  "SUNXI_CDC_LUT3D": lut}
        if buffer.format == XRGB8888:
            values["CRTC_W"] = width
        if encoding is not None:
            values["COLOR_ENCODING"] = self.drm.enum_value(props["COLOR_ENCODING"][2], encoding)
            values["COLOR_RANGE"] = self.drm.enum_value(props["COLOR_RANGE"][2], "YCbCr limited range")
        changes[plane] = {props[k][0]: v for k, v in values.items()}
        fence = ctypes.c_int32(-1)
        if capture:
            changes[self.writeback] = {self.prop(self.writeback, OBJ_CONNECTOR, "CRTC_ID"): self.crtc,
                                       self.prop(self.writeback, OBJ_CONNECTOR, "WRITEBACK_FB_ID"): capture.fb,
                                       self.prop(self.writeback, OBJ_CONNECTOR, "WRITEBACK_OUT_FENCE_PTR"):
                                           ctypes.addressof(fence)}
        error = self.drm.commit(changes)
        if not error and capture:
            ready, _, _ = select.select([fence.value], [], [], 2)
            os.close(fence.value)
            error = 0 if ready else 110
        return error

    def lut(self):
        if not self.lut_planes or not self.writeback:
            print("SKIP lut: no plane with SUNXI_CDC_LUT3D, or no writeback connector")
            return
        width, height = self.mode.hdisplay, self.mode.vdisplay
        capture = Buffer(self.drm, width // 2, height // 2, XRGB8888)
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
            tables = [("identity", lambda v: v), ("channel mix", lambda v: [.4 * v[0] + .2 * v[1] + .1 * v[2],
                       .1 * v[0] + .3 * v[1] + .4 * v[2], .2 * v[0] + .3 * v[1] + .1 * v[2]]),
                      ("inversion, switched while active", lambda v: [1 - c for c in v])]
            for name, f in tables:
                nodes, data = quantized(lattice(f))
                blob = self.drm.blob(data)
                error = self.show(plane, rgb, blob, capture=capture)
                want = to8(trilinear(nodes, [c / 255 for c in signal]))
                got = capture.pixel(*centre) if not error else None
                self.check(f"plane {plane}: RGB {name}", not error and max(abs(a - b) for a, b in zip(got, want)) <= TOLERANCE,
                           f"got {got} want {want}")
                if name == "channel mix":
                    held = 0
                    for flip in range(60):
                        rgb.fill_rgb(signal)
                        self.show(plane, rgb, blob, capture=capture if flip % 10 == 9 else None)
                        held += flip % 10 == 9 and max(abs(a - b) for a, b in zip(capture.pixel(*centre), want)) <= TOLERANCE
                    self.check(f"plane {plane}: the table held across 60 flips", held == 6, f"({held} of 6 captures)")
                self.drm.unblob(blob)

            grid, side = 8, 64
            cases = [("HDR10 to SDR", P010, 2020, hdr10_to_sdr, "ITU-R BT.709 YCbCr", 709),
                     ("HLG to SDR", P010, 2020, hlg_to_sdr, "ITU-R BT.709 YCbCr", 709),
                     ("SDR to PQ", NV12, 709, sdr_to_pq, "ITU-R BT.2020 YCbCr", 2020),
                     ("HLG to PQ", P010, 2020, hlg_to_pq, "ITU-R BT.2020 YCbCr", 2020)]
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
                        codes.append(((16 + (seed >> 8) % 220) * scale, (40 + (seed >> 12) % 177) * scale,
                                      (40 + (seed >> 16) % 177) * scale))
                picture = Buffer(self.drm, grid * side, grid * side, fourcc)
                picture.fill_patches(codes, grid, side)
                nodes, data = quantized(lattice(f))
                blob = self.drm.blob(data)
                error = self.show(plane, picture, blob, encoding, capture) or self.show(plane, picture, blob, encoding, capture)
                worst, total = 0, 0
                for i, code in enumerate(codes):
                    x = (i % grid * side + side // 2) * height // (grid * side) // 2
                    y = (i // grid * side + side // 2) * height // (grid * side) // 2
                    want = to8(yuv_to_rgb(trilinear(nodes, [c / depth for c in code]), out_space))
                    got = capture.pixel(x, y)
                    error_here = max(abs(a - b) for a, b in zip(got, want))
                    worst, total = max(worst, error_here), total + error_here
                self.check(f"plane {plane}: {name}, 64 patches", not error and worst <= TOLERANCE,
                           f"max {worst} mean {total / len(codes):.2f}" if not error else f"(errno {error})")
                self.drm.unblob(blob)
            self.show(plane, rgb, 0)

    def hdmi_registers(self):
        paths = glob.glob("/sys/kernel/debug/regmap/*.hdmi/registers")
        if not paths:
            return None
        regs = {}
        with open(paths[0]) as f:
            for line in f:
                address, value = line.split(":")
                regs[int(address, 16)] = int(value, 16)
        return regs

    def hdmi(self):
        regs = self.hdmi_registers()
        if not self.hdmi_connector or regs is None:
            print("SKIP hdmi: no connected HDMI connector, or no dw-hdmi register map in debugfs")
            return
        props = self.drm.props(self.hdmi_connector, OBJ_CONNECTOR)
        if not all(k in props for k in ("HDR_OUTPUT_METADATA", "Colorspace", "max bpc")):
            print("SKIP hdmi: the connector lacks HDR_OUTPUT_METADATA, Colorspace or max bpc")
            return
        before = {k: props[k][1] for k in ("HDR_OUTPUT_METADATA", "Colorspace", "max bpc")}
        for eotf, name in ((None, "SDR"), (2, "PQ"), (3, "HLG")):
            for bpc in (8, 10):
                blob = 0
                if eotf is not None:
                    # hdr_output_metadata: type 0, then the static type 1 block: EOTF, BT.2020 primaries,
                    # D65, 1000 / 0.005 nits, MaxCLL 1000, MaxFALL 400.
                    blob = self.drm.blob(struct.pack("<I2B8H4H2x", 0, eotf, 0, 35400, 14600, 8500, 39850, 6550, 2300,
                                                     15635, 16450, 1000, 50, 1000, 400))
                space = "Default" if eotf is None else "BT2020_YCC"
                error = self.drm.commit({self.hdmi_connector: {props["HDR_OUTPUT_METADATA"][0]: blob,
                                                     props["Colorspace"][0]: self.drm.enum_value(props["Colorspace"][2], space),
                                                     props["max bpc"][0]: bpc}})
                time.sleep(1)
                regs = self.hdmi_registers()
                drm_sent = bool(regs[0x10E3] & 0x80)
                eotf_sent = regs[0x116A]
                avi_y, avi_ec = regs[0x1019] & 3, regs[0x101B] >> 4 & 7
                ok = not error and drm_sent == (eotf is not None) and (eotf is None or eotf_sent == eotf)
                ok = ok and (avi_ec == 6) == (eotf is not None)
                fmt = {0: "RGB", 1: "YCbCr 4:2:2", 2: "YCbCr 4:4:4", 3: "YCbCr 4:2:0"}[avi_y]
                ok = ok and (fmt == "RGB" if eotf is None or bpc == 8 else fmt in ("RGB", "YCbCr 4:2:2", "YCbCr 4:2:0"))
                self.check(f"hdmi: {name}, max bpc {bpc}", ok,
                           f"DRM InfoFrame {'EOTF %d' % eotf_sent if drm_sent else 'off'}, {fmt}, EC {avi_ec}")
                if blob:
                    self.drm.unblob(blob)
        self.drm.commit({self.hdmi_connector: {props[k][0]: v for k, v in before.items()}})

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


def main():
    box = Box()
    if box.crtc is None:
        print("SKIP: no active CRTC")
        return 77
    print(f"CRTC {box.crtc} {box.mode.hdisplay}x{box.mode.vdisplay}, LUT planes {box.lut_planes}, writeback {box.writeback}")
    box.lut()
    box.hdmi()
    box.underruns()
    print(f"{box.passes} passed, {box.failures} failed")
    return 1 if box.failures else 0 if box.passes else 77


if __name__ == "__main__":
    sys.exit(main())
