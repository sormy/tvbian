"""Header parsers for the codecs FFmpeg's trace_headers cannot read: MPEG-4 Part 2, H.263, VC-1.

Each parser returns a header's syntax elements by name, as the standard names them, so a rebuild
can be compared with the clip element by element. Python's standard library only.
"""

from __future__ import annotations

import re

Fields = dict[str, int]

MPEG4_VOL_FIRST, MPEG4_VOL_LAST = 0x20, 0x2F
MPEG4_VOP = 0xB6
MATRIX_SIZE = 64
ZIGZAG = [
    0, 1, 8, 16, 9, 2, 3, 10, 17, 24, 32, 25, 18, 11, 4, 5, 12, 19, 26, 33, 40, 48, 41, 34, 27,
    20, 13, 6, 7, 14, 21, 28, 35, 42, 49, 56, 57, 50, 43, 36, 29, 22, 15, 23, 30, 37, 44, 51, 58,
    59, 52, 45, 38, 31, 39, 46, 53, 60, 61, 54, 47, 55, 62, 63,
]  # fmt: skip
# ISO/IEC 14496-2's default matrices, in raster order
MPEG4_DEFAULT_MATRICES = {
    "intra": [
        8, 17, 18, 19, 21, 23, 25, 27, 17, 18, 19, 21, 23, 25, 27, 28, 20, 21, 22, 23, 24, 26, 28,
        30, 21, 22, 23, 24, 26, 28, 30, 32, 22, 23, 24, 26, 28, 30, 32, 35, 23, 24, 26, 28, 30, 32,
        35, 38, 25, 26, 28, 30, 32, 35, 38, 41, 27, 28, 30, 32, 35, 38, 41, 45,
    ],
    "nonintra": [
        16, 17, 18, 19, 20, 21, 22, 23, 17, 18, 19, 20, 21, 22, 23, 24, 18, 19, 20, 21, 22, 23, 24,
        25, 19, 20, 21, 22, 23, 24, 26, 27, 20, 21, 22, 23, 25, 26, 27, 28, 21, 22, 23, 24, 26, 27,
        28, 30, 22, 23, 24, 26, 27, 28, 30, 31, 23, 24, 25, 27, 28, 30, 31, 33,
    ],
}  # fmt: skip
H263_HEADER_BITS = 50
H263_PICTURE_START = re.compile(rb"\x00\x00[\x80-\x83]")
VC1_SEQUENCE, VC1_ENTRY_POINT = 0x0F, 0x0E
VC1_PICTURE_UNITS = {0x0B, 0x0C, 0x0D}
VC1_PROFILE_ADVANCED = 3
# after STRUCT_C: the height, the width, 0xC and STRUCT_B
RCV_AFTER_STRUCT_C = 24
RCV_FRAME_HEADER_SIZE = 8
RCV_FRAME_SIZE_MASK = 0x3FFFFFFF


class Bits:
    """An MSB-first reader over bytes."""

    def __init__(self, data: bytes) -> None:
        self.value = int.from_bytes(data, "big")
        self.size = len(data) * 8
        self.at = 0

    def read(self, count: int) -> int:
        if self.at + count > self.size:
            raise ValueError("header runs past its unit")
        self.at += count
        return (self.value >> (self.size - self.at)) & ((1 << count) - 1)

    def rest(self) -> int:
        """The bits left, as an integer the width of what is left."""
        return self.value & ((1 << (self.size - self.at)) - 1)


def start_code_units(data: bytes) -> list[tuple[int, bytes]]:
    """Each start-code unit as its code and its payload, trailing zero bytes left out."""
    starts = [m.end() for m in re.finditer(b"\x00\x00\x01", data)]
    ends = [s - 3 for s in starts[1:]] + [len(data)]
    return [(data[s], data[s + 1 : e].rstrip(b"\x00")) for s, e in zip(starts, ends) if s < e]


def unescape(data: bytes) -> bytes:
    return re.sub(b"\x00\x00\x03(?=[\x00-\x03])", b"\x00\x00", data)


