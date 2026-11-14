"""Mainline nodes the vendor describes in its own nodes and properties: one conversion each, named by
the conf's action (vocabulary.BUILT), written into the translated tree once it is whole.
"""

from __future__ import annotations

import re
from collections.abc import Callable

from dts import Node, Prop, base_name, walk
from vocabulary import UNRESOLVED

REFERENCE = re.compile(r"&([\w-]+)")
NUMBER = re.compile(r"^(0x[0-9a-fA-F]+|[0-9]+)$")
SYSCONFIG_ON = 1000000  # sys_config's power_sply: 1000000 + mV, the leading 1 the rail's on
VBUS_MICROVOLT = 5000000  # USB's VBUS
SDIO_MICROVOLT = 3300000  # an SDIO card's supply
MMC_VDD_33_34 = 0x200000  # the OCR bit for a card at 3.3 V
NSEC_PER_SEC = 1000000000
# what aml_slot reads, and what only the vendor's driver does: its pin names for debug, its
# minimum clock and request size, which meson-gx-mmc sets from its own limits, and the card class
# it probes for, which mainline's core finds by probing
SLOT_READ = {"ocr_avail", "f_max", "caps", "phandle", "linux,phandle"}
SLOT_DRIVER = {"pinname", "f_min", "max_req_size", "card_type"}
# what aml_pwrseq reads, and what only the vendor's Wi-Fi driver does: its device name, Broadcom
# DHD's static buffers, and the host-wake line and its interrupt, an out-of-band wake mainline's
# SDIO drivers do not take
WIFI_READ = {"compatible", "status", "power_on_pin", "pinctrl-names", "pinctrl-0"}
WIFI_DRIVER = {"dev_name", "dhd_static_buf", "interrupt_pin", "interrupts", "irq_trigger_type"}
# what aml_32k reads of a channel, and its duty, a half period, which pwm-clock always runs
PWM_TURN = {"pwms", "times", "duty-cycle"}
POLARITY = {"GPIO_ACTIVE_HIGH": "GPIO_ACTIVE_LOW", "GPIO_ACTIVE_LOW": "GPIO_ACTIVE_HIGH"}
GPIO_ACTIVE = {"high": "GPIO_ACTIVE_HIGH", "low": "GPIO_ACTIVE_LOW"}
GPIO_PULL = {1: "GPIO_PULL_UP", 2: "GPIO_PULL_DOWN"}  # sunxi's pull cell
USB_PORT_TYPE = {0: "peripheral", 1: "host", 2: "otg"}


def gpio(value: str, active: str, pull: bool = False) -> str:
    """A vendor gpio, <&pio bank pin mux pull drive data>, as mainline's <&pio bank pin flags>: the
    polarity the binding gives it, which the vendor's cells do not carry; with pull, the vendor's
    pull cell as a pull flag."""
    cells = value.strip("<>").split()
    flags = [GPIO_ACTIVE[active]]
    if pull and int(cells[4], 0) in GPIO_PULL:
        flags.append(GPIO_PULL[int(cells[4], 0)])
    spelled = flags[0] if len(flags) == 1 else f"({' | '.join(flags)})"
    return f"<{cells[0]} {int(cells[1], 0)} {int(cells[2], 0)} {spelled}>"


def number(value: str) -> int:
    """A one-cell value, <n> or n, as a number."""
    return int(value.strip("<>").split()[0], 0)


def okay(node: Node) -> bool:
    status = node.prop("status")
    return status is None or "okay" in status.value


def enabled(node: Node) -> None:
    node.props = [p for p in node.props if p.name != "status"] + [Prop.of("status", '"okay"')]


def fixed(microvolt: int) -> list[Prop]:
    return [
        Prop.of("regulator-min-microvolt", f"<{microvolt}>"),
        Prop.of("regulator-max-microvolt", f"<{microvolt}>"),
    ]


