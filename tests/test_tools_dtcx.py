"""tools/dtcx/dtcx.py's rendering, on hand-made trees and headers. Needs cc, for the header values:
./build.sh test runs it in the build container, and the runner has one."""

from __future__ import annotations

import re
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools/dtcx"))
from dtcx import (  # noqa: E402
    DEFINE,
    Base,
    Cells,
    Renderer,
    Tree,
    WIDTH,
    arithmetic,
    cells_in_strings,
    irq_type,
    joined,
    names_of,
    split,
)

HEADERS = {
    "dt-bindings/clock/test.h": "#define CLK_A 1\n#define CLK_B (CLK_A + 1)\n"
    "#define CLK_TWIN1 5\n#define CLK_TWIN2 5\n",
    "dt-bindings/input/linux-event-codes.h": "#define KEY_POWER 116\n"
    "#define KEY_X 50\n#define KEY_Y 50\n#define KEY_MUTE 113\n#define KEY_MIN_INTERESTING KEY_MUTE\n",
    "dt-bindings/gpio/meson.h": "#define GPIOAO_2 2\n#define GPIOZ_2 2\n#define GPIOX_9 88\n",
    "dt-bindings/suspend/test.h": "#define PM_A (1 << 0)\n#define PM_B (1 << 4)\n#define PM_C (1 << 4)\n",
}
MESON = """/dts-v1/;

/ {
\tpinctrl@14 {
\t\tcompatible = "amlogic,meson-gxl-aobus-pinctrl";

\t\tgpio_ao: bank@14 {
\t\t\tgpio-controller;
\t\t\t#gpio-cells = <2>;
\t\t\tphandle = <0x01>;
\t\t};
\t};

\tpinctrl@4b0 {
\t\tcompatible = "amlogic,meson-gxl-periphs-pinctrl";

\t\tgpio: bank@4b0 {
\t\t\tgpio-controller;
\t\t\t#gpio-cells = <2>;
\t\t\tphandle = <0x02>;
\t\t};
\t};

\tdev {
\t\tkey-gpios = <&gpio_ao 0x02 0x01>;
\t\treset-gpios = <&gpio 0x02 0x00>;
\t\tpower-gpios = <&gpio 0x58 0x00>;
\t\twake-gpios = <&gpio 0x64 0x00>;
\t};
};
"""
SUNXI = """/dts-v1/;

/ {
\tpio: pinctrl@300b000 {
\t\tgpio-controller;
\t\t#gpio-cells = <3>;
\t\tphandle = <0x01>;
\t};

\tdev {
\t\tcd-gpios = <&pio 0x05 0x06 0x11>;
\t\treset-gpios = <&pio 0x06 0x13 0x01>;
\t\tdrain-gpios = <&pio 0x02 0x07 0x06>;
\t\todd-gpios = <&pio 0x02 0x07 0x40>;
\t};
};
"""
TREE = """/dts-v1/;

/ {
\tinterrupt-parent = <&gic>;

\tgic: interrupt-controller@1 {
\t\tcompatible = "arm,gic-400";
\t\tphandle = <0x01>;
\t};

\tcru: clock-controller@2 {
\t\t#clock-cells = <1>;
\t\t#dma-cells = <1>;
\t\tphandle = <0x02>;
\t};

\tgpio0: gpio@3 {
\t\tgpio-controller;
\t\t#gpio-cells = <2>;
\t\tphandle = <0x03>;
\t};

\tdev@4 {
\t\tclocks = <&cru 0x01 &cru 0x02>;
\t\tclock-names = "a", "b";
\t\tassigned-clocks = <&cru 0x05>;
\t\tinterrupts = <0x00 0x20 0x04>;
\t\treset-gpios = <&gpio0 0x0a 0x01>;
\t\tstartup-delay-us = <0x64>;
\t\tlinux,code = <0x74>;
\t\tkey-twin = <0x32>;
\t\tdmas = <&cru 0x0c>;
\t\tmagic = <0x5242c300>;
\t\tbytes = "", "\\f5";
\t};

\taliases {
\t\tgpio0 = "/gpio@3";
\t\tunlabelled = "/dev@4";
\t};
};
"""


