"""tools/dtcx/translate.py, vocabulary.py, mainline.py, conversions.py and dts.py: a vendor tree
written in mainline's dialect, by a vocabulary, against a mainline SoC dtsi."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools/dtcx"))
from conversions import Conversions, gpio, speed_bins, voltage_bins  # noqa: E402
from dtcx import Base  # noqa: E402
from dts import Node, Prop, Source, compatibles, unit, walk  # noqa: E402
from mainline import MESON_FUNCTION, Mainline, amend, numeric_units, touching  # noqa: E402
from translate import (  # noqa: E402
    Report,
    rests,
    selected_functions,
    translate,
    unselected,
    unthrottled,
)
from vocabulary import Pattern, Vocabulary, fill  # noqa: E402

FACTORY = """/dts-v1/;

/ {
\tsoc@03000000 {
\t\tsdc0: sdmmc@04020000 {
\t\t\tcompatible = "allwinner,sunxi-mmc";
\t\t\t/* the vendor's own */
\t\t\tbus-width = <4>;
\t\t\tcd-gpios = <&pio 5 6 6 1 3 0xffffffff>;
\t\t\tpinctrl-names = "default", "sleep";
\t\t\tpinctrl-0 = <&sdc0_pins_a>;
\t\t\tpinctrl-1 = <&sdc0_pins_a>;
\t\t};

\t\tcodec: codec@0x05096000 {
\t\t\tcompatible = "allwinner,sunxi-codec";
\t\t\tlineout-vol = <31>;
\t\t};

\t\tcpudai: cpudai@0x05096000 {
\t\t\tcompatible = "allwinner,sunxi-cpudai";
\t\t\tdma-names = "tx";
\t\t};

\t\tpio: pinctrl@0300b000 {
\t\t\tsdc0_pins_a: sdc0@0 {
\t\t\t\tallwinner,pins = "PF0", "PF1";
\t\t\t\tallwinner,function = "sdc0";
\t\t\t\tallwinner,drive = <3>;
\t\t\t\tallwinner,pull = <1>;
\t\t\t};
\t\t};

\t\tvendor-only@0 {
\t\t\tcompatible = "allwinner,mystery";
\t\t};

\t\tbt {
\t\t\tcompatible = "allwinner,sunxi-bt";
\t\t};
\t};

\taliases {
\t\tmmc0 = "/soc@03000000/sdmmc@04020000";
\t\tdisp = "/soc@03000000/disp";
\t};

\topp_l_table {
\t\topp@480000000 {
\t\t\topp-supported-hw = <0x05>;
\t\t};
\t};
};
"""
MAINLINE = """/ {
\tsoc {
\t\tcompatible = "simple-bus";

\t\tmmc0: mmc@4020000 {
\t\t\tcompatible = "allwinner,sun50i-h616-mmc";
\t\t\treg = <0x04020000 0x1000>;
\t\t\tstatus = "disabled";
\t\t};

\t\tcodec: codec@5096000 {
\t\t\tcompatible = "allwinner,sun50i-h616-codec";
\t\t\tstatus = "disabled";
\t\t};

\t\tpio: pinctrl@300b000 {
\t\t\tcompatible = "allwinner,sun50i-h616-pinctrl";
\t\t};

\t\ttimer@3009000 {
\t\t\tcompatible = "allwinner,sun50i-h616-timer";
\t\t};
\t};

\topp-table-cpu {
\t\tcompatible = "allwinner,sun50i-h616-operating-points";
\t};
};
"""
VOCABULARY = r"""## a heading, which explains no rule
label sdc{n} mmc{n}
name opp_l_table opp-table-cpu
name opp opp-
value function sdc{n} mmc{n}
compatible allwinner,sunxi-mmc allwinner,sun50i-h616-mmc
compatible allwinner,sunxi-codec allwinner,sun50i-h616-codec
compatible allwinner,sunxi-cpudai allwinner,sun50i-h616-codec
# a test's question
node allwinner,sunxi-bt unresolved

prop compatible status #address-cells mainline
prop bus-width same
prop allwinner,pins as pins
prop allwinner,function as function
prop allwinner,drive scale drive-strength 10 10 0xffffffff:-
prop allwinner,pull flag 0:bias-disable 1:bias-pull-up
prop cd-gpios gpio low pull
prop pinctrl-names pinctrl

# read with pinctrl-names
prop pinctrl-{n} none

# a volume the codec driver exposes as an ALSA control
prop lineout-vol@allwinner,sunxi-codec none

prop dma-names same
prop mmc{n}@aliases disp@aliases alias
prop opp-supported-hw bits 2:4

# no mainline MMC driver selects it
state sleep none
"""


def base() -> Base:
    return Base("test", "mainline", "", headers=["dt-bindings/clock/test.h"])


def translated(factory: str = FACTORY, mainline: str = MAINLINE) -> tuple[dict[str, Node], Report]:
    source, report = translate(
        Source.parse(factory),
        Vocabulary.parse(VOCABULARY),
        Mainline(Source.parse(mainline)),
        base(),
    )
    return dict(walk(source.root)) | {"/": source.root}, report


def values(node: Node) -> dict[str, str]:
    return {p.name: p.value for p in node.props}


class SourceTest(unittest.TestCase):
    def test_a_tree_reads_back_as_written(self) -> None:
        self.assertEqual(Source.parse(FACTORY).render(), FACTORY)

    def test_comments_stay_with_what_follows(self) -> None:
        mmc = Source.parse(FACTORY).root.children[0].children[0]
        self.assertEqual(mmc.props[1].comments, ["/* the vendor's own */"])
        self.assertEqual(mmc.props[1].statement, ["bus-width = <4>;"])

    def test_a_comment_line_that_reads_as_a_statement_stays_a_comment(self) -> None:
        text = (
            "/ {\n\t/* 1.8 V signalling it never switches\n\t   to; 50 MHz */\n\tmax = <5>;\n};\n"
        )
        prop = Source.parse(text).root.props[0]
        self.assertEqual(prop.statement, ["max = <5>;"])
        self.assertEqual(len(prop.comments), 2)

    def test_a_node_opened_with_a_trailing_comment_is_a_node(self) -> None:
        root = Source.parse("/ {\n\taldo2 {\t/* 3.3V on headers */\n\t\ton;\n\t};\n};\n").root
        self.assertEqual([c.name for c in root.children], ["aldo2"])

    def test_a_node_on_one_line_is_a_node(self) -> None:
        root = Source.parse("/ {\n\tsetup {\n\t\tqueue0 {};\n\t\tq1: queue1 {};\n\t};\n};\n").root
        setup = root.children[0]
        self.assertEqual(
            [(c.name, c.labels) for c in setup.children], [("queue0", []), ("queue1", ["q1"])]
        )
        self.assertEqual(setup.props, [])

    def test_a_property_over_lines_is_one(self) -> None:
        root = Source.parse('/ {\n\tcompatible = "a",\n\t\t     "b"; /* two */\n};\n').root
        self.assertEqual(root.props[0].value, '"a", "b"')

    def test_a_property_of_one_line(self) -> None:
        self.assertEqual(Prop.of("ranges").statement, ["ranges;"])
        self.assertEqual(Prop.of("reg", "<1>").value, "<1>")

    def test_unit_addresses_as_mainline_writes_them(self) -> None:
        cases = (("a@04020000", "4020000"), ("a@0x0509", "509"), ("a@0", "0"), ("a", ""))
        for name, address in cases:
            self.assertEqual(unit(name), address, name)


class VocabularyTest(unittest.TestCase):
    def test_patterns(self) -> None:
        cases = [
            ("sdc{n}", "sdc2", ["2"]),
            ("{w}_thermal_zone", "gpu_thermal_zone", ["gpu"]),
            ("*_vol", "dcdc1_vol", []),
            ("opp@{n}-ab", "opp@480-ab", ["480"]),
            ("sdc{n}", "sdcx", None),
        ]
        for text, token, captures in cases:
            self.assertEqual(Pattern(text).match(token), captures, text)
        self.assertEqual(fill("{w}-thermal", ["gpu"]), "gpu-thermal")

    def test_rules_and_their_scopes(self) -> None:
        vocabulary = Vocabulary.parse(VOCABULARY)
        codec = next(r for r in vocabulary.props if r.text == "lineout-vol")
        self.assertEqual((codec.action, codec.scope), ("none", "allwinner,sunxi-codec"))
        self.assertIn("mmc{n}", [r.text for r in vocabulary.props if r.scope == "aliases"])

    def test_a_node_rule_keeps_its_unit_address(self) -> None:
        rule = Vocabulary.parse("# never run\nnode opp@{n}-ab none\n").nodes[0]
        self.assertEqual((rule.text, rule.scope), ("opp@{n}-ab", ""))

    def test_refusals(self) -> None:
        cases = [
            "prop foo none\n",
            "prop foo unresolved\n",
            "## a heading explains nothing\nprop foo none\n",
            "# a comment reaches no further than a blank line\n\nprop foo none\n",
            "prop foo\n",
            "bogus foo\n",
        ]
        for text in cases:
            with self.assertRaises(SystemExit, msg=text):
                Vocabulary.parse(text)

    def test_a_comment_explains_the_rules_below_it(self) -> None:
        vocabulary = Vocabulary.parse("# why\nprop foo none\nprop bar unresolved\n")
        self.assertEqual([r.action for r in vocabulary.props], ["none", "unresolved"])

    def test_pin_functions_take_a_source_a_line(self) -> None:
        vocabulary = Vocabulary.parse("pin-functions a.c\npin-functions b.c\n")
        self.assertEqual(vocabulary.pin_functions, ["a.c", "b.c"])


class MainlineTest(unittest.TestCase):
    def test_a_patch_s_part_for_one_file(self) -> None:
        body = "@@ -1 +1 @@\n-a\n+b\n"
        git = f"diff --git a/x b/x\n--- a/x\n+++ b/x\n{body}diff --git a/y b/y\n--- a/y\n+++ b/y\n{body}"
        plain = f"Subject: one\n---\n--- a/x\n+++ b/x\n{body}"
        self.assertEqual(touching(git, "x"), f"--- a/x\n+++ b/x\n{body}diff --git a/y b/y\n")
        self.assertEqual(touching(plain, "x"), f"--- a/x\n+++ b/x\n{body}")
        self.assertEqual(touching(git, "z"), "")

    def test_a_dtsi_moves_a_block_by_deleting_and_rewriting_it(self) -> None:
        dtsi = """#include "base.dtsi"

