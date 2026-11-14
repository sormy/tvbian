"""tools/dtcx/semdiff.py: a new tree against the last proven one, by meaning, across layouts."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools/dtcx"))
from dts import Source, walk  # noqa: E402
from references import Dialect  # noqa: E402
from semdiff import Tree, report  # noqa: E402

PINS = Dialect(gpio=frozenset({"clk_pin"}))  # a vendor's GPIO property, as its base declares

# the vendor's layout: one-cell addresses, every block at the root
PROVEN = """/ {
\t#address-cells = <1>;
\t#size-cells = <1>;

\tclkc {
\t\tcompatible = "vendor,clkc";
\t\t#clock-cells = <1>;
\t\tphandle = <0x05>;
\t};

\tserial@c81004c0 {
\t\tcompatible = "amlogic,meson-gx-uart";
\t\treg = <0xc81004c0 0x18>;
\t\tclocks = <0x05 0x03>;
\t\tfifosize = <0x40>;
\t};

\tremote@c8100580 {
\t\tcompatible = "amlogic,meson-ir";
\t\treg = <0xc8100580 0x40>;
\t};
};
"""
# mainline's: two-cell addresses, the same blocks nested under a bus with ranges
NEW = """/ {
\t#address-cells = <2>;
\t#size-cells = <2>;

\tclkc {
\t\tcompatible = "vendor,clkc";
\t\t#clock-cells = <1>;
\t\tphandle = <0x09>;
\t};

\tsoc {
\t\tcompatible = "simple-bus";
\t\t#address-cells = <2>;
\t\t#size-cells = <2>;
\t\tranges;

\t\tbus@c8100000 {
\t\t\tcompatible = "simple-bus";
\t\t\treg = <0x0 0xc8100000 0x0 0x100000>;
\t\t\t#address-cells = <2>;
\t\t\t#size-cells = <2>;
\t\t\tranges = <0x0 0x0 0x0 0xc8100000 0x0 0x100000>;

\t\t\tserial@4c0 {
\t\t\t\tcompatible = "amlogic,meson-gx-uart";
\t\t\t\treg = <0x0 0x4c0 0x0 0x18>;
\t\t\t\tclocks = <0x09 0x03>;
\t\t\t\tfifo-size = <0x40>;
\t\t\t};

\t\t\tir@580 {
\t\t\t\tcompatible = "amlogic,meson-ir";
\t\t\t\treg = <0x0 0x580 0x0 0x40>;
\t\t\t\tstatus = "disabled";
\t\t\t};
\t\t};
\t};

\tcrypto@c883e000 {
\t\tcompatible = "amlogic,gxl-crypto";
\t\treg = <0x0 0xc883e000 0x0 0x24>;
\t};
};
"""


def tree(text: str) -> Tree:
    root = Source.parse(text).root
    return Tree(dict(walk(root)) | {"/": root})


class SemdiffTest(unittest.TestCase):
    def test_a_node_meets_its_counterpart_through_the_buses_ranges(self) -> None:
        new = tree(NEW)
        self.assertEqual(new.address("/soc/bus@c8100000/serial@4c0"), 0xC81004C0)
        lines = report(tree(PROVEN), new)
        self.assertFalse([line for line in lines if "serial" in line and "enabled" in line])

    def test_a_renumbered_phandle_is_no_difference(self) -> None:
        lines = report(tree(PROVEN), tree(NEW))
        self.assertFalse([line for line in lines if "clocks" in line])

    def test_what_each_tree_alone_enables_and_each_property_change(self) -> None:
        lines = report(tree(PROVEN), tree(NEW))
        self.assertIn(
            "- enabled before only: /remote@c8100580 ['amlogic,meson-ir']"
            " -> /soc/bus@c8100000/ir@580 (disabled)",
            lines,
        )
        self.assertIn("+ enabled now only: /crypto@c883e000 ['amlogic,gxl-crypto']", lines)
        self.assertIn("  /soc/bus@c8100000/serial@4c0: dropped fifosize = <0x40>", lines)
        self.assertIn("  /soc/bus@c8100000/serial@4c0: added fifo-size = <0x40>", lines)


SRAM = """/ {
\tsram: sram {
\t\tcompatible = "mmio-sram";
\t\t#clock-cells = <0>;
\t\tphandle = <%(sram)s>;
\t};

\tgic {
\t\tcompatible = "arm,gic-400";
\t\t#clock-cells = <0>;
\t\tphandle = <%(gic)s>;
\t};

\tvideo-codec {
\t\tcompatible = "allwinner,sun50i-h616-video-engine";
\t\tallwinner,sram = <%(sram)s 0x01>;
\t\tclocks = <%(gic)s %(gic)s>;
\t\tclock-names = %(names)s;
\t};
};
"""


class ReferenceTest(unittest.TestCase):
    def test_a_fixed_argument_is_no_phandle(self) -> None:
        old = tree(SRAM % {"sram": "0x05", "gic": "0x01", "names": '"bus", "mod"'})
        new = tree(SRAM % {"sram": "0x07", "gic": "0x02", "names": '"bus", "mod"'})
        self.assertEqual(
            new.value("/video-codec", "allwinner,sram", "<0x07 0x01>", str), "&/sram 1"
        )
        self.assertEqual(report(old, new), [])

    def test_a_named_list_compares_by_name_not_order(self) -> None:
        old = tree(SRAM % {"sram": "0x05", "gic": "0x01", "names": '"bus", "mod"'})
        swapped = SRAM.replace("<%(gic)s %(gic)s>", "<%(gic)s %(sram)s>")
        new = tree(swapped % {"sram": "0x05", "gic": "0x01", "names": '"mod", "bus"'})
        self.assertEqual(
            report(old, new),
            ["  /video-codec: clocks: bus: &/gic, mod: &/gic -> bus: &/sram, mod: &/gic"],
        )

    def test_a_clock_swapped_under_its_unchanged_name_is_a_difference(self) -> None:
        mixed = SRAM.replace("<%(gic)s %(gic)s>", "<%(gic)s %(sram)s>")
        swapped = SRAM.replace("<%(gic)s %(gic)s>", "<%(sram)s %(gic)s>")
        names = {"sram": "0x05", "gic": "0x01", "names": '"bus", "mod"'}
        self.assertNotEqual(report(tree(mixed % names), tree(swapped % names)), [])

    def test_a_list_named_in_one_tree_only_is_the_same_list(self) -> None:
        named = tree(SRAM % {"sram": "0x05", "gic": "0x01", "names": '"bus", "mod"'})
        unnamed = tree(
            SRAM.replace("\t\tclock-names = %(names)s;\n", "") % {"sram": "5", "gic": "1"}
        )
        self.assertFalse([line for line in report(named, unnamed) if "clocks" in line])


CHILDREN = """/ {
\tcompatible = "test,board";

\tpinctrl {
\t\tcompatible = "test,pinctrl";
\t\tgpio-controller;

\t\tuart-pins {
\t\t\tpins = "PH0";
\t\t\tphandle = <0x01>;
\t\t};

\t\tspare-pins {
\t\t\tpins = "PH1";
\t\t\tphandle = <0x02>;
\t\t};
\t};

\tserial {
\t\tcompatible = "snps,dw-apb-uart";
\t\tpinctrl-0 = <0x01>;
\t};

\tdisabled-serial {
\t\tcompatible = "snps,dw-apb-uart";
\t\tpinctrl-0 = <0x02>;
\t\tstatus = "disabled";
\t};

\tleds {
\t\tcompatible = "gpio-leds";

\t\tled-0 {
\t\t\tlabel = "power";
\t\t};
\t};
};
"""


class ChildrenTest(unittest.TestCase):
    def test_a_child_described_by_its_parent_is_compared(self) -> None:
        old = tree(CHILDREN)
        new = tree(CHILDREN.replace('\t\tled-0 {\n\t\t\tlabel = "power";\n\t\t};\n', ""))
        self.assertEqual(report(old, new), ["- dropped node: /leds/led-0"])
        relabelled = tree(CHILDREN.replace('"power"', '"standby"'))
        self.assertEqual(report(old, relabelled), ['  /leds/led-0: label: "power" -> "standby"'])

    def test_a_pin_group_no_enabled_device_selects_describes_nothing(self) -> None:
        old = tree(CHILDREN)
        new = tree(
            CHILDREN.replace(
                '\t\tspare-pins {\n\t\t\tpins = "PH1";', '\t\tspare-pins {\n\t\t\tpins = "PH2";'
            )
        )
        self.assertEqual(report(old, new), [])
        unselected = tree(CHILDREN.replace("\t\tpinctrl-0 = <0x01>;\n", ""))
        self.assertEqual(
            report(old, unselected),
            [
                "- dropped node: /pinctrl/uart-pins",
                "  /serial: dropped pinctrl-0 = &/pinctrl/uart-pins",
            ],
        )

    def test_a_hog_on_a_pin_controller_is_compared(self) -> None:
        hogged = CHILDREN.replace(
            "\t\tspare-pins {",
            "\t\treset-hog {\n\t\t\tgpio-hog;\n\t\t\toutput-high;\n\t\t};\n\n\t\tspare-pins {",
        )
        self.assertEqual(
            report(tree(hogged), tree(CHILDREN)), ["- dropped node: /pinctrl/reset-hog"]
        )


REGULATORS = """/ {
\tcompatible = "test,board";

\tvcc5v {
\t\tcompatible = "regulator-fixed";
\t\tregulator-name = "vcc-5v";
\t};

\tusb1-vbus {
\t\tcompatible = "regulator-fixed";
\t\tregulator-name = "usb1-vbus";
\t};
};
"""


class PairingTest(unittest.TestCase):
    def test_a_node_gone_is_not_paired_with_its_compatible_s_last_one(self) -> None:
        old = tree(REGULATORS)
        new = tree(
            REGULATORS.replace(
                '\tvcc5v {\n\t\tcompatible = "regulator-fixed";\n\t\tregulator-name = "vcc-5v";\n\t};\n\n',
                "",
            )
        )
        self.assertEqual(
            report(old, new), ["- enabled before only: /vcc5v ['regulator-fixed'] (no counterpart)"]
        )


VENDOR_REFERENCES = """/ {
\tcompatible = "test,board";

\tgpio4: gpio {
\t\tcompatible = "rockchip,gpio-bank";
\t\tgpio-controller;
\t\t#gpio-cells = <2>;
\t\tphandle = <0x84>;
\t};

\tgrf {
\t\tcompatible = "rockchip,rk3528-ioc-grf";
\t\tphandle = <%(grf)s>;
\t};

\tfd655 {
\t\tcompatible = "rockchip,fd655_dev";
\t\tclk_pin = <%(pin)s 0x13 0x00>;
\t};
};
"""


class VendorReferenceTest(unittest.TestCase):
    def test_a_pin_property_reads_as_the_gpio_it_names(self) -> None:
        proven = tree(VENDOR_REFERENCES % {"grf": "0x85", "pin": "0x84"})
        self.assertEqual(
            proven.value("/fd655", "clk_pin", "<0x84 0x13 0x00>", str, PINS), "&/gpio 19 0"
        )
        # dtc numbered the grf as the factory numbered gpio4: the same number, another node
        renumbered = tree(VENDOR_REFERENCES % {"grf": "0x84", "pin": "0x84"})
        gpio = renumbered.nodes["/gpio"]
        gpio.props = [p for p in gpio.props if p.name != "phandle"]
        # the grf has no #gpio-cells, so the value no longer decodes: numbers
        self.assertEqual(
            report(proven, renumbered, dialect=PINS),
            ["  /fd655: clk_pin: &/gpio 19 0 -> 132, 19, 0"],
        )

    def test_a_rockchip_pin_entry_reads_its_config_as_a_node(self) -> None:
        pins = (
            "/ {\n\tpcfg_a {\n\t\tphandle = <%s>;\n\t};\n\n\tpcfg_b {\n\t\tphandle = <%s>;"
            "\n\t};\n};\n"
        )
        old, new = tree(pins % ("0x01", "0x02")), tree(pins % ("0x02", "0x01"))
        # bank 1 and function 1 are numbers, not the phandle 1; the fourth cell is
        self.assertEqual(old.value("/x", "rockchip,pins", "<1 2 1 0x01>", str), "1, 2, 1, &/pcfg_a")
        self.assertEqual(new.value("/x", "rockchip,pins", "<1 2 1 0x02>", str), "1, 2, 1, &/pcfg_a")


ROCKCHIP_PINS = """/ {
\tcompatible = "test,board";

\tpinctrl {
\t\tcompatible = "rockchip,rk3528-pinctrl";

\t\thdmi {
\t\t\thdmi-pins {
\t\t\t\trockchip,pins = <0 %(pin)s 1 0x09>;
\t\t\t\tphandle = <0x01>;
\t\t\t};
\t\t};

\t\tpcfg-pull-none {
\t\t\tbias-disable;
\t\t\tphandle = <0x09>;
\t\t};
\t};

\thdmi {
\t\tcompatible = "rockchip,rk3528-dw-hdmi";
\t\tpinctrl-0 = <0x01>;
\t\tstatus = "%(status)s";
\t};
};
"""


class PinGroupTest(unittest.TestCase):
    def test_a_selected_group_s_pin_configuration_is_compared(self) -> None:
        old = tree(ROCKCHIP_PINS % {"pin": "3", "status": "okay"})
        pulled = ROCKCHIP_PINS.replace("\t\t\tbias-disable;", "\t\t\tbias-pull-up;")
        new = tree(pulled % {"pin": "3", "status": "okay"})
        self.assertNotEqual(report(old, new), [])

    def test_a_selected_group_below_a_function_node_is_compared(self) -> None:
        old = tree(ROCKCHIP_PINS % {"pin": "3", "status": "okay"})
        new = tree(ROCKCHIP_PINS % {"pin": "4", "status": "okay"})
        self.assertEqual(
            report(old, new),
            [
                "  /pinctrl/hdmi/hdmi-pins: rockchip,pins: 0, 3, 1, &/pinctrl/pcfg-pull-none"
                " -> 0, 4, 1, &/pinctrl/pcfg-pull-none"
            ],
        )

    def test_a_group_only_a_disabled_device_selects_is_not(self) -> None:
        old = tree(ROCKCHIP_PINS % {"pin": "3", "status": "disabled"})
        new = tree(ROCKCHIP_PINS % {"pin": "4", "status": "disabled"})
        self.assertEqual(report(old, new), [])


ALIASED = """/ {
\tcompatible = "test,board";
\t#address-cells = <1>;
\t#size-cells = <1>;

\taliases {
\t\tserial0 = "%(alias)s";
\t};

\t%(bus)s {
\t\tcompatible = "simple-bus";
\t\t#address-cells = <1>;
\t\t#size-cells = <1>;
\t\tranges;

\t\tserial@ff9f0000 {
\t\t\tcompatible = "snps,dw-apb-uart";
\t\t\treg = <0xff9f0000 0x100>;
\t\t};
\t};
};
"""


class AliasTest(unittest.TestCase):
    def test_an_alias_reads_as_the_node_its_path_names(self) -> None:
        old = tree(ALIASED % {"bus": "bus", "alias": "/bus/serial@ff9f0000"})
        moved = tree(ALIASED % {"bus": "soc", "alias": "/soc/serial@ff9f0000"})
        self.assertEqual(report(old, moved), [])
        elsewhere = tree(ALIASED % {"bus": "soc", "alias": "/soc"})
        self.assertEqual(
            report(old, elsewhere),
            ["  /aliases: serial0: &/soc/serial@ff9f0000 -> &/soc"],
        )


OPP_TABLES = """/ {
\t#address-cells = <1>;
\t#size-cells = <1>;

\tcpu {
\t\tcompatible = "arm,cortex-a53";
\t\toperating-points-v2 = <%s>;
\t};

\tcpu-opp {
\t\tcompatible = "operating-points-v2";
\t\tphandle = <0x01>;
\t};

\tdmc-opp {
\t\tcompatible = "operating-points-v2";
\t\tphandle = <0x02>;
\t};

\tmemory@40000000 {
\t\tdevice_type = "memory";
\t\treg = <0x40000000 %s>;
\t};
};
"""


class SameLayoutTest(unittest.TestCase):
    def test_a_reference_to_a_look_alike_node_is_a_difference(self) -> None:
        old, new = tree(OPP_TABLES % ("0x01", "0x20000000")), tree(
            OPP_TABLES % ("0x02", "0x20000000")
        )
        self.assertEqual(report(old, new), ["  /cpu: operating-points-v2: &/cpu-opp -> &/dmc-opp"])

    def test_a_child_at_its_parent_s_base_meets_the_child(self) -> None:
        sram = """/ {
\t#address-cells = <1>;
\t#size-cells = <1>;

\tsram@fe480000 {
\t\tcompatible = "mmio-sram";
\t\treg = <0xfe480000 0xc000>;
\t\t#address-cells = <1>;
\t\t#size-cells = <1>;
\t\tranges = <0x00 0xfe480000 0xc000>;

\t\tvdec-sram@0 {
\t\t\treg = <0x00 0xc000>;
\t\t\tphandle = <0x30>;
\t\t};
\t};

\tvdec {
\t\tcompatible = "rockchip,rkv-decoder";
\t\trockchip,sram = <0x30>;
\t};
};
"""
        self.assertEqual(report(tree(sram), tree(sram)), [])

    def test_a_deleted_look_alike_is_reported(self) -> None:
        device = '\t{0}@100 {{\n\t\tcompatible = "test,device";\n\t\treg = <0x100 0x10>;\n\t}};\n'
        both = "/ {\n\t#address-cells = <1>;\n\t#size-cells = <1>;\n%s};\n"
        old = tree(both % (device.format("a") + device.format("b")))
        new = tree(both % device.format("a"))
        lost = ["- enabled before only: /b@100 ['test,device'] (no counterpart)"]
        self.assertEqual(report(old, new), lost)

    def test_a_reference_into_a_moved_parent_meets_its_child(self) -> None:
        leds = """/ {
\t%s {
\t\tcompatible = "gpio-leds";

\t\tled-0 {
\t\t\tlabel = "power";
\t\t\tphandle = <0x01>;
\t\t};
\t};

\tother-leds {
\t\tcompatible = "test,leds";

\t\tled-0 {
\t\t\tlabel = "other";
\t\t};
\t};

\ttrigger {
\t\tcompatible = "test,trigger";
\t\tphy-handle = <0x01>;
\t};
};
"""
        self.assertEqual(report(tree(leds % "old-leds"), tree(leds % "new-leds")), [])

    def test_the_likest_old_node_keeps_a_renamed_survivor(self) -> None:
        device = '\t{0}@100 {{\n\t\tcompatible = "{1}";\n\t\treg = <0x100 0x10>;\n\t}};\n'
        layout = "/ {\n\t#address-cells = <1>;\n\t#size-cells = <1>;\n%s};\n"
        old = tree(layout % (device.format("a", "test,other") + device.format("b", "test,dev")))
        new = tree(layout % device.format("c", "test,dev"))
        self.assertEqual(
            report(old, new), ["- enabled before only: /a@100 ['test,other'] (no counterpart)"]
        )


class AddressTest(unittest.TestCase):
    def test_a_node_met_by_path_with_its_registers_moved(self) -> None:
        layout = "/ {\n\t#address-cells = <1>;\n\t#size-cells = <1>;\n%s};\n"
        uart = '\tserial@%s {\n\t\tcompatible = "test,uart";\n\t\treg = <0x%s 0x18>;\n\t};\n'
        old = tree(layout % (uart % ("4c0", "4c0")))
        new = tree(layout % (uart % ("4c0", "4d0")))
        self.assertEqual(report(old, new), ["  /serial@4c0: address: 0x4c0 -> 0x4d0"])


if __name__ == "__main__":
    unittest.main()
