"""tools/dtcx/devices.py: one block described twice, and devices that share registers."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools/dtcx"))
from devices import overlaps  # noqa: E402
from dts import Source, walk  # noqa: E402
from semdiff import Tree  # noqa: E402

# a vendor's SRAM left at the root while the imported dtsi adds it under /soc: the failed boot
TWICE = """/ {
\t#address-cells = <2>;
\t#size-cells = <2>;

\tmemory@0 {
\t\tdevice_type = "memory";
\t\treg = <0x0 0x0 0x0 0x80000000>;
\t};

\treserved-memory {
\t\t#address-cells = <2>;
\t\t#size-cells = <2>;
\t\tranges;

\t\tramoops@110000 {
\t\t\treg = <0x0 0x110000 0x0 0xf0000>;
\t\t};
\t};

\tsram@fe480000 {
\t\tcompatible = "mmio-sram";
\t\treg = <0x0 0xfe480000 0x0 0xc000>;
\t\t#address-cells = <1>;
\t\t#size-cells = <1>;
\t\tranges = <0x0 0x0 0xfe480000 0xc000>;

\t\trkvdec-sram@0 {
\t\t\treg = <0x0 0xc000>;
\t\t};
\t};

\tsoc {
\t\tcompatible = "simple-bus";
\t\t#address-cells = <2>;
\t\t#size-cells = <2>;
\t\tranges;

\t\tsram@fe480000 {
\t\t\tcompatible = "mmio-sram";
\t\t\treg = <0x0 0xfe480000 0x0 0xc000>;
\t\t\t#address-cells = <1>;
\t\t\t#size-cells = <1>;
\t\t\tranges = <0x0 0x0 0xfe480000 0xc000>;

\t\t\trkvdec-sram@0 {
\t\t\t\treg = <0x0 0xc000>;
\t\t\t};
\t\t};
\t};
};
"""
# what works on the vendor trees: a clock in the GRF's window, an IOMMU inside its master's, an
# HDMI node mapping a GPIO bank's window as its second, and a duplicate the vendor disabled
SHARED = """/ {
\t#address-cells = <1>;
\t#size-cells = <1>;

\tsyscon@ff300000 {
\t\tcompatible = "rockchip,rk3528-grf", "syscon";
\t\treg = <0xff300000 0x90000>;
\t};

\tmclkout-sai0@ff340014 {
\t\tcompatible = "rockchip,clk-out";
\t\treg = <0xff340014 0x4>;
\t};

\trga@ff850000 {
\t\tcompatible = "rockchip,rga2";
\t\treg = <0xff850000 0x1000>;
\t};

\tiommu@ff850f00 {
\t\tcompatible = "rockchip,iommu-v2";
\t\treg = <0xff850f00 0x100>;
\t};

\tgpio@ff610000 {
\t\tcompatible = "rockchip,gpio-bank";
\t\treg = <0xff610000 0x200>;
\t};

\thdmi@ff8d0000 {
\t\tcompatible = "rockchip,rk3528-dw-hdmi";
\t\treg = <0xff8d0000 0x20000 0xff610000 0x200>;
\t};

\tgpio-copy@ff610000 {
\t\tcompatible = "rockchip,gpio-bank";
\t\treg = <0xff610000 0x200>;
\t\tstatus = "disabled";
\t};
};
"""


def tree(text: str) -> Tree:
    root = Source.parse(text).root
    return Tree(dict(walk(root)) | {"/": root})


class DevicesTest(unittest.TestCase):
    def test_a_block_described_twice_across_layouts_is_reported_once(self) -> None:
        twice, _ = overlaps(tree(TWICE))
        self.assertEqual(
            twice, ["/soc/sram@fe480000 and /sram@fe480000 both claim 0xfe480000-0xfe48bfff"]
        )

    def test_reserved_memory_carved_from_the_memory_is_no_device(self) -> None:
        twice, shared = overlaps(tree(TWICE))
        self.assertFalse([line for line in twice + shared if "memory" in line])

    def test_devices_sharing_registers_are_listed_but_not_twice(self) -> None:
        twice, shared = overlaps(tree(SHARED))
        self.assertEqual(twice, [])
        self.assertCountEqual(
            shared,
            [
                "/mclkout-sai0@ff340014 and /syscon@ff300000 both claim 0xff340014-0xff340017",
                "/iommu@ff850f00 and /rga@ff850000 both claim 0xff850f00-0xff850fff",
                "/gpio@ff610000 and /hdmi@ff8d0000 both claim 0xff610000-0xff6101ff",
            ],
        )

    def test_the_windows_are_read_through_the_buses_ranges(self) -> None:
        sram = tree(TWICE).registers("/soc/sram@fe480000/rkvdec-sram@0")
        self.assertEqual(sram, [(0xFE480000, 0xC000)])


if __name__ == "__main__":
    unittest.main()
