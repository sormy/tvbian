"""Code that takes the address of a string: AArch64 ADRP + ADD pairs, in a stripped ELF."""

import sys

import numpy as np
from elftools.elf.elffile import ELFFile

ADRP_MASK, ADRP_BITS = 0x9F000000, 0x90000000
ADD_IMM_MASK, ADD_IMM_BITS = 0xFFC00000, 0x91000000  # 64-bit ADD (immediate), no shift
PAIR_WINDOW = 8  # instructions between an ADRP and the ADD that completes it


def main(path: str, needle: bytes) -> None:
    data = open(path, "rb").read()
    with open(path, "rb") as stream:
        elf = ELFFile(stream)
        segments = [
            (s["p_offset"], s["p_vaddr"], s["p_filesz"], s["p_flags"])
            for s in elf.iter_segments()
            if s["p_type"] == "PT_LOAD"
        ]

    def vaddr(offset: int) -> int:
        return next(
            v + offset - o for o, v, size, _ in segments if o <= offset < o + size
        )

    targets = []
    start = data.find(needle + b"\0")
    while start >= 0:
        targets.append(vaddr(start))
        start = data.find(needle + b"\0", start + 1)
    print("string at", [hex(t) for t in targets])

    for offset, base, size, flags in segments:
        if not flags & 1:  # executable only
            continue
        words = np.frombuffer(data, dtype="<u4", count=size // 4, offset=offset)
        pcs = base + 4 * np.arange(len(words), dtype=np.int64)
        adrp = (words & ADRP_MASK) == ADRP_BITS
        imm = ((words >> 5) & 0x7FFFF).astype(np.int64) << 2 | (
            (words >> 29) & 3
        ).astype(np.int64)
        imm = np.where(imm & (1 << 20), imm - (1 << 21), imm) << 12
        pages = (pcs & ~0xFFF) + imm
        for target in targets:
            for index in np.nonzero(adrp & (pages == (target & ~0xFFF)))[0]:
                register = int(words[index]) & 0x1F
                for step in range(1, PAIR_WINDOW):
                    word = int(words[index + step])
                    if (
                        (word & ADD_IMM_MASK) == ADD_IMM_BITS
                        and (word >> 5) & 0x1F == register
                        and (word >> 10) & 0xFFF == target & 0xFFF
                    ):
                        print(f"reference at {int(pcs[index]):#x}")


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2].encode())