/delete-node/ &hdmi_tx;

/ {
\tsoc {
\t\thdmi_tx: hdmi-tx@da800000 {
\t\t\treg = <0x0 0xda800000 0x0 0x10000>;
\t\t};
\t};
};
"""
        source = Source.parse(dtsi)
        root = Source.parse(
            "/ {\n\tsoc {\n\t\thdmi_tx: hdmi-tx@c883a000 {\n\t\t};\n\t};\n};\n"
        ).root
        amend(root, source.overlays, "test")
        self.assertEqual([path for path, _ in walk(root)], ["/soc", "/soc/hdmi-tx@da800000"])
        self.assertIn("/delete-node/ &hdmi_tx;", source.render())

    def test_a_label_block_s_deletions_remove_what_they_name(self) -> None:
        dtsi = "/ {\n\tl: a {\n\t\tx = <1>;\n\t\ty = <2>;\n\t\tb {\n\t\t};\n\t};\n};\n"
        board = "&l {\n\t/delete-property/ x;\n\t/delete-node/ b;\n};\n"
        source = Source.parse(dtsi)
        amend(source.root, Source.parse(board).overlays, "board")
        a = source.root.children[0]
        self.assertEqual(([p.name for p in a.props], a.children), (["y"], []))


class TranslateTest(unittest.TestCase):
    def test_a_node_meets_its_counterpart_by_label_or_address(self) -> None:
        nodes, _ = translated()
        self.assertEqual(nodes["/soc/mmc@4020000"].labels, ["mmc0"])
        self.assertIn("/soc/codec@5096000", nodes)

    def test_a_label_naming_a_block_at_another_address_is_a_question(self) -> None:
        nodes, report = translated(FACTORY.replace("sdmmc@04020000", "sdmmc@04021000"))
        self.assertIn(("unresolved", "label at another address: /soc/mmc@4020000"), report.entries)
        self.assertEqual(values(nodes["/soc/mmc@4020000"])["status"], '"disabled"')

    def test_a_label_meets_its_block_where_the_vendor_s_registers_start(self) -> None:
        misnamed = FACTORY.replace(
            "sdmmc@04020000 {\n", "sdmmc@04020800 {\n\t\t\treg = <0x0 0x04020000 0x0 0x1000>;\n"
        )
        nodes, report = translated(misnamed)
        self.assertFalse([e for e in report.entries if "another address" in e[1]])
        self.assertEqual(values(nodes["/soc/mmc@4020000"])["status"], '"okay"')

    def test_an_opp_table_keeps_only_the_vendor_s_rows(self) -> None:
        mainline = MAINLINE.replace(
            '\t\tcompatible = "allwinner,sun50i-h616-operating-points";\n',
            '\t\tcompatible = "operating-points-v2";\n\n'
            "\t\topp-1800000000 {\n\t\t\topp-hz = /bits/ 64 <1800000000>;\n\t\t};\n",
        )
        nodes, _ = translated(mainline=mainline)
        self.assertIn("/opp-table-cpu/opp-480000000", nodes)
        self.assertNotIn("/opp-table-cpu/opp-1800000000", nodes)

    def test_an_opp_row_meets_only_a_row_of_its_own_table(self) -> None:
        mainline = MAINLINE.replace(
            '\t\tcompatible = "allwinner,sun50i-h616-operating-points";\n\t};\n',
            '\t\tcompatible = "operating-points-v2";\n\t};\n\n'
            '\topp-table-gpu {\n\t\tcompatible = "operating-points-v2";\n\n'
            "\t\topp-480000000 {\n\t\t\topp-hz = /bits/ 64 <480000000>;\n\t\t};\n\t};\n",
        )
        factory = FACTORY.replace("\t\topp@480000000 {", "\t\topp-480000000 {")  # no unit address
        nodes, _ = translated(factory, mainline)
        self.assertIn("/opp-table-cpu/opp-480000000", nodes)

    def test_mainline_completes_what_the_vendor_does_not_say(self) -> None:
        nodes, _ = translated()
        mmc = values(nodes["/soc/mmc@4020000"])
        self.assertEqual(mmc["reg"], "<0x04020000 0x1000>")
        self.assertEqual(mmc["status"], '"okay"')  # the vendor's: no status is okay
        self.assertIn("/soc/timer@3009000", nodes)

    def test_board_properties_converted(self) -> None:
        nodes, _ = translated()
        mmc = values(nodes["/soc/mmc@4020000"])
        self.assertEqual(mmc["bus-width"], "<4>")
        self.assertEqual(mmc["cd-gpios"], "<&pio 5 6 (GPIO_ACTIVE_LOW | GPIO_PULL_UP)>")
        self.assertEqual(mmc["pinctrl-names"], '"default"')
        self.assertEqual(mmc["pinctrl-0"], "<&sdc0_pins_a>")
        pins = values(nodes["/soc/pinctrl@300b000/sdc0@0"])
        expected = {
            "pins": '"PF0", "PF1"',
            "function": '"mmc0"',
            "drive-strength": "<40>",
            "bias-pull-up": "",
        }
        self.assertEqual(pins, expected)

    def test_a_state_its_vendor_named_is_renamed_by_its_rule(self) -> None:
        factory = FACTORY.replace(
            '\t\t\tpinctrl-names = "default", "sleep";\n\t\t\tpinctrl-0 = <&sdc0_pins_a>;',
            '\t\t\tpinctrl-names = "clk_cmd_pins", "all_pins";\n\t\t\tpinctrl-0 = <&clk_cmd>;',
        )
        self.assertIn("<&clk_cmd>", factory)
        vocabulary = (
            VOCABULARY + "state all_pins as default\n\n# never selected\nstate clk_cmd_pins none\n"
        )
        source, report = translate(
            Source.parse(factory),
            Vocabulary.parse(vocabulary),
            Mainline(Source.parse(MAINLINE)),
            base(),
        )
        mmc = values(dict(walk(source.root))["/soc/mmc@4020000"])
        self.assertEqual(mmc["pinctrl-names"], '"default"')
        self.assertEqual(mmc["pinctrl-0"], "<&sdc0_pins_a>")  # the vendor's pinctrl-1
        states = [e for e in report.entries if "pin state" in e[1]]
        self.assertEqual(states, [("none", "pin state clk_cmd_pins")])

    def test_a_used_block_takes_its_active_pins_as_default(self) -> None:
        factory = FACTORY.replace(
            '\t\t\tpinctrl-names = "default", "sleep";\n\t\t\tpinctrl-0 = <&sdc0_pins_a>;',
            '\t\t\tpinctrl-names = "active";\n\t\t\tpinctrl-0 = <&sdc0_pins_a>;',
        )
        vocabulary = VOCABULARY + "state active used-as default\n"
        for used in (True, False):
            with self.subTest(used=used):
                tree = (
                    factory.replace(
                        '\t\t\tdma-names = "tx";', '\t\t\tdma-names = "tx";\n\t\t\tmmc = <&sdc0>;'
                    )
                    if used
                    else factory
                )
                source, _ = translate(
                    Source.parse(tree),
                    Vocabulary.parse(vocabulary),
                    Mainline(Source.parse(MAINLINE)),
                    base(),
                )
                mmc = values(dict(walk(source.root))["/soc/mmc@4020000"])
                if used:
                    self.assertEqual(mmc["pinctrl-names"], '"default"')
                    self.assertEqual(mmc["pinctrl-0"], "<&sdc0_pins_a>")
                else:
                    self.assertNotIn("pinctrl-names", mmc)

    def test_a_drop_is_reported_only_on_an_enabled_node(self) -> None:
        for status, reported in (("okay", True), ("disabled", False)):
            with self.subTest(status=status):
                factory = FACTORY.replace(
                    "\t\t\tbus-width = <4>;",
                    f'\t\t\tbus-width = <4>;\n\t\t\tstatus = "{status}";',
                    1,
                )
                _, report = translated(factory)
                drops = [what for kind, what in report.entries if kind == "none"]
                self.assertEqual("pin state sleep" in drops, reported)

    def test_a_state_with_no_pin_groups_is_not_written(self) -> None:
        factory = FACTORY.replace("\t\t\tpinctrl-0 = <&sdc0_pins_a>;\n", "", 1)
        factory = factory.replace("\t\t\tpinctrl-1 = <&sdc0_pins_a>;\n", "", 1)
        self.assertNotIn("pinctrl-1", factory)
        nodes, _ = translated(factory)
        mmc = values(nodes["/soc/mmc@4020000"])
        self.assertNotIn("pinctrl-0", mmc)
        self.assertNotIn("pinctrl-names", mmc)

    def test_a_block_the_vendor_splits_is_one_node(self) -> None:
        nodes, _ = translated()
        codec = values(nodes["/soc/codec@5096000"])
        self.assertEqual(codec["dma-names"], '"tx"')
        self.assertNotIn("lineout-vol", codec)
        self.assertEqual(
            [p for p in nodes if "codec@" in p or "cpudai" in p], ["/soc/codec@5096000"]
        )

    def test_aliases_point_at_labels(self) -> None:
        by_label = FACTORY.replace('"/soc@03000000/sdmmc@04020000"', "&sdc0")
        for factory in (FACTORY, by_label):
            with self.subTest(by_label=factory is by_label):
                nodes, _ = translated(factory)
                self.assertEqual(values(nodes["/aliases"]), {"mmc0": "&mmc0"})

    def test_binding_constants_in_unit_addresses_meet_vendor_numbers(self) -> None:
        mainline = Source.parse(
            "/ {\n\tpower {\n\t\tpower-domain@PD_GPU {\n\t\t\treg = <PD_GPU>;\n\t\t};\n\t};\n};\n"
        )
        numeric_units(mainline, {"PD_GPU": 4})
        index = Mainline(mainline)
        self.assertEqual(index.child("/power", "pd_gpu", "4"), "/power/power-domain@4")

    def test_aliases_before_their_targets_are_preserved(self) -> None:
        for by_label in (False, True):
            factory = Source.parse(FACTORY)
            aliases = next(n for n in factory.root.children if n.name == "aliases")
            factory.root.children.remove(aliases)
            factory.root.children.insert(0, aliases)
            if by_label:
                aliases.props[0] = Prop.of("mmc0", "&sdc0")
            with self.subTest(by_label=by_label):
                nodes, _ = translated(factory.render())
                self.assertEqual(values(nodes["/aliases"]), {"mmc0": "&mmc0"})

    def test_speed_grade_bits_renumbered_and_the_rest_asked(self) -> None:
        nodes, report = translated()
        opp = values(nodes["/opp-table-cpu/opp-480000000"])
        self.assertEqual(opp["opp-supported-hw"], "<0x10>")
        self.assertIn(("unresolved", "property opp-supported-hw: vendor bit 0"), report.entries)

    def test_what_is_not_decided_is_reported_never_guessed(self) -> None:
        nodes, report = translated()
        self.assertIn(("unknown", "compatible allwinner,mystery"), report.entries)
        self.assertIn(("unresolved", "node allwinner,sunxi-bt"), report.entries)
        self.assertFalse([p for p in nodes if "vendor-only" in p or p.endswith("/bt")])

    def test_a_question_on_a_disabled_node_is_dormant(self) -> None:
        disabled = FACTORY.replace("\t\tbt {\n", '\t\tbt {\n\t\t\tstatus = "disabled";\n')
        _, report = translated(disabled)
        self.assertIn(("dormant", "node allwinner,sunxi-bt"), report.entries)


BOARD = """/dts-v1/;