def rendered(
    tree: str = TREE,
    renderers: frozenset[str] = frozenset({"cells", "gpio-flags", "gic", "input-codes"}),
    prefixes: tuple[str, ...] = ("CLK_",),
    masks: dict[str, str] | None = None,
) -> tuple[dict[str, str], Renderer]:
    """Each property's rendered line, by name, and the renderer that made them: the clock
    controller's cells named from prefixes."""
    with tempfile.TemporaryDirectory() as tmp:
        for name, body in HEADERS.items():
            (Path(tmp) / name).parent.mkdir(parents=True, exist_ok=True)
            (Path(tmp) / name).write_text(body)
        base = Base("test", "test headers", "", headers=list(HEADERS))
        base.renderers = set(renderers)
        base.masks = masks or {}
        base.cells = [Cells("clock-controller@2", ["clocks", "assigned-clocks"], prefixes)]
        base.__dict__["root"] = Path(tmp)  # the headers here, not fetched
        renderer = Renderer(base, Tree(tree))
        text = renderer.render()
    lines = {
        line.strip().split(" = ")[0]: line.strip() for line in text.splitlines() if " = " in line
    }
    return lines, renderer


class ArithmeticTest(unittest.TestCase):
    def test_c_integer_expressions(self) -> None:
        cases: dict[str, int | None] = {
            "(1 << 3)": 8,
            "((25 + 25) + 14)": 64,
            "0x10UL": 16,
            "(2 | 4)": 6,
            "~0": 0xFFFFFFFF,
            "-1": 0xFFFFFFFF,
            "4 / 2": None,  # Python's division is not C's
            "7 % 2": None,
            "2 ** 3": None,
            "__import__('os')": None,
            "CLK_A": None,
            "1 +": None,
        }
        for expression, value in cases.items():
            with self.subTest(expression):
                self.assertEqual(arithmetic(expression), value)


class CellsInStringsTest(unittest.TestCase):
    def test_strings_that_are_no_text(self) -> None:
        for value, cells in [
            ('"", "\\f5"', "<0xc3500>"),
            ('"soc"', None),
            ('"pio", "rtc"', None),
            ('"\\x01"', None),
            ("<1>", None),
        ]:
            with self.subTest(value=value):
                self.assertEqual(cells_in_strings(value), cells)


class JoinedTest(unittest.TestCase):
    def test_a_property_over_lines_is_one_line(self) -> None:
        self.assertEqual(
            joined("\tclocks = <&a 1>,\n\t\t <&b 2>;\n"), "\tclocks = <&a 1>, <&b 2>;\n"
        )

    def test_a_path_reference_braces_do_not_end_it(self) -> None:
        text = "\tclocks = <&{/clock-controller@1} 1>,\n\t\t <&{/clock-controller@1} 2>;"
        self.assertEqual(
            joined(text), "\tclocks = <&{/clock-controller@1} 1>, <&{/clock-controller@1} 2>;"
        )

    def test_a_trailing_comment_ends_a_statement(self) -> None:
        text = '\tstatus = "okay"; /* why */\n\tnext = <1>;'
        self.assertEqual(joined(text), text)

    def test_nodes_and_comments_are_left_alone(self) -> None:
        text = "\tnode {\n\t\t/* a = b,\n\t\t   c */\n\t};"
        self.assertEqual(joined(text), text)


class SplitTest(unittest.TestCase):
    def test_entries(self) -> None:
        cases: list[tuple[str, list[str], str, int, list[str]]] = [
            ("by -names", ["&cru", "A", "&cru", "B"], "clocks", 2, ["&cru A", "&cru B"]),
            (
                "by -names, without references",
                ["0x0", "0x1000", "0x0", "0x2000"],
                "reg",
                2,
                ["0x0 0x1000", "0x0 0x2000"],
            ),
            ("by reference", ["&a", "1", "&b", "2", "3"], "pwms", 0, ["&a 1", "&b 2 3"]),
            (
                "by pin",
                ["1", "2", "3", "&p", "4", "5", "6", "&q"],
                "rockchip,pins",
                0,
                ["1 2 3 &p", "4 5 6 &q"],
            ),
            (
                "by interrupt",
                ["GIC_SPI", "1", "X", "GIC_PPI", "2", "Y"],
                "interrupts",
                0,
                ["GIC_SPI 1 X", "GIC_PPI 2 Y"],
            ),
            ("one value", ["1", "2"], "reg", 0, ["1 2"]),
        ]
        for name, tokens, prop, count, want in cases:
            with self.subTest(name):
                self.assertEqual(split(tokens, prop, count), want)

    def test_names_of(self) -> None:
        for prop, names in {
            "clocks": "clock-names",
            "mboxes": "mbox-names",
            "reg": "reg-names",
        }.items():
            with self.subTest(prop):
                self.assertEqual(names_of(prop), names)


class IrqTypeTest(unittest.TestCase):
    def test_cells(self) -> None:
        cases: dict[int | None, str] = {
            4: "IRQ_TYPE_LEVEL_HIGH",
            8: "IRQ_TYPE_LEVEL_LOW",
            0xF04: "(GIC_CPU_MASK_SIMPLE(4) | IRQ_TYPE_LEVEL_HIGH)",
            0x504: "",  # not a run of CPUs from 0
            3: "",
            0x10004: "",
            None: "",
        }
        for cell, name in cases.items():
            with self.subTest(cell):
                self.assertEqual(irq_type(cell), name)