# MPEG-4 Part 2


def mpeg4_matrix(bits: Bits) -> list[int]:
    values: list[int] = []
    while len(values) < MATRIX_SIZE:
        value = bits.read(8)
        if not value:
            break
        values.append(value)
    return values + [values[-1]] * (MATRIX_SIZE - len(values))


def mpeg4_vol(payload: bytes) -> Fields:
    """video_object_layer() up to the scalability flag, rectangular shape only."""
    bits = Bits(payload)
    f: Fields = {"random_accessible_vol": bits.read(1)}
    f["video_object_type_indication"] = bits.read(8)
    f["is_object_layer_identifier"] = bits.read(1)
    version = 1
    if f["is_object_layer_identifier"]:
        version = f["video_object_layer_verid"] = bits.read(4)
        f["video_object_layer_priority"] = bits.read(3)
    f["aspect_ratio_info"] = bits.read(4)
    if f["aspect_ratio_info"] == 15:
        f["par_width"], f["par_height"] = bits.read(8), bits.read(8)
    f["vol_control_parameters"] = bits.read(1)
    if f["vol_control_parameters"]:
        f["chroma_format"], f["low_delay"] = bits.read(2), bits.read(1)
        f["vbv_parameters"] = bits.read(1)
        if f["vbv_parameters"]:
            bits.read(79)
    f["video_object_layer_shape"] = bits.read(2)
    bits.read(1)
    f["vop_time_increment_resolution"] = bits.read(16)
    bits.read(1)
    f["fixed_vop_rate"] = bits.read(1)
    if f["fixed_vop_rate"]:
        increment_bits = max(1, (f["vop_time_increment_resolution"] - 1).bit_length())
        f["fixed_vop_time_increment"] = bits.read(increment_bits)
    bits.read(1)
    f["video_object_layer_width"] = bits.read(13)
    bits.read(1)
    f["video_object_layer_height"] = bits.read(13)
    bits.read(1)
    f["interlaced"], f["obmc_disable"] = bits.read(1), bits.read(1)
    f["sprite_enable"] = bits.read(1 if version == 1 else 2)
    f["not_8_bit"] = bits.read(1)
    f["quant_precision"] = 5
    if f["not_8_bit"]:
        f["quant_precision"], f["bits_per_pixel"] = bits.read(4), bits.read(4)
    f["quant_type"] = bits.read(1)
    if f["quant_type"]:
        # in scan order, a matrix not loaded as its default
        for matrix in MPEG4_DEFAULT_MATRICES:
            loaded = bits.read(1)
            default = MPEG4_DEFAULT_MATRICES[matrix]
            values = mpeg4_matrix(bits) if loaded else [default[z] for z in ZIGZAG]
            for i, value in enumerate(values):
                f[f"{matrix}_quant_mat[{i}]"] = value
    f["quarter_sample"] = bits.read(1) if version != 1 else 0
    f["complexity_estimation_disable"] = bits.read(1)
    if not f["complexity_estimation_disable"]:
        raise ValueError("complexity estimation is not parsed")
    f["resync_marker_disable"] = bits.read(1)
    f["data_partitioned"] = bits.read(1)
    f["reversible_vlc"] = bits.read(1) if f["data_partitioned"] else 0
    if version != 1:
        f["newpred_enable"], f["reduced_resolution_vop_enable"] = bits.read(1), bits.read(1)
    f["scalability"] = bits.read(1)
    return f


# H.263


def h263_pictures(data: bytes) -> list[bytes]:
    """Pictures split at their byte-aligned picture start codes."""
    starts = [m.start() for m in H263_PICTURE_START.finditer(data)]
    return [data[s:e] for s, e in zip(starts, starts[1:] + [len(data)])]