/ {
\tsoc@03000000 {
\t\tpio: pinctrl@0300b000 {
\t\t\tuart1_pins_a: uart1_x@0 {
\t\t\t\tallwinner,pins = "PG6";
\t\t\t\tallwinner,function = "uart1";
\t\t\t\tallwinner,data = <1>;
\t\t\t};
\t\t};

\t\tgmac0: eth@05020000 {
\t\t\tcompatible = "allwinner,sunxi-gmac";
\t\t\tphy-mode;
\t\t};

\t\tcodec: codec@0x05096000 {
\t\t\tcompatible = "allwinner,sunxi-codec";
\t\t\tlineout_vol = <26>;
\t\t};

\t\treg_aldo1: aldo1 {
\t\t\tregulator-min-microvolt = <1800000>;
\t\t\tregulator-max-microvolt = <1800000>;
\t\t};

\t\treg_dcdc2: dcdc2 {
\t\t\tregulator-min-microvolt = <500000>;
\t\t\tregulator-max-microvolt = <1540000>;
\t\t};

\t\tgpio_bias {
\t\t\tpc_bias = <1800>;
\t\t};

\t\tkey_boot_recovery {
\t\t\trecovery_key_used = <1>;
\t\t\trecovery_key = <&pio 7 9 0 0xffffffff 0xffffffff 0xffffffff>;
\t\t};

\t\tbt: bt {
\t\t\tcompatible = "allwinner,sunxi-bt";
\t\t\tbt_rst_n = <&pio 6 19 1 0xffffffff 0xffffffff 0>;
\t\t};

\t\tbtlpm {
\t\t\tcompatible = "allwinner,sunxi-btlpm";
\t\t\tuart_index = <1>;
\t\t\tbt_wake = <&pio 6 17 1 0xffffffff 0xffffffff 1>;
\t\t\tbt_hostwake = <&pio 6 16 6 0xffffffff 0xffffffff 0>;
\t\t};
\t};

\tcpus {
\t\tcpu@0 {
\t\t\tdevice_type = "cpu";
\t\t\toperating-points-v2 = <&cpu_opp_table>;
\t\t\tcpu-supply = <&reg_dcdc2>;
\t\t};
\t};

\tcpu_opp_table: opp_l_table {
\t\topp@480000000-0 {
\t\t\topp-hz = /bits/ 64 <480000000>;
\t\t\topp-microvolt = <900000>;
\t\t\topp-supported-hw = <0x04>;
\t\t};

\t\topp@480000000-1 {
\t\t\topp-hz = /bits/ 64 <480000000>;
\t\t\topp-microvolt = <950000>;
\t\t\topp-supported-hw = <0x01>;
\t\t};
\t};

\taliases: aliases {
\t\tserial0 = "/soc@03000000/codec@0x05096000";
\t};
};
"""
BOARD_MAINLINE = """/ {
\tsoc {
\t\tpio: pinctrl@300b000 {
\t\t\tcompatible = "allwinner,sun50i-h616-pinctrl";
\t\t};

\t\tcodec: codec@5096000 {
\t\t\tcompatible = "allwinner,sun50i-h616-codec";
\t\t};

\t\tuart1: serial@5000400 {
\t\t\tcompatible = "snps,dw-apb-uart";
\t\t};
\t};
};
"""
BOARD_VOCABULARY = r"""pin-group allwinner,pins
label aliases -
name opp_l_table opp-table-cpu
name opp opp-
value function gmac{n} emac{n}
compatible allwinner,sunxi-gmac allwinner,sun50i-h616-emac0
compatible allwinner,sunxi-codec allwinner,sun50i-h616-codec
node gpio_bias bank-bias
node key_boot_recovery recovery-key low
node allwinner,sunxi-bt bluetooth-reset bt_rst_n
node allwinner,sunxi-btlpm bluetooth-uart
prop compatible device_type mainline
prop allwinner,pins as pins
prop allwinner,function as function

# sunxi pinctrl takes no level from a group
prop allwinner,data none

# sys_config's unset
prop phy-mode none-if-empty same