class Conversions:
    """The conversions, run over the translated root; what one cannot decide goes to report."""

    def __init__(
        self,
        root: Node,
        report: Callable[[str, str, str], None],
        relabel: Callable[[str], str],
        clocks: Callable[[Node, str, str], list[Prop]],
        revalued: Callable[[str, str], str],
    ) -> None:
        self.root, self.report, self.relabel, self.clocks = (root, report, relabel, clocks)
        self.revalued = revalued
        self.nodes = [root, *(n for _, n in walk(root))]
        self.by_label = {label: node for node in self.nodes for label in node.labels}
        self.cards: list[tuple[Node, Node, str]] = []  # (SDIO host, vendor wlan node, path)
        self.supplied: list[tuple[str, str]] = []  # (rail label, its consumer's label)
        self.sleep_clock: str = ""  # the label of a 32 kHz clock built for a Wi-Fi power sequence
        self.bluetooth: tuple[list[str], str, str] | None = None  # (labels, reset gpio, path)
        self.bluetooth_bus: tuple[str, str] | None = None  # (UART label, vendor wake gpio)

    def run(self, action: str, fnode: Node, path: str, args: list[str]) -> None:
        conversions: dict[str, Callable[[Node, str, list[str]], None]] = {
            "pwrseq": self.pwrseq,
            "vbus": self.vbus,
            "enable": self.enable,
            "boot-voltage": self.boot_voltage,
            "leds": self.leds,
            "hdmi-connector": self.hdmi_connector,
            "bluetooth-reset": self.bluetooth_reset,
            "bluetooth-uart": self.bluetooth_uart,
            "bank-bias": self.bank_bias,
            "recovery-key": self.recovery_key,
            "supply": self.supply,
            "aml-slot": self.aml_slot,
            "aml-pwrseq": self.aml_pwrseq,
            "aml-32k": self.aml_32k,
            "cec": self.cec,
        }
        conversions[action](fnode, path, args)

    def add(self, node: Node, to_label: str, prop: Prop) -> None:
        self.root.children.append(node)
        target = self.by_label.get(to_label)
        if target is None:
            self.report(UNRESOLVED, f"node {node.name}: no {to_label} to point at it", "/")
        else:
            target.props.append(prop)

    def pwrseq(self, fnode: Node, path: str, args: list[str]) -> None:
        """The vendor's wlan node as mmc-pwrseq-simple: wlan_regon held low keeps the chip in reset,
        its 32 kHz clock through the clock vocabulary, fed from args (a parent) where given, on the
        MMC bus wlan_busnum names, which holds a soldered card: non-removable."""
        regon, bus = fnode.prop("wlan_regon"), fnode.prop("wlan_busnum")
        if regon is None or bus is None:
            self.report(UNRESOLVED, "node wlan: no wlan_regon or wlan_busnum", path)
            return
        props = [
            Prop.of("compatible", '"mmc-pwrseq-simple"'),
            *self.clocks(fnode, path, "ext_clock"),
        ]
        for name in ("pinctrl-names", "pinctrl-0"):
            state = fnode.prop(name)
            if state is not None:
                props.append(Prop.of(name, self.relabel(state.value)))
        clock = next((p for p in props if p.name == "clocks"), None)
        if args and clock is not None:
            props.append(Prop.of("assigned-clocks", clock.value))
            props.append(Prop.of("assigned-clock-parents", f"<{' '.join(args)}>"))
        props.append(Prop.of("reset-gpios", self.relabel(gpio(regon.value, "low"))))
        bus_label = f"mmc{int(bus.value.strip('<>'), 0)}"
        pwrseq = Prop.of("mmc-pwrseq", "<&wifi_pwrseq>")
        self.add(Node("pwrseq", ["wifi_pwrseq"], [], props), bus_label, pwrseq)
        host = self.by_label.get(bus_label)
        if host is not None and host.prop("non-removable") is None:
            host.props.append(Prop.of("non-removable"))
        if host is not None and not any(c.name == "wifi@1" for c in host.children):
            # the card's function 1, which an ethernetN alias names for U-Boot's stable MAC
            host.children.append(Node("wifi@1", ["sdio_wifi"], [], [Prop.of("reg", "<1>")]))
        if host is not None and host.prop("vmmc-supply") is None:
            self.cards.append((host, fnode, path))

    def supply(self, fnode: Node, path: str, args: list[str]) -> None:
        """A consumer's supply the vendor's PMIC fixes by design, args: the consumer's label, the
        supply property, the rail's label; the rail then held to the consumer's OPPs."""
        consumer, name, rail = args
        target = self.by_label.get(consumer)
        if target is None or rail not in self.by_label:
            self.report(UNRESOLVED, f"supply {name}: no {consumer} or {rail}", path)
            return
        target.props.append(Prop.of(name, f"<&{rail}>"))
        self.supplied.append((rail, consumer))

    def finish(self) -> None:
        """What reads the rails' final ranges, so runs once every conversion set them; the Wi-Fi
        power sequence's sleep clock, built from another vendor node; and the Bluetooth node,
        from two."""
        for host, fnode, path in self.cards:
            self.card_supply(host, fnode, path)
        if self.bluetooth is not None:
            self.bluetooth_node(*self.bluetooth)
        pwrseq = self.by_label.get("wifi_pwrseq")
        if pwrseq is not None and self.sleep_clock:
            pwrseq.props += [
                Prop.of("clocks", f"<&{self.sleep_clock}>"),
                Prop.of("clock-names", '"ext_clock"'),
            ]

    def bluetooth_node(self, labels: list[str], reset: str, path: str) -> None:
        """A UART-attached chip's Bluetooth node on the vendor's UART, its reset and wake lines for
        its driver to hold; the board's patch names the chip."""
        uart = self.by_label.get(self.bluetooth_bus[0]) if self.bluetooth_bus else None
        if uart is None or self.bluetooth_bus is None:
            self.report(UNRESOLVED, "bt_rst_n: no UART the vendor's btlpm names", path)
            return
        props = [Prop.of("reset-gpios", reset)]
        if self.bluetooth_bus[1]:
            props.append(Prop.of("device-wakeup-gpios", gpio(self.bluetooth_bus[1], "high")))
        uart.children.append(Node("bluetooth", labels, [], props))

    def aml_slot(self, fnode: Node, path: str, args: list[str]) -> None:
        """An Amlogic slot node, its host's settings for the vendor's driver, as mainline's on the
        host args[0] names: ocr_avail at 3.3 V as the card's supply, which mainline's host reads its
        voltages from, and its signalling too, the vendor describing no switch; f_max as the
        host's max-frequency where lower; each cap through the conf's caps values."""
        host = self.by_label.get(args[0])
        if host is None:
            self.report(UNRESOLVED, f"slot {fnode.name}: no host {args[0]}", path)
            return
        ocr = fnode.prop("ocr_avail")
        if ocr is not None and not number(ocr.value) & MMC_VDD_33_34:
            self.report(UNRESOLVED, f"slot ocr_avail {ocr.value}: a card not at 3.3 V", path)
        elif ocr is not None:
            rail = self.card_rail()
            for name in ("vmmc-supply", "vqmmc-supply"):
                if host.prop(name) is None:
                    host.props.append(Prop.of(name, f"<&{rail}>"))
        limit, have = fnode.prop("f_max"), host.prop("max-frequency")
        if limit is not None and (have is None or number(limit.value) < number(have.value)):
            host.props = [p for p in host.props if p.name != "max-frequency"]
            host.props.append(Prop.of("max-frequency", limit.value))
        caps = fnode.prop("caps")
        for cap in re.findall(r'"([^"]*)"', self.revalued("caps", caps.value) if caps else ""):
            if cap.startswith("MMC_"):
                self.report(UNRESOLVED, f"slot cap {cap}", path)
            elif cap != "-" and host.prop(cap) is None:
                host.props.append(Prop.of(cap))
        for prop in fnode.props:
            if prop.name not in SLOT_READ | SLOT_DRIVER:
                self.report(UNRESOLVED, f"slot property {prop.name}", f"{path} = {prop.value}")

    def card_rail(self) -> str:
        """The card's 3.3 V rail, a fixed regulator, written once."""
        label = "vcc_3v3"
        if label not in self.by_label:
            props = [
                Prop.of("compatible", '"regulator-fixed"'),
                Prop.of("regulator-name", '"VCC_3V3"'),
                *fixed(SDIO_MICROVOLT),
                Prop.of("regulator-always-on"),
            ]
            node = Node("regulator-vcc-3v3", [label], [], props)
            self.root.children.append(node)
            self.by_label[label] = node
        return label

    def aml_pwrseq(self, fnode: Node, path: str, args: list[str]) -> None:
        """Amlogic's aml_wifi as mmc-pwrseq-simple on the SDIO host args[0] names: power_on_pin
        at its inactive level keeps the radio off, so it is the sequence's reset, of the opposite
        polarity, and the vendor's pin state, which muxes the 32 kHz clock out, its default."""
        power = fnode.prop("power_on_pin")
        if power is None:
            self.report(UNRESOLVED, "node aml_wifi: no power_on_pin", path)
            return
        reset = re.sub(r"GPIO_ACTIVE_(HIGH|LOW)", lambda m: POLARITY[m.group(0)], power.value)
        props = [Prop.of("compatible", '"mmc-pwrseq-simple"'), Prop.of("reset-gpios", reset)]
        for prop in fnode.props:
            if prop.name not in WIFI_READ | WIFI_DRIVER | {"phandle", "linux,phandle"}:
                self.report(UNRESOLVED, f"aml_wifi property {prop.name}", f"{path} = {prop.value}")
        state = fnode.prop("pinctrl-0")
        if state is not None:
            props += [Prop.of("pinctrl-names", '"default"'), Prop.of("pinctrl-0", state.value)]
        node = Node("sdio-pwrseq", ["wifi_pwrseq"], [], props)
        self.add(node, args[0], Prop.of("mmc-pwrseq", "<&wifi_pwrseq>"))
        self.by_label["wifi_pwrseq"] = node

    def aml_32k(self, fnode: Node, path: str, args: list[str]) -> None:
        """Amlogic's wifi_pwm_conf, the radio's 32.768 kHz sleep clock as PWM channels taking turns,
        each for its times periods, as one pwm-clock at their weighted mean period: mainline's
        pwm-clock runs one channel at one period."""
        turns = [(c.prop("pwms"), c.prop("times")) for c in fnode.children]
        if not turns or any(pwms is None or times is None for pwms, times in turns):
            self.report(UNRESOLVED, "wifi_pwm_conf: a channel with no pwms or times", path)
            return
        for turn in fnode.children:
            for prop in turn.props:
                if prop.name not in PWM_TURN | {"phandle", "linux,phandle"}:
                    self.report(UNRESOLVED, f"wifi_pwm_conf property {prop.name}", path)
        cells = [(p.value.strip("<>").split(), number(t.value)) for p, t in turns if p and t]
        periods = sum(int(c[2]) * n for c, n in cells)
        mean = round(periods / sum(n for _, n in cells))
        first = cells[0][0]
        props = [
            Prop.of("compatible", '"pwm-clock"'),
            Prop.of("#clock-cells", "<0>"),
            Prop.of("clock-frequency", f"<{round(NSEC_PER_SEC / mean)}>"),
            Prop.of("pwms", f"<{first[0]} {first[1]} {mean} {first[3]}>"),
        ]
        self.root.children.append(Node("wifi32k", ["wifi32k"], [], props))
        self.sleep_clock = "wifi32k"

    def card_supply(self, host: Node, fnode: Node, path: str) -> None:
        """An SDIO card's vmmc-supply, which mainline's MMC host reads its voltage range from: with
        wlan_power empty the vendor powers the card from no switched rail, so from the one rail
        held at 3.3 V, an SDIO card's supply."""
        named = fnode.prop("wlan_power")
        if named is not None and named.value:
            self.report(UNRESOLVED, f"wlan_power {named.value}: the card's switched rail", path)
            return
        held = self.held(SDIO_MICROVOLT)
        if len(held) != 1:
            self.report(UNRESOLVED, f"SDIO card supply: {len(held)} rails at 3.3 V", path)
            return
        host.props.append(Prop.of("vmmc-supply", f"<&{held[0].labels[0]}>"))

    def held(self, microvolt: int) -> list[Node]:
        """The labelled regulators held at exactly microvolt."""
        return [
            n
            for n in self.nodes
            if n.labels
            and {p.value for p in n.props if p.name.startswith("regulator-m")} == {f"<{microvolt}>"}
        ]

    def recovery_key(self, fnode: Node, path: str, args: list[str]) -> None:
        """sys_config's key_boot_recovery, the button boot0 reads for recovery, as a gpio-keys
        KEY_VENDOR at the level args[0] names pressed: disabled, and a question, since the EVB's
        template sets it on boards with no button; a board with one enables it."""
        used, key = fnode.prop("recovery_key_used"), fnode.prop("recovery_key")
        if used is None or key is None or not int(used.value.strip("<>"), 0):
            return
        props = [
            Prop.of("label", '"recovery"'),
            Prop.of("linux,code", "<KEY_VENDOR>"),
            Prop.of("gpios", self.relabel(gpio(key.value, args[0]))),
        ]
        keys = [Prop.of("compatible", '"gpio-keys"'), Prop.of("status", '"disabled"')]
        self.root.children.append(Node("gpio-keys", [], [], keys, [Node("key", [], [], props)]))
        self.report(UNRESOLVED, "recovery key: is one fitted?", path)

    def bank_bias(self, fnode: Node, path: str, args: list[str]) -> None:
        """sys_config's gpio_bias, p<bank>_bias = <mV>, the voltage boot0 sets a pin bank's I/O to,
        as that bank's vcc-p<bank>-supply: mainline's pinctrl sets the bank's bias from it."""
        for prop in fnode.props:
            bank = re.fullmatch(r"p([a-z])_bias", prop.name)
            if bank:
                self.bank_supply(bank.group(1), int(prop.value.strip("<>"), 0), path)

    def bank_supply(self, bank: str, millivolt: int, path: str) -> None:
        """vcc-p<bank>-supply on the pin controller: the one regulator held at millivolt."""
        held = self.held(millivolt * 1000)
        pio = self.by_label.get("pio")
        if len(held) != 1 or pio is None:
            self.report(UNRESOLVED, f"p{bank} at {millivolt} mV: {len(held)} rails hold it", path)
            return
        name = f"vcc-p{bank}-supply"
        pio.props = [p for p in pio.props if p.name != name] + [
            Prop.of(name, f"<&{held[0].labels[0]}>")
        ]

    def group_bank_1v8(self, group: str, path: str) -> None:
        """The bank of a pin group a host runs at 1.8 V, the vendor's sdio-used-1v8."""
        node = self.by_label.get(group)
        listed = node.prop("pins") if node else None
        pins = re.findall(r'"P([A-Z])\d+"', listed.value) if listed else []
        if len(set(pins)) != 1:
            self.report(UNRESOLVED, f"sdio-used-1v8: no one bank in {group}", path)
            return
        self.bank_supply(pins[0].lower(), 1800, path)

    def bluetooth_reset(self, fnode: Node, path: str, args: list[str]) -> None:
        """The vendor rfkill's reset line, args[0], held low for reset and raised to leave it: kept
        for the Bluetooth node finish writes; no line, no node."""
        line = fnode.prop(args[0])
        if line is not None and line.value.startswith("<"):
            cells = line.value.strip("<>").split()
            reset = f"<&pio {int(cells[1], 0)} {int(cells[2], 0)} GPIO_ACTIVE_LOW>"
            self.bluetooth = (fnode.labels[:1], reset, path)

    def bluetooth_uart(self, fnode: Node, path: str, args: list[str]) -> None:
        """The vendor low-power driver's UART and its wake line, high to keep the chip awake, for
        the Bluetooth node finish writes; its host wake line a question."""
        index, wake = fnode.prop("uart_index"), fnode.prop("bt_wake")
        if index is not None:
            self.bluetooth_bus = (f"uart{number(index.value)}", wake.value if wake else "")
        if fnode.prop("bt_hostwake") is not None:
            self.report(
                UNRESOLVED, "bt_hostwake: the chip's host wake, which hci_h4 takes no IRQ of", path
            )

    def opp_range(self, rail: str, opps: str) -> None:
        """A regulator its consumer's OPPs scale, held to the voltages those OPPs name, every speed
        bin's: the chip's span the vendor writes would let a request outside them through."""
        table = next((n for _, n in walk(self.root) if opps in n.labels), None)
        target = next((n for _, n in walk(self.root) if rail in n.labels), None)
        if table is None or target is None:
            self.report(UNRESOLVED, f"opp-range: no {opps} or {rail}", "/")
            return
        volts = [
            int(cell, 0)
            for row in table.children
            for p in row.props
            if p.name.startswith("opp-microvolt")
            for cell in p.value.strip("<>").split()
        ]
        if volts:
            target.props = [p for p in target.props if not p.name.startswith("regulator-m")]
            target.props += [
                Prop.of("regulator-min-microvolt", f"<{min(volts)}>"),
                Prop.of("regulator-max-microvolt", f"<{max(volts)}>"),
            ]

    def enable(self, fnode: Node, path: str, args: list[str]) -> None:
        """A vendor node standing for blocks mainline's dtsi describes disabled: each block args
        names enabled, as the board's vendor tree has it."""
        for label in args:
            target = self.by_label.get(label)
            if target is None:
                self.report("unknown", f"enable {label}: no such label in the translation", path)
                continue
            enabled(target)

    def boot_voltage(self, fnode: Node, path: str, args: list[str]) -> None:
        """sys_config's power_sply, the voltage the vendor's boot chain holds each PMIC rail at,
        as that regulator's fixed range; a rail a CPU's OPPs scale is left to them."""
        scaled = {
            ref
            for node in self.nodes
            for p in node.props
            if p.name == "cpu-supply"
            for ref in REFERENCE.findall(p.value)
        }
        for prop in fnode.props:
            rail = prop.name.removesuffix("_vol")
            value = NUMBER.match(prop.value.strip("<>"))
            if rail == prop.name or value is None or int(value.group(1), 0) < SYSCONFIG_ON:
                continue
            target = next((n for n in self.nodes if n.name == rail and n.labels), None)
            if target is None:
                self.report(UNRESOLVED, f"power_sply {prop.name}: no {rail} regulator", path)
                continue
            if set(target.labels) & scaled:
                continue
            microvolt = (int(value.group(1), 0) - SYSCONFIG_ON) * 1000
            target.props = [p for p in target.props if not p.name.startswith("regulator-m")]
            target.props += fixed(microvolt)

    def leds(self, fnode: Node, path: str, args: list[str]) -> None:
        """sys_config's gpio_para LEDs as gpio-leds: normal_led and standby_led name the pins, their
        *_light the level that lights them; labels power and standby, which the shared LED hooks
        drive and keep through suspend and shutdown (docs/bring-up/trees.md)."""
        leds: list[Node] = []
        roles = (("normal", "power", "POWER", "on"), ("standby", "standby", "STANDBY", "off"))
        for index, (role, label, function, state) in enumerate(roles):
            pin_name, light = fnode.prop(f"{role}_led"), fnode.prop(f"{role}_led_light")
            pin = fnode.prop(pin_name.value.strip('"')) if pin_name else None
            if pin is None or light is None:
                continue
            active = "high" if int(light.value.strip("<>"), 0) else "low"
            props = [
                Prop.of("label", f'"{label}"'),
                Prop.of("function", f"LED_FUNCTION_{function}"),
                Prop.of("gpios", self.relabel(gpio(pin.value, active))),
                Prop.of("default-state", f'"{state}"'),
                Prop.of("retain-state-suspended"),
                Prop.of("retain-state-shutdown"),
            ]
            leds.append(Node(f"led-{index}", [], [], props))
        if leds:
            compatible = [Prop.of("compatible", '"gpio-leds"')]
            self.root.children.append(Node("leds", [], [], compatible, leds))

    def hdmi_connector(self, fnode: Node, path: str, args: list[str]) -> None:
        """An enabled HDMI controller's type A socket, as mainline's hdmi-connector on the output
        port args[1] names: the DRM bridge chain ends at a connector node. The controller args[0]
        names is enabled, where the vendor describes it in a node of its own, with the vendor's
        pin states for hot-plug and DDC as its default."""
        controller, port = self.by_label.get(args[0]), self.by_label.get(args[1])
        if controller is None or port is None:
            self.report("unknown", f"hdmi-connector: no {args[0]} or {args[1]}", path)
            return
        if not okay(controller):
            enabled(controller)
        states = [p.value for p in fnode.props if re.fullmatch(r"pinctrl-\d+", p.name)]
        if states and controller.prop("pinctrl-0") is None:
            controller.props += [
                Prop.of("pinctrl-names", '"default"'),
                Prop.of("pinctrl-0", ", ".join(states)),
            ]
        out = Prop.of("remote-endpoint", "<&hdmi_con_in>")
        port.children.append(Node("endpoint", ["hdmi_out_con"], [], [out]))
        back = Prop.of("remote-endpoint", "<&hdmi_out_con>")
        socket = Node("port", [], [], [], [Node("endpoint", ["hdmi_con_in"], [], [back])])
        props = [Prop.of("compatible", '"hdmi-connector"'), Prop.of("type", '"a"')]
        self.root.children.append(Node("connector", [], [], props, [socket]))

    def cec(self, fnode: Node, path: str, args: list[str]) -> None:
        """A vendor CEC node, enabled, as mainline's CEC controller args[0] names enabled on the
        vendor's pin state, and bound to the HDMI controller args[1] names, whose hot-plug and
        physical address it follows."""
        controller, hdmi = self.by_label.get(args[0]), self.by_label.get(args[1])
        if controller is None or hdmi is None:
            self.report("unknown", f"cec: no {args[0]} or {args[1]}", path)
            return
        if not okay(fnode):
            return
        enabled(controller)
        states = [p.value for p in fnode.props if re.fullmatch(r"pinctrl-\d+", p.name)]
        if states and controller.prop("pinctrl-0") is None:
            controller.props += [
                Prop.of("pinctrl-names", '"default"'),
                Prop.of("pinctrl-0", ", ".join(states)),
            ]
        controller.props.append(Prop.of("hdmi-phandle", f"<&{args[1]}>"))

    def vbus(self, fnode: Node, path: str, args: list[str]) -> None:
        """A vendor usbc port's usb_drv_vbus_gpio as the fixed 5 V regulator mainline's USB PHY
        takes for that port; usb_port_type as the OTG port's dr_mode; the PHY enabled where a port
        is, since the vendor describes the PHY by its ports."""
        port = re.sub(r"\D", "", base_name(fnode))  # usbc1: port 1
        phy = self.by_label.get("usbphy")
        if phy is not None and okay(fnode):
            enabled(phy)
        drive = fnode.prop("usb_drv_vbus_gpio")
        if drive is not None and drive.value.startswith("<"):
            name = f"usb{port}-vbus"
            props = [
                Prop.of("compatible", '"regulator-fixed"'),
                Prop.of("regulator-name", f'"{name}"'),
            ]
            props += fixed(VBUS_MICROVOLT)
            props += [Prop.of("gpio", self.relabel(gpio(drive.value, "high")))]
            props += [Prop.of("enable-active-high")]
            supply = Prop.of(f"usb{port}_vbus-supply", f"<&reg_usb{port}_vbus>")
            self.add(Node(name, [f"reg_usb{port}_vbus"], [], props), "usbphy", supply)
        kind = fnode.prop("usb_port_type")
        target = self.by_label.get("usbotg")
        if kind is not None and port == "0" and target is not None:
            mode = USB_PORT_TYPE.get(int(kind.value.strip("<>"), 0))
            if mode:
                target.props.append(Prop.of("dr_mode", f'"{mode}"'))


