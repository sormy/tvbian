"""tools/dtcx/canonical.py: two blobs equal but for phandle numbering, read from their bytes."""

from __future__ import annotations

import struct
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools/dtcx"))
from canonical import (  # noqa: E402
    BEGIN_NODE,
    END,
    END_NODE,
    MAGIC,
    PROP,
    Blob,
    Projection,
    differences,
)
from references import Dialect  # noqa: E402

Tree = dict[str, dict[str, bytes]]
HEADER_SIZE = 40
DISABLED, OKAY = b"disabled\0", b"okay\0"


def cells(*values: int) -> bytes:
    return b"".join(v.to_bytes(4, "big") for v in values)


def padded(data: bytes) -> bytes:
    return data + b"\0" * (-len(data) % 4)


def blob(tree: Tree, reservations: tuple[tuple[int, int], ...] = ()) -> bytes:
    """A flattened tree of nodes by path, the root first and parents before children."""
    names: dict[str, int] = {}
    strings = b""
    structs = b""
    open_nodes: list[str] = []
    for path, props in tree.items():
        parts = [] if path == "/" else path.strip("/").split("/")
        while open_nodes and open_nodes != parts[: len(open_nodes)] or len(open_nodes) > len(parts):
            structs += cells(END_NODE)
            open_nodes.pop()
        if parts:
            open_nodes.append(parts[-1])
        structs += cells(BEGIN_NODE) + padded((parts[-1] if parts else "").encode() + b"\0")
        for name, value in props.items():
            if name not in names:
                names[name] = len(strings)
                strings += name.encode() + b"\0"
            structs += cells(PROP, len(value), names[name]) + padded(value)
    structs += cells(END_NODE) * (len(open_nodes) + 1) + cells(END)
    reserved = b"".join(struct.pack(">QQ", a, s) for a, s in (*reservations, (0, 0)))
    structs_at = HEADER_SIZE + len(reserved)
    strings_at = structs_at + len(structs)
    header = struct.pack(
        ">10I",
        MAGIC,
        strings_at + len(strings),
        structs_at,
        strings_at,
        HEADER_SIZE,
        17,
        16,
        0,
        len(strings),
        len(structs),
    )
    return header + reserved + structs + strings


def board(gic: int, uart: int, target: int, extra: Tree | None = None) -> Tree:
    """A clock controller and a GPIO bank, numbered as given, and a device using both."""
    return {
        "/": {"compatible": b"test\0"},
        "/cru": {"#clock-cells": cells(1), "phandle": cells(gic)},
        "/gpio": {"#gpio-cells": cells(2), "phandle": cells(uart)},
        "/serial": {
            "clocks": cells(target, 7),
            "reset-gpios": cells(uart, 3, 0),
            "status": DISABLED,
        },
        **(extra or {}),
    }


def diff(a: Tree, b: Tree, dialect: Dialect = Dialect()) -> list[str]:
    return differences(Blob.read(blob(a)), Blob.read(blob(b)), dialect)


def word(data: bytes, at: int) -> int:
    return int.from_bytes(data[at : at + 4], "big")


def with_word(data: bytes, at: int, value: int) -> bytes:
    """A header with one field changed."""
    return data[:at] + value.to_bytes(4, "big") + data[at + 4 :]


def cut_in_header(data: bytes) -> bytes:
    """The struct block ended four bytes into its first property's header, the bytes after it
    still readable."""
    structs = word(data, 8)
    first_prop = data.index(cells(PROP), structs)
    return with_word(data, 36, first_prop + 8 - structs)