prop lineout_vol implies allwinner,audio-routing "Line Out", "LINEOUT"
prop regulator-* opp-hz opp-microvolt operating-points-v2 same
prop opp-supported-hw bits 0:0 2:4
prop cpu-supply opp-range
prop serial{n}@aliases alias
"""


def board() -> tuple[dict[str, Node], Report]:
    source, report = translate(
        Source.parse(BOARD),
        Vocabulary.parse(BOARD_VOCABULARY),
        Mainline(Source.parse(BOARD_MAINLINE)),
        base(),
    )
    return dict(walk(source.root)) | {"/": source.root}, report


class BoardTest(unittest.TestCase):
    def test_a_vendor_pin_group_takes_mainline_s_name(self) -> None:
        selecting = BOARD.replace(
            "\t\t\tphy-mode;\n",
            '\t\t\tphy-mode;\n\t\t\tpinctrl-names = "default";\n\t\t\tpinctrl-0 = <&uart1_pins_a>;\n',
        )
        vocabulary = (
            BOARD_VOCABULARY
            + "\nprop pinctrl-names pinctrl\n\n# read with pinctrl-names\nprop pinctrl-{n} none\n"
        )
        source, _ = translate(
            Source.parse(selecting),
            Vocabulary.parse(vocabulary),
            Mainline(Source.parse(BOARD_MAINLINE)),
            base(),
        )
        nodes = dict(walk(source.root))
        group = nodes["/soc/pinctrl@300b000/uart1-x-a-pins"]  # @0 as the label letters it
        self.assertEqual(group.labels, ["uart1_pins_a"])
        self.assertEqual(values(group), {"pins": '"PG6"', "function": '"uart1"'})

    def test_a_node_left_without_its_pin_groups_goes_one_written_empty_stays(self) -> None:
        unused = Node("wifi-host-wake-irq", ["wifi_host_wake_irq"])
        used = Node("uart2m1-xfer", ["uart2m1_xfer"])
        pinctrl = Node(
            "pinctrl",
            children=[
                Node("wireless-wlan", children=[unused]),
                Node("uart2", children=[used]),
                Node("written-empty"),
            ],
        )
        user = Node("serial", props=[Prop.of("pinctrl-0", "<&uart2m1_xfer>")])
        root = Node("/", children=[pinctrl, user])
        unselected(root, {id(unused), id(used)})
        self.assertEqual([c.name for c in pinctrl.children], ["uart2", "written-empty"])

    def test_a_vendor_pin_group_nothing_selects_is_not_written(self) -> None:
        nodes, _ = board()
        self.assertFalse([p for p in nodes if p.endswith("-pins")])

    def test_an_empty_value_drops_a_set_one_stays(self) -> None:
        nodes, _ = board()
        self.assertNotIn("phy-mode", values(nodes["/soc/eth@5020000"]))

    def test_a_vendor_property_implies_a_mainline_one(self) -> None:
        nodes, _ = board()
        codec = values(nodes["/soc/codec@5096000"])
        self.assertEqual(codec["allwinner,audio-routing"], '"Line Out", "LINEOUT"')

    def test_a_label_mapped_to_dash_is_dropped(self) -> None:
        nodes, _ = board()
        self.assertEqual(nodes["/aliases"].labels, [])

    def test_conversions_write_what_the_vendor_describes(self) -> None:
        nodes, _ = board()
        pio = values(nodes["/soc/pinctrl@300b000"])
        self.assertEqual(pio["vcc-pc-supply"], "<&reg_aldo1>")
        key = values(nodes["/gpio-keys/key"])
        self.assertEqual(key["gpios"], "<&pio 7 9 GPIO_ACTIVE_LOW>")
        self.assertEqual(key["linux,code"], "<KEY_VENDOR>")
        self.assertEqual(values(nodes["/gpio-keys"])["status"], '"disabled"')  # until a board says

    def test_a_uart_chip_s_bluetooth_node_holds_its_reset_and_wake_lines(self) -> None:
        nodes, report = board()
        bluetooth = nodes["/soc/serial@5000400/bluetooth"]
        self.assertEqual(bluetooth.labels, ["bt"])
        self.assertEqual(
            values(bluetooth),
            {
                "reset-gpios": "<&pio 6 19 GPIO_ACTIVE_LOW>",
                "device-wakeup-gpios": "<&pio 6 17 GPIO_ACTIVE_HIGH>",
            },
        )
        self.assertTrue([e for e in report.entries if e[1].startswith("bt_hostwake")])
        self.assertFalse([p for p in nodes if p.endswith("-hog")])

    def test_rockchip_wifi_lines_join_the_sdio_power_sequence_once(self) -> None:
        cases = (
            ("<&gpio1 RK_PA6 GPIO_ACTIVE_HIGH>", None, "<&gpio1 RK_PA6 GPIO_ACTIVE_LOW>"),
            (
                "<&gpio3 RK_PB2 GPIO_ACTIVE_HIGH>",
                "<&gpio3 RK_PB4 GPIO_ACTIVE_LOW>",
                "<&gpio3 RK_PB4 GPIO_ACTIVE_LOW>, <&gpio3 RK_PB2 GPIO_ACTIVE_LOW>",
            ),
            (
                "<&gpio3 RK_PB2 GPIO_ACTIVE_HIGH>",
                "<&gpio3 RK_PB2 GPIO_ACTIVE_LOW>",
                "<&gpio3 RK_PB2 GPIO_ACTIVE_LOW>",
            ),
        )
        for line, held, expected in cases:
            with self.subTest(line=line, held=held):
                props = [Prop.of("compatible", '"mmc-pwrseq-simple"')]
                if held:
                    props.append(Prop.of("reset-gpios", held))
                sequence = Node("sdio-pwrseq", ["sdio_pwrseq"], props=props)
                vendor = Node(
                    "wireless-wlan",
                    props=[Prop.of("WIFI,reset_gpio", line), Prop.of("status", '"okay"')],
                )
                RockchipTest.converted(Node("/", children=[sequence]), "rk-wlan", vendor, [])
                self.assertEqual(values(sequence)["reset-gpios"], expected)

    def test_rockchip_bluetooth_becomes_a_serdev_node_on_its_uart(self) -> None:
        for status, written in (('"okay"', True), ('"disabled"', False)):
            with self.subTest(status=status):
                uart = Node(
                    "serial@ff9e0000",
                    ["uart2"],
                    props=[Prop.of("pinctrl-0", "<&uart2m0_xfer>, <&uart2m0_ctsn>")],
                )
                vendor = Node(
                    "wireless-bluetooth",
                    props=[
                        Prop.of("pinctrl-0", "<&uart2m0_rtsn>"),
                        Prop.of("BT,reset_gpio", "<&gpio3 RK_PC1 GPIO_ACTIVE_HIGH>"),
                        Prop.of("BT,wake_gpio", "<&gpio3 RK_PB4 GPIO_ACTIVE_HIGH>"),
                        Prop.of("status", status),
                    ],
                )
                RockchipTest.converted(Node("/", children=[uart]), "rk-bluetooth", vendor, [])
                nodes = [c for c in uart.children if c.name == "bluetooth"]
                self.assertEqual(bool(nodes), written)
                if written:
                    self.assertEqual(
                        values(nodes[0]),
                        {
                            "reset-gpios": "<&gpio3 RK_PC1 GPIO_ACTIVE_LOW>",
                            "device-wakeup-gpios": "<&gpio3 RK_PB4 GPIO_ACTIVE_HIGH>",
                        },
                    )
                    self.assertEqual(
                        values(uart)["pinctrl-0"],
                        "<&uart2m0_xfer>, <&uart2m0_ctsn>, <&uart2m0_rtsn>",
                    )

    def test_no_reset_line_no_bluetooth_node(self) -> None:
        unset = BOARD.replace("bt_rst_n = <&pio 6 19 1 0xffffffff 0xffffffff 0>", "bt_rst_n")
        source, _ = translate(
            Source.parse(unset),
            Vocabulary.parse(BOARD_VOCABULARY),
            Mainline(Source.parse(BOARD_MAINLINE)),
            base(),
        )
        self.assertFalse([p for p, _ in walk(source.root) if p.endswith("/bluetooth")])

    def test_a_cpu_rail_is_held_to_its_opps(self) -> None:
        nodes, _ = board()
        rail = values(nodes["/soc/dcdc2"])
        self.assertEqual(
            (rail["regulator-min-microvolt"], rail["regulator-max-microvolt"]),
            ("<900000>", "<950000>"),
        )

    def test_rows_of_one_frequency_merge_by_speed_bin(self) -> None:
        nodes, _ = board()
        row = values(nodes["/opp-table-cpu/opp-480000000"])
        self.assertEqual(row["opp-microvolt-speed0"], "<950000>")
        self.assertEqual(row["opp-microvolt-speed4"], "<900000>")
        self.assertEqual(row["opp-supported-hw"], "<0x11>")
        self.assertNotIn("opp-microvolt", row)

    def test_a_row_no_bin_selects_goes(self) -> None:
        table = Node(
            "t",
            [],
            [],
            [],
            [
                Node(
                    "a", [], [], [Prop.of("opp-hz", "<1>"), Prop.of("opp-supported-hw", "<0x00>")]
                ),
                Node(
                    "b",
                    [],
                    [],
                    [
                        Prop.of("opp-hz", "<1>"),
                        Prop.of("opp-supported-hw", "<0x01>"),
                        Prop.of("opp-microvolt", "<5>"),
                    ],
                ),
            ],
        )
        speed_bins(table)
        self.assertEqual([c.name for c in table.children], ["opp-1"])

    def test_only_a_suspend_row_below_every_vendor_row_rests_there(self) -> None:
        slowest = 700000000
        for hz, suspend, kept in [
            (300000000, True, True),
            (700000000, True, False),
            (900000000, True, False),
            (300000000, False, False),
        ]:
            with self.subTest(hz=hz, suspend=suspend):
                props = [Prop.of("opp-hz", f"/bits/ 64 <{hz}>")]
                props += [Prop.of("opp-suspend")] if suspend else []
                self.assertEqual(rests(Node(f"opp-{hz}", props=props), slowest), kept)

    def test_a_bin_left_to_the_default_gets_it_as_its_own_column(self) -> None:
        table = Node(
            "opp-table",
            props=[Prop.of("rockchip,pvtm-voltage-sel", "<0 10 0>, <11 20 1>, <21 99 2>")],
            children=[
                Node(
                    "opp-1",
                    props=[
                        Prop.of("opp-hz", "<1>"),
                        Prop.of("opp-microvolt", "<900000>"),
                        Prop.of("opp-microvolt-L0", "<962500>"),
                    ],
                ),
                Node("opp-2", props=[Prop.of("opp-hz", "<2>"), Prop.of("opp-microvolt", "<5>")]),
            ],
        )
        voltage_bins(table)
        volts = {p.name: p.value for p in table.children[0].props}
        self.assertEqual(volts["opp-microvolt"], "<962500>")
        self.assertEqual(
            [volts[f"opp-microvolt-L{n}"] for n in range(3)], ["<962500>", "<900000>", "<900000>"]
        )
        self.assertEqual([p.name for p in table.children[1].props], ["opp-hz", "opp-microvolt"])

    def test_voltage_bins_default_to_the_highest_and_stay(self) -> None:
        def row(name: str, *volts: tuple[str, str]) -> Node:
            props = [Prop.of("opp-hz", "<1>")] + [Prop.of(n, v) for n, v in volts]
            return Node(name, [], [], props)

        table = Node(
            "opp-table",
            [],
            [],
            [],
            [
                row(
                    "binned",
                    ("opp-microvolt", "<825000 825000 1100000>"),
                    ("opp-microvolt-L0", "<900000 900000 1100000>"),
                    ("opp-microvolt-L1", "<887500 887500 1100000>"),
                ),
                row(
                    "default-highest",
                    ("opp-microvolt", "<962500 962500 1100000>"),
                    ("opp-microvolt-L1", "<950000 950000 1100000>"),
                ),
                row("unbinned", ("opp-microvolt", "<5>")),
            ],
        )
        voltage_bins(table)
        self.assertEqual(
            [
                [(p.name, p.value) for p in c.props if p.name.startswith("opp-microvolt")]
                for c in table.children
            ],
            [
                [
                    ("opp-microvolt", "<900000 900000 1100000>"),
                    ("opp-microvolt-L0", "<900000 900000 1100000>"),
                    ("opp-microvolt-L1", "<887500 887500 1100000>"),
                ],
                [
                    ("opp-microvolt", "<962500 962500 1100000>"),
                    ("opp-microvolt-L1", "<950000 950000 1100000>"),
                ],
                [("opp-microvolt", "<5>")],
            ],
        )


LAYOUT = """/dts-v1/;

