"""A stateless decoder driven through the media request API, for what FFmpeg never sends: one
MPEG-4 VOP whose vop_time_increment_resolution is 0, which hangs VDPU2 unless refused."""

import ctypes as C
import fcntl
import glob
import mmap
import os
import select
from dataclasses import dataclass

WIDTH, HEIGHT = 320, 240
OUTPUT, CAPTURE = 10, 9  # V4L2_BUF_TYPE_VIDEO_{OUTPUT,CAPTURE}_MPLANE
MMAP = 1
BUF_FLAG_REQUEST_FD, BUF_FLAG_ERROR = 0x00800000, 0x40
WHICH_REQUEST_VAL = 0x0F010000
STATELESS_BASE = 0x00A40900
CID_VOL, CID_VOP, CID_QUANT, CID_SLICE = (STATELESS_BASE + n for n in (520, 521, 522, 523))
MPEG4_SLICE, NV12 = (int.from_bytes(f.encode(), "little") for f in ("MG4S", "NV12"))
# a VOP start code and no picture: the driver must refuse before reading it
VOP = bytes([0x00, 0x00, 0x01, 0xB6]) + bytes(60)
MACROBLOCKS = (WIDTH // 16) * (HEIGHT // 16)


class PlaneFmt(C.Structure):
    _fields_ = [("sizeimage", C.c_uint32), ("bytesperline", C.c_uint32), ("r", C.c_uint16 * 6)]


class PixMp(C.Structure):
    _fields_ = [
        ("width", C.c_uint32),
        ("height", C.c_uint32),
        ("pixelformat", C.c_uint32),
        ("field", C.c_uint32),
        ("colorspace", C.c_uint32),
        ("plane_fmt", PlaneFmt * 8),
        ("num_planes", C.c_uint8),
        ("r", C.c_uint8 * 11),
    ]


class FmtUnion(C.Union):
    _fields_ = [("pix_mp", PixMp), ("raw", C.c_uint8 * 200), ("align", C.c_uint64)]


class Format(C.Structure):
    _fields_ = [("type", C.c_uint32), ("fmt", FmtUnion)]


class ReqBufs(C.Structure):
    _fields_ = [
        ("count", C.c_uint32),
        ("type", C.c_uint32),
        ("memory", C.c_uint32),
        ("caps", C.c_uint32),
        ("flags", C.c_uint8),
        ("r", C.c_uint8 * 3),
    ]


class Plane(C.Structure):
    _fields_ = [
        ("bytesused", C.c_uint32),
        ("length", C.c_uint32),
        ("mem_offset", C.c_uint64),
        ("data_offset", C.c_uint32),
        ("r", C.c_uint32 * 11),
    ]


class Buffer(C.Structure):
    _fields_ = [
        ("index", C.c_uint32),
        ("type", C.c_uint32),
        ("bytesused", C.c_uint32),
        ("flags", C.c_uint32),
        ("field", C.c_uint32),
        ("timestamp", C.c_int64 * 2),
        ("timecode", C.c_uint32 * 4),
        ("sequence", C.c_uint32),
        ("memory", C.c_uint32),
        ("planes", C.c_void_p),
        ("length", C.c_uint32),
        ("reserved2", C.c_uint32),
        ("request_fd", C.c_int32),
    ]


class ExtControl(C.Structure):
    _pack_ = 1
    _fields_ = [("id", C.c_uint32), ("size", C.c_uint32), ("r", C.c_uint32), ("ptr", C.c_void_p)]


class ExtControls(C.Structure):
    _fields_ = [
        ("which", C.c_uint32),
        ("count", C.c_uint32),
        ("error_idx", C.c_uint32),
        ("request_fd", C.c_int32),
        ("r", C.c_uint32),
        ("controls", C.c_void_p),
    ]


class Vol(C.Structure):
    _fields_ = [
        ("width", C.c_uint16),
        ("height", C.c_uint16),
        ("sprite", C.c_uint8 * 4),
        ("flags", C.c_uint32),
    ]


class Vop(C.Structure):
    _fields_ = [
        ("forward_ref_ts", C.c_uint64),
        ("backward_ref_ts", C.c_uint64),
        ("flags", C.c_uint32),
        ("tr", C.c_uint16 * 4),
        ("sprite", C.c_int16 * 6),
        ("vop_coding_type", C.c_uint8),
        ("intra_dc_vlc_thr", C.c_uint8),
        ("vop_fcode_forward", C.c_uint8),
        ("vop_fcode_backward", C.c_uint8),
        ("vop_time_increment_resolution", C.c_uint16),
        ("last_ref_coding_type", C.c_uint8),
        ("reserved", C.c_uint8),
    ]


class Quant(C.Structure):
    _fields_ = [("intra", C.c_uint8 * 64), ("inter", C.c_uint8 * 64)]


class Slice(C.Structure):
    _fields_ = [
        ("bit_size", C.c_uint32),
        ("data_bit_offset", C.c_uint32),
        ("macroblock_number", C.c_uint16),
        ("num_macroblocks", C.c_uint16),
        ("quant_scale", C.c_uint8),
        ("r", C.c_uint8 * 3),
    ]


def ioc(direction: int, group: str, nr: int, size: int) -> int:
    return (direction << 30) | (size << 16) | (ord(group) << 8) | nr


READ_WRITE, READ, WRITE, NONE = 3, 2, 1, 0
S_FMT = ioc(READ_WRITE, "V", 5, C.sizeof(Format))
REQBUFS = ioc(READ_WRITE, "V", 8, C.sizeof(ReqBufs))
QUERYBUF = ioc(READ_WRITE, "V", 9, C.sizeof(Buffer))
QBUF = ioc(READ_WRITE, "V", 15, C.sizeof(Buffer))
DQBUF = ioc(READ_WRITE, "V", 17, C.sizeof(Buffer))
STREAMON = ioc(WRITE, "V", 18, 4)
S_EXT_CTRLS = ioc(READ_WRITE, "V", 72, C.sizeof(ExtControls))
REQUEST_ALLOC = ioc(READ, "|", 5, 4)
REQUEST_QUEUE = ioc(NONE, "|", 0x80, 0)


@dataclass
class Outcome:
    """What came back: the request signalled done, and each buffer's error flag."""

    completed: bool
    output_error: bool
    capture_error: bool


def find_device(pattern: str) -> tuple[str, str] | None:
    """The video node whose name contains pattern, and its media node."""
    for node in sorted(glob.glob("/sys/class/video4linux/video*")):
        with open(f"{node}/name") as f:
            if pattern not in f.read():
                continue
        media = glob.glob(f"{node}/device/media*")
        if media:
            return f"/dev/{os.path.basename(node)}", f"/dev/{os.path.basename(media[0])}"
    return None


def set_format(fd: int, buf_type: int, pixelformat: int) -> None:
    f = Format(type=buf_type)
    f.fmt.pix_mp.width, f.fmt.pix_mp.height = WIDTH, HEIGHT
    f.fmt.pix_mp.pixelformat, f.fmt.pix_mp.num_planes = pixelformat, 1
    fcntl.ioctl(fd, S_FMT, f)


def one_buffer(fd: int, buf_type: int) -> tuple[Buffer, Plane]:
    fcntl.ioctl(fd, REQBUFS, ReqBufs(count=1, type=buf_type, memory=MMAP))
    plane = Plane()
    buf = Buffer(index=0, type=buf_type, memory=MMAP, planes=C.addressof(plane), length=1)
    fcntl.ioctl(fd, QUERYBUF, buf)
    fcntl.ioctl(fd, STREAMON, C.c_int(buf_type))
    return buf, plane


def errored(fd: int, buf_type: int) -> bool:
    """The queue's buffer, dequeued, carries the error flag; one not given back carries none."""
    plane = Plane()
    buf = Buffer(type=buf_type, memory=MMAP, planes=C.addressof(plane), length=1)
    try:
        fcntl.ioctl(fd, DQBUF, buf)
    except BlockingIOError:
        return False
    return bool(buf.flags & BUF_FLAG_ERROR)


def zero_resolution_vop(video: str, media: str, timeout_ms: int) -> Outcome:
    """One VOP with vop_time_increment_resolution 0 through a request on video."""
    fd = os.open(video, os.O_RDWR | os.O_NONBLOCK)
    mfd = os.open(media, os.O_RDWR)
    try:
        set_format(fd, OUTPUT, MPEG4_SLICE)
        set_format(fd, CAPTURE, NV12)
        out, out_plane = one_buffer(fd, OUTPUT)
        cap, cap_plane = one_buffer(fd, CAPTURE)
        with mmap.mmap(fd, out_plane.length, offset=out_plane.mem_offset) as mm:
            mm[: len(VOP)] = VOP
        cap.planes = C.addressof(cap_plane)
        fcntl.ioctl(fd, QBUF, cap)

        req = C.c_int()
        fcntl.ioctl(mfd, REQUEST_ALLOC, req)
        vol, vop, quant = Vol(width=WIDTH, height=HEIGHT), Vop(), Quant()
        piece = Slice(bit_size=len(VOP) * 8, data_bit_offset=32, num_macroblocks=MACROBLOCKS)
        piece.quant_scale = 4
        values = ((CID_VOL, vol), (CID_VOP, vop), (CID_QUANT, quant), (CID_SLICE, piece))
        ctrls = (ExtControl * len(values))(
            *(ExtControl(id=i, size=C.sizeof(v), ptr=C.addressof(v)) for i, v in values)
        )
        sent = ExtControls(
            which=WHICH_REQUEST_VAL,
            count=len(values),
            request_fd=req.value,
            controls=C.addressof(ctrls),
        )
        fcntl.ioctl(fd, S_EXT_CTRLS, sent)
        out.planes, out_plane.bytesused = C.addressof(out_plane), len(VOP)
        out.flags, out.request_fd = BUF_FLAG_REQUEST_FD, req.value
        fcntl.ioctl(fd, QBUF, out)
        fcntl.ioctl(req.value, REQUEST_QUEUE)

        poll = select.poll()
        poll.register(req.value, select.POLLPRI)
        completed = bool(poll.poll(timeout_ms))
        os.close(req.value)
        return Outcome(completed, errored(fd, OUTPUT), errored(fd, CAPTURE))
    finally:
        os.close(fd)
        os.close(mfd)
