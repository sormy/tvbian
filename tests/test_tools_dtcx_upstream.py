"""tools/dtcx/upstream.py: a board's final tree as its SoC dtsi included and only its changes."""

from __future__ import annotations

import sys
import tempfile
import unittest
from unittest import mock
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools/dtcx"))
from dts import Node, Prop, Source  # noqa: E402
from upstream import (
    written,  # noqa: E402
    Demand,
    Setting,
    Upstream,
    base_kernel,
    kernel_patches,
    needs,
    normal,
    pin_group,
    pinned,
    tidied,
)

SOC = """/ {
\tsoc {
\t\tcompatible = "simple-bus";

\t\tpio: pinctrl@300b000 {
\t\t\tcompatible = "test,pinctrl";
\t\t\tgpio-controller;

\t\t\tuart0_pins: uart0-pins {
\t\t\t\tpins = "PH0";
\t\t\t\tfunction = "uart0";
\t\t\t};
\t\t};

\t\tuart0: serial@5000000 {
\t\t\tcompatible = "snps,dw-apb-uart";
\t\t\tstatus = "disabled";
\t\t};

\t\tuart1: serial@5000400 {
\t\t\tcompatible = "snps,dw-apb-uart";
\t\t\tstatus = "disabled";
\t\t};

\t\tmmc0: mmc@4020000 {
\t\t\tcompatible = "test,mmc";
\t\t\tbus-width = <4>;
\t\t\tstatus = "disabled";

\t\t\tslot {
\t\t\t\treg = <0>;
\t\t\t};
\t\t};
\t};

\tunlabelled {
\t\tcompatible = "test,unlabelled";
\t\tstatus = "disabled";
\t};
};
"""
BOARD = """/dts-v1/;

#include <dt-bindings/gpio/gpio.h>

/ {
\tmodel = "Box";

\tsoc {
\t\tcompatible = "simple-bus";

\t\tpio: pinctrl@300b000 {
\t\t\tcompatible = "test,pinctrl";
\t\t\tgpio-controller;

\t\t\tuart0_pins: uart0-pins {
\t\t\t\tpins = "PH0";
\t\t\t\tfunction = "uart0";
\t\t\t};

\t\t\tuart1_pins: uart1-0-pins {
\t\t\t\tpins = "PG6";
\t\t\t\tfunction = "uart1";
\t\t\t};

\t\t\tspare_pins: spare-pins {
\t\t\t\tpins = "PG7";
\t\t\t\tfunction = "gpio_out";
\t\t\t};
\t\t};

\t\tuart0: serial@5000000 {
\t\t\tcompatible = "snps,dw-apb-uart";
\t\t\tpinctrl-0 = <&uart0_pins>;
\t\t};

\t\tuart1: serial@5000400 {
\t\t\tcompatible = "snps,dw-apb-uart";
\t\t\tpinctrl-0 = <&uart1_pins>;
\t\t\tstatus = "disabled";
\t\t};

\t\t/* the SD slot */
\t\tmmc0: mmc@4020000 {
\t\t\tcompatible = "test,mmc";
\t\t\tbus-width = <4>;
\t\t\tstatus = "okay";

\t\t\tslot {
\t\t\t\treg = <1>;
\t\t\t};
\t\t};
\t};

\tunlabelled {
\t\tcompatible = "test,unlabelled";
\t\tstatus = "okay";
\t};

\tleds {
\t\tcompatible = "gpio-leds";

\t\tled-0 {
\t\t\tfunction = "status";
\t\t\tgpios = <&pio 7 6 GPIO_ACTIVE_LOW>;
\t\t};
\t};
};
"""


def upstream() -> str:
    return Upstream(Source.parse(SOC).root, Source.parse(BOARD)).render(Setting("test.dtsi"))