/ {
\t#address-cells = <1>;
\t#size-cells = <1>;

\tsoc {
\t};

\ti2c@c1108500 {
\t\tcompatible = "amlogic, meson-gx-i2c";
\t};

\tnmi: intc-nmi@07010320 {
\t\tcompatible = "allwinner,sun8i-nmi";
\t};

\tramoops@7400000 {
\t\treg = <0x7400000 0x100000>;
\t};

\tuboot: uboot {
\t};

\tlcd0 {
\t\tcompatible = "allwinner,sunxi-lcd0";
\t\tlcd_used = <0>;
\t};

\tlcd1 {
\t\tcompatible = "allwinner,sunxi-lcd1";
\t\tlcd_used = <1>;
\t};

\thdmi {
\t\thdmi_power0 = "vcc-hdmi";
\t\thdmi_power1 = "vcc1v8";
\t};

\tsecure {
\t\tdevice_type = "secure";
\t\tdram_region_mbytes = <80>;
\t};

\teth1 {
\t\tphy-mode = "rmii";
\t};

\tpio: pinctrl {
\t\tsdio_pins: sdio {
\t\t\tallwinner,pins = "PG0", "PG1";
\t\t};
\t};

\treg_dldo1: dldo1 {
\t\tregulator-min-microvolt = <3300000>;
\t\tregulator-max-microvolt = <3300000>;
\t};

\treg_aldo1: aldo1 {
\t\tregulator-name = "vcc1v8";
\t\tregulator-min-microvolt = <1800000>;
\t\tregulator-max-microvolt = <1800000>;
\t};

\tmmc1: host {
\t\tpinctrl-0 = <&sdio_pins>;
\t\tsdio-used-1v8;
\t};

\twlan {
\t\tcompatible = "allwinner,sunxi-wlan";
\t\tclocks = <&clk_losc_out>;
\t\twlan_regon = <&pio 6 18 1 0 0 0>;
\t\twlan_busnum = <1>;
\t\twlan_power;
\t};

\tinit {
\t\tcompatible = "allwinner,sunxi-init-gpio";
\t\tnormal_led = "led_pin";
\t\tled_pin = <&pio 7 6 1 0 0 1>;
\t\tnormal_led_light = <1>;
\t};

\topp_l_table {
\t\topp@480000000 {
\t\t\topp-hz = /bits/ 64 <480000000>;
\t\t\topp-microvolt = <900000>;
\t\t\topp-supported-hw = <0x04>;
\t\t};

\t\topp@600000000 {
\t\t\topp-hz = /bits/ 64 <600000000>;
\t\t\topp-microvolt = <950000>;
\t\t\topp-supported-hw = <0x10>;
\t\t};
\t};
};
"""
LAYOUT_MAINLINE = """/ {
\t#address-cells = <2>;
\t#size-cells = <2>;

\tsoc {
\t\tcompatible = "simple-bus";
\t\t#address-cells = <2>;
\t\t#size-cells = <2>;
\t\tranges;

\t\tbus@c1100000 {
\t\t\tcompatible = "simple-bus";
\t\t\treg = <0x0 0xc1100000 0x0 0x100000>;
\t\t\t#address-cells = <2>;
\t\t\t#size-cells = <2>;
\t\t\tranges = <0x0 0x0 0x0 0xc1100000 0x0 0x100000>;

\t\t\ti2c@8500 {
\t\t\t\tcompatible = "amlogic,meson-gxbb-i2c";
\t\t\t\tstatus = "disabled";
\t\t\t};
\t\t};

\t\tnmi_intc: interrupt-controller@7010320 {
\t\t\tcompatible = "allwinner,sun9i-a80-nmi";
\t\t};
\t};
};
"""
LAYOUT_VOCABULARY = r"""cells / 2 2
label nmi nmi_intc
name opp_l_table opp-table-cpu
name opp opp-
compatible amlogic,meson-gx-i2c amlogic,meson-gxbb-i2c
compatible allwinner,sun8i-nmi allwinner,sun9i-a80-nmi
node allwinner,sunxi-wlan pwrseq &ccu CLK_PLL_SYSTEM_32K
node allwinner,sunxi-init-gpio leds
clock clk_losc_out as &rtc CLK_OSC32K_FANOUT
prop compatible status device_type reg #address-cells #size-cells mainline

# a test's
prop dram_region_mbytes pinctrl-0 none
prop phy-mode none-if-empty same

prop sdio-used-1v8 bank-1v8

# a test's
node allwinner,sunxi-lcd{n} unused-by lcd_used
prop hdmi_power{n} supply-name

prop allwinner,pins as pins
prop regulator-* opp-hz opp-microvolt same
prop opp-supported-hw bits 2:4
"""


def layout() -> tuple[dict[str, Node], Report]:
    source, report = translate(
        Source.parse(LAYOUT),
        Vocabulary.parse(LAYOUT_VOCABULARY),
        Mainline(Source.parse(LAYOUT_MAINLINE)),
        base(),
    )
    return dict(walk(source.root)) | {"/": source.root}, report


class LayoutTest(unittest.TestCase):
    """The regressions found translating trees whose layout differs from mainline's."""

    def test_a_vendor_compatible_s_space_is_no_part_of_it(self) -> None:
        node = Source.parse('/ {\n\tcompatible = "amlogic, meson-uart", "a,b";\n};\n').root
        self.assertEqual(compatibles(node), ["amlogic,meson-uart", "a,b"])

    def test_a_node_meets_its_counterpart_at_the_cpu_s_address(self) -> None:
        mainline = Mainline(Source.parse(LAYOUT_MAINLINE))
        self.assertEqual(mainline.at("c1108500"), "/soc/bus@c1100000/i2c@8500")
        nodes, _ = layout()
        self.assertNotIn("/i2c@c1108500", nodes)

    def test_a_node_moves_under_a_bus_the_vendor_never_names(self) -> None:
        nodes, _ = layout()
        self.assertNotIn("/i2c@8500", nodes)  # no copy left where the vendor wrote it
        i2c = nodes["/soc/bus@c1100000/i2c@8500"]
        self.assertEqual(values(i2c)["status"], '"okay"')  # the vendor's node, not mainline's

    def test_a_node_met_after_mainline_s_parent_is_written_once(self) -> None:
        nodes, _ = layout()
        nmi = [p for p in nodes if "7010320" in p]
        self.assertEqual(nmi, ["/soc/interrupt-controller@7010320"])

    def test_reg_widens_to_mainline_s_cells(self) -> None:
        nodes, _ = layout()
        ramoops = values(nodes["/ramoops@7400000"])
        self.assertEqual(ramoops["reg"], "<0 0x7400000 0 0x100000>")

    def test_a_memory_node_its_bootloader_sizes_stays(self) -> None:
        factory = LAYOUT.replace(
            "\tsoc {\n\t};", '\tsoc {\n\t};\n\n\tmemory@0 {\n\t\tdevice_type = "memory";\n\t};'
        )
        self.assertIn("memory@0", factory)
        source, _ = translate(
            Source.parse(factory),
            Vocabulary.parse(LAYOUT_VOCABULARY),
            Mainline(Source.parse(LAYOUT_MAINLINE)),
            base(),
        )
        self.assertIn("/memory@0", dict(walk(source.root)))

    def test_a_shell_whose_contents_all_went_is_not_written(self) -> None:
        nodes, _ = layout()
        self.assertNotIn("/secure", nodes)
        self.assertNotIn("/uboot", nodes)  # labelled, but nothing references it
        self.assertIn("non-removable", values(nodes["/host"]))  # labelled and given contents

    def test_a_set_value_is_kept_by_none_if_empty_same(self) -> None:
        nodes, _ = layout()
        self.assertEqual(values(nodes["/eth1"])["phy-mode"], '"rmii"')

    def test_a_host_at_1v8_supplies_its_pins_bank_from_the_1v8_rail(self) -> None:
        nodes, _ = layout()
        self.assertEqual(values(nodes["/pinctrl"])["vcc-pg-supply"], "<&reg_aldo1>")

    def test_the_wifi_power_sequence(self) -> None:
        nodes, _ = layout()
        pwrseq = values(nodes["/pwrseq"])
        self.assertEqual(pwrseq["assigned-clocks"], "<&rtc CLK_OSC32K_FANOUT>")
        self.assertEqual(pwrseq["assigned-clock-parents"], "<&ccu CLK_PLL_SYSTEM_32K>")
        self.assertIn("non-removable", values(nodes["/host"]))
        # wlan_power empty: no switched rail, so the card's supply is the one rail at 3.3 V
        self.assertEqual(values(nodes["/host"])["vmmc-supply"], "<&reg_dldo1>")
        card = nodes["/host/wifi@1"]  # the card, which an alias names for U-Boot's stable MAC
        self.assertEqual((card.labels, values(card)["reg"]), (["sdio_wifi"], "<1>"))

    def test_leds_keep_their_state_through_suspend_and_shutdown(self) -> None:
        nodes, _ = layout()
        led = values(nodes["/leds/led-0"])
        self.assertEqual(led["gpios"], "<&pio 7 6 GPIO_ACTIVE_HIGH>")
        self.assertIn("retain-state-suspended", led)
        self.assertIn("retain-state-shutdown", led)

    def test_an_unmapped_speed_bit_reaches_no_mainline_bin(self) -> None:
        nodes, report = layout()
        rows = [p for p in nodes if p.startswith("/opp-table-cpu/")]
        # one row a frequency, even unmerged
        self.assertEqual(rows, ["/opp-table-cpu/opp-480000000"])
        row = values(nodes["/opp-table-cpu/opp-480000000"])
        self.assertEqual(
            (row["opp-supported-hw"], row["opp-microvolt-speed4"]), ("<0x10>", "<900000>")
        )
        self.assertIn(("unresolved", "property opp-supported-hw: vendor bit 4"), report.entries)