def h263_picture(picture: bytes) -> tuple[Fields, int, int]:
    """The picture header's elements, then the coded data after it and its width in bits."""
    bits = Bits(picture.rstrip(b"\x00"))
    f: Fields = {"psc": bits.read(22), "temporal_reference": bits.read(8)}
    f["marker_bit"], f["zero_bit"] = bits.read(1), bits.read(1)
    f["split_screen_indicator"], f["document_camera_indicator"] = bits.read(1), bits.read(1)
    f["full_picture_freeze_release"], f["source_format"] = bits.read(1), bits.read(3)
    f["picture_coding_type"], f["unrestricted_mv"] = bits.read(1), bits.read(1)
    f["syntax_based_arithmetic"], f["advanced_prediction"] = bits.read(1), bits.read(1)
    f["pb_frames"], f["pquant"], f["cpm"], f["pei"] = (
        bits.read(1),
        bits.read(5),
        bits.read(1),
        bits.read(1),
    )
    if f["pei"] or bits.at != H263_HEADER_BITS:
        raise ValueError("PEI or a longer header is not parsed")
    width = bits.size - bits.at
    rest = bits.rest()
    # the trailing zero bits are stuffing up to the next start code
    while width and not rest & 1:
        rest >>= 1
        width -= 1
    return f, rest, width


# VC-1


def vc1_sequence(payload: bytes) -> Fields:
    """The Advanced profile sequence header, SMPTE 421M 6.1."""
    bits = Bits(unescape(payload))
    f: Fields = {"PROFILE": bits.read(2), "LEVEL": bits.read(3), "COLORDIFF_FORMAT": bits.read(2)}
    f["FRMRTQ_POSTPROC"], f["BITRTQ_POSTPROC"] = bits.read(3), bits.read(5)
    f["POSTPROCFLAG"] = bits.read(1)
    f["MAX_CODED_WIDTH"], f["MAX_CODED_HEIGHT"] = bits.read(12), bits.read(12)
    for name in ("PULLDOWN", "INTERLACE", "TFCNTRFLAG", "FINTERPFLAG", "RESERVED", "PSF"):
        f[name] = bits.read(1)
    f["DISPLAY_EXT"] = bits.read(1)
    if f["DISPLAY_EXT"]:
        f["DISP_HORIZ_SIZE"], f["DISP_VERT_SIZE"] = bits.read(14), bits.read(14)
        f["ASPECT_RATIO_FLAG"] = bits.read(1)
        if f["ASPECT_RATIO_FLAG"] and bits.read(4) == 15:
            bits.read(16)
        f["FRAMERATE_FLAG"] = bits.read(1)
        if f["FRAMERATE_FLAG"]:
            bits.read(16 if bits.read(1) else 12)
        f["COLOR_FORMAT_FLAG"] = bits.read(1)
        if f["COLOR_FORMAT_FLAG"]:
            bits.read(24)
    f["HRD_PARAM_FLAG"] = bits.read(1)
    f["HRD_NUM_LEAKY_BUCKETS"] = bits.read(5) if f["HRD_PARAM_FLAG"] else 0
    return f


def vc1_entry_point(payload: bytes, hrd_buckets: int = 0) -> Fields:
    """The entry-point header, SMPTE 421M 6.2; the sequence's HRD buckets must be 0."""
    bits = Bits(unescape(payload))
    f: Fields = {}
    for name in ("BROKEN_LINK", "CLOSED_ENTRY", "PANSCAN_FLAG", "REFDIST_FLAG", "LOOPFILTER"):
        f[name] = bits.read(1)
    f["FASTUVMC"], f["EXTENDED_MV"], f["DQUANT"] = bits.read(1), bits.read(1), bits.read(2)
    f["VSTRANSFORM"], f["OVERLAP"], f["QUANTIZER"] = bits.read(1), bits.read(1), bits.read(2)
    bits.read(8 * hrd_buckets)
    f["CODED_SIZE_FLAG"] = bits.read(1)
    if f["CODED_SIZE_FLAG"]:
        f["CODED_WIDTH"], f["CODED_HEIGHT"] = bits.read(12), bits.read(12)
    f["EXTENDED_DMV"] = bits.read(1) if f["EXTENDED_MV"] else 0
    f["RANGE_MAPY_FLAG"] = bits.read(1)
    f["RANGE_MAPY"] = bits.read(3) if f["RANGE_MAPY_FLAG"] else 0
    f["RANGE_MAPUV_FLAG"] = bits.read(1)
    f["RANGE_MAPUV"] = bits.read(3) if f["RANGE_MAPUV_FLAG"] else 0
    return f