class UpstreamTest(unittest.TestCase):
    def test_the_dtsi_is_included_with_the_board_s_headers(self) -> None:
        text = upstream()
        self.assertTrue(text.startswith("/dts-v1/;\n\n/*\n * Written by tools/dtcx/upstream.py"))
        self.assertIn(' */\n\n#include "test.dtsi"\n', text)
        self.assertIn("#include <dt-bindings/gpio/gpio.h>", text)

    def test_a_labelled_node_changes_by_its_label_with_its_comment(self) -> None:
        text = upstream()
        self.assertIn(
            '/* the SD slot */\n&mmc0 {\n\tstatus = "okay";\n\n\tslot {\n\t\treg = <1>;\n\t};\n};',
            text,
        )

    def test_an_unlabelled_node_changes_in_its_nearest_labelled_ancestor_s_block(self) -> None:
        text = upstream()
        self.assertIn('\tunlabelled {\n\t\tstatus = "okay";\n\t};', text)
        self.assertNotIn("&{", text)

    def test_a_node_the_board_enables_is_okay_not_a_deleted_status(self) -> None:
        text = upstream()
        self.assertIn('&uart0 {\n\tpinctrl-0 = <&uart0_pins>;\n\tstatus = "okay";\n};', text)
        self.assertNotIn("/delete-property/", text)

    def test_a_node_off_in_both_trees_is_not_written(self) -> None:
        self.assertNotIn("&uart1", upstream())

    def test_a_pin_group_nothing_written_selects_is_left_out(self) -> None:
        text = upstream()
        self.assertNotIn("uart1-0-pins", text)  # selected only by the disabled UART
        self.assertNotIn("spare-pins", text)
        self.assertNotIn("uart0-pins {", text)  # the dtsi's own

    def test_a_vendor_s_function_of_pin_groups_is_a_pin_group(self) -> None:
        root = Source.parse(
            "/ {\n\tpinctrl {\n\t\ti2s1 {\n\t\t\ti2s1_sclk: i2s1-sclk {\n"
            "\t\t\t\trockchip,pins = <4 1 3 &pcfg_pull_none>;\n\t\t\t};\n\t\t};\n\t};\n};\n"
        ).root
        pinctrl = root.children[0]
        self.assertTrue(pin_group(pinctrl.children[0], under_pinctrl=True))
        self.assertFalse(pin_group(pinctrl.children[0], under_pinctrl=False))

    def test_an_led_s_function_makes_it_no_pin_group(self) -> None:
        self.assertIn("led-0 {", upstream())

    def test_a_device_the_board_lacks_is_disabled_not_deleted(self) -> None:
        soc = SOC.replace(
            "\tunlabelled {",
            '\tspare: spare@1 {\n\t\tcompatible = "test,spare";\n\t};\n\n'
            '\tnotes {\n\t\tnote = "x";\n\t};\n\n\tunlabelled {',
        )
        text = Upstream(Source.parse(soc).root, Source.parse(BOARD)).render(Setting("test.dtsi"))
        self.assertIn('&spare {\n\tstatus = "disabled";\n};', text)
        self.assertIn("\t/delete-node/ notes;", text)
        self.assertNotIn("/delete-node/ spare", text)
        self.assertNotIn("uart1", text)  # off in the dtsi already: nothing to write

    def test_a_device_pointing_to_a_node_deleted_here_is_deleted_too(self) -> None:
        soc = SOC.replace(
            "\tunlabelled {",
            "\tnotes {\n\t\tout: endpoint {\n\t\t};\n\t};\n\n"
            '\tconnector {\n\t\tcompatible = "test,connector";\n\t\tremote = <&out>;\n\t};\n\n'
            "\tunlabelled {",
        )
        text = Upstream(Source.parse(soc).root, Source.parse(BOARD)).render(Setting("test.dtsi"))
        self.assertIn("\t/delete-node/ notes;", text)
        self.assertIn("\t/delete-node/ connector;", text)

    def test_the_patches_the_board_file_needs_beyond_its_base(self) -> None:
        driver = "--- a/drivers/test/bt.c\n+++ b/drivers/test/bt.c\n"
        binding = "--- a/Documentation/bindings/mmc.yaml\t2026-10-25\n+++ b/Documentation/bindings/mmc.yaml\n"
        with tempfile.TemporaryDirectory() as tmp:
            patches = {
                "dtsi.patch": '--- a/arch/x.dtsi\n+++ b/arch/x.dtsi\n+\tcompatible = "test,bt";\n',
                "bt.patch": driver + '+\t{ .compatible = "test,bt" },\n',
                "near.patch": driver + '+\t{ .compatible = "test,bt-2" },\n',
                "delay.patch": binding + "+  test,sample-delay:\n+    maximum: 63\n",
                "keymap.patch": binding + "+      - rc-test-box\n",
            }
            for name, body in patches.items():
                (Path(tmp) / name).write_text(body)
            demand = Demand(
                {"test,bt", "rc-test-box"}, {"test,sample-delay"}, {f"{tmp}/dtsi.patch": ["&mmc0"]}
            )
            self.assertEqual(
                needs(demand, [f"{tmp}/{n}" for n in patches]),
                [
                    f"{tmp}/dtsi.patch: &mmc0",  # a dtsi change, not the compatible it writes
                    f'{tmp}/bt.patch: "test,bt"',
                    f"{tmp}/delay.patch: test,sample-delay",
                    f'{tmp}/keymap.patch: "rc-test-box"',
                ],
            )

    def test_what_a_dtsi_patch_changes_that_the_view_keeps(self) -> None:
        before = Source.parse(SOC).root
        after = Source.parse(
            SOC.replace(
                "\t\t\tbus-width = <4>;", "\t\t\tbus-width = <4>;\n\t\t\tiommus = <&iommu>;"
            ).replace(
                "\tunlabelled {",
                '\tpwm: pwm@1 {\n\t\tcompatible = "test,pwm";\n\t};\n\n\tunlabelled {',
            )
        ).root
        board = BOARD.replace(
            "\t\t\tbus-width = <4>;\n\t\t\tstatus",
            "\t\t\tbus-width = <4>;\n\t\t\tiommus = <&iommu>;\n\t\t\tstatus",
        ).replace(
            "\tunlabelled {", '\tpwm: pwm@1 {\n\t\tcompatible = "test,pwm";\n\t};\n\n\tunlabelled {'
        )
        upstream = Upstream(after, Source.parse(board))
        demand = upstream.demand([("", before), ("p.patch", after)], upstream.render(Setting("t")))
        self.assertEqual(demand.kept, {"p.patch": ["&mmc0 iommus", "&pwm"]})
        self.assertEqual(
            demand.strings,
            {"test,mmc", "test,pinctrl", "test,pwm", "test,unlabelled", "snps,dw-apb-uart"},
        )
        empty = Node("/")
        self.assertEqual(upstream.kept(empty, after, set()), ["the dtsi, which it creates"])

    def test_the_kernel_s_patches_and_its_modules_only(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            conf = Path(tmp) / "kernel" / "box64.conf"
            conf.parent.mkdir()
            conf.write_text('PATCHES="\n  .:patches/a.patch\n"\n')
            modules = Path(tmp) / "modules"
            modules.mkdir()
            (modules / "wifi.conf").write_text(
                'KERNELS="box64 other"\nPATCHES="\n  .:patches/w.patch\n"\n'
            )
            (modules / "codec.conf").write_text(
                'KERNELS="other"\nPATCHES="\n  .:patches/c.patch\n"\n'
            )
            with mock.patch("upstream.REPO", Path(tmp)):
                self.assertEqual(
                    kernel_patches("kernel/box64.conf"), ["patches/a.patch", "patches/w.patch"]
                )

    def test_the_base_kernel_is_the_tree_the_dtsi_pins(self) -> None:
        sha = "77168c8d5ab82399f65a80e9f807b50ba37cf483"
        self.assertEqual(
            base_kernel(
                f"https://raw.githubusercontent.com/rockchip-linux/kernel/{sha}/arch/x.dts"
            ),
            "rockchip-linux/kernel at 77168c8d5ab8",
        )
        self.assertEqual(
            base_kernel("https://raw.githubusercontent.com/gregkh/linux/v7.3.4/arch/x.dtsi"),
            "gregkh/linux at v7.3.4",
        )

    def test_labels_alone_on_a_reference_are_one_line_each_under_a_comment(self) -> None:
        block = Node("&vdd_cpu", ["vdd_logic", "vdd_gpu"])
        self.assertEqual(
            written(block, {}),
            [
                "/* on this board vdd_cpu is also vdd_gpu and vdd_logic */",
                "vdd_gpu: &vdd_cpu { };",
                "vdd_logic: &vdd_cpu { };",
            ],
        )

    def test_status_comes_last(self) -> None:
        node = Node("x", props=[Prop.of("status", '"okay"'), Prop.of("bus-width", "<4>")])
        self.assertEqual([p.name for p in tidied(node, {}).props], ["bus-width", "status"])

    def test_each_sunxi_gpio_of_a_list_is_named(self) -> None:
        both = pinned(Prop.of("reset-gpios", "<&pio 6 18 GPIO_ACTIVE_LOW>, <&pio 6 19 0>"))
        self.assertTrue(both.statement[-1].endswith("; /* PG18, PG19 */"))
        flagged = pinned(Prop.of("cd-gpios", "<&pio 5 6 (GPIO_ACTIVE_LOW | GPIO_PULL_UP)>"))
        self.assertTrue(flagged.statement[-1].endswith("; /* PF6 */"))
        mixed = Prop.of("reset-gpios", "<&pio 6 18 GPIO_ACTIVE_LOW>, <&gpio 3 0>")
        self.assertEqual(pinned(mixed), mixed)

    def test_a_sunxi_gpio_is_named_by_its_pin(self) -> None:
        gpio = pinned(Prop.of("gpios", "<&pio 7 6 GPIO_ACTIVE_LOW>"))
        self.assertEqual(gpio.statement, ["gpios = <&pio 7 6 GPIO_ACTIVE_LOW>; /* PH6 */"])
        r_gpio = pinned(Prop.of("reset-gpios", "<&r_pio 0 2 GPIO_ACTIVE_HIGH>"))
        self.assertEqual(
            r_gpio.statement[-1], "reset-gpios = <&r_pio 0 2 GPIO_ACTIVE_HIGH>; /* PL2 */"
        )
        self.assertEqual(
            pinned(Prop.of("clocks", "<&pio 7 6>")).statement[-1], "clocks = <&pio 7 6>;"
        )

    def test_a_header_whose_names_are_not_used_is_not_included(self) -> None:
        board = BOARD.replace(
            "#include <dt-bindings/gpio/gpio.h>\n",
            "#include <dt-bindings/gpio/gpio.h>\n#include <dt-bindings/leds/common.h>\n",
        )
        defines = {
            "dt-bindings/gpio/gpio.h": {"GPIO_ACTIVE_LOW"},
            "dt-bindings/leds/common.h": {"LED_COLOR_ID_RED"},
        }
        text = Upstream(Source.parse(SOC).root, Source.parse(board)).render(
            Setting("test.dtsi", defines=defines)
        )
        self.assertIn("#include <dt-bindings/gpio/gpio.h>", text)
        self.assertNotIn("leds/common.h", text)

    def test_the_distribution_s_nodes_are_left_out_and_named(self) -> None:
        board = BOARD.replace(
            "\tleds {", '\tramoops@7e000000 {\n\t\tcompatible = "ramoops";\n\t};\n\n\tleds {'
        )
        upstream = Upstream(Source.parse(SOC).root, Source.parse(board))
        text = upstream.render(Setting("test.dtsi"))
        self.assertNotIn("ramoops@7e000000 {", text)
        self.assertIn(" *   /ramoops@7e000000", text)
        self.assertEqual(upstream.omitted, ["/ramoops@7e000000"])

    def test_a_value_as_dtc_compiles_it(self) -> None:
        self.assertEqual(normal("<&a 1>,\n\t\t <&b 2>"), normal("<&a 1 &b 2>"))


DOMAINS = """/ {
\tpower: power-controller {
\t\tpd_gpu@%(unit)s {
\t\t\treg = <%(reg)s>;
\t\t\tclocks = <%(clocks)s>;
\t\t};
\t};
};
"""


class SpellingTest(unittest.TestCase):
    def test_a_macro_unit_address_meets_its_number(self) -> None:
        soc = Source.parse(DOMAINS % {"unit": "RK_PD_GPU", "reg": "RK_PD_GPU", "clocks": "1"}).root
        same = Source.parse(DOMAINS % {"unit": "4", "reg": "0x04", "clocks": "1"})
        self.assertNotIn("&power", Upstream(soc, same, {"RK_PD_GPU": 4}).render(Setting("t")))
        changed = Source.parse(DOMAINS % {"unit": "4", "reg": "0x04", "clocks": "2"})
        text = Upstream(soc, changed, {"RK_PD_GPU": 4}).render(Setting("t"))
        self.assertIn("&power {\n\tpd_gpu@RK_PD_GPU {\n\t\tclocks = <2>;\n\t};\n};", text)
        self.assertNotIn("/delete-node/", text)


ALIASES = """/ {
\taliases {
\t\tethernet0 = %(ethernet0)s;
\t\tserial0 = %(serial0)s;
\t};

\tgmac0: ethernet@ffbd0000 {
\t\tcompatible = "test,gmac";
\t};

\tuart0: serial@ff9f0000 {
\t\tcompatible = "test,uart";
\t};

\tuart1: serial@ff9f8000 {
\t\tcompatible = "test,uart";
\t};
};
"""


class AliasTest(unittest.TestCase):
    def test_an_alias_by_path_is_the_alias_by_label(self) -> None:
        soc = Source.parse(ALIASES % {"ethernet0": "&gmac0", "serial0": "&uart0"}).root
        board = Source.parse(
            ALIASES % {"ethernet0": '"/ethernet@ffbd0000"', "serial0": '"/serial@ff9f8000"'}
        )
        text = Upstream(soc, board).render(Setting("t"))
        self.assertIn("\taliases {\n\t\tserial0 = &uart1;\n\t};", text)
        self.assertNotIn("ethernet0", text)


DISABLES = """/ {
\tpinctrl {
\t\tcompatible = "test,pinctrl";
\t\tgpio-controller;

\t\tir_pins: ir-pins {
\t\t\tpins = "%(ir_pin)s";
\t\t};
\t};

\tpwm3: pwm@ff00 {
\t\tcompatible = "test,pwm";
\t\tpinctrl-0 = <&ir_pins>;
\t\tremote_support_psci = <%(psci)s>;
%(status)s
\t\tir_key1 {
\t\t\trockchip,usercode = <%(usercode)s>;
\t\t};
%(extra)s\t};
};
"""
ENABLED_IR = {"ir_pin": "PH0", "psci": "0", "status": "", "usercode": "1", "extra": ""}


class DisabledTest(unittest.TestCase):
    def test_a_node_the_board_disables_is_only_disabled(self) -> None:
        soc = Source.parse(DISABLES % ENABLED_IR).root
        board = DISABLES % {
            "ir_pin": "PH1",
            "psci": "1",
            "status": '\t\tstatus = "disabled";\n',
            "usercode": "2",
            "extra": "\n\t\tir_key2 {\n\t\t\trockchip,usercode = <3>;\n\t\t};\n",
        }
        text = Upstream(soc, Source.parse(board)).render(Setting("t"))
        self.assertIn('&pwm3 {\n\tstatus = "disabled";\n};', text)
        for gone in ("psci", "ir_key", "usercode", "ir_pins", "ir-pins", "PH1"):
            self.assertNotIn(gone, text)

    def test_what_keeps_a_reference_whole_is_kept(self) -> None:
        soc = Source.parse(DISABLES % ENABLED_IR).root
        board = DISABLES % {
            **ENABLED_IR,
            "status": '\t\tstatus = "disabled";\n',
            "extra": "\n\t\tkey: ir_key2 {\n\t\t};\n",
        }
        board = board.replace(
            "};\n};\n",
            '};\n\n\tuser {\n\t\tcompatible = "test,user";\n' "\t\tkeys = <&key>;\n\t};\n};\n",
            1,
        )
        text = Upstream(soc, Source.parse(board)).render(Setting("t"))
        self.assertIn("\tkey: ir_key2 {\n\t};", text)


BUS = '/ {\n\tbus {\n\t\tcompatible = "test,bus";\n%s\t};\n};\n'
DISABLED_DEVICE = '\t\tdev {\n\t\t\tcompatible = "test,dev";\n\t\t\tstatus = "disabled";\n\t\t};\n'


class NormalTest(unittest.TestCase):
    def test_spacing_inside_a_string_is_the_string_s(self) -> None:
        self.assertNotEqual(normal('"a  b"'), normal('"a b"'))
        self.assertEqual(normal("<0x01>,  <2>"), normal("<1 2>"))
        self.assertEqual(normal('<1>, "a  b"'), '<1>, "a  b"')


class EmptyTest(unittest.TestCase):
    def test_a_node_left_with_nothing_of_its_own_goes(self) -> None:
        soc = Source.parse(BUS % "").root
        text = Upstream(soc, Source.parse(BUS % DISABLED_DEVICE)).render(Setting("t"))
        self.assertNotIn("bus", text)
        self.assertIn(" * Over mainline.", text)

    def test_a_node_the_board_adds_empty_stays(self) -> None:
        soc = Source.parse(BUS % "").root
        text = Upstream(soc, Source.parse(BUS % "\t\tqueue0 {\n\t\t};\n")).render(Setting("t"))
        self.assertIn("\t\tqueue0 {\n\t\t};", text)


class OrderTest(unittest.TestCase):
    def test_the_dtsi_s_own_first_standard_before_vendor_new_in_board_order(self) -> None:
        theirs = Node("x", props=[Prop.of("vendor,a", "<1>"), Prop.of("bus-width", "<4>")])
        mine = Node(
            "x",
            props=[
                Prop.of("vendor,new", "<1>"),
                Prop.of("vendor,a", "<2>"),
                Prop.of("new", "<1>"),
                Prop.of("bus-width", "<8>"),
                Prop("gone", ["/delete-property/ gone;"]),
            ],
            children=[Node("new-child"), Node("b"), Node("a")],
        )
        theirs.children = [Node("a"), Node("b")]
        tidy = tidied(mine, {id(mine): theirs})
        names = [p.name for p in tidy.props]
        self.assertEqual(names, ["gone", "bus-width", "vendor,a", "vendor,new", "new"])
        self.assertEqual([c.name for c in tidy.children], ["a", "b", "new-child"])

    def test_aliases_the_dtsi_has_go_by_name(self) -> None:
        theirs = Node("aliases", props=[Prop.of(n, "&x") for n in ("serial10", "serial2")])
        mine = Node("aliases", props=[Prop.of(n, "&y") for n in ("serial10", "serial2", "mmc0")])
        names = [p.name for p in tidied(mine, {id(mine): theirs}).props]
        self.assertEqual(names, ["serial2", "serial10", "mmc0"])


if __name__ == "__main__":
    unittest.main()