class PinFunctionTest(unittest.TestCase):
    def test_a_state_naming_an_unknown_function_is_reported(self) -> None:
        factory = FACTORY.replace(
            'allwinner,function = "sdc0"', 'allwinner,function = "io_disabled"'
        )
        _, report = translate(
            Source.parse(factory),
            Vocabulary.parse(VOCABULARY),
            Mainline(Source.parse(MAINLINE)),
            base(),
            {"PF0": {"mmc0"}, "PF1": {"mmc1"}},
        )
        self.assertIn(("unknown", "pin function io_disabled selected by pinctrl-0"), report.entries)
        _, mismatched = translate(
            Source.parse(FACTORY),
            Vocabulary.parse(VOCABULARY),
            Mainline(Source.parse(MAINLINE)),
            base(),
            {"PF0": {"mmc0"}, "PF1": {"mmc1"}},
        )
        self.assertIn(
            ("unresolved", "pin function mmc0 not on PF1, by pinctrl-0"), mismatched.entries
        )
        _, clean = translated()
        self.assertFalse([k for k in clean.entries if "pin function" in k[1]])

    def test_a_meson_group_is_checked_in_its_mux_node(self) -> None:
        source = 'static const char * const hdmi_i2c_groups[] = {\n\t"hdmi_sda", "hdmi_scl",\n};'
        self.assertEqual(MESON_FUNCTION.findall(source)[0][0], "hdmi_i2c")
        functions = {"hdmi_sda": {"hdmi_i2c"}}
        for function, expected in [("hdmi_ddc", ["unknown"]), ("hdmi_i2c", [])]:
            tree = Source.parse(
                "/ {\n\thdmi {\n\t\tpinctrl-0 = <&ddc>;\n\t};\n\n\tddc: ddc {\n\t\tmux {\n"
                f'\t\t\tgroups = "hdmi_sda";\n\t\t\tfunction = "{function}";\n'
                "\t\t};\n\t};\n};\n"
            )
            report = Report()
            selected_functions(tree.root, functions, report)
            self.assertEqual([kind for kind, _ in report.entries], expected, function)


AML_FACTORY = """/dts-v1/;

/ {
\twifi {
\t\tcompatible = "amlogic, aml_wifi";
\t\tpower_on_pin = <&gpio GPIOX_6 GPIO_ACTIVE_HIGH>;
\t\tdhd_static_buf;
\t\tpinctrl-names = "wifi_32k_pins";
\t\tpinctrl-0 = <&wifi_32k_pins>;
\t};

\taml_sound_meson {
\t\tcompatible = "aml, meson-snd-card";
\t};

\taocec {
\t\tcompatible = "amlogic, amlogic-aocec";
\t\tpinctrl-names = "default";
\t\tpinctrl-0 = <&hdmitx_aocec>;
\t};

\twifi_pwm_conf {
\t\tone {
\t\t\tpwms = <&pwm_ef 0 30541 0>;
\t\t\tduty-cycle = <15270>;
\t\t\ttimes = <8>;
\t\t};

\t\ttwo {
\t\t\tpwms = <&pwm_ef 2 30500 0>;
\t\t\ttimes = <12>;
\t\t};
\t};

\tsdio@d0070000 {
\t\tcompatible = "amlogic, meson-mmc-gxlx";
\t\treg = <0xd0070000 0x2000>;
\t\tmax-frequency = <100000000>;

\t\tsdio {
\t\t\tocr_avail = <0x200080>;
\t\t\tf_max = <50000000>;
\t\t\tcaps = "MMC_CAP_4_BIT_DATA", "MMC_PM_KEEP_POWER", "MMC_CAP_POLL";
\t\t\tcard_type = <0x03>;
\t\t\tgpio_cd = <&gpio GPIOX_1 GPIO_ACTIVE_HIGH>;
\t\t};
\t};
};
"""
AML_MAINLINE = """/ {
	cec_AO: cec@c8100100 {
		compatible = "amlogic,meson-gx-ao-cec";
		status = "disabled";
	};

	hdmi_tx: hdmi-tx@da800000 {
	};

	aiu: audio-controller@c1105400 {
		status = "disabled";
	};

	hdmi_sound: sound {
		status = "disabled";
	};

\tsd_emmc_a: mmc@d0070000 {
\t\tcompatible = "amlogic,meson-gx-mmc";
\t\treg = <0x0 0xd0070000 0x0 0x800>;
\t};
};
"""
AML_VOCABULARY = r"""prop compatible reg mainline
prop max-frequency same
node amlogic,meson-mmc-gxlx same
node sdio aml-slot sd_emmc_a
node amlogic,aml_wifi aml-pwrseq sd_emmc_a
node wifi_pwm_conf aml-32k
node amlogic,amlogic-aocec cec cec_AO hdmi_tx
node aml,meson-snd-card enable hdmi_sound aiu
value caps MMC_PM_KEEP_POWER keep-power-in-suspend

# a test's
value caps MMC_CAP_4_BIT_DATA -
"""


def amlogic(factory: str = AML_FACTORY) -> tuple[dict[str, Node], Report]:
    source, report = translate(
        Source.parse(factory),
        Vocabulary.parse(AML_VOCABULARY),
        Mainline(Source.parse(AML_MAINLINE)),
        base(),
    )
    return dict(walk(source.root)) | {"/": source.root}, report


class AmlogicTest(unittest.TestCase):
    def test_a_slot_s_settings_land_on_its_host(self) -> None:
        nodes, report = amlogic()
        host = values(nodes["/mmc@d0070000"])
        self.assertEqual(host["vmmc-supply"], "<&vcc_3v3>")
        self.assertEqual(host["vqmmc-supply"], "<&vcc_3v3>")
        self.assertEqual(host["max-frequency"], "<50000000>")  # the slot's, below the host's
        self.assertIn("keep-power-in-suspend", host)
        self.assertIn(("unresolved", "slot cap MMC_CAP_POLL"), report.entries)
        self.assertIn(("unresolved", "slot property gpio_cd"), report.entries)
        self.assertFalse([k for k in report.entries if "card_type" in k[1]])  # the driver's own

    def test_the_power_line_is_the_sequence_s_reset_of_opposite_polarity(self) -> None:
        for vendor, reset in (
            ("GPIO_ACTIVE_HIGH", "GPIO_ACTIVE_LOW"),
            ("GPIO_ACTIVE_LOW", "GPIO_ACTIVE_HIGH"),
        ):
            nodes, _ = amlogic(AML_FACTORY.replace("GPIOX_6 GPIO_ACTIVE_HIGH", f"GPIOX_6 {vendor}"))
            pwrseq = values(nodes["/sdio-pwrseq"])
            self.assertEqual(pwrseq["reset-gpios"], f"<&gpio GPIOX_6 {reset}>")
            self.assertEqual(pwrseq["pinctrl-names"], '"default"')
            self.assertEqual(pwrseq["clocks"], "<&wifi32k>")
        self.assertEqual(values(nodes["/mmc@d0070000"])["mmc-pwrseq"], "<&wifi_pwrseq>")

    def test_a_wired_cec_enables_mainline_s_on_the_vendor_s_pins(self) -> None:
        nodes, _ = amlogic()
        cec = values(nodes["/cec@c8100100"])
        self.assertEqual(cec["status"], '"okay"')
        self.assertEqual(cec["pinctrl-0"], "<&hdmitx_aocec>")
        self.assertEqual(cec["hdmi-phandle"], "<&hdmi_tx>")

    def test_one_vendor_node_enables_each_block_it_stands_for(self) -> None:
        nodes, _ = amlogic()
        self.assertEqual(values(nodes["/sound"])["status"], '"okay"')
        self.assertEqual(values(nodes["/audio-controller@c1105400"])["status"], '"okay"')

    def test_turns_of_two_channels_are_one_clock_at_their_weighted_mean(self) -> None:
        nodes, _ = amlogic()
        clock = values(nodes["/wifi32k"])
        self.assertEqual(clock["pwms"], "<&pwm_ef 0 30516 0>")  # (8 x 30541 + 12 x 30500) / 20
        self.assertEqual(clock["clock-frequency"], "<32770>")


class UsedTest(unittest.TestCase):
    def test_a_node_its_own_flag_leaves_unused_goes_quietly(self) -> None:
        nodes, report = layout()
        self.assertFalse([p for p in nodes if p.startswith("/lcd")])
        self.assertIn(("unresolved", "node allwinner,sunxi-lcd{n}"), report.entries)
        self.assertEqual(report.entries[("unresolved", "node allwinner,sunxi-lcd{n}")], ["/lcd1"])

    def test_a_supply_no_regulator_is_named_goes_a_named_one_is_asked(self) -> None:
        nodes, report = layout()
        self.assertNotIn("hdmi_power0", values(nodes["/hdmi"]) if "/hdmi" in nodes else {})
        asked = [k for k in report.entries if "hdmi_power" in k[1]]
        self.assertEqual(asked, [("unresolved", 'property hdmi_power{n} = "vcc1v8"')])


class StatusTest(unittest.TestCase):
    def test_a_status_a_rule_drops_leaves_mainline_s(self) -> None:
        factory = FACTORY.replace(
            "\t\t\tbus-width = <4>;", '\t\t\tbus-width = <4>;\n\t\t\tstatus = "okay";'
        )
        vocabulary = VOCABULARY.replace(
            "prop bus-width same", "prop bus-width same\n\n# a test's\nprop status none\n"
        )
        source, _ = translate(
            Source.parse(factory),
            Vocabulary.parse(vocabulary),
            Mainline(Source.parse(MAINLINE)),
            base(),
        )
        mmc = dict(walk(source.root))["/soc/mmc@4020000"]
        self.assertEqual(values(mmc)["status"], '"disabled"')  # mainline's; the vendor's went


