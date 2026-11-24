"""Debian's arm64 Chromium on GLES 2, with video on Wayland overlays: patch.py CHROMIUM PATCHED.
Each site is found from anchors that survive a rebuild (strings, a feature's name, instruction shapes) and must be
found exactly once, or nothing is written.
1. The GPU probe asks for its ES context without the ES 2.0 fallback: load its attributes from a constant identical
   but for allow_es_version_fallback.
2. ANGLE's per-stage sampler limit: a vertex stage with none counts the fragment's; Mesa still checks its own.
3. WaylandOverlayManager::CanHandleCandidate refuses any candidate with a clip_rect: a code cave refuses it only when
   the clip, grown by 0.01 px of rounding, does not hold the display_rect (0001-viz-... is the upstream form).
4. No AV1 unless the hardware decodes it: IsDefaultDecoderSupportedVideoType, which RenderMediaClient asks once the
   GPU's decoders have declined, answers false for VideoCodec::kAV1, so sites serve a codec the hardware decodes.
5. Overlays with fractional scaling: WaylandConnection::ShouldUseOverlayDelegation, inlined, refuses delegation
   when wp_fractional_scale_manager_v1 is bound; without it the page renders at the output's scale.
6. CanHandleCandidate's last check refuses a display_rect off whole pixels, as at a fractional scale: accept it;
   the subsurface lands on whole logical pixels.
7. OverlayCandidateFactory::FromDrawQuadResource refuses a quad with rounded corners where the strategy cannot mask
   (kFailMaskFilterNotSupported), so a page's rounded video is composited: take it square instead, as a plane shows it.
"""

import struct
import sys
from collections.abc import Iterator
from typing import NoReturn

import numpy as np
import numpy.typing as npt
from elftools.elf.elffile import ELFFile
from elftools.elf.sections import Section

Words = npt.NDArray[np.int64]
Patches = dict[int, tuple[int, int]]  # pc: (instruction, replacement)

NOP, RET, PACIASP, BR_X16 = 0xD503201F, 0xD65F03C0, 0xD503233F, 0xD61F0200
MOV_W0_1, MOV_W1_1 = 0x52800020, 0x52800021
MOV_W8_ONE_HUNDREDTH_LOW, MOVK_W8_ONE_HUNDREDTH_HIGH, FMOV_S0_W8 = (
    0x529AE148,
    0x72A78468,
    0x1E270100,
)
MOV_W0_WZR = 0x2A1F03E0
MOV_W0_MASK_FILTER_NOT_SUPPORTED = (
    0x528001E0  # mov w0, #CandidateStatus::kFailMaskFilterNotSupported
)
CMP_W8_1 = 0x7100051F
NE = 0x1
ATTRIBUTES_WITHOUT_FALLBACK = bytes.fromhex("0000000100010001")
ATTRIBUTES_WITH_FALLBACK = bytes.fromhex("0100000100010001")
VIDEO_CODEC_AV1 = 10
R_AARCH64_RELATIVE = 1027
EQ, MI, HI, GT = 0x0, 0x4, 0x8, 0xC
B_REACH, B_COND_REACH = 1 << 27, 1 << 20
FUNCTION_SEARCH_LIMIT = 4096
CLIP_CAVE_LENGTH = 33


def fail(message: str) -> NoReturn:
    sys.exit(f"patch.py: {message}; nothing written")


def only[T](found: list[T], what: str) -> T:
    if len(found) != 1:
        fail(f"{what}: found {len(found)} times, not once")
    return found[0]


def signed(value: int, bits: int) -> int:
    return value - (1 << bits) if value & (1 << (bits - 1)) else value


def b(pc: int, target: int) -> int:
    if not -B_REACH <= target - pc < B_REACH:
        fail(f"{pc:#x} cannot branch to {target:#x}")
    return 0x14000000 | ((target - pc) >> 2) & 0x3FFFFFF


def b_cond(pc: int, target: int, condition: int) -> int:
    if not -B_COND_REACH <= target - pc < B_COND_REACH:
        fail(f"{pc:#x} cannot branch conditionally to {target:#x}")
    return 0x54000000 | (((target - pc) >> 2) & 0x7FFFF) << 5 | condition