class TreeTest(unittest.TestCase):
    def test_paths_labels_and_the_interrupt_parent(self) -> None:
        tree = Tree(TREE)
        self.assertIn("/dev@4", tree.props)
        self.assertEqual(tree.labels["/gpio@3"], ["gpio0"])
        self.assertEqual(tree.references("/gpio@3"), {"&gpio0", "&{/gpio@3}"})
        self.assertEqual(tree.interrupt_parent("/dev@4"), "&gic")


class RendererTest(unittest.TestCase):
    def test_rendered_properties(self) -> None:
        lines, _ = rendered()
        cases = {
            "clocks": "clocks = <&cru CLK_A>, <&cru CLK_B>;",
            "interrupts": "interrupts = <GIC_SPI 32 IRQ_TYPE_LEVEL_HIGH>;",
            "reset-gpios": "reset-gpios = <&gpio0 10 GPIO_ACTIVE_LOW>;",
            "startup-delay-us": "startup-delay-us = <100>;",
            "linux,code": "linux,code = <KEY_POWER>;",
            "dmas": "dmas = <&cru 12>;",
            "magic": "magic = <0x5242c300>;",
            "bytes": "bytes = <0xc3500>;",
            "gpio0": "gpio0 = &gpio0;",
            "unlabelled": 'unlabelled = "/dev@4";',
        }
        for prop, line in cases.items():
            with self.subTest(prop):
                self.assertEqual(lines[prop], line)

    def test_a_key_table_names_its_codes_and_packs_whole_pairs(self) -> None:
        pairs = " ".join(f"0x{n:02x} 0x74" for n in range(20))
        tree = f"/ {{\n\tir {{\n\t\trockchip,key_table = <{pairs}>;\n\t}};\n}};\n"
        _, renderer = rendered(tree)
        lines = renderer.render().splitlines()
        first = next(i for i, line in enumerate(lines) if "rockchip,key_table" in line)
        last = next(i for i in range(first, len(lines)) if lines[i].endswith(";"))
        table = lines[first : last + 1]
        self.assertGreater(len(table), 1)
        for line in table:
            self.assertLessEqual(len(line.expandtabs(8)), WIDTH)
        entries = re.findall(r"<([^<>]*)>", "\n".join(table))
        self.assertEqual(entries, [f"0x{n:02x} KEY_POWER" for n in range(20)])

    def test_a_value_with_two_names_stays_a_number_and_is_counted(self) -> None:
        lines, renderer = rendered()
        self.assertEqual(lines["assigned-clocks"], "assigned-clocks = <&cru 5>;")
        self.assertTrue(any("assigned-clocks" in u for u in renderer.unnamed))

    def test_a_key_code_with_two_names_is_counted(self) -> None:
        tree = TREE.replace("linux,code = <0x74>", "linux,code = <0x32>")
        _, renderer = rendered(tree)
        self.assertTrue(any("linux,code" in u for u in renderer.unnamed))

    def test_a_meson_pin_takes_its_controller_s_name(self) -> None:
        lines, renderer = rendered(MESON, frozenset({"gpio-flags", "meson-gpio"}))
        self.assertEqual(lines["key-gpios"], "key-gpios = <&gpio_ao GPIOAO_2 GPIO_ACTIVE_LOW>;")
        self.assertEqual(lines["reset-gpios"], "reset-gpios = <&gpio GPIOZ_2 GPIO_ACTIVE_HIGH>;")
        self.assertEqual(lines["power-gpios"], "power-gpios = <&gpio GPIOX_9 GPIO_ACTIVE_HIGH>;")
        self.assertEqual(lines["wake-gpios"], "wake-gpios = <&gpio 100 GPIO_ACTIVE_HIGH>;")
        self.assertTrue(any("wake-gpios 100" in u for u in renderer.unnamed))  # no such pin

    def test_a_sunxi_specifier_names_its_last_cell_and_ors_a_pull(self) -> None:
        lines, renderer = rendered(SUNXI, frozenset({"gpio-flags"}))
        cases = {
            "cd-gpios": "cd-gpios = <&pio 5 6 (GPIO_ACTIVE_LOW | GPIO_PULL_UP)>;",
            "reset-gpios": "reset-gpios = <&pio 6 19 GPIO_ACTIVE_LOW>;",
            "drain-gpios": "drain-gpios = <&pio 2 7 GPIO_OPEN_DRAIN>;",
            "odd-gpios": "odd-gpios = <&pio 2 7 64>;",
        }
        for prop, line in cases.items():
            with self.subTest(prop):
                self.assertEqual(lines[prop], line)
        self.assertEqual(
            [u for u in renderer.unnamed if "gpio flag" in u],
            ["/dev odd-gpios 0x40: no gpio flag name"],
        )

    def test_a_define_after_a_blank_line_is_its_own(self) -> None:
        header = "#ifndef G_H\n#define G_H\n\n#define CLK_RTC_1K 0\n#endif\n"
        self.assertEqual(DEFINE.findall(header), ["CLK_RTC_1K"])

    def test_gxlx_pins_as_read_off_the_box(self) -> None:
        header = Path(__file__).resolve().parents[1] / "tools/dtcx/headers/dt-bindings/gpio/gxlx.h"
        pins = dict(re.findall(r"#define\s+(\w+)\s+(\d+)", header.read_text()))
        box = {"GPIOX_6": "88", "GPIOX_17": "99", "GPIOX_18": "100", "GPIODV_24": "76"}
        self.assertEqual({name: pins[name] for name in box}, box)

    def test_a_header_limited_rule_names_only_that_header(self) -> None:
        only_input = ("dt-bindings/input/linux-event-codes.h", "")
        lines, _ = rendered(renderers=frozenset({"cells"}), prefixes=only_input)
        self.assertEqual(lines["clocks"], "clocks = <&cru 1>, <&cru 2>;")  # CLK_A, CLK_B unused