class SupplyTest(unittest.TestCase):
    def test_a_consumer_gets_its_design_rail_held_to_its_opps(self) -> None:
        factory = LAYOUT.replace(
            "\topp_l_table {",
            '\tpmu {\n\t\tcompatible = "x-powers,axp1530";\n\t};\n\n\tgpu: gpu {\n\t\toperating-points-v2 = <&cpu_opp_table>;\n\t};\n\n\topp_l_table {',
        )
        factory = factory.replace("\topp_l_table {", "\tcpu_opp_table: opp_l_table {", 1)
        vocabulary = (
            LAYOUT_VOCABULARY
            + "also x-powers,axp1530 supply gpu mali-supply reg_dldo1\nprop operating-points-v2 same\n"
        )
        source, _ = translate(
            Source.parse(factory),
            Vocabulary.parse(vocabulary),
            Mainline(Source.parse(LAYOUT_MAINLINE)),
            base(),
        )
        nodes = dict(walk(source.root))
        self.assertEqual(values(nodes["/gpu"])["mali-supply"], "<&reg_dldo1>")
        rail = values(nodes["/dldo1"])
        self.assertEqual(
            (rail["regulator-min-microvolt"], rail["regulator-max-microvolt"]),
            ("<900000>", "<900000>"),
        )


class ConfTest(unittest.TestCase):
    def test_every_base_s_translation_parses(self) -> None:
        bases = Path(__file__).resolve().parents[1] / "tools/dtcx/bases"
        for conf in sorted(bases.glob("*.translate.conf")):
            Vocabulary.load(conf.name.removesuffix(".translate.conf"))


class ConversionsTest(unittest.TestCase):
    def test_gpio(self) -> None:
        cases = [
            ("<&pio 7 8 1 0 1 0>", "high", False, "<&pio 7 8 GPIO_ACTIVE_HIGH>"),
            (
                "<&pio 0x5 0x6 6 2 3 0>",
                "low",
                True,
                "<&pio 5 6 (GPIO_ACTIVE_LOW | GPIO_PULL_DOWN)>",
            ),
            ("<&pio 5 6 6 0 3 0>", "low", True, "<&pio 5 6 GPIO_ACTIVE_LOW>"),
        ]
        for value, active, pull, expected in cases:
            self.assertEqual(gpio(value, active, pull), expected, value)


if __name__ == "__main__":
    unittest.main()


RK_FACTORY = """/dts-v1/;

/ {
\thdmi_sound: hdmi-sound {
\t\tcompatible = "rockchip,hdmi";
\t\trockchip,mclk-fs = <128>;
\t\trockchip,card-name = "rockchip,hdmi";
\t\trockchip,cpu = <&sai3>;
\t\trockchip,codec = <&hdmi>;
\t};

\tpwm3: pwm@ffa90030 {
\t\tcompatible = "rockchip,remotectl-pwm";
\t\tpinctrl-names = "default";
\t\tpinctrl-0 = <&pwm3m0_pins>;
\t\tremote_pwm_id = <3>;
\t\tstatus = "okay";
\t};

\tpinctrl {
\t\tpwm3 {
\t\t\tpwm3m0_pins: pwm3m0-pins {
\t\t\t\trockchip,pins = <4 RK_PC6 1 &pcfg_pull_none>;
\t\t\t};
\t\t};
\t};

\tsai3: sai@ffbb0000 {
\t};

\thdmi: hdmi@ff8d0000 {
\t};

\tvdd_cpu: vdd-cpu {
\t\tcompatible = "pwm-regulator";
\t\tregulator-min-microvolt = <746000>;
\t\tregulator-max-microvolt = <1201000>;
\t\tregulator-init-microvolt = <953000>;
\t};

\tvdd_logic: vdd-logic {
\t\tcompatible = "pwm-regulator";
\t\tregulator-min-microvolt = <705000>;
\t\tregulator-max-microvolt = <1006000>;
\t\tregulator-init-microvolt = <900000>;
\t};

\tconsumer {
\t\tcompatible = "test,consumer";
\t\toperating-points-v2 = <&vdd_cpu>;
\t\tcpu-supply = <&vdd_cpu>;
\t};

\tgpu: gpu@ff700000 {
\t\tcompatible = "arm,mali-450";
\t\toperating-points-v2 = <&gpu_opp_table>;
\t};

\tusbdrd {
\t\tcompatible = "rockchip,rk3528-dwc3";

\t\tdwc3@fe500000 {
\t\t\tcompatible = "snps,dwc3";
\t\t\treg = <0x00 0xfe500000 0x00 0x400000>;
\t\t\tdr_mode = "host";
\t\t};
\t};
};
"""
RK_MAINLINE = """/ {
\tpinctrl {
\t\tpwm3 {
\t\t\tpwm3m0_pins: pwm3m0-pins {
\t\t\t\trockchip,pins = <4 RK_PC6 1 &pcfg_pull_none>;
\t\t\t};
\t\t};
\t};

\tsai3: sai@ffbb0000 {
\t};

\thdmi: hdmi@ff8d0000 {
\t};

\tgpu: gpu@ff700000 {
\t\tcompatible = "arm,mali-450";
\t\toperating-points-v2 = <&gpu_opp_table>;
\t};

\tusb_host0_xhci: usb@fe500000 {
\t\tcompatible = "rockchip,rk3528-dwc3", "snps,dwc3";
\t\treg = <0x0 0xfe500000 0x0 0x400000>;
\t\tdr_mode = "otg";
\t\tstatus = "disabled";
\t};
};
"""
RK_PANEL = """\tfd655_dev {
\t\tcompatible = "rockchip,fd655_dev";
\t\tstatus = "okay";
\t\tclk_pin = <&gpio4 RK_PC3 GPIO_ACTIVE_HIGH>;
\t\tdat_pin = <&gpio4 RK_PC4 GPIO_ACTIVE_HIGH>;
\t};
"""
RK_VOCABULARY = r"""prop compatible reg rockchip,pins mainline
node rockchip,fd655_dev panel-bus clk_pin dat_pin
# a test's
prop remote_pwm_id none
node rockchip,hdmi rk-sound-card
node rockchip,remotectl-pwm pwm-ir
# a test's
node rockchip,rk3528-dwc3 wrapper
compatible snps,dwc3 rockchip,rk3528-dwc3
prop dr_mode same
compatible pwm-regulator pwm-regulator
compatible test,consumer test,consumer
prop regulator-* cpu-supply operating-points-v2 same
also pwm-regulator init-voltage
# a test's
prop operating-points-v2@arm,mali-450 withhold
"""


def rockchip(factory: str = RK_FACTORY) -> tuple[dict[str, Node], Report]:
    source, report = translate(
        Source.parse(factory),
        Vocabulary.parse(RK_VOCABULARY),
        Mainline(Source.parse(RK_MAINLINE)),
        base(),
    )
    return dict(walk(source.root)) | {"/": source.root}, report


def with_panel(panel: str) -> str:
    """The factory tree with a front-panel node at the end of its root."""
    head, _, _ = RK_FACTORY.rpartition("};\n")
    return head + panel + "};\n"


