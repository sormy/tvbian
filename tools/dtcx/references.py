"""Which properties hold phandles, and where in their cells: the one model every tool here reads
— dtcx's renderer, semdiff's comparison, upstream's views — and that dtc's -P table
(patches/dtc) must agree with, a test checks. Which properties hold phandles is binding
knowledge: a value alone cannot tell, since a phandle is a small number like any other.
"""

from __future__ import annotations

import re
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from fnmatch import fnmatch
from typing import Protocol


class Valued(Protocol):
    @property
    def value(self) -> str: ...


class Provider(Protocol):
    """A node a phandle points at, as far as reading its specifier needs: its #-cells."""

    def prop(self, name: str) -> Valued | None: ...


CELL = re.compile(r"0x[0-9a-fA-F]+|\d+")
GROUP = re.compile(r"<([^>]*)>")
# what counts the cells after each phandle: the provider's #-cells property, or a fixed count, 0
# for a list of bare phandles
Layout = str | int
BARE = 0
REFERENCES: dict[str, Layout] = {
    "clocks": "#clock-cells",
    "assigned-clocks": "#clock-cells",
    "assigned-clock-parents": "#clock-cells",
    "resets": "#reset-cells",
    "phys": "#phy-cells",
    "dmas": "#dma-cells",
    "iommus": "#iommu-cells",
    "power-domains": "#power-domain-cells",
    "pwms": "#pwm-cells",
    "mboxes": "#mbox-cells",
    "sound-dai": "#sound-dai-cells",
    "thermal-sensors": "#thermal-sensor-cells",
    "cooling-device": "#cooling-cells",
    "io-channels": "#io-channel-cells",
    "interrupts-extended": "#interrupt-cells",
    "gpios": "#gpio-cells",
    "interrupt-parent": BARE,
    "remote-endpoint": BARE,
    "operating-points-v2": BARE,
    "memory-region": BARE,
    "nvmem-cells": BARE,
    "mmc-pwrseq": BARE,
    "hdmi-phandle": BARE,
    "ddc-i2c-bus": BARE,
    "interrupt-affinity": BARE,
    "next-level-cache": BARE,
    "cpu": BARE,
    "trip": BARE,
    "hwlocks": "#hwlock-cells",
    "phy-handle": BARE,
    "amlogic,canvas": BARE,
    "amlogic,ao-sysctrl": BARE,
    "shmem": BARE,
    "secure-monitor": BARE,
    "allwinner,sram": 1,
    "allwinner,pipelines": BARE,
    "allwinner,planes": BARE,
    "allwinner,plane-mapping": BARE,
    "allwinner,top": BARE,
    "syscon": BARE,
    "extcon": BARE,
    "audio-codec": BARE,
    "audio-cpu": 1,
    "gpio": "#gpio-cells",
    "gpio-ranges": 3,
    "pm_qos": BARE,
    "rockchip,codec": BARE,
    "rockchip,cpu": BARE,
    "rockchip,grf": BARE,
    "rockchip,sram": BARE,
    "rockchip,srv": BARE,
    "snps,axi-config": BARE,
    "snps,mtl-rx-config": BARE,
    "snps,mtl-tx-config": BARE,
    "connect": BARE,
    "cpu-idle-states": BARE,
    "devfreq-events": BARE,
    "mdio-parent-bus": BARE,
    "ports": BARE,
    "rockchip,pipe-grf": BARE,
    "rockchip,pipe-phy-grf": BARE,
    "rockchip,usbgrf": BARE,
}
# lists of fixed-size entries holding one phandle each: the cells an entry, the phandle's index
ENTRIES = {"rockchip,pins": (4, 3)}
PINCTRL = re.compile(r"pinctrl-\d+")
# a GPIO specifier by the names bindings give it: gpios, reset-gpios, the vendors' reset_gpio
GPIO = re.compile(r"(^|[-_])gpios?$")