VENDOR = """/dts-v1/;

/ {
\tintc: interrupt-controller@1 {
\t\t#interrupt-cells = <1>;
\t\tphandle = <0x05>;
\t};

\tgpio0: gpio@3 {
\t\tcompatible = "rockchip,gpio-bank";
\t\tgpio-controller;
\t\t#gpio-cells = <2>;
\t\tphandle = <0x03>;
\t};

\texpander: gpio@4 {
\t\tgpio-controller;
\t\t#gpio-cells = <2>;
\t\tphandle = <0x04>;
\t};

\tits: msi@6 {
\t\t#address-cells = <1>;
\t\t#interrupt-cells = <1>;
\t\tphandle = <0x06>;
\t};

\tpcie@2 {
\t\t#address-cells = <3>;
\t\t#interrupt-cells = <1>;
\t\tinterrupt-map = <0x00 0x00 0x00 0x01 0x05 0x00 0x00 0x00 0x00 0x02 0x06 0x00 0x01>;
\t\treset-gpios = <&gpio0 0x0a 0x01>;
\t\tenable-gpios = <&expander 0x0a 0x01>;
\t\tlinux,code = <0x71>;
\t\twake = <0x11>;
\t\ttwin = <0x10>;
\t\tunnamed = <0x02>;
\t};
};
"""


class VendorRenderingTest(unittest.TestCase):
    def test_masks_pins_and_interrupt_maps(self) -> None:
        masks = {"wake": "PM_[AB]", "twin": "PM_*", "unnamed": "PM_[AB]"}
        renderers = frozenset({"gpio-flags", "rockchip-pins", "input-codes"})
        lines, renderer = rendered(VENDOR, renderers, masks=masks)
        cases = {
            "reset-gpios": "reset-gpios = <&gpio0 RK_PB2 GPIO_ACTIVE_LOW>;",
            "enable-gpios": "enable-gpios = <&expander 10 GPIO_ACTIVE_LOW>;",  # no Rockchip bank
            "linux,code": "linux,code = <KEY_MUTE>;",  # not the range marker sharing its value
            "wake": "wake = <(PM_A | PM_B)>;",
            "twin": "twin = <0x10>;",  # two names for the bit
            "unnamed": "unnamed = <0x02>;",  # no name for the bit
        }
        for prop, line in cases.items():
            with self.subTest(prop):
                self.assertEqual(lines[prop], line)
        # one mapping a group, however wide each parent's: one to a line, as they do not fit
        mappings = re.findall(r"<[^<>]*&\w+[^<>]*>", renderer.render())
        self.assertIn("<0x00 0x00 0x00 0x01 &intc 0x00>", mappings)
        self.assertIn("<0x00 0x00 0x00 0x02 &its 0x00 0x01>", mappings)

    def test_an_interrupt_map_to_no_known_parent_stays_as_read(self) -> None:
        tree = VENDOR.replace(
            "0x05 0x00 0x00 0x00 0x00 0x02 0x06", "0x09 0x00 0x00 0x00 0x00 0x02 0x09"
        )
        lines, _ = rendered(tree, frozenset())
        self.assertEqual(
            lines["interrupt-map"],
            "interrupt-map = <0x00 0x00 0x00 0x01 0x09 0x00 0x00 0x00 0x00 0x02 0x09 0x00 0x01>;",
        )


if __name__ == "__main__":
    unittest.main()
