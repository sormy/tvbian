"""Every BL to a function, in a stripped AArch64 ELF."""

import sys

import numpy as np
from elftools.elf.elffile import ELFFile

BL_MASK, BL_BITS = 0xFC000000, 0x94000000


def main(path: str, target: int) -> None:
    data = open(path, "rb").read()
    with open(path, "rb") as stream:
        segments = [
            (s["p_offset"], s["p_vaddr"], s["p_filesz"], s["p_flags"])
            for s in ELFFile(stream).iter_segments()
            if s["p_type"] == "PT_LOAD"
        ]
    for offset, base, size, flags in segments:
        if not flags & 1:
            continue
        words = np.frombuffer(data, dtype="<u4", count=size // 4, offset=offset)
        pcs = base + 4 * np.arange(len(words), dtype=np.int64)
        imm = (words & 0x3FFFFFF).astype(np.int64)
        imm = np.where(imm & (1 << 25), imm - (1 << 26), imm) * 4
        for index in np.nonzero(((words & BL_MASK) == BL_BITS) & (pcs + imm == target))[
            0
        ]:
            print(f"call at {int(pcs[index]):#x}")


if __name__ == "__main__":
    main(sys.argv[1], int(sys.argv[2], 16))