def adrp(pc: int, register: int, target: int) -> int:
    pages = (((target & ~0xFFF) - (pc & ~0xFFF)) >> 12) & 0x1FFFFF
    return 0x90000000 | (pages & 3) << 29 | (pages >> 2) << 5 | register


def ldr_d(register: int, base: int, offset: int) -> int:
    return 0xFD400000 | (offset // 8) << 10 | base << 5 | register


def ldr_w(register: int, base: int, offset: int) -> int:
    return 0xB9400000 | (offset // 4) << 10 | base << 5 | register


def ldp_s(first: int, second: int, base: int, offset: int) -> int:
    return 0x2D400000 | ((offset // 4) & 0x7F) << 15 | second << 10 | base << 5 | first


def is_adrp(word: int) -> bool:
    return word & 0x9F000000 == 0x90000000


def is_b(word: int) -> bool:
    return word & 0xFC000000 == 0x14000000


def is_bl(word: int) -> bool:
    return word & 0xFC000000 == 0x94000000


def ends_flow(word: int) -> bool:
    """ret, b, br, brk or hlt: nothing runs on into the next word."""
    return (
        word == RET
        or is_b(word)
        or word & 0xFFFFFC1F == 0xD61F0000
        or word & 0xFFE0001F in (0xD4200000, 0xD4400000)
    )


def branch_target(pc: int, word: int) -> int:
    if word & 0x7C000000 == 0x14000000:  # b, bl
        return pc + 4 * signed(word & 0x3FFFFFF, 26)
    if (
        word & 0xFF000010 == 0x54000000 or word & 0x7E000000 == 0x34000000
    ):  # b.cond, cbz, cbnz
        return pc + 4 * signed((word >> 5) & 0x7FFFF, 19)
    if word & 0x7E000000 == 0x36000000:  # tbz, tbnz
        return pc + 4 * signed((word >> 5) & 0x3FFF, 14)
    fail(f"{pc:#x}: {word:#010x} is no branch")


def page(pc: int, word: int) -> int:
    return (pc & ~0xFFF) + (
        signed(((word >> 5) & 0x7FFFF) << 2 | (word >> 29) & 3, 21) << 12
    )


def low_offset(word: int, base: int) -> int | None:
    """What an ADD (immediate) or an unsigned-offset load on base adds to the page in it."""
    if (word >> 5) & 0x1F != base:
        return None
    if word & 0xFFC00000 == 0x91000000:
        return (word >> 10) & 0xFFF
    if word & 0x3B400000 == 0x39400000:
        quad = 4 if word & 0x04800000 == 0x04800000 else 0
        return ((word >> 10) & 0xFFF) << (word >> 30 | quad)
    return None


def extend(values: Words, bits: int) -> Words:
    return np.where(values & (1 << (bits - 1)), values - (1 << bits), values)


def section(elf: ELFFile, name: str) -> Section:
    found = elf.get_section_by_name(name)
    if found is None:
        fail(f"no {name}")
    return found


class Binary:
    def __init__(self, path: str) -> None:
        self.data = bytearray(open(path, "rb").read())
        with open(path, "rb") as stream:
            elf = ELFFile(stream)
            self.segments = [
                (s["p_offset"], s["p_vaddr"], s["p_filesz"])
                for s in elf.iter_segments()
                if s["p_type"] == "PT_LOAD"
            ]
            text, rodata = section(elf, ".text"), section(elf, ".rodata")
            relocations = np.frombuffer(
                section(elf, ".rela.dyn").data(),
                dtype=np.dtype([("offset", "<u8"), ("info", "<u8"), ("addend", "<i8")]),
            )
        self.rodata = (rodata["sh_addr"], rodata["sh_addr"] + rodata["sh_size"])
        relative = relocations[relocations["info"] == R_AARCH64_RELATIVE]
        self.pointers: dict[int, list[int]] = {}
        for at, value in zip(relative["offset"].tolist(), relative["addend"].tolist()):
            self.pointers.setdefault(value, []).append(at)
        self.text = text["sh_addr"]
        self.words: Words = np.frombuffer(
            self.data, "<u4", text["sh_size"] // 4, self.offset(self.text)
        ).astype(np.int64)
        w = self.words
        self.pcs: Words = self.text + 4 * np.arange(len(w), dtype=np.int64)
        self.bl = (w & 0xFC000000) == 0x94000000
        unconditional = (w & 0x7C000000) == 0x14000000
        conditional = ((w & 0xFF000010) == 0x54000000) | (
            (w & 0x7E000000) == 0x34000000
        )
        test = (w & 0x7E000000) == 0x36000000
        self.branch_to: Words = np.select(
            [unconditional, conditional, test],
            [
                self.pcs + 4 * extend(w & 0x3FFFFFF, 26),
                self.pcs + 4 * extend((w >> 5) & 0x7FFFF, 19),
                self.pcs + 4 * extend((w >> 5) & 0x3FFF, 14),
            ],
            -1,
        )
        self.pages: Words = self.pcs & ~0xFFF
        adrps = (w & 0x9F000000) == 0x90000000
        self.pages[~adrps] = -1
        self.pages[adrps] += (
            extend(((w[adrps] >> 5) & 0x7FFFF) << 2 | (w[adrps] >> 29) & 3, 21) << 12
        )

    def offset(self, vaddr: int) -> int:
        return next(
            o + vaddr - v for o, v, size in self.segments if v <= vaddr < v + size
        )

    def word(self, pc: int) -> int:
        return struct.unpack_from("<I", self.data, self.offset(pc))[0]

    def put(self, pc: int, word: int) -> None:
        struct.pack_into("<I", self.data, self.offset(pc), word)

    def branches_to(self, target: int) -> list[int]:
        return self.pcs[(self.branch_to == target) & ~self.bl].tolist()

    def calls_to(self, target: int) -> set[int]:
        return set(self.pcs[(self.branch_to == target) & self.bl].tolist())

    def strings(self, text: str) -> list[int]:
        """Where text ends a string, alone or as the tail the linker merged into a longer one."""
        start, end = self.rodata
        needle, found = text.encode() + b"\0", []
        at = self.data.find(needle, self.offset(start), self.offset(end))
        while at >= 0:
            found.append(at - self.offset(start) + start)
            at = self.data.find(needle, at + 1, self.offset(end))
        return found

    def aligned_constant(self, value: bytes) -> int:
        start, end = self.rodata
        at = self.data.find(value, self.offset(start), self.offset(end))
        while at >= 0 and (at - self.offset(start) + start) % len(value):
            at = self.data.find(value, at + 1, self.offset(end))
        if at < 0:
            fail(f"no constant {value.hex()}")
        return at - self.offset(start) + start

    def references(self, *targets: int) -> list[int]:
        """ADRPs that, with an ADD or a load on their register, make one of targets."""
        return [
            pc
            for target in targets
            for pc in self.pcs[self.pages == target & ~0xFFF].tolist()
            if any(use == target for _, use in self.uses(pc))
        ]

    def uses(self, adrp_pc: int, reach: int = 8) -> Iterator[tuple[int, int]]:
        word = self.word(adrp_pc)
        for pc in range(adrp_pc + 4, adrp_pc + 4 * reach, 4):
            low = low_offset(self.word(pc), word & 0x1F)
            if low is not None:
                yield pc, page(adrp_pc, word) + low

    def function_start(self, pc: int) -> int:
        for start in range(pc, pc - 4 * FUNCTION_SEARCH_LIMIT, -4):
            if self.word(start) == PACIASP:
                return start
        fail(f"no function start before {pc:#x}")

    def callee(self, call: int) -> int:
        """A BL's target, through the linker's thunk (b; or adrp x16; add x16; br x16) when it lands on one."""
        target = branch_target(call, self.word(call))
        if is_b(self.word(target)):
            return branch_target(target, self.word(target))
        if is_adrp(self.word(target)) and self.word(target + 8) == BR_X16:
            return page(target, self.word(target)) + (
                low_offset(self.word(target + 4), 16) or 0
            )
        return target

    def padding(self, length: int) -> int:
        """The longest run of zero words in .text, after a function's end and with no branch into it."""
        zero = (self.words == 0).astype(np.int8)
        edges = np.diff(np.concatenate(([0], zero, [0])))
        starts, ends = np.nonzero(edges == 1)[0], np.nonzero(edges == -1)[0]
        longest = int(np.argmax(ends - starts))
        start, end = self.text + 4 * int(starts[longest]), self.text + 4 * int(
            ends[longest]
        )
        if end - start < 4 * length or not ends_flow(self.word(start - 4)):
            fail(f"no padding for a {length}-word cave")
        if np.any((self.branch_to >= start) & (self.branch_to < end)):
            fail(f"a branch lands in the padding at {start:#x}")
        return start


def es_fallback(binary: Binary) -> Patches:
    trace = only(
        binary.references(*binary.strings("gpu_info_collector::InitializeGLContext")),
        "the GPU probe's trace event",
    )
    tracing = only(binary.branches_to(trace), "the GPU probe's tracing branch")
    attributes = [
        (adrp_pc, load_pc)
        for adrp_pc in range(tracing, tracing + 64, 4)
        if is_adrp(binary.word(adrp_pc))
        for load_pc, target in binary.uses(adrp_pc)
        if binary.word(load_pc) & 0xFFC00000 == 0xFD400000
        and binary.data[binary.offset(target) : binary.offset(target) + 8]
        == ATTRIBUTES_WITHOUT_FALLBACK
    ]
    adrp_pc, load_pc = only(attributes, "the GPU probe's context attributes")
    load = binary.word(load_pc)
    replacement = binary.aligned_constant(ATTRIBUTES_WITH_FALLBACK)
    base = (load >> 5) & 0x1F
    return {
        adrp_pc: (binary.word(adrp_pc), adrp(adrp_pc, base, replacement)),
        load_pc: (load, ldr_d(load & 0x1F, base, replacement & 0xFFF)),
    }


def sampler_limit(binary: Binary) -> Patches:
    message = only(
        binary.references(*binary.strings("s count exceeds ")), "ANGLE's limit message"
    )
    reports = binary.calls_to(binary.function_start(message))
    blocks = [
        pc - 4
        for pc in binary.pcs[binary.words == MOV_W1_1].tolist()
        if is_b(binary.word(pc + 4))
        and any(
            branch_target(pc + 4, binary.word(pc + 4)) + 4 * i in reports
            for i in range(4)
        )
    ]
    block = only(blocks, "ANGLE's texture image units report")
    check = only(binary.branches_to(block), "ANGLE's texture image units check")
    if binary.word(check) & 0xFF00001F != 0x54000000 | HI:
        fail(f"{check:#x} is not a b.hi")
    return {check: (binary.word(check), NOP)}


class OverlayCheck:
    """WaylandOverlayManager::CanHandleCandidate's last checks: clip_rect, background, whole pixels (0.01f)."""

    def __init__(self, binary: Binary) -> None:
        sites = [
            site
            for pc in binary.pcs[binary.words == MOV_W8_ONE_HUNDREDTH_LOW].tolist()
            for site in self.sites(binary, pc)
        ]
        self.clip_check, self.pixel_check, self.tail_call, start = only(
            sites, "CanHandleCandidate's last checks"
        )
        self.back = self.clip_check + 4
        self.reject = branch_target(self.clip_check, binary.word(self.clip_check))
        self.clip = (
            (binary.word(self.clip_check - 4) >> 10) & 0xFFF
        ) - 16  # optional<Rect>: rect, flag
        body = [binary.word(pc) for pc in range(start, self.pixel_check, 4)]
        rect_loads = {
            ((w >> 10) & 0xFFF) * 4 for w in body if w & 0xFFC003E0 == 0xBD400260
        }  # ldr s, [x19, #]
        self.display = max(rect_loads) - 12
        rect_address = {
            (w >> 10) & 0xFFF for w in body if w & 0xFFC003E0 == 0x91000260
        }  # add xN, x19, #
        rect_address |= {
            (w >> 12) & 0x1FF for w in body if w & 0xFFE00C00 == 0xBC400C00
        }  # ldr s, [xN, #]!
        if (
            not {self.display + 8, self.display + 12} <= rect_loads
            or self.display not in rect_address
        ):
            fail("CanHandleCandidate's display_rect")

    @staticmethod
    def sites(binary: Binary, pc: int) -> Iterator[tuple[int, int, int, int]]:
        """Its tail: s0 = 0.01f, then the tail call; its clip check: an ldrb on x19 and a tbnz to "return false",
        before the background's ldrb."""
        tail = [binary.word(pc + 4 * i) for i in range(12)]
        if MOVK_W8_ONE_HUNDREDTH_HIGH not in tail[:6] or FMOV_S0_W8 not in tail:
            return
        pixel_check = pc + 4 * tail.index(FMOV_S0_W8)
        calls = [
            p for p in range(pixel_check, pixel_check + 16, 4) if is_b(binary.word(p))
        ]
        if not calls:
            return
        start = binary.function_start(pc)
        for check in range(start + 4, pc, 4):
            load, test, following = (binary.word(check + 4 * i) for i in (-1, 0, 1))
            if (
                load & 0xFFC003FF == 0x39400268  # ldrb w8, [x19, #]
                and test & 0xFFF8001F == 0x37000008  # tbnz w8, #0
                and following & 0xFFC003FF == 0x39400268
            ):
                reject = branch_target(check, test)
                if any(binary.word(reject + 4 * i) == MOV_W0_WZR for i in range(3)):
                    yield check, pixel_check, calls[0], start

    def cave(self, at: int) -> list[int]:
        code: list[int] = []
        reject = at + 4 * (CLIP_CAVE_LENGTH - 1)

        def refuse_unless(compare: int, condition: int) -> None:
            code.append(compare)
            code.append(b_cond(at + 4 * len(code), reject, condition))

        code += [0x37000048, b(at + 4, self.back)]  # tbnz w8, #0, .+8: a clip to check
        code += [ldr_w(9 + i, 19, self.clip + 4 * i) for i in range(4)]
        code += [0x0B0B012B, 0x0B0C014C]  # add w11, w9, w11; add w12, w10, w12
        code += [
            0x1E220124,
            0x1E220145,
            0x1E220166,
            0x1E220187,
        ]  # scvtf s4..s7, w9..w12
        code += [0x529AE149, 0x72A78469, 0x1E270130]  # s16 = 0.01f
        code += [
            0x1E303884,
            0x1E3038A5,
            0x1E3028C6,
            0x1E3028E7,
        ]  # s4, s5 -= s16; s6, s7 += s16
        code += [ldp_s(0, 1, 19, self.display), ldp_s(2, 3, 19, self.display + 8)]
        code += [0x1E222802, 0x1E232823]  # s2 = s0 + s2; s3 = s1 + s3
        refuse_unless(0x1E202080, GT)  # fcmp s4, s0
        refuse_unless(0x1E2120A0, GT)  # fcmp s5, s1
        refuse_unless(0x1E2220C0, MI)  # fcmp s6, s2
        refuse_unless(0x1E2320E0, MI)  # fcmp s7, s3
        code.append(b(at + 4 * len(code), self.back))
        code.append(b(reject, self.reject))
        assert len(code) == CLIP_CAVE_LENGTH
        return code

    def patches(self, binary: Binary, cave: int) -> Patches:
        return {
            self.clip_check: (binary.word(self.clip_check), b(self.clip_check, cave)),
            self.pixel_check: (FMOV_S0_W8, MOV_W0_1),
            self.tail_call: (binary.word(self.tail_call), RET),
        }


def no_av1(binary: Binary) -> Patches:
    source = set(
        binary.references(
            *binary.strings("../../content/renderer/media/render_media_client.cc")
        )
    )
    anchor = only(
        [
            pc
            for pc in binary.references(*binary.strings("IsDecoderSupportedVideoType"))
            if any(pc + 4 * i in source for i in range(1, 5))
        ],
        "RenderMediaClient::IsDecoderSupportedVideoType",
    )
    switches = []
    for call in range(anchor, anchor + 4 * 32, 4):
        if not is_bl(binary.word(call)):
            continue
        function = binary.callee(call)
        words = [binary.word(function + 4 * i) for i in range(64)]
        for load, word in enumerate(words):
            if word & 0xFFFFFC00 != 0xB9400000:  # ldr wN, [xM]: VideoType::codec
                continue
            codec = word & 0x1F
            unknown = [
                i
                for i in range(load + 1, 64)
                if words[i] & 0xFF00001F == 0x34000000 | codec
            ]
            av1 = [
                i + 1
                for i in range(load + 1, 63)
                if words[i]
                == 0x7100001F | VIDEO_CODEC_AV1 << 10 | codec << 5  # cmp wN, #kAV1
                and words[i + 1] & 0xFF00001F == 0x54000000 | EQ
            ]
            if unknown and av1:
                switches.append((function + 4 * av1[0], function + 4 * unknown[0]))
                break
    check, unknown = only(switches, "IsDefaultDecoderSupportedVideoType's codec switch")
    refuse = branch_target(unknown, binary.word(unknown))
    if binary.word(refuse) & 0xFFFFFFE0 != 0x2A1F03E0:  # mov wN, wzr
        fail(f"{refuse:#x} does not refuse")
    return {check: (binary.word(check), b_cond(check, refuse, EQ))}


def fractional_overlays(binary: Binary) -> Patches:
    feature = only(
        [
            at
            for name in binary.strings("WaylandOverlayDelegation")
            for at in binary.pointers.get(name, [])
            if binary.references(at)
        ],
        "the WaylandOverlayDelegation feature",
    )
    patches: Patches = {}
    fields = set()
    for reference in binary.references(feature):
        enabled = next(
            (
                pc
                for pc in range(reference, reference + 4 * 24, 4)
                if is_bl(binary.word(pc))
            ),
            None,
        )
        if (
            enabled is None or binary.word(enabled + 4) & 0xFFF8001F != 0x36000000
        ):  # tbz w0, #0
            continue
        load, first, second = (binary.word(enabled + 8 + 4 * i) for i in range(3))
        if (
            load & 0xFFC00000 != 0xF9400000
        ):  # ldr xM, [xN, #fractional_scale_manager_v1_]
            continue
        manager = load & 0x1F
        if first == 0xF100001F | manager << 5 and second & 0xFFFFFFE0 == 0x1A9F17E0:
            patches[enabled + 16] = (
                second,
                0x52800020 | second & 0x1F,
            )  # cset wD, eq -> mov wD, #1
        elif (
            first & 0xFFFFFFE0 == 0x2A1F03E0
            and second & 0xFF00001F == 0xB5000000 | manager
        ):
            patches[enabled + 16] = (second, NOP)  # mov wD, wzr; cbnz xM, false
        else:
            continue
        fields.add((load >> 10) & 0xFFF)
    if not patches or len(fields) != 1:
        fail(
            f"ShouldUseOverlayDelegation's checks: {len(patches)} sites on fields {fields}"
        )
    return patches


def square_rounded_overlays(binary: Binary) -> Patches:
    w, pcs = binary.words, binary.pcs
    sites = []
    for k in np.nonzero(w[:-3] == MOV_W0_MASK_FILTER_NOT_SUPPORTED)[0].tolist():
        exit_ = int(binary.branch_to[k + 1])
        if not (
            is_b(int(w[k + 1]))
            and int(w[k + 2]) == MOV_W0_WZR
            and int(binary.branch_to[k + 3]) == exit_
        ):
            continue
        fail_pc, success = int(pcs[k]), int(pcs[k + 2])
        for test in binary.branches_to(fail_pc):
            word = binary.word(test)
            ldrb = binary.word(test - 8)
            if (
                word & 0xFF00001F == 0x54000000 | NE
                and binary.word(test - 4) == CMP_W8_1
                and ldrb & 0xFFC0001F
                == 0x39400008  # ldrb w8, [xN, #supports_mask_filter]
                and binary.word(test - 12) & 0xFFF8001F
                == 0x36000000  # tbz w0, #0, success
                and branch_target(test - 12, binary.word(test - 12)) == success
            ):
                sites.append((test, word, success))
    test, word, success = only(sites, "FromDrawQuadResource's mask-filter refusal")
    return {test: (word, b_cond(test, success, NE))}


def main(source: str, destination: str) -> None:
    binary = Binary(source)
    overlay = OverlayCheck(binary)
    cave = binary.padding(CLIP_CAVE_LENGTH)
    patches = (
        es_fallback(binary)
        | sampler_limit(binary)
        | overlay.patches(binary, cave)
        | no_av1(binary)
        | fractional_overlays(binary)
        | square_rounded_overlays(binary)
    )
    for pc, (instruction, replacement) in patches.items():
        if binary.word(pc) != instruction:
            fail(f"{pc:#x} changed under the patch")
        binary.put(pc, replacement)
        print(f"{pc:#x}: {instruction:#010x} -> {replacement:#010x}")
    for i, instruction in enumerate(overlay.cave(cave)):
        binary.put(cave + 4 * i, instruction)
    print(f"cave at {cave:#x}, {CLIP_CAVE_LENGTH} words")
    open(destination, "wb").write(binary.data)


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])