@dataclass(frozen=True)
class Dialect:
    """A vendor's own reference properties, which no binding names, as patterns: its GPIO
    specifiers (BT,wake_host_irq, clk_pin) and its bare references. Global, they would be wrong:
    another dialect's key or map is a number."""

    gpio: frozenset[str] = frozenset()
    bare: tuple[str, ...] = ()
    numbers: tuple[str, ...] = ()  # properties known to hold no phandle, as patterns

    def numeric(self, name: str) -> bool:
        """Whether a property is known to hold numbers only: a value that equals some phandle is
        no reference in it."""
        return any_match(name, NUMBERS + self.numbers)

    def layouts(self, name: str, hog: bool = False) -> list[Layout]:
        """How a property's cells may hold phandles, the binding's first, then the dialect's: a
        vendor's pwms are bare phandles to nodes with no #pwm-cells, mainline's in the same
        base's trees <&pwm 5 2000 0>. None where it holds none: a hog's gpios are its own
        controller's pins."""
        if hog and name == "gpios":
            return []
        out: list[Layout] = []
        if name in REFERENCES:
            out.append(REFERENCES[name])
        if PINCTRL.fullmatch(name) or name.endswith("-supply") or any_match(name, self.bare):
            out.append(BARE)
        if GPIO.search(name) or any_match(name, self.gpio):
            out.append("#gpio-cells")
        return list(dict.fromkeys(out))

    def holds(self, name: str, hog: bool = False) -> bool:
        return name in ENTRIES or bool(self.layouts(name, hog))

    def decode(
        self, name: str, flat: list[int], targets: Mapping[int, Provider], hog: bool = False
    ) -> dict[int, int] | None:
        """Each phandle in a property's cells, by its index, with its argument count; {} for a
        property that holds none, and None for one that should but does not lay out, or lays
        out two ways: a cell no node has as its phandle where one belongs, a provider without
        its #-cells, an entry cut short. Never a phandle by a number's coincidence. A 0 is an
        empty entry."""
        if name in ENTRIES:
            size, at = ENTRIES[name]
            if len(flat) % size or any(flat[i] not in targets for i in range(at, len(flat), size)):
                return None
            return {i: 0 for i in range(at, len(flat), size)}
        layouts = self.layouts(name, hog)
        if not layouts:
            return {}
        # two layouts that both decode and disagree are a guess: <1 2> is one PWM with an
        # argument or two bare references
        readings = {
            tuple(found.items())
            for layout in layouts
            if (found := laid_out(layout, flat, targets)) is not None
        }
        return dict(readings.pop()) if len(readings) == 1 else None


def laid_out(
    layout: Layout, flat: list[int], targets: Mapping[int, Provider]
) -> dict[int, int] | None:
    """Each phandle in cells laid out so, with its argument count; None where they are not."""
    # a fixed count is the consumer's: allwinner,sram is <&sram 1> to the video engine, a bare
    # <&sram> to the thermal sensor, and a lone phandle can carry no arguments
    if isinstance(layout, int) and len(flat) == 1:
        layout = BARE
    out: dict[int, int] = {}
    i = 0
    while i < len(flat):
        if flat[i] == 0:
            i += 1
            continue
        target = targets.get(flat[i])
        if target is None:
            return None
        count = arguments(layout, target)
        if count is None or i + 1 + count > len(flat):
            return None
        out[i] = count
        i += 1 + count
    return out


STANDARD = Dialect()
# what a pin controller muxes, by pins or groups, and a vendor's own <vendor>,pins
PIN_GROUP_PROPS = ("pins", "groups", "function")


def muxes(names: Iterable[str]) -> bool:
    """Whether properties by these names mux pins."""
    return any(n in PIN_GROUP_PROPS or n.endswith(",pins") for n in names)


# standard properties of numbers, besides those a base names: a cell in one that equals a phandle
# is a coincidence, in any other a reference the model does not know yet
NUMBERS = (
    "interrupts",
    "reg",
    "ranges",
    "dma-ranges",
    "bus-range",
    "interrupt-map-mask",
    "#*-cells",
    "linux,code",
    "poll-interval",
    "dynamic-power-coefficient",
    "*,mclk-fs",
    "*cache-line-size",
    "*cache-sets",
    "*cache-size",
    "cache-level",
    "color",
    "function-enumerator",
    "opp-supported-hw",
    "dma-channels",
    "dma-requests",
    "*fifo-size",
)


def interrupt_map(
    flat: list[int], node: Provider, targets: Mapping[int, Provider]
) -> dict[int, int] | None:
    """Each mapping's parent in an interrupt-map, by its index, with the cells after it: a child
    unit address and interrupt by the node's #-cells, then the parent's unit address and
    interrupt by the parent's own, an absent #address-cells being none. None where the node or a
    parent lacks #interrupt-cells, a parent is no node, or a mapping is cut short."""
    interrupts = count(node, "#interrupt-cells")
    if interrupts is None:
        return None
    child = (count(node, "#address-cells") or 0) + interrupts
    out: dict[int, int] = {}
    start = 0
    while start < len(flat):
        at = start + child
        parent = targets.get(flat[at]) if at < len(flat) else None
        parent_interrupts = count(parent, "#interrupt-cells") if parent is not None else None
        if parent is None or parent_interrupts is None:
            return None
        width = (count(parent, "#address-cells") or 0) + parent_interrupts
        if at + 1 + width > len(flat):
            return None
        out[at] = width
        start = at + 1 + width
    return out


def count(node: Provider, name: str) -> int | None:
    found = node.prop(name)
    return cells(found.value)[0] if found is not None and cells(found.value) else None


def any_match(name: str, patterns: Iterable[str]) -> bool:
    return any(fnmatch(name, p) for p in patterns)


def arguments(layout: Layout, target: Provider) -> int | None:
    """The cells after a phandle: the provider's #-cells, a fixed count, or none."""
    if isinstance(layout, int):
        return layout
    return count(target, layout)


def cells(value: str) -> list[int]:
    return [int(c, 0) for group in GROUP.findall(value) for c in CELL.findall(group)]