def vc1_struct_c(data: bytes) -> Fields:
    """Annex J's STRUCT_C, the Simple and Main profile sequence layer."""
    bits = Bits(data[:4])
    names = [
        ("PROFILE", 4), ("FRMRTQ_POSTPROC", 3), ("BITRTQ_POSTPROC", 5), ("LOOPFILTER", 1),
        ("RES_X8", 1), ("MULTIRES", 1), ("RES_FASTTX", 1), ("FASTUVMC", 1), ("EXTENDED_MV", 1),
        ("DQUANT", 2), ("VSTRANSFORM", 1), ("RES_TRANSTAB", 1), ("OVERLAP", 1),
        ("SYNCMARKER", 1), ("RANGERED", 1), ("MAXBFRAMES", 3), ("QUANTIZER", 2),
        ("FINTERPFLAG", 1), ("RES_RTM_FLAG", 1),
    ]  # fmt: skip
    return {name: bits.read(width) for name, width in names}


def rcv(data: bytes) -> tuple[bytes, list[bytes]]:
    """An RCV file's STRUCT_C and its frames (SMPTE 421M Annex L)."""
    struct_c_size = int.from_bytes(data[4:8], "little")
    struct_c = data[8 : 8 + struct_c_size]
    at = 8 + struct_c_size + RCV_AFTER_STRUCT_C
    frames = []
    while at + RCV_FRAME_HEADER_SIZE <= len(data):
        size = int.from_bytes(data[at : at + 4], "little") & RCV_FRAME_SIZE_MASK
        at += RCV_FRAME_HEADER_SIZE
        frames.append(data[at : at + size])
        at += size
    return struct_c, frames


# what a stateless decoder is told each picture, from the clip, for the Cedrus mapping test

Values = dict[str, list[int]]
VOP_I, VOP_P, VOP_B = 0, 1, 2
RESYNC_ZEROS = 16
H263_GOB_START = re.compile("0{16}1")
H263_GOB_NUMBER_BITS = 5
VC1_PTYPES = {"0": 1, "10": 2, "110": 0, "1110": 3, "1111": 4}
VC1_SKIPPED = 4
VC1_BFRACTION_ESCAPE = 0b111


def bit_string(data: bytes) -> str:
    return "".join(f"{byte:08b}" for byte in data)


def resync_zeros(vop_type: int, forward: int, backward: int) -> int:
    if vop_type == VOP_I:
        return RESYNC_ZEROS
    if vop_type == VOP_B:
        return max(forward, backward, 2) + RESYNC_ZEROS - 1
    return forward + RESYNC_ZEROS - 1