class CanonicalTest(unittest.TestCase):
    def test_renumbering_is_no_difference(self) -> None:
        self.assertEqual(diff(board(1, 2, 1), board(2, 1, 2)), [])

    def test_a_moved_reference_is(self) -> None:
        self.assertEqual(
            diff(board(1, 2, 1), board(1, 2, 2)),
            ["  /serial: clocks: &/cru 7 -> <0x2 0x7>"],  # the gpio has no #clock-cells
        )

    def test_a_disabled_node_and_the_reservations_are_compared(self) -> None:
        changed = board(1, 2, 1)
        changed["/serial"]["status"] = OKAY
        self.assertEqual(
            diff(board(1, 2, 1), changed),
            ['  /serial: status: "disabled" -> "okay"'],
        )
        a, b = Blob.read(blob(board(1, 2, 1))), Blob.read(blob(board(1, 2, 1), ((0x1000, 0x10),)))
        self.assertEqual(differences(a, b), ["reservations: [] -> [(4096, 16)]"])

    def test_an_unknown_property_holding_a_phandle_fails_safe(self) -> None:
        vendor = {"/serial": {"vendor,handle": cells(1)}}
        before = board(1, 2, 1) | {"/serial": board(1, 2, 1)["/serial"] | vendor["/serial"]}
        after = board(2, 1, 2) | {
            "/serial": board(2, 1, 2)["/serial"] | {"vendor,handle": cells(2)}
        }
        found = diff(before, after)
        self.assertEqual(found, ["  /serial: vendor,handle: <0x1> -> <0x2>"])
        self.assertEqual(diff(before, after, Dialect(bare=("vendor,handle",))), [])

    def test_an_interrupt_map_reads_its_parents(self) -> None:
        def mapped(intc: int, parent: int) -> Tree:
            pcie = {
                "#address-cells": cells(3),
                "#interrupt-cells": cells(1),
                "interrupt-map": cells(0, 0, 0, 1, parent, 0),
            }
            intc_node = {"#interrupt-cells": cells(1), "phandle": cells(intc)}
            return {"/": {}, "/intc": intc_node, "/pcie": pcie}

        self.assertEqual(diff(mapped(5, 5), mapped(9, 9)), [])
        self.assertNotEqual(diff(mapped(5, 5), mapped(9, 5)), [])  # the parent no node

    def test_an_unknown_reference_kept_its_number_but_lost_its_node(self) -> None:
        swapped = board(2, 1, 2)  # the cru and the gpio trade numbers
        before = board(1, 2, 1) | {"/vendor": {"vendor,handle": cells(1)}}
        after = swapped | {"/vendor": {"vendor,handle": cells(1)}}
        self.assertEqual(len(diff(before, after)), 1)
        self.assertIn("a phandle references.py does not know", diff(before, after)[0])
        self.assertEqual(diff(before, after, Dialect(numbers=("vendor,handle",))), [])

    def test_strings_compare_as_bytes_not_as_shown(self) -> None:
        a = board(1, 2, 1) | {"/vendor": {"names": b"a\0b\0"}}
        b = board(1, 2, 1) | {"/vendor": {"names": b'a", "b\0'}}
        self.assertEqual(len(diff(a, b)), 1)

    def test_the_overlay_bookkeeping_is_bytes(self) -> None:
        def fixups(offset: int) -> Tree:
            return board(1, 2, 1) | {"/__local_fixups__": {"clocks": cells(offset)}}

        self.assertEqual(len(diff(fixups(4), fixups(8))), 1)

        def named(offset: int) -> Tree:
            return board(1, 2, 1) | {"/__local_fixups__": {"phandle": cells(offset)}}

        self.assertEqual(len(diff(named(4), named(8))), 1)  # a name, not a node's phandle

    def test_a_node_named_like_the_bookkeeping_is_not_it(self) -> None:
        before = board(1, 2, 1) | {"/__symbols__device": {"vendor,handle": cells(1)}}
        after = board(2, 1, 2) | {"/__symbols__device": {"vendor,handle": cells(1)}}
        self.assertEqual(len(diff(before, after)), 1)

    def test_the_memory_and_the_layout_are_compared(self) -> None:
        def memory(size: int) -> Tree:
            return board(1, 2, 1) | {"/memory@40000000": {"reg": cells(0x40000000, size)}}

        self.assertEqual(
            diff(memory(0x20000000), memory(0x10)),
            ["  /memory@40000000: reg: <0x40000000 0x20000000> -> <0x40000000 0x10>"],
        )


def pins(selected: bytes, extra: Tree | None = None) -> Tree:
    """A pin controller with two groups, a device selecting one, and a disabled device."""
    return {
        "/": {},
        "/pinctrl": {"#address-cells": cells(1)},
        "/pinctrl/uart-pins": {"pins": b"PH0\0", "phandle": cells(7)},
        "/pinctrl/spi-pins": {"pins": b"PC0\0", "phandle": cells(8)},
        "/serial@100": {"pinctrl-0": selected, "status": OKAY},
        "/spi@200": {"status": DISABLED, "num-cs": cells(1)},
        **(extra or {}),
    }


def viewed(a: Tree, b: Tree, omitted: tuple[str, ...] = ()) -> list[str]:
    return differences(Blob.read(blob(a)), Blob.read(blob(b)), Dialect(), Projection(omitted))


