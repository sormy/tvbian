"""tools/dtcx/references.py: the one model of which properties hold phandles, its decoding, and
dtc's -P table in patches/dtc, which must agree with it."""

from __future__ import annotations

import re
import sys
import unittest
from dataclasses import dataclass, field
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "tools/dtcx"))
from references import BARE, REFERENCES, STANDARD, Dialect, interrupt_map  # noqa: E402

DTC_ENTRY = re.compile(r'^\+\t\{ "([^"]+)",\s+(?:"([^"]+)"|NULL) \},$', re.MULTILINE)


@dataclass(frozen=True)
class Value:
    value: str


@dataclass
class Provider:
    """A node, as far as decoding needs: its properties by name."""

    props: dict[str, str] = field(default_factory=dict)

    def prop(self, name: str) -> Value | None:
        return Value(self.props[name]) if name in self.props else None


# phandle 1 a clock provider with one cell, 2 a GPIO bank with two, 3 a node with no #-cells
TARGETS = {
    1: Provider({"#clock-cells": "<1>"}),
    2: Provider({"#gpio-cells": "<2>"}),
    3: Provider(),
}


def dtc_table() -> dict[str, str | None]:
    """The properties dtc's patches teach -P, with the provider's #-cells or None for bare."""
    text = "".join(p.read_text() for p in sorted((REPO / "patches/dtc").glob("*.patch")))
    return {name: cells or None for name, cells in DTC_ENTRY.findall(text)}


class DtcAgreesTest(unittest.TestCase):
    def test_dtc_s_table_is_in_the_model(self) -> None:
        table = dtc_table()
        self.assertGreater(len(table), 40)
        for name, cells in table.items():
            with self.subTest(name):
                self.assertIn(name, REFERENCES)
                model = REFERENCES[name]
                if cells is None:  # bare in dtc: the model may also fix an argument count
                    self.assertIsInstance(model, int)
                else:
                    self.assertEqual(model, cells)


class DecodeTest(unittest.TestCase):
    def test_layouts(self) -> None:
        cases: list[tuple[str, list[int], dict[int, int] | None]] = [
            ("clocks", [1, 5, 1, 6], {0: 1, 2: 1}),
            ("reset-gpios", [2, 7, 0], {0: 2}),
            ("reset_gpio", [2, 7, 0], {0: 2}),  # a vendor's spelling of the standard name
            ("extcon", [1, 3], {0: BARE, 1: BARE}),  # bare references, none an argument
            ("extcon", [3, 0], {0: BARE}),  # Allwinner's trailing 0, an empty entry
            ("gpios", [0, 2, 7, 0], {1: 2}),  # an empty entry, then a GPIO
            ("vcc-supply", [3], {0: BARE}),
            ("rockchip,pins", [1, 2, 1, 3], {3: 0}),
            ("bus-width", [3], {}),  # holds no phandle, whatever the number
            ("clocks", [99, 2, 1, 7], None),  # no node is 99: no resynchronising on the 2
            ("clocks", [3, 1], None),  # the provider has no #clock-cells
            ("clocks", [1], None),  # the entry cut short
            ("allwinner,sram", [3, 1], {0: 1}),  # the video engine's, with its argument
            ("allwinner,sram", [3], {0: BARE}),  # the thermal sensor's, alone
            ("rockchip,pins", [1, 2, 1, 99], None),  # no node is the config
            ("rockchip,pins", [1, 2, 1], None),  # not whole entries
        ]
        for name, flat, found in cases:
            with self.subTest(name=name, flat=flat):
                self.assertEqual(STANDARD.decode(name, flat, TARGETS), found)

    def test_a_hog_s_gpios_are_its_own_pins(self) -> None:
        self.assertEqual(STANDARD.decode("gpios", [2, 7, 0], TARGETS, hog=True), {})
        self.assertFalse(STANDARD.holds("gpios", hog=True))

    def test_a_vendor_name_is_a_reference_only_in_its_dialect(self) -> None:
        vendor = Dialect(gpio=frozenset({"clk_pin", "*_irq"}), bare=("act_handle",))
        for name in ("clk_pin", "WIFI,host_wake_irq", "act_handle"):
            with self.subTest(name):
                self.assertFalse(STANDARD.holds(name))
                self.assertTrue(vendor.holds(name))
        self.assertEqual(vendor.decode("clk_pin", [2, 19, 0], TARGETS), {0: 2})
        # a vendor's own reading of a standard name wins in its trees
        self.assertEqual(Dialect(bare=("pwms",)).decode("pwms", [1, 3], TARGETS), {0: 0, 1: 0})
        self.assertIsNone(STANDARD.decode("pwms", [1, 3], TARGETS))  # no #pwm-cells
        # both readings decode and disagree: a guess, so no reading
        one_cell = {**TARGETS, 4: Provider({"#pwm-cells": "<1>"})}
        self.assertIsNone(Dialect(bare=("pwms",)).decode("pwms", [4, 3], one_cell))
        for name in ("pinctrl-names", "rockchip,taskqueue-node", "gpio_chip_en"):
            with self.subTest(name):
                self.assertFalse(STANDARD.holds(name))


class InterruptMapTest(unittest.TestCase):
    def test_mappings(self) -> None:
        pcie = Provider({"#address-cells": "<1>", "#interrupt-cells": "<1>"})
        intc = {5: Provider({"#interrupt-cells": "<1>"})}
        cases: list[tuple[list[int], Provider, dict[int, int] | None]] = [
            ([0, 1, 5, 9, 0, 2, 5, 10], pcie, {2: 1, 6: 1}),
            ([0, 0, 1, 5, 99], pcie, None),  # a mapping cut short
            ([0], pcie, None),  # a child prefix cut short
            ([0, 1, 7, 9], pcie, None),  # no node is the parent
            ([0, 1, 5, 9], Provider({"#address-cells": "<1>"}), None),  # no #interrupt-cells
        ]
        for flat, node, found in cases:
            with self.subTest(flat=flat):
                self.assertEqual(interrupt_map(flat, node, intc), found)


if __name__ == "__main__":
    unittest.main()