def mpeg4_mapping(data: bytes) -> Values:
    """Each VOP's type, DC threshold and forward f_code; each video packet's first macroblock and
    quantiser, the VOP's own first."""
    values: Values = {}
    vol: Fields = {}
    for code, payload in start_code_units(data):
        if MPEG4_VOL_FIRST <= code <= MPEG4_VOL_LAST:
            vol = mpeg4_vol(payload)
        if code != MPEG4_VOP or not vol:
            continue
        bits = Bits(payload)
        vop_type = bits.read(2)
        while bits.read(1):
            pass
        resolution = vol["vop_time_increment_resolution"]
        bits.read(2 + max(1, (resolution - 1).bit_length()))
        if not bits.read(1):
            continue
        if vop_type == VOP_P:
            bits.read(1)
        values.setdefault("vop_coding_type", []).append(vop_type)
        values.setdefault("intra_dc_vlc_thr", []).append(bits.read(3))
        if vol["interlaced"]:
            bits.read(2)
        quant = bits.read(vol["quant_precision"])
        forward = bits.read(3) if vop_type != VOP_I else 0
        backward = bits.read(3) if vop_type == VOP_B else 0
        if vop_type != VOP_I:
            values.setdefault("vop_fcode_forward", []).append(forward)
        values.setdefault("macroblock_number", []).append(0)
        values.setdefault("quant_scale", []).append(quant)
        if vol["resync_marker_disable"]:
            continue
        stream = bit_string(payload)
        macroblocks = -(-vol["video_object_layer_width"] // 16) * -(
            -vol["video_object_layer_height"] // 16
        )
        number_bits = max(1, (macroblocks - 1).bit_length())
        zeros = resync_zeros(vop_type, forward, backward)
        for byte in range(-(-bits.at // 8), len(payload)):
            one = stream.find("1", byte * 8)
            if payload[byte] or one - byte * 8 != zeros:
                continue
            values["macroblock_number"].append(int(stream[one + 1 : one + 1 + number_bits], 2))
            at = one + 1 + number_bits
            values["quant_scale"].append(int(stream[at : at + vol["quant_precision"]], 2))
    return values


def h263_mapping(data: bytes) -> Values:
    """Each picture's type and quantiser, then each GOB's first macroblock and quantiser."""
    values: Values = {}
    for picture in h263_pictures(data):
        fields, _, _ = h263_picture(picture)
        values.setdefault("vop_coding_type", []).append(fields["picture_coding_type"])
        values.setdefault("macroblock_number", []).append(0)
        values.setdefault("quant_scale", []).append(fields["pquant"])
        stream = bit_string(picture)
        per_gob = -(-H263_SIZES[fields["source_format"]][0] // 16)
        for found in H263_GOB_START.finditer(stream, H263_HEADER_BITS):
            at = found.end()
            number = int(stream[at : at + H263_GOB_NUMBER_BITS], 2)
            if number:
                values["macroblock_number"].append(
                    number * per_gob * GOB_ROWS[fields["source_format"]]
                )
                at += H263_GOB_NUMBER_BITS + 2
                values["quant_scale"].append(int(stream[at : at + 5], 2))
    return values


H263_SIZES = {1: (128, 96), 2: (176, 144), 3: (352, 288), 4: (704, 576), 5: (1408, 1152)}
# macroblock rows a GOB covers, by source format
GOB_ROWS = {1: 1, 2: 1, 3: 1, 4: 2, 5: 4}


def vc1_mapping(data: bytes) -> Values | None:
    """Each Advanced profile frame's PTYPE and PQINDEX, and the entry points' coding tools; None
    where a picture is interlaced or carries pan-scan or postprocessing, which this does not read.
    """
    values: Values = {}
    sequence: Fields = {}
    entry: Fields = {}
    for code, payload in start_code_units(data):
        if code == VC1_SEQUENCE:
            sequence = vc1_sequence(payload)
        elif code == VC1_ENTRY_POINT:
            entry = vc1_entry_point(payload, sequence["HRD_NUM_LEAKY_BUCKETS"])
            for name in ("DQUANT", "QUANTIZER", "LOOPFILTER", "OVERLAP", "VSTRANSFORM"):
                values.setdefault(name, []).append(entry[name])
        if code != 0x0D:
            continue
        if sequence["POSTPROCFLAG"]:
            return None
        bits = Bits(unescape(payload))
        if sequence["INTERLACE"] and bits.read(1):
            return None
        code_bits = ""
        while code_bits not in VC1_PTYPES:
            code_bits += str(bits.read(1))
        ptype = VC1_PTYPES[code_bits]
        values.setdefault("PTYPE", []).append(ptype)
        if sequence["TFCNTRFLAG"]:
            bits.read(8)
        if sequence["PULLDOWN"]:
            bits.read(2)
        if ptype == VC1_SKIPPED:
            continue
        if entry.get("PANSCAN_FLAG"):
            return None
        bits.read(1 + sequence["INTERLACE"] + sequence["FINTERPFLAG"])
        if ptype == 2 and bits.read(3) == VC1_BFRACTION_ESCAPE:
            bits.read(4)
        values.setdefault("PQINDEX", []).append(bits.read(5))
    return values