class ProjectionTest(unittest.TestCase):
    def test_what_a_view_leaves_out(self) -> None:
        ramoops = {
            "/reserved-memory": {},
            "/reserved-memory/ramoops@1000": {"reg": cells(0x1000, 4)},
        }
        board = pins(cells(7), ramoops)
        view = {
            k: v
            for k, v in pins(cells(7), {"/reserved-memory": {}}).items()
            if k != "/pinctrl/spi-pins"
        }
        view["/spi@200"] = {"status": DISABLED}  # a disabled device's contents
        view["/serial@100"] = {"pinctrl-0": cells(7)}  # a missing status is okay
        view["/i2c@300"] = {"status": DISABLED}  # a device the board lacks, off
        self.assertEqual(viewed(board, view, ("/reserved-memory/ramoops@1000",)), [])

    def test_what_a_view_must_keep(self) -> None:
        board = pins(cells(7))
        cases = {
            "a selected group": {k: v for k, v in board.items() if k != "/pinctrl/uart-pins"},
            "a device turned on": board | {"/spi@200": {"status": OKAY, "num-cs": cells(1)}},
            "another group selected": board | {"/serial@100": {"pinctrl-0": cells(8)}},
            "another failure reason": board | {"/spi@200": {"status": b"fail\0"}},
            # a device below the pin controller is no pin group, selected or not
            "a device below the controller": board | {"/pinctrl/device": {"compatible": b"test\0"}},
        }
        for name, view in cases.items():
            with self.subTest(name):
                self.assertNotEqual(viewed(board, view), [])

    def test_an_alias_s_unit_address_however_spelled(self) -> None:
        a = {"/": {}, "/aliases": {"serial0": b"/serial@0010\0"}, "/serial@0010": {}}
        b = {"/": {}, "/aliases": {"serial0": b"/serial@10\0"}, "/serial@10": {}}
        self.assertEqual(viewed(a, b), [])

    def test_a_hog_below_a_respelled_unit_address(self) -> None:
        def hogged(unit: str) -> Tree:
            gpio = {"gpio-controller": b"", "#gpio-cells": cells(2), "phandle": cells(1)}
            hog = {"gpio-hog": b"", "gpios": cells(1, 0)}
            return {"/": {}, f"/gpio@{unit}": gpio, f"/gpio@{unit}/hog": hog}

        self.assertEqual(viewed(hogged("00"), hogged("0")), [])

    def test_two_nodes_one_unit_address_are_refused(self) -> None:
        both = {"/": {}, "/dev@00": {"reg": cells(1)}, "/dev@0": {"reg": cells(2)}}
        with self.assertRaises(ValueError):
            viewed(both, both)

    def test_a_unit_address_however_spelled(self) -> None:
        a = {"/": {}, "/logo@00000000": {"reg": cells(0, 4)}}
        b = {"/": {}, "/logo@0": {"reg": cells(0, 4)}}
        self.assertEqual(viewed(a, b), [])
        self.assertNotEqual(differences(Blob.read(blob(a)), Blob.read(blob(b))), [])
        empty = {"/": {}, "/logo@1,": {"reg": cells(0, 4)}}  # an empty part, spelled as is
        self.assertEqual(viewed(empty, empty), [])

    def test_a_hog_s_pins_that_equal_phandles_are_pins(self) -> None:
        def hogged(cru: int, gpio: int) -> Tree:
            hog = {"gpio-hog": b"", "gpios": cells(1, 0)}
            return board(cru, gpio, cru) | {"/gpio/hog": hog}

        self.assertEqual(diff(hogged(1, 2), hogged(2, 1)), [])

    def test_exact_a_node_off_on_one_side_only_is_a_difference(self) -> None:
        off = board(1, 2, 1) | {"/off": {"status": DISABLED}}
        self.assertEqual(diff(board(1, 2, 1), off), ["+ /off"])


class MalformedTest(unittest.TestCase):
    def test_refused(self) -> None:
        good = blob(board(1, 2, 1))
        twice = blob(board(1, 2, 1) | {"/cru": {"phandle": cells(2)}})  # 2 is the gpio's too
        cases = {
            "short": good[:20],
            "old version": good[:20] + (16).to_bytes(4, "big") + good[24:],
            "past its end": good[:4] + (40).to_bytes(4, "big") + good[8:],
            "a phandle twice": twice,
            "a phandle not one cell": blob(board(1, 2, 1) | {"/dev": {"phandle": b"a"}}),
            "a token cut short": with_word(good, 36, word(good, 36) - 3),  # the struct block
            "a property header cut short": cut_in_header(good),
            "a name unterminated": with_word(good, 32, word(good, 32) - 1),  # strings one short
            "reservations past the end": with_word(good, 16, word(good, 4)),  # moved to the end
        }
        for name, data in cases.items():
            with self.subTest(name):
                with self.assertRaises(ValueError):
                    Blob.read(data)


if __name__ == "__main__":
    unittest.main()