def speed_bins(table: Node) -> None:
    """A table whose rows serve speed bins (opp-supported-hw) in OPP v2's form for them: one row a
    frequency, the bins' mask, a voltage per bin as opp-microvolt-speed<bin>, which the cpufreq
    driver names by bin. A row no bin selects says nothing and goes."""
    rows: dict[str, list[tuple[Node, int]]] = {}
    for row in table.children:
        hz, mask = row.prop("opp-hz"), row.prop("opp-supported-hw")
        if hz is not None and mask is not None:
            rows.setdefault(hz.value, []).append((row, int(mask.value.strip("<>"), 0)))
    if not rows:
        return
    merged: list[Node] = []
    for hz, same in rows.items():
        volts: dict[int, str] = {}
        for row, bits in same:
            microvolt = row.prop("opp-microvolt")
            for speed in range(bits.bit_length()):
                if bits >> speed & 1 and microvolt is not None:
                    volts[speed] = microvolt.value
        if not volts:
            continue
        first = same[0][0]
        props = [Prop.of("opp-hz", hz)]
        props += [Prop.of(f"opp-microvolt-speed{s}", v) for s, v in sorted(volts.items())]
        props += [p for p in first.props if p.name not in ("opp-hz", "opp-supported-hw")]
        props = [p for p in props if p.name != "opp-microvolt"]
        props.append(Prop.of("opp-supported-hw", f"<0x{sum(1 << s for s in volts):02x}>"))
        merged.append(Node(f"opp-{hz.split('<')[1].strip('>')}", [], [], props))
    table.children = [c for c in table.children if c.prop("opp-supported-hw") is None] + merged


def opp_v2(label: str, value: str) -> Node:
    """A v1 operating-points list, <kHz uV> pairs, as the OPP v2 table it means: one opp node a
    pair, opp-hz in Hz, opp-microvolt as it is."""
    cells = [int(c, 0) for c in value.strip("<>").split()]
    rows = [
        Node(
            f"opp-{khz * 1000}",
            [],
            [],
            [Prop.of("opp-hz", f"/bits/ 64 <{khz * 1000}>"), Prop.of("opp-microvolt", f"<{uv}>")],
        )
        for khz, uv in sorted(zip(cells[::2], cells[1::2], strict=True))
    ]
    compatible = [Prop.of("compatible", '"operating-points-v2"')]
    return Node(f"opp-table-{label.split('_')[0]}", [label], [], compatible, rows)