class RockchipTest(unittest.TestCase):
    def test_the_vendor_sound_card_is_a_simple_card_on_its_dais(self) -> None:
        nodes, _ = rockchip()
        card = values(nodes["/hdmi-sound"])
        self.assertEqual(card["compatible"], '"simple-audio-card"')
        self.assertEqual(card["simple-audio-card,mclk-fs"], "<128>")
        cpu = values(nodes["/hdmi-sound/simple-audio-card,cpu"])
        self.assertEqual(cpu["sound-dai"], "<&sai3>")
        self.assertEqual((cpu["dai-tdm-slot-num"], cpu["dai-tdm-slot-width"]), ("<2>", "<32>"))
        codec = values(nodes["/hdmi-sound/simple-audio-card,codec"])
        self.assertEqual(codec["sound-dai"], "<&hdmi>")

    def test_a_card_without_its_dais_is_a_question(self) -> None:
        nodes, report = rockchip(RK_FACTORY.replace("\t\trockchip,cpu = <&sai3>;\n", ""))
        self.assertNotIn("/hdmi-sound", nodes)
        self.assertIn("rk-sound-card", report.text())

    def test_the_pwm_remote_is_a_gpio_receiver_on_its_pin(self) -> None:
        nodes, _ = rockchip()
        receiver = values(nodes["/ir-receiver"])
        self.assertEqual(receiver["compatible"], '"gpio-ir-receiver"')
        self.assertEqual(receiver["gpios"], "<&gpio4 RK_PC6 GPIO_ACTIVE_LOW>")
        pin = values(nodes["/pinctrl/pwm3/ir-rx-gpio"])
        self.assertEqual(pin["rockchip,pins"], "<4 RK_PC6 RK_FUNC_GPIO &pcfg_pull_none>")

    def test_a_remote_without_its_pin_is_a_question(self) -> None:
        nodes, report = rockchip(RK_FACTORY.replace("\t\tpinctrl-0 = <&pwm3m0_pins>;\n", ""))
        self.assertNotIn("/ir-receiver", nodes)
        self.assertIn("pwm-ir", report.text())

    def test_a_front_panel_is_an_i2c_gpio_bus_on_its_two_lines(self) -> None:
        nodes, _ = rockchip(with_panel(RK_PANEL))
        bus = values(nodes["/i2c-display"])
        self.assertEqual(bus["compatible"], '"i2c-gpio"')
        self.assertEqual(bus["sda-gpios"], "<&gpio4 RK_PC4 (GPIO_ACTIVE_HIGH | GPIO_OPEN_DRAIN)>")
        self.assertEqual(bus["scl-gpios"], "<&gpio4 RK_PC3 (GPIO_ACTIVE_HIGH | GPIO_OPEN_DRAIN)>")
        self.assertNotIn("/fd655_dev", nodes)

    def test_a_panel_without_its_lines_is_a_question(self) -> None:
        panel = RK_PANEL.replace("\t\tdat_pin = <&gpio4 RK_PC4 GPIO_ACTIVE_HIGH>;\n", "")
        nodes, report = rockchip(with_panel(panel))
        self.assertNotIn("/i2c-display", nodes)
        self.assertIn("panel-bus", report.text())

    def test_a_disabled_panel_has_no_bus(self) -> None:
        panel = RK_PANEL.replace('"okay"', '"disabled"')
        nodes, _ = rockchip(with_panel(panel))
        self.assertNotIn("/i2c-display", nodes)

    def test_a_wrapper_goes_and_its_child_meets_mainline_s_node(self) -> None:
        nodes, _ = rockchip()
        self.assertFalse([p for p in nodes if p.startswith("/usbdrd")])
        usb = values(nodes["/usb@fe500000"])
        self.assertEqual(usb["dr_mode"], '"host"')
        self.assertEqual(usb["status"], '"okay"')

    def test_a_rail_no_consumer_scales_is_held_at_its_initial_voltage(self) -> None:
        nodes, _ = rockchip()
        logic = values(nodes["/vdd-logic"])
        self.assertEqual(logic["regulator-min-microvolt"], "<900000>")
        self.assertEqual(logic["regulator-max-microvolt"], "<900000>")
        self.assertNotIn("regulator-init-microvolt", logic)

    def test_a_rail_a_consumer_s_opps_scale_keeps_its_range(self) -> None:
        nodes, _ = rockchip()
        cpu = values(nodes["/vdd-cpu"])
        self.assertEqual(cpu["regulator-min-microvolt"], "<746000>")
        self.assertEqual(cpu["regulator-max-microvolt"], "<1201000>")
        self.assertNotIn("regulator-init-microvolt", cpu)

    def test_a_cooling_map_on_a_node_without_its_opps_goes(self) -> None:
        def cooling_map(name: str, device: str) -> Node:
            return Node(name, props=[Prop.of("cooling-device", f"<&{device} 0 1>")])

        maps = Node(
            "cooling-maps", children=[cooling_map("map0", "cpu0"), cooling_map("map1", "gpu")]
        )
        root = Node("/", children=[Node("thermal-zones", children=[maps])])
        unthrottled(root, {"gpu"})
        self.assertEqual([c.name for c in maps.children], ["map0"])

    def test_hdmi_ddc_moves_to_the_i2c_controller_on_its_pins(self) -> None:
        def group(label: str, pins: str) -> Node:
            return Node(label, [label], props=[Prop.of("rockchip,pins", pins)])

        hdmi = Node("hdmi@ff8d0000", ["hdmi"], props=[Prop.of("pinctrl-0", "<&hdmi_pins>")])
        i2c = Node("i2c@ffa58000", ["i2c2"], props=[Prop.of("pinctrl-0", "<&i2c2m0_xfer>")])
        i2c.props.append(Prop.of("status", '"disabled"'))
        pins = "<0 RK_PA3 1 &pcfg_pull_none>, <0 RK_PA4 1 &pcfg_pull_none>, <0 RK_PA5 1 &x>"
        ddc = "<0 RK_PA4 2 &pcfg_pull_none_smt>, <0 RK_PA5 2 &pcfg_pull_none_smt>"
        pinctrl = Node("pinctrl", children=[group("hdmi_pins", pins), group("i2c2m0_xfer", ddc)])
        root = Node("/", children=[hdmi, i2c, pinctrl])
        report: list[str] = []
        conversions = Conversions(
            root, lambda *a: report.append(a[1]), lambda s: s, lambda *a: [], lambda *a: ""
        )
        conversions.run("hdmi-ddc-i2c", Node("hdmi@ff8d0000", ["hdmi"]), "/hdmi@ff8d0000", [])
        self.assertEqual(values(hdmi)["ddc-i2c-bus"], "<&i2c2>")
        self.assertEqual(
            values(pinctrl.children[0])["rockchip,pins"], "<0 RK_PA3 1 &pcfg_pull_none>"
        )
        self.assertEqual(values(i2c)["status"], '"okay"')
        self.assertEqual(report, [])

    @staticmethod
    def converted(
        root: Node, action: str, vendor: Node, args: list[str], path: str = ""
    ) -> list[str]:
        """Run one conversion over root; what it reported."""
        report: list[str] = []
        conversions = Conversions(
            root,
            lambda *a: report.append(f"{a[0]} {a[1]}"),
            lambda s: s,
            lambda *a: [],
            lambda *a: "",
        )
        conversions.run(action, vendor, path or f"/{vendor.name}", args)
        return report

    def test_the_fiq_debugger_s_console_is_its_uart_on_its_pins(self) -> None:
        for status, lit in (('"okay"', True), ('"disabled"', False)):
            with self.subTest(status=status):
                uart = Node("serial@ff9f0000", ["uart0"], props=[Prop.of("status", '"disabled"')])
                fiq = Node(
                    "fiq-debugger",
                    props=[
                        Prop.of("rockchip,serial-id", "<0x00>"),
                        Prop.of("pinctrl-0", "<&uart0m0_xfer>"),
                        Prop.of("status", status),
                    ],
                )
                report = self.converted(Node("/", children=[uart]), "console", fiq, [])
                expected = '"okay"' if lit else '"disabled"'
                self.assertEqual(values(uart)["status"], expected)
                self.assertEqual("pinctrl-0" in values(uart), lit)
                self.assertEqual(report, [])

    def test_leds_take_their_roles_and_others_stay(self) -> None:
        timer = Prop.of("linux,default-trigger", '"timer"')
        leds = Node(
            "gpio-leds",
            ["leds"],
            children=[Node("work-green"), Node("work-red", props=[timer]), Node("net")],
        )
        args = ["work-green:power", "work-red:standby"]
        self.converted(Node("/", children=[leds]), "led-roles", Node("gpio-leds", ["leds"]), args)
        self.assertEqual([c.name for c in leds.children], ["led-power", "led-standby", "net"])
        power = values(leds.children[0])
        self.assertEqual((power["label"], power["default-state"]), ('"power"', '"on"'))
        self.assertIn("retain-state-shutdown", power)
        self.assertEqual(values(leds.children[1])["default-state"], '"off"')
        self.assertNotIn("linux,default-trigger", values(leds.children[1]))
        self.assertNotIn("label", values(leds.children[2]))

    def test_the_template_s_adc_key_is_the_recovery_button(self) -> None:
        for name in ("vol-up-key", "menu-key"):
            with self.subTest(key=name):
                key = Node(name, props=[Prop.of("linux,code", "<KEY_VOLUMEUP>")])
                keys = Node("adc-keys", ["adc_keys"], children=[key])
                vendor = Node("adc-keys", ["adc_keys"])
                self.converted(Node("/", children=[keys]), "adc-recovery", vendor, ["vol-up-key"])
                moved = name == "vol-up-key"
                self.assertEqual(key.name, "button-recovery" if moved else name)
                code = "<KEY_VENDOR>" if moved else "<KEY_VOLUMEUP>"
                self.assertEqual(values(key)["linux,code"], code)

    def test_a_reset_the_power_sequence_drives_takes_its_polarity(self) -> None:
        for line, expected in (("RK_PB2", "GPIO_ACTIVE_LOW"), ("RK_PB5", "GPIO_ACTIVE_HIGH")):
            with self.subTest(sequence=line):
                radio = Node(
                    "seekwcn_boot",
                    ["seekwcn_boot"],
                    props=[Prop.of("reset-gpios", "<&gpio3 RK_PB2 GPIO_ACTIVE_HIGH>")],
                )
                sequence = Node(
                    "sdio-pwrseq",
                    props=[Prop.of("reset-gpios", f"<&gpio3 {line} GPIO_ACTIVE_LOW>")],
                )
                root = Node("/", children=[radio, sequence])
                self.converted(root, "shared-reset", Node("seekwcn_boot", ["seekwcn_boot"]), [])
                self.assertEqual(values(radio)["reset-gpios"], f"<&gpio3 RK_PB2 {expected}>")

    def test_an_enabled_sai0_lends_its_pins_to_the_radio_s_power_sequence(self) -> None:
        for status, lent in (('"okay"', True), ('"disabled"', False)):
            with self.subTest(status=status):
                sequence = Node(
                    "sdio-pwrseq",
                    props=[
                        Prop.of("compatible", '"mmc-pwrseq-simple"'),
                        Prop.of("pinctrl-0", "<&wifi_enable_h>"),
                    ],
                )
                sai = Node(
                    "sai@ffb80000",
                    props=[Prop.of("pinctrl-0", "<&i2s0m0_lrck>"), Prop.of("status", status)],
                )
                report = self.converted(Node("/", children=[sequence]), "radio-pcm", sai, [])
                pins = "<&wifi_enable_h>, <&i2s0m0_lrck>" if lent else "<&wifi_enable_h>"
                self.assertEqual(values(sequence)["pinctrl-0"], pins)
                self.assertEqual(report, ["unsupported node sai@ffb80000"])

    def test_the_gpu_s_power_model_gives_it_a_dynamic_power_coefficient(self) -> None:
        model = Node("power-model", props=[Prop.of("dynamic-coefficient", "<724>")])
        for path, gives in (("/gpu@ff700000/power-model", True), ("/power-model", False)):
            with self.subTest(path=path):
                gpu = Node("gpu@ff700000")
                report = self.converted(Node("/", children=[gpu]), "gpu-power", model, [], path)
                self.assertEqual(
                    values(gpu).get("dynamic-power-coefficient"), "<724>" if gives else None
                )
                self.assertEqual(bool(report), not gives)

    def test_a_withheld_property_leaves_mainline_s_node_too(self) -> None:
        nodes, _ = rockchip()
        self.assertNotIn("operating-points-v2", values(nodes["/gpu@ff700000"]))
