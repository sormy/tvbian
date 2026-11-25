"""x98h_vfd - driver for the X98H front 4-digit 7-segment panel.

Hardware (vendor DTB, eMMC VNDRBOOT p7, node `aw_vfd`, compatible amediatech,yxt_vfd):
    data  = PC2  -> /dev/gpiochip1 line 66
    clock = PC7  -> line 71
    stb   = PC12 -> line 76

Chip: SM1628/TM1623-class serial LED driver. The matrix is TRANSPOSED:
address selects the SEGMENT line, data bit selects the DIGIT (or icon row).

    segments: a=addr0 b=2 c=4 d=6 e=8 f=10 g=12   (odd addresses unused)
    digits:   bit7 = leftmost ... bit4 = rightmost
    icons:    bit3, chosen per segment address
              usb@4 card@6 colon@8 hd@10 cvbs@12
    control:  0x88|brightness = on, 0x80 = off
"""

import time

import gpiod
from gpiod.line import Direction, Value

CHIP = "/dev/gpiochip1"
DATA, CLK, STB = 66, 71, 76
BIT_DELAY = 0.00002

CMD_WRITE = 0x40
ADDR_BASE = 0xC0
CMD_ON = 0x88
CMD_OFF = 0x80

SEG_ADDR = (0, 2, 4, 6, 8, 10, 12)
POS_BIT = (7, 6, 5, 4)
ICON_BIT = 3
NDIGITS = 4
NSEGS = 7

# 7-segment font. Letters without a true glyph use the usual approximations:
#   X/K/M/W -> H,  Z/S -> 2,  G -> 6,  N -> n,  V -> U,  Y -> y,  T -> t
FONT = {
    "0": 0x3F, "1": 0x06, "2": 0x5B, "3": 0x4F, "4": 0x66,
    "5": 0x6D, "6": 0x7D, "7": 0x07, "8": 0x7F, "9": 0x6F,
    " ": 0x00, "-": 0x40, "_": 0x08, ".": 0x80, ",": 0x00,
    "A": 0x77, "b": 0x7C, "B": 0x7C, "C": 0x39, "c": 0x58, "d": 0x5E,
    "D": 0x5E, "E": 0x79, "e": 0x79, "F": 0x71, "f": 0x71, "G": 0x3D,
    "g": 0x6F, "H": 0x76, "h": 0x74, "I": 0x06, "i": 0x04, "J": 0x1E,
    "K": 0x76, "k": 0x76, "L": 0x38, "l": 0x38, "M": 0x76, "m": 0x76,
    "n": 0x54, "N": 0x54, "O": 0x3F, "o": 0x5C, "P": 0x73, "p": 0x73,
    "Q": 0x3F, "q": 0x67, "r": 0x50, "R": 0x50, "S": 0x6D, "s": 0x6D,
    "t": 0x78, "T": 0x78, "U": 0x3E, "u": 0x1C, "V": 0x3E, "v": 0x1C,
    "W": 0x76, "w": 0x76, "X": 0x76, "x": 0x76, "Y": 0x6E, "y": 0x6E,
    "Z": 0x5B, "z": 0x5B, "?": 0x53, "!": 0x06, "'": 0x20, "+": 0x70,
    "=": 0x48, "/": 0x52, "\\": 0x64, "(": 0x39, ")": 0x0F, "*": 0x63,
}

ICONS = {"usb": 4, "card": 6, "colon": 8, ":": 8, "hd": 10, "cvbs": 12,
         "colon2": 8}


def open_lines():
    cfg = {
        DATA: gpiod.LineSettings(direction=Direction.OUTPUT, output_value=Value.INACTIVE),
        CLK: gpiod.LineSettings(direction=Direction.OUTPUT, output_value=Value.ACTIVE),
        STB: gpiod.LineSettings(direction=Direction.OUTPUT, output_value=Value.ACTIVE),
    }
    return gpiod.request_lines(CHIP, consumer="x98h-vfd", config=cfg)


class Vfd:
    def __init__(self, req):
        self.req = req

    def _v(self, on):
        return Value.ACTIVE if on else Value.INACTIVE

    def stb(self, v): self.req.set_value(STB, self._v(v))
    def clk(self, v): self.req.set_value(CLK, self._v(v))
    def dio(self, v): self.req.set_value(DATA, self._v(v))

    def write_byte(self, b):
        for i in range(8):
            self.clk(False)
            self.dio(bool((b >> i) & 1))
            time.sleep(BIT_DELAY)
            self.clk(True)
            time.sleep(BIT_DELAY)

    def command(self, *bytes_):
        self.clk(True)
        self.stb(False)
        time.sleep(BIT_DELAY)
        for b in bytes_:
            self.write_byte(b)
        self.stb(True)
        time.sleep(0.00005)

    def commit(self, seg_bytes, brightness=7, icons=()):
        data = [b & 0xFF for b in seg_bytes]
        for icon in icons:
            addr = ICONS.get(icon, icon)
            if addr in SEG_ADDR:
                data[SEG_ADDR.index(addr)] |= 1 << ICON_BIT
        self.command(CMD_WRITE)
        for seg in range(NSEGS):
            self.command(ADDR_BASE + SEG_ADDR[seg], data[seg])
        self.command(CMD_ON | (brightness & 7))

    def off(self):
        self.command(CMD_OFF)


def render(text, reverse=False):
    """text -> 7 bytes (one per segment line), each a bitmask of digits."""
    chars = list(text)[:NDIGITS]
    while len(chars) < NDIGITS:
        chars.append(" ")
    masks = [FONT.get(c, 0x00) for c in chars]
    if reverse:
        masks = list(reversed(masks))
    out = []
    for seg in range(NSEGS):
        b = 0
        for pos, mask in enumerate(masks):
            if (mask >> seg) & 1:
                b |= 1 << POS_BIT[pos]
        out.append(b)
    return out


def show(vfd, text, brightness=7, icons=(), reverse=False):
    vfd.commit(render(text, reverse), brightness, icons)
