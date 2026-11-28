#!/usr/bin/env python3
"""A running box against the bring-up criteria, unattended: one sub-suite a bring-up phase.

On the box, as root, Python's standard library only; regression.py copies it there and runs it
detached, as a sub-suite may reload the Wi-Fi driver the session rides on:

    python3 box.py [--suite system,storage,...] [--iperf HOST] [--sleep SECONDS] [--soak SECONDS]

Every line is "key value"; a missing tool or device is a value, never a gap. The sub-suites, in
order, each named after the bring-up doc it measures:

    system     identity, boot, log, modules, devices and their inventory, firmware, packages,
               kernel baseline, RAM
    cpu        the CPU ladder with its voltages, under load: heat, throttling, trips (5 min)
    storage    each MMC bus's mode and errors, the root device, fio as storage.md writes it
    network    Ethernet's PHY and link; each radio driver mode: link, bands, regions, throughput
               idle and loaded, module reloads; each Bluetooth controller: flags, a scan
    display    connectors, planes, CEC, video devices
    audio      each card at 44.1 and 48 kHz, 8 channels, routes left disabled
    gpu        the full glmark2 suite off-screen, every scene's frame rate
    input      inputs named, the IR keymap, USB topology, buttons, LEDs
    power      wake sources, sleep states, s2idle past the watchdog and back, the RTC
    soak       CPU, memory, GPU, storage and Wi-Fi together, then the errors they left
"""

from __future__ import annotations

import argparse
import contextlib
import ctypes
import glob
import hashlib
import os
import random
import re
import shutil
import signal
import socket
import struct
import subprocess
import sys
import tempfile
import time
from collections.abc import Callable, Iterator
from dataclasses import dataclass, replace
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from display import SINKS, hdr_edid, hdr_sink  # noqa: E402

Line = tuple[str, str]
NONE = "none"
# Wi-Fi drivers with more than one mode: the module parameters to load each with, and whether
# Bluetooth, which rides on the Wi-Fi firmware, exists in it
MODES: dict[str, list[tuple[str, bool]]] = {
    "atbm6031": [("wifi_bt_comb=0", False), ("wifi_bt_comb=1", True)]
}
# the modules this box's devices ask for, by modalias
MODALIAS_MODULES = (
    "cat /sys/bus/*/devices/*/modalias 2>/dev/null | sort -u | xargs -r -n1 modprobe -qR"
)
# the device classes a kernel must offer as many of as the board's own: each a glob, the name its stem
INVENTORY = {
    "net": "/sys/class/net/*",
    "bluetooth": "/sys/class/bluetooth/hci*",
    "input": "/sys/class/input/input*",
    "sound": "/proc/asound/card[0-9]*",
    "leds": "/sys/class/leds/*",
    "thermal": "/sys/class/thermal/thermal_zone*",
    "cooling": "/sys/class/thermal/cooling_device*",
    "devfreq": "/sys/class/devfreq/*",
    "drm": "/sys/class/drm/card*-*",
    "rfkill": "/sys/class/rfkill/rfkill*",
    "rtc": "/sys/class/rtc/rtc*",
    "watchdog": "/sys/class/watchdog/watchdog*",
    "hwmon": "/sys/class/hwmon/hwmon*",
}
# each sample format played at this rate, which every card here takes
FORMAT_RATE = 48000
# the rates a datasheet's audio interfaces quote; a play this short only asks whether one is taken
AUDIO_RATES = (
    8000,
    11025,
    12000,
    16000,
    22050,
    24000,
    32000,
    44100,
    48000,
    64000,
    88200,
    96000,
)
AUDIO_RATES += (176400, 192000)
RATE_PROBE_SAMPLES = 64
# a display manager starting at boot takes the screen from the checks mid-run: none may
DISPLAY_MANAGERS = ("greetd.service", "gdm.service", "lightdm.service", "sddm.service")
STARTUP_WAIT_S = 300  # how long the system step waits for systemd's startup to finish
COOL_SAMPLE_S = 10  # how often the idle temperature is read while the box cools
COOL_STEADY_S = 60  # the idle temperature counts once this long passes with no lower reading
COOL_WAIT_S = 300  # the longest the box is given to cool from the step before
LOAD_SAMPLE_S = 5  # how often the load check reads the clock and the heat
# the DDR controller's devfreq, as each kernel names it
DDR_DEVFREQ = ("dmc", "memory-controller")
# IR receivers, by compatible: a board whose tree enables one must give it a node
IR_RECEIVERS = ("sun6i-a31-ir", "meson-ir", "meson-gxbb-ir", "remotectl")
# the tools this suite installs, which the image itself does not ship
TEST_TOOLS = {
    "glmark2-es2-drm",
    "iperf3",
    "iputils-ping",
    "ffmpeg9",
    "drm-info",
    "cec-utils",
    "fio",
    "stress-ng",
    "ir-keytable",
    "v4l-utils",
    "bluez",
    # the VA suite's clients
    "vainfo",
    "ffmpeg",
    "mpv",
    "gstreamer1.0-tools",
    "gstreamer1.0-plugins-bad",
}
# tree nodes that never get a driver of their own: register banks, buses' QoS, the arch timer
DRIVERLESS = ("syscon", "qos", "timer", "opp-", "psci", "shmem", "debug")
# a SoC's crypto engine, not the CPU's instructions (the -ce drivers alone)
CRYPTO_ENGINE = r"sun8i-ce|^rk|-rk2$|meson|gxl-crypto"
# RSA through an engine: fresh keys a size, each one's PKCS#1 SHA-256 signature verified by
# OpenSSL, then signs timed at one size beside the CPU's; routed by priority, generic's being 100
RSA_BITS = (1024, 2048, 4096)
RSA_KEYS = 4
RSA_TIMED_BITS = 2048
RSA_SIGNS = 10
RSA_ROUTE_PRIORITY, RSA_AWAY_PRIORITY = 300, 10
RSA_SIGN_INFO = b"enc=pkcs1 hash=sha256"
RSA_DIGEST_BYTES = 32
# NETLINK_CRYPTO's messages and attribute, and the arm64 keyring syscalls
NETLINK_CRYPTO, CRYPTO_MSG_DELALG, CRYPTO_MSG_UPDATEALG, CRYPTOCFGA_PRIORITY_VAL = 21, 0x11, 0x12, 1
NLM_F_REQUEST, NLM_F_ACK = 1, 4
SYS_ADD_KEY, SYS_KEYCTL = 217, 219
KEYCTL_UNLINK, KEYCTL_PKEY_SIGN = 9, 27
# struct keyctl_pkey_params: key, input length, output length, seven spare words that must be 0
KEYCTL_PKEY_PARAMS = "iII7I"
KEYCTL_PKEY_SPARE = 7
KEY_SPEC_PROCESS_KEYRING = -2
# tcrypt's speed test for each /proc/crypto type the engines serve: in the kernel, as the
# userspace socket refuses an async driver
TCRYPT_MODES = {"skcipher": 600, "ahash": 400, "shash": 400}
# a packet's request and a page, among the sizes tcrypt times; a page is what bulk users ask
BENCH_BYTES = (256, 4096)
JUDGED_BYTES = 4096
TCRYPT_MARK = "box.py tcrypt"
HMAC_KEY_BYTES = 32
# a debug build's knob: the next hash times out (1) or wedges the engine (2)
FAIL_NEXT_HASH = Path("/sys/module/rk_crypto2/parameters/fail_next_job")
HASH_FAILURES = {"timeout": "1", "wedge": "2"}
# a default this close to the fastest is as good: the runs' noise
FASTEST_SLACK = 0.9
# family.md's baseline: what every kernel config must set
CONFIG = (
    "CONFIG_FONT_TER16x32=y",
    "CONFIG_SOFTLOCKUP_DETECTOR=y",
    "CONFIG_PSTORE_RAM=y",
    "CONFIG_WATCHDOG=y",
    "CONFIG_CFG80211_REQUIRE_SIGNED_REGDB=y",
)
REGIONS = ("DE", "US", "JP")
SUITES = (
    "system",
    "cpu",
    "storage",
    "network",
    "throughput",
    "display",
    "audio",
    "gpu",
    "input",
    "power",
    "crypto",
    "soak",
)
# what passes, by key: a line no rule names is a measurement, compared run to run
EMPTY = ("none", "0")
RULES: list[tuple[str, Callable[[str], bool]]] = [
    (
        r"units\.failed|units\.autostart|dmesg\.deferred|modules\.missing|drivers\.unbound|firmware\.failed"
        r"|memory\.usable_memory|config\.missing|addresses\.assigned|input\.unnamed"
        r"|usb\.controllers\.unbound|audio\..*\.disabled|glmark2\.unsupported",
        lambda v: v == "none",
    ),
    (
        r"iommu\.faults|iommu\.irqs|mmc\.errors|usb\.errors|tainted"
        r"|firmware\.unowned|cpu\.load\.cooling|soak\.warnings",
        lambda v: v == "0",
    ),
    (r"irq\.spurious", lambda v: v in EMPTY),
    (r"watchdog|suspend\.watchdog", lambda v: "active" in v),
    (r"pstore\.backend|cpu\.supply|planes\.formats|ir\.node", lambda v: v != "none"),
    (r"ram\.verify", lambda v: "verified" in v),
    (r"crypto\.selftests", lambda v: v == "none" or v.endswith("failed: none")),
    (r"crypto\.bench\..*", lambda v: crypto_default_fastest(v)),
    (r"crypto\.recovery\..*", lambda v: crypto_recovered(v)),
    (r"crypto\.rsa\..*", lambda v: rsa_all_verified(v)),
    (r"hwrng", lambda v: v == "none" or int(v.split(": ")[1].split()[0]) >= 200),
    (r"emmc\..*\.wear", lambda v: v.endswith("pre-eol 0x01")),
    (r"eth\..*\.phy", lambda v: "Generic" not in v),
    (r"eth\..*\.hot", lambda v: v.startswith("not run") or "never" not in v),
    (r".*\.reload|wifi\.restored", lambda v: v.endswith(" s")),
    (r"wifi\.reloads", lambda v: v.split("/")[0] == v.split("/")[1].split()[0]),
    (
        r".*\.region\.\w+",
        lambda v: not v.endswith("not taken"),
    ),  # N10: iw reg get shows it
    (r".*\.scan\.unset", lambda v: not v.startswith("0 ")),
    (r".*\.mbits", lambda v: v[:1].isdigit()),
    (r"fio\..*", lambda v: v[:1].isdigit()),
    (r"cpu\.load|soak\.server", lambda v: not v.startswith("failed")),
    (
        r"bt.*\.hci\d+",
        lambda v: "UP RUNNING" in v and set(v.split("errors ")[1]) <= {"0", "+"},
    ),
    (r"bt.*\.find", lambda v: v != "0"),
    (r"audio\..*\.3s", lambda v: v != "refused" and 2.9 <= float(v) <= 3.3),
    # a rate off by more than 1.5% plays audibly sharp or flat
    (r"audio\..*\.2s", lambda v: v != "refused" and 1.97 <= float(v) <= 2.03),
    (r"glmark2\.score", lambda v: v.isdigit()),
    (r"wake\.remote", lambda v: not re.match(r"0 of [1-9]", v)),
    (r"boot\.startup", lambda v: v == "running"),
    (r"boot\.seconds", lambda v: bool(re.fullmatch(r"[\d.]+", v))),
    (r"hdmi\.edid", lambda v: "BAD" not in v),
    (
        r"leds\.driven",
        lambda v: all(a != b for a, b in (s.split(":")[1].split("/") for s in v.split())),
    ),
    (r"buttons\.idle", lambda v: "held: none" in v or "held" not in v),
    (r"button\.recovery", lambda v: v in ("KEY_VENDOR", "none")),
    (r"suspend\.s2idle", lambda v: v.startswith("same boot, slept")),
    (r"rtc\.drift\.s", lambda v: abs(int(v)) <= 2),
    (r"soak\.jobs", lambda v: set(v.split()) <= {"0"}),
    (r"soak\.ping\.loss", lambda v: v != "failed" and float(v.split()[0]) < 1),
    # changes close together hang the RK3528's DDR: load scaling polls them that close
    (r"ddr\.governor", lambda v: v != "simple_ondemand"),
    (r"audio\..*\.hdmi-jack", lambda v: v in ("on connected", "off disconnected")),
    (r"audio\..*\.hdmi-jack\.follows", lambda v: v == "on with a screen, off without"),
]
TAINT_STAGING, TAINT_OOT, TAINT_UNSIGNED = 1 << 10, 1 << 12, 1 << 13
SETTLE_PERCENT = 8
SUSPENDS = "/sys/power/suspend_stats/success"  # the kernel's count of system sleeps entered
SOAK_SETTLE_S = 30  # how long the soak waits for the server: a radio rejoining after sleep
SOAK_GRACE_S = 15  # past the soak's end, how long a job may take to finish on its own
FIO_LAYOUT_S = 120  # fio writes its file first: 512 MB on a slow SD card takes most of this
BUSY_WAIT_S = 900  # how long a box waits for the iperf3 server other boxes are using
JACK_WAIT_S = 15  # a forced status reaches the output by DRM's 10 s connector poll at worst
JACK_POLL_S = 0.2


@dataclass(frozen=True)
class Profile:
    """How long each check runs: short while working, minutes; default for every change, under
    30 minutes for both kernels; extended for a release, as long as bring-up's own checks.
    """

    ram_verify_s: int
    stream_s: int
    iommu_s: int
    load_s: int
    fio_s: int
    fio_mb: int  # its test file: the layout alone is seconds on an SD card
    iperf_s: int
    iperf_runs: int
    loaded_s: int
    reloads: int
    sleep_s: int  # s2idle: extended's outlasts the watchdog's 80 s
    soak_s: int
    glmark2: str  # glmark2's scene options; empty for its whole default suite
    driver_modes: bool = True  # each mode a radio's driver offers, reloaded; else the one loaded


PROFILES = {
    "short": Profile(
        ram_verify_s=5,
        stream_s=2,
        iommu_s=2,
        load_s=15,
        fio_s=3,
        fio_mb=64,
        iperf_s=3,
        iperf_runs=1,
        loaded_s=10,
        reloads=1,
        sleep_s=10,
        soak_s=30,
        glmark2="-b build",
        driver_modes=False,
    ),
    "default": Profile(
        ram_verify_s=20,
        stream_s=5,
        iommu_s=5,
        load_s=60,
        fio_s=10,
        fio_mb=512,
        iperf_s=5,
        iperf_runs=1,
        loaded_s=20,
        reloads=1,
        sleep_s=20,
        soak_s=120,
        glmark2="-b build -b texture -b shading -b effect2d -b desktop",
    ),
    "extended": Profile(
        ram_verify_s=60,
        stream_s=15,
        iommu_s=10,
        load_s=300,
        fio_s=30,
        fio_mb=512,
        iperf_s=8,
        iperf_runs=3,
        loaded_s=60,
        reloads=3,
        sleep_s=120,
        soak_s=1800,
        glmark2="",
    ),
}
PROFILE = PROFILES["default"]  # set from --profile, once, before any check


def sh(command: str, timeout: float = 120) -> str:
    """A shell command's output, stripped; empty when it fails or runs out of time."""
    process = subprocess.Popen(
        command,
        shell=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        start_new_session=True,
    )
    try:
        out, _ = process.communicate(timeout=timeout)
    except subprocess.TimeoutExpired:
        os.killpg(process.pid, signal.SIGKILL)  # the shell and what it started: none holds the pipe
        process.communicate()
        return ""
    return out.strip()


def read(path: str) -> str:
    with contextlib.suppress(OSError):
        return Path(path).read_text(errors="replace").replace("\0", " ").strip()
    return ""


def have(tool: str) -> bool:
    return shutil.which(tool) is not None


def hottest() -> float:
    temps = [int(t) for t in map(read, glob.glob("/sys/class/thermal/thermal_zone*/temp")) if t]
    return max(temps, default=0) / 1000


def cooled(read_temp: Callable[[], float], wait: Callable[[float], None]) -> tuple[float, int]:
    """The idle temperature once it stops falling, and the seconds that took: read at once, it is
    the heat of whatever ran before, a kernel's tests or the build."""
    low, since, waited = read_temp(), 0, 0
    while since < COOL_STEADY_S and waited < COOL_WAIT_S:
        wait(COOL_SAMPLE_S)
        waited += COOL_SAMPLE_S
        now = read_temp()
        since = 0 if now < low else since + COOL_SAMPLE_S
        low = min(low, now)
    return low, waited


def busy() -> tuple[int, int]:
    fields = [int(x) for x in read("/proc/stat").splitlines()[0].split()[1:]]
    return sum(fields) - fields[3] - fields[4], fields[3] + fields[4]


def settle() -> int:
    """Seconds until the CPU idles: a box busy from boot or a player skews every number."""
    for waited in range(0, 120, 2):
        a = busy()
        time.sleep(2)
        b = busy()
        work, idle = b[0] - a[0], b[1] - a[1]
        if 100 * work < SETTLE_PERCENT * (work + idle):
            return waited + 2
    return 120


def pvtm_levels(log: list[str]) -> dict[str, str]:
    """Each block's PVTM count and the OPP voltage level it selects, from the kernel's log, as the
    vendor's (`pvtm=N`, then `pvtm-volt-sel=L`) or next2's (`pvtm N: bin LL`) prints it.
    """
    out: dict[str, str] = {}
    for block, ours in (
        ("cpu", lambda l: "gpu" not in l.lower()),
        ("gpu", lambda l: "gpu" in l.lower()),
    ):
        lines = [l for l in log if "pvtm" in l and ours(l)]
        count = next((m.group(1) for l in lines if (m := re.search(r"pvtm[= ](\d+)", l))), None)
        level = next(
            (m.group(1) for l in lines if (m := re.search(r"(?:pvtm-volt-sel=|bin L)(\d+)", l))),
            None,
        )
        if count or level:
            out[block] = f"{count or '?'} L{level if level is not None else '?'}"
    return out


def boot_seconds() -> str:
    """From the kernel's start to systemd's startup finished, as systemd counts it: a boot past a
    minute prints as minutes and seconds, which systemd-analyze's line spells."""
    finished = sh("systemctl show --value -p FinishTimestampMonotonic")
    return f"{int(finished) / 1e6:.1f}" if finished.isdigit() and int(finished) else NONE


def dmesg(levels: str = "") -> list[str]:
    flag = f"-l {levels}" if levels else ""
    return [re.sub(r"^\[ *[\d.]+\] ", "", line) for line in sh(f"dmesg {flag}").splitlines()]


# system.md, boot.md, trees.md, family.md


def system() -> Iterator[Line]:
    yield "settled.after.s", str(settle())
    yield "kernel", os.uname().release
    yield "tree", f"{sha('/usr/lib/tvb/board.dtb')[:8]} {read('/proc/device-tree/model')}"
    for name in ("id", "name", "pcb"):
        yield f"identity.{name}", read(f"/usr/lib/tvb/board-{name}") or NONE
    temp, waited = cooled(hottest, time.sleep)
    yield "temp.idle.c", f"{temp:.1f}"
    yield "temp.idle.cooled.s", str(waited)
    # systemd-analyze answers only once startup has finished, which a check run at boot can precede
    yield "boot.startup", sh("systemctl is-system-running --wait", timeout=STARTUP_WAIT_S) or NONE
    yield "boot.seconds", boot_seconds()
    blame = sh("systemd-analyze blame").splitlines()
    yield "boot.slowest", " ".join(blame[0].split()) if blame else NONE
    yield "units.failed", sh("systemctl --failed --no-legend --plain | awk '{print $1}' | xargs")
    starting = [u for u in DISPLAY_MANAGERS if sh(f"systemctl is-enabled {u}") == "enabled"]
    yield "units.autostart", " ".join(starting) or NONE
    warnings = dmesg("err,warn")
    sources = [w.split(":")[0].split(" ")[0] for w in warnings]
    top = max(set(sources), key=sources.count) if sources else NONE
    yield "dmesg.warnings", f"{len(warnings)}, most from {top}"
    yield "dmesg.deferred", read("/sys/kernel/debug/devices_deferred").replace("\n", "; ") or NONE
    yield "iommu.faults", str(sum("Page fault" in line for line in dmesg()))
    yield "iommu.irqs", iommu_irqs()
    yield "irq.spurious", spurious_irqs()
    yield "tainted", tainted()
    yield "drivers.unbound", unbound_devices()
    yield "firmware.failed", failed_firmware()
    yield "cma.mib", meminfo_mib("CmaTotal")
    yield "regulators", regulators()
    yield "crypto.selftests", crypto()
    yield "hwrng", hwrng()
    yield "modules.missing", missing_modules()
    yield "ram.mib", str(int(read("/proc/meminfo").split()[1]) // 1024)
    usable = glob.glob("/proc/device-tree/memory*/linux,usable-memory")
    yield "memory.usable_memory", "present" if usable else NONE
    yield "watchdog", watchdog()
    yield "panic.seconds", read("/proc/sys/kernel/panic")
    yield "pstore.backend", read("/sys/module/pstore/parameters/backend") or NONE
    config = read(f"/boot/config-{os.uname().release}")
    yield "config.missing", " ".join(c for c in CONFIG if c not in config) or NONE
    yield "firmware.unowned", unowned_firmware()
    yield "packages.added", added_packages()
    yield "addresses.assigned", assigned_addresses()
    for device_class, pattern in INVENTORY.items():
        yield f"inventory.{device_class}", inventory(pattern)
    yield "loaders", loaders()
    yield "ram.verify", ram_verify()
    for workers in (1, os.cpu_count() or 1):
        yield f"ram.stream.{workers}", stream(workers)


def enabled(*compatibles: str) -> bool:
    """Whether the tree enables a node whose compatible holds any of these."""
    for root, _, files in os.walk("/proc/device-tree"):
        if "compatible" in files and any(c in read(f"{root}/compatible") for c in compatibles):
            if read(f"{root}/status") in ("", "okay", "ok"):
                return True
    return False


def sha(path: str, offset: int = 0, size: int = -1) -> str:
    digest = hashlib.sha256()
    with contextlib.suppress(OSError), open(path, "rb") as f:
        f.seek(offset)
        digest.update(f.read(size))
        return digest.hexdigest()
    return NONE


def tainted() -> str:
    """The kernel's taint, less what we ship by design: out-of-tree (O), staging (C) and
    unsigned (E) modules. Anything left, a warning or an oops among them, is a failure.
    """
    value = int(read("/proc/sys/kernel/tainted") or 0)
    return str(value & ~(TAINT_OOT | TAINT_STAGING | TAINT_UNSIGNED))


def spurious_irqs() -> str:
    found = re.search(r"^\s*ERR:\s*(\d+)", read("/proc/interrupts"), re.MULTILINE)
    return found.group(1) if found else NONE


def failed_firmware() -> str:
    """Firmware the kernel asked for and did not find."""
    log = "\n".join(dmesg())
    names = re.findall(r"(?:firmware: failed to load|Direct firmware load for) (\S+)", log)
    return " ".join(sorted(set(names))) or NONE


def meminfo_mib(field: str) -> str:
    found = re.search(rf"^{field}:\s+(\d+)", read("/proc/meminfo"), re.MULTILINE)
    return str(int(found.group(1)) // 1024) if found else NONE


def unbound_devices() -> str:
    """Enabled tree nodes with a compatible and a platform device, but no driver bound."""
    unbound = []
    for device in glob.glob("/sys/bus/platform/devices/*"):
        node = Path(f"{device}/of_node")
        if not node.exists() or Path(f"{device}/driver").exists():
            continue
        status = read(f"{node}/status")
        compatible = read(f"{node}/compatible")
        if (
            compatible
            and status in ("", "okay", "ok")
            and not any(d in compatible for d in DRIVERLESS)
        ):
            unbound.append(Path(device).name)
    return " ".join(sorted(unbound)) or NONE


def regulators() -> str:
    """Each named regulator's voltage and users, a digest: a change shows between runs."""
    rows = sorted(
        f"{read(f'{r}/name')}={read(f'{r}/microvolts')}/{read(f'{r}/num_users')}"
        for r in glob.glob("/sys/class/regulator/regulator.*")
    )
    return f"{len(rows)} {hashlib.sha256(' '.join(rows).encode()).hexdigest()[:8]}"


def crypto() -> str:
    """The crypto engine's algorithms, and each whose self-test did not pass."""
    failed, engine = [], 0
    for block in read("/proc/crypto").split("\n\n"):
        driver = re.search(r"driver\s*:\s*(\S+)", block)
        test = re.search(r"selftest\s*:\s*(\w+)", block)
        if not driver or not re.search(CRYPTO_ENGINE, driver.group(1)):
            continue
        engine += 1
        if test and test.group(1) != "passed":
            failed.append(driver.group(1))
    return f"{engine} algorithms, failed: {' '.join(failed) or NONE}" if engine else NONE


@dataclass(frozen=True)
class CryptoAlg:
    name: str
    driver: str
    kind: str
    priority: int
    keysize: int
    ivsize: int
    digestsize: int


def crypto_algs(proc: str) -> list[CryptoAlg]:
    """/proc/crypto's self-tested, callable algorithms, in its order: newest registered first."""
    algs = []
    for block in proc.split("\n\n"):
        f = dict(
            (k.strip(), v.strip()) for k, _, v in (ln.partition(":") for ln in block.splitlines())
        )
        if f.get("selftest") != "passed" or f.get("internal") == "yes" or "driver" not in f:
            continue
        algs.append(
            CryptoAlg(
                f["name"],
                f["driver"],
                f.get("type", ""),
                int(f.get("priority", "0")),
                int(f.get("min keysize", "0")),
                int(f.get("ivsize", "0")),
                int(f.get("digestsize", "0")),
            )
        )
    return algs


def is_engine(driver: str) -> bool:
    return bool(re.search(CRYPTO_ENGINE, driver))


def socket_drivers(algs: list[CryptoAlg], name: str) -> list[CryptoAlg]:
    """An algorithm's drivers of the types the userspace socket serves."""
    return [a for a in algs if a.name == name and a.kind in TCRYPT_MODES]


def default_driver(algs: list[CryptoAlg], name: str) -> str:
    """The driver a lookup by name gets: the highest priority, a tie to the newest."""
    named = socket_drivers(algs, name)
    top = max(a.priority for a in named)
    return next(a.driver for a in named if a.priority == top)


def contenders(algs: list[CryptoAlg], name: str) -> list[CryptoAlg]:
    """Each driver of an algorithm, and where none is the CPU's, its mode on the CPU's best
    cipher: a template nobody asked for is not in /proc/crypto yet."""
    named = socket_drivers(algs, name)
    mode, _, inner = name.partition("(")
    cpu = [a for a in algs if a.name == inner[:-1] and not is_engine(a.driver)]
    if inner and cpu and all(is_engine(a.driver) for a in named):
        best = max(cpu, key=lambda a: a.priority)
        named.append(replace(named[0], driver=f"{mode}({best.driver})", priority=0))
    return named


def tcrypt_rates(log: list[str], kind: str) -> dict[int, float]:
    """MB/s by request size from a tcrypt speed run's lines: encryption's, or a hash's in one
    update; a size that failed is absent."""
    rates: dict[int, float] = {}
    for line in log:
        if "decryption" in line:
            break
        cipher = re.search(
            r"(\d+) byte blocks\): \d+ operations in (\d+) seconds \((\d+) bytes", line
        )
        digest = re.search(
            r"(\d+) byte blocks, +(\d+) bytes per update.*opers/sec, +(\d+) bytes/sec", line
        )
        if kind == "skcipher" and cipher:
            rates[int(cipher[1])] = int(cipher[3]) / int(cipher[2]) / 1e6
        elif kind != "skcipher" and digest and digest[1] == digest[2]:
            rates[int(digest[1])] = int(digest[3]) / 1e6
    return rates


def tcrypt_log(alg: CryptoAlg, driver: str) -> list[str]:
    """One driver's tcrypt speed run, its kernel lines; tcrypt always refuses to load once run."""
    keylen = HMAC_KEY_BYTES if alg.name.startswith("hmac(") else alg.keysize
    marker = f"{TCRYPT_MARK} {driver} {time.monotonic_ns()}"
    Path("/dev/kmsg").write_text(marker + "\n")
    sh(f"modprobe tcrypt mode={TCRYPT_MODES[alg.kind]} alg='{driver}' klen={keylen} sec=1")
    return after_marker(dmesg(), marker)


def tcrypt(alg: CryptoAlg, driver: str) -> dict[int, float]:
    return tcrypt_rates(tcrypt_log(alg, driver), alg.kind)


def tcrypt_failure(log: list[str]) -> str:
    """The run's first line that is not a timing: why a size has no rate."""
    found = [l for l in log if re.search(r"fail|error|timed out", l, re.IGNORECASE)]
    return found[0].split("] ", 1)[-1] if found else "no failure logged"


def after_marker(log: list[str], marker: str) -> list[str]:
    """The lines after a run's marker: a full log buffer drops old lines, so no count holds."""
    found = [i for i, line in enumerate(log) if line.endswith(marker)]
    return log[found[-1] + 1 :] if found else []


def bench_line(algs: list[CryptoAlg], name: str) -> str:
    """Each driver's MB/s at each size, the default's, and the fastest at a page."""
    logs = {a.driver: (a, tcrypt_log(a, a.driver)) for a in contenders(algs, name)}
    rates = {d: tcrypt_rates(log, a.kind) for d, (a, log) in logs.items()}
    shown = ", ".join(
        f"{d} {'/'.join(f'{rs[s]:.0f}' if s in rs else '-' for s in BENCH_BYTES)}"
        for d, rs in rates.items()
    )
    default = default_driver(algs, name)
    page = {d: rs[JUDGED_BYTES] for d, rs in rates.items() if JUDGED_BYTES in rs}
    if len(page) < 2:
        why = "; ".join(f"{d}: {tcrypt_failure(logs[d][1])}" for d in rates if d not in page)
        return (
            f"not run: {len(page)} of {len(rates)} drivers timed at {JUDGED_BYTES} B; {shown} MB/s"
            f"; {why}"
        )
    fastest = max(page, key=lambda d: page[d])
    if default in page and page[default] >= FASTEST_SLACK * page[fastest]:
        fastest = default
    return f"{shown} MB/s; default {default}, fastest {fastest}"


def crypto_default_fastest(value: str) -> bool:
    default, _, fastest = value.rpartition("; default ")[2].partition(", fastest ")
    return default == fastest


def crypto_recovered(value: str) -> bool:
    return value.startswith("provoked: failed, next: ") and value[-1].isdigit()


def crypto_recovery(algs: list[CryptoAlg]) -> Iterator[Line]:
    """A hash made to time out or wedge the engine, then the next one, which must run."""
    plain = [a for a in algs if is_engine(a.driver) and a.kind == "ahash" and "(" not in a.name]
    for failure, value in HASH_FAILURES.items():
        if not plain or not FAIL_NEXT_HASH.exists():
            yield f"crypto.recovery.{failure}", "not run: no debug build's knob"
            continue
        FAIL_NEXT_HASH.write_text(value)
        provoked = tcrypt(plain[0], plain[0].driver)
        FAIL_NEXT_HASH.write_text("0")
        after = tcrypt(plain[0], plain[0].driver).get(BENCH_BYTES[1])
        verdict = "not failed" if BENCH_BYTES[1] in provoked else "failed"
        yield f"crypto.recovery.{failure}", (
            f"provoked: {verdict}, next: {f'{after:.0f}' if after else 'failed'}"
        )


def crypto_msg(driver: str, priority: int | None) -> bytes:
    """A NETLINK_CRYPTO message: an algorithm's new priority, or None to delete an idle one."""
    alg = struct.pack("64s64s64sIIII", b"", driver.encode(), b"", 0, 0, 0, 0)
    attr = b"" if priority is None else struct.pack("HHI", 8, CRYPTOCFGA_PRIORITY_VAL, priority)
    kind = CRYPTO_MSG_DELALG if priority is None else CRYPTO_MSG_UPDATEALG
    header = struct.pack("IHHII", 16 + len(alg) + len(attr), kind, NLM_F_REQUEST | NLM_F_ACK, 1, 0)
    return header + alg + attr


def crypto_update(driver: str, priority: int | None) -> int:
    """The kernel's answer to crypto_msg: 0, or a negative errno."""
    with socket.socket(socket.AF_NETLINK, socket.SOCK_RAW, NETLINK_CRYPTO) as s:
        s.bind((0, 0))
        s.send(crypto_msg(driver, priority))
        return struct.unpack_from("i", s.recv(4096), 16)[0]


@contextlib.contextmanager
def rsa_routed(engine: CryptoAlg, priority: int, away: str) -> Iterator[None]:
    """RSA signs through the engine or away from it: its priority set, the other PKCS#1
    instance deleted so the next lookup builds one over the preferred RSA."""
    crypto_update(engine.driver, priority)
    crypto_update(f"pkcs1({away},sha256)", None)
    try:
        yield
    finally:
        crypto_update(engine.driver, engine.priority)


def keyring_sign(der: bytes, digest: bytes, bits: int) -> bytes:
    """A PKCS#8 private key into the process keyring, a digest signed by it, the key dropped:
    the signature is the key's size, and the kernel takes no other."""
    libc = ctypes.CDLL(None, use_errno=True)
    libc.syscall.restype = ctypes.c_long
    key = libc.syscall(
        SYS_ADD_KEY, b"asymmetric", b"tvb-rsa", der, len(der), KEY_SPEC_PROCESS_KEYRING
    )
    if key < 0:
        return b""
    out = ctypes.create_string_buffer(bits // 8)
    params = struct.pack(KEYCTL_PKEY_PARAMS, key, len(digest), len(out), *(0,) * KEYCTL_PKEY_SPARE)
    size = libc.syscall(SYS_KEYCTL, KEYCTL_PKEY_SIGN, params, RSA_SIGN_INFO, digest, out)
    libc.syscall(SYS_KEYCTL, KEYCTL_UNLINK, key, KEY_SPEC_PROCESS_KEYRING)
    return out.raw[:size] if size > 0 else b""


def rsa_key(bits: int, root: Path) -> tuple[bytes, Path]:
    """A fresh RSA key: its PKCS#8 DER, and its public key's PEM."""
    pem, der, pub = root / "k.pem", root / "k.der", root / "p.pem"
    sh(f"openssl genpkey -algorithm RSA -pkeyopt rsa_keygen_bits:{bits} -out {pem}")
    sh(f"openssl pkcs8 -topk8 -nocrypt -outform DER -in {pem} -out {der}")
    sh(f"openssl pkey -in {pem} -pubout -out {pub}")
    return (der.read_bytes() if der.exists() else b""), pub


def rsa_verified(digest: bytes, sig: bytes, pub: Path, root: Path) -> bool:
    (root / "dig").write_bytes(digest)
    (root / "sig").write_bytes(sig)
    out = sh(
        f"openssl pkeyutl -verify -pubin -inkey {pub} -in {root / 'dig'} -sigfile {root / 'sig'}"
        " -pkeyopt digest:sha256"
    )
    return bool(sig) and "Verified Successfully" in out


def rsa_rate(bits: int, digest: bytes, root: Path) -> float:
    der, _ = rsa_key(bits, root)
    start = time.monotonic()
    signed = sum(bool(keyring_sign(der, digest, bits)) for _ in range(RSA_SIGNS))
    return signed / (time.monotonic() - start)


def rsa_through() -> str:
    return " ".join(
        a.driver for a in crypto_algs(read("/proc/crypto")) if a.driver.startswith("pkcs1(rsa")
    )


def rsa_line(verified: dict[int, int], rate: float, cpu_rate: float, through: str) -> str:
    shown = ", ".join(f"{n}/{RSA_KEYS} at {b}" for b, n in verified.items())
    return (
        f"verified {shown}; {RSA_TIMED_BITS} bits {rate:.1f}/s, the CPU's {cpu_rate:.1f}/s;"
        f" through {through}"
    )


def rsa_all_verified(value: str) -> bool:
    pairs = re.findall(r"(\d+)/(\d+) at", value)
    return bool(pairs) and all(a == b for a, b in pairs)


def crypto_rsa() -> Iterator[Line]:
    """Each engine's RSA with fresh keys, about half carrying DER's leading zero byte in a
    number, each signature verified, then its rate beside the CPU's."""
    engines = [
        a for a in crypto_algs(read("/proc/crypto")) if a.name == "rsa" and is_engine(a.driver)
    ]
    if not engines:
        yield "crypto.rsa", NONE
        return
    if not have("openssl"):
        yield "crypto.rsa", "not run: no openssl"
        return
    sh("modprobe pkcs8_key_parser")
    digest = os.urandom(RSA_DIGEST_BYTES)
    for engine in engines:
        with tempfile.TemporaryDirectory(dir="/var/tmp") as tmp:
            root = Path(tmp)
            with rsa_routed(engine, RSA_ROUTE_PRIORITY, "rsa-generic"):
                verified = {}
                for bits in RSA_BITS:
                    keys = (rsa_key(bits, root) for _ in range(RSA_KEYS))
                    verified[bits] = sum(
                        rsa_verified(digest, keyring_sign(der, digest, bits), pub, root)
                        for der, pub in keys
                    )
                rate = rsa_rate(RSA_TIMED_BITS, digest, root)
                through = rsa_through()
            with rsa_routed(engine, RSA_AWAY_PRIORITY, engine.driver):
                cpu_rate = rsa_rate(RSA_TIMED_BITS, digest, root)
        yield f"crypto.rsa.{engine.driver}", rsa_line(verified, rate, cpu_rate, through)


def crypto_bench() -> Iterator[Line]:
    """Every algorithm an engine serves: each driver against the CPU's, which one is used, and
    the engine recovering from a failed job."""
    algs = crypto_algs(read("/proc/crypto"))
    served = sorted({a.name for a in algs if is_engine(a.driver) and a.kind in TCRYPT_MODES})
    if not served:
        yield "crypto.bench", NONE
        return
    for name in served:
        yield f"crypto.bench.{name}", bench_line(algs, name)
    yield from crypto_recovery(algs)
    yield from crypto_rsa()


def hwrng() -> str:
    current = read("/sys/class/misc/hw_random/rng_current")
    if not current or current == "none":
        return NONE
    with contextlib.suppress(OSError), open("/dev/hwrng", "rb") as f:
        data = f.read(4096)
        return f"{current}: {len(set(data))} distinct bytes of {len(data)}"
    return f"{current}: unreadable"


def iommu_lines(interrupts: str) -> list[str]:
    """The /proc/interrupts lines an IOMMU alone serves: one it shares with its master (VOP2's)
    counts the master's own interrupts, and that IOMMU's faults show in iommu.faults instead.
    """
    out = []
    for line in interrupts.splitlines():
        actions = re.split(r"\s(?:Level|Edge)\s", line, maxsplit=1)[-1].split(",")
        if all("mmu" in a.lower() for a in actions):
            out.append(line)
    return out


def iommu_irqs() -> str:
    """The IOMMU's interrupt count over 10 s at idle: one still firing is a fault storm."""

    def count() -> int:
        lines = iommu_lines(read("/proc/interrupts"))
        return sum(int(x) for l in lines for x in l.split()[1:] if x.isdigit())

    before = count()
    time.sleep(PROFILE.iommu_s)
    return str(count() - before)


def missing_modules() -> str:
    """Our packages' modules a device on this box asks for, by its modalias, yet not loaded: a
    module for a chip the box does not carry is not missing."""
    packages = sh("dpkg-query -W -f '${Package}\\n' 'tvb-*-modules-*'").split()
    files = sh(f"dpkg -L {' '.join(packages)}").splitlines() if packages else []
    ours = {Path(f).name.removesuffix(".ko") for f in files if f.endswith(".ko")}
    asked = set(sh(MODALIAS_MODULES).split())
    loaded = {line.split()[0] for line in read("/proc/modules").splitlines()}
    return " ".join(sorted({m.replace("-", "_") for m in ours} & asked - loaded)) or NONE


def watchdog() -> str:
    """The timeout set, the most the clock allows, and whether systemd pings it."""
    timeout = read("/sys/class/watchdog/watchdog0/timeout")
    if not timeout and Path("/dev/watchdog0").exists():
        held = sh("systemctl show -p RuntimeWatchdogUSec --value")
        return (
            f"{held} by systemd, no sysfs timeout, active"
            if held not in ("", "0", "infinity")
            else NONE
        )
    most = (
        read("/sys/class/watchdog/watchdog0/max_timeout").strip("0")
        and read("/sys/class/watchdog/watchdog0/max_timeout")
        or "?"
    )
    state = read("/sys/class/watchdog/watchdog0/state") or "?"
    return f"{timeout} of {most} s, {state}" if timeout else NONE


def unowned_firmware() -> str:
    owned = {line.strip() for f in glob.glob("/var/lib/dpkg/info/*.list") for line in open(f)}
    files = {
        str(p).replace("/usr/lib/firmware", "/lib/firmware", 1)
        for root in ("/lib/firmware", "/usr/lib/tvb/firmware")
        for p in Path(root).rglob("*")
        if p.is_file() and not p.is_symlink()
    }
    stray = sorted(f for f in files if not {f, f.replace("/lib/", "/usr/lib/", 1)} & owned)
    return f"{len(stray)}: {' '.join(stray[:5])}" if stray else "0"


def added_packages() -> str:
    """Packages installed by hand since the image: dpkg's log, less ours and this suite's tools."""
    log = "\n".join(
        read(f) for f in sorted(glob.glob("/var/log/dpkg.log*")) if not f.endswith(".gz")
    )
    installed = {m.split(":")[0] for m in re.findall(r" install (\S+)", log)}
    manual = set(sh("apt-mark showmanual").split())
    added = {p for p in (installed & manual) - TEST_TOOLS if not p.startswith(("tvb-", "linux-"))}
    return " ".join(sorted(added)) or NONE


def assigned_addresses() -> str:
    """Interfaces whose address userspace set (addr_assign_type 3), and units that attach or set
    addresses."""
    set_by_user = [
        n
        for n in board_nets("addr_assign_type")
        if read(f"/sys/class/net/{n}/addr_assign_type") == "3"
    ]
    units = sh("systemctl list-unit-files --no-legend | grep -iE 'hciattach|macaddr|btattach'")
    return " ".join(set_by_user + units.split()[:1]) or NONE


def inventory(pattern: str) -> str:
    """How many devices of a class, then what each calls itself: its name or type, else its node's."""
    paths = sorted(glob.glob(pattern))
    names = [read(f"{p}/name") or read(f"{p}/type") or os.path.basename(p) for p in paths]
    return " ".join([str(len(names)), *(n.replace(" ", "_") for n in names)])


def loaders() -> str:
    """Rockchip's loaders on the boot device: the idbloader at sector 64, U-Boot at 16384."""
    if "rockchip" not in read("/proc/device-tree/compatible"):
        return NONE
    disk = boot_disk()
    return f"{sha(disk, 64 * 512, 1 << 20)[:12]} {sha(disk, 16384 * 512, 4 << 20)[:12]}"


def boot_disk() -> str:
    source = sh("findmnt -no SOURCE /")
    parent = sh(f"lsblk -no PKNAME {source}").splitlines()
    return f"/dev/{parent[0]}" if parent else source


def ram_verify() -> str:
    if not have("stress-ng"):
        return "no stress-ng"
    done = subprocess.run(
        [
            "stress-ng",
            "--vm",
            "4",
            "--vm-bytes",
            "80%",
            "--verify",
            "-t",
            f"{PROFILE.ram_verify_s}s",
            "-q",
        ],
        capture_output=True,
        check=False,
    )
    return f"{PROFILE.ram_verify_s} s over 80 %: " + (
        "verified" if done.returncode == 0 else f"exit {done.returncode}"
    )


def stream(workers: int) -> str:
    if not have("stress-ng"):
        return "no stress-ng"
    out = sh(
        f"stress-ng --stream {workers} -t {PROFILE.stream_s}s --metrics 2>&1",
        timeout=60,
    )
    rate = re.findall(r"memory rate: ([\d.]+) MB read", out)
    return f"{sum(float(r) for r in rate):.0f} MB/s read" if rate else NONE


# system.md S19, S20


def cpu() -> Iterator[Line]:
    policy = "/sys/devices/system/cpu/cpu0/cpufreq"
    ladder = read(f"{policy}/scaling_available_frequencies").split()
    supply = cpu_supply()
    governor = read(f"{policy}/scaling_governor")
    steps = []
    if ladder and supply and "userspace" in read(f"{policy}/scaling_available_governors"):
        with contextlib.suppress(OSError):
            Path(f"{policy}/scaling_governor").write_text("userspace")
            for khz in ladder:
                Path(f"{policy}/scaling_setspeed").write_text(khz)
                time.sleep(0.5)
                volts = int(read(f"{supply}/microvolts") or 0) // 1000
                steps.append(f"{int(khz) // 1000}@{volts}")
        Path(f"{policy}/scaling_governor").write_text(governor)
    yield "cpu.ladder", " ".join(steps) or ",".join(ladder) or NONE
    for block, line in pvtm_levels(dmesg()).items():
        yield f"pvtm.{block}", line
    yield from ddr()
    if Path("/proc/device-tree/cpus/cpu@0/cpu-supply").exists():
        yield "cpu.supply", read(f"{supply}/name") if supply else NONE
    trips = sorted(
        {read(t) for t in glob.glob("/sys/class/thermal/thermal_zone*/trip_point_*_temp")}
    )
    yield "thermal.trips.c", " ".join(str(int(t) // 1000) for t in trips if t) or NONE
    if not have("stress-ng"):
        yield "cpu.load", "no stress-ng"
        return
    load = subprocess.Popen(["stress-ng", "--cpu", "0", "-t", f"{PROFILE.load_s}s", "-q"])
    hot, slowest, cooling = 0.0, 10**9, 0
    while True:
        time.sleep(LOAD_SAMPLE_S)
        if load.poll() is not None:  # sampled after the load, the governor is already stepping down
            break
        hot = max(hot, hottest())
        slowest = min(slowest, int(read(f"{policy}/scaling_cur_freq") or 0))
        states = [
            int(s or 0)
            for s in map(read, glob.glob("/sys/class/thermal/cooling_device*/cur_state"))
        ]
        cooling = max([cooling, *states])
    if load.returncode:  # no load ran: a cool, unthrottled CPU would say nothing
        yield "cpu.load", f"failed, stress-ng exit {load.returncode}"
        return
    yield "cpu.load.c", f"{hot:.1f} max over {PROFILE.load_s} s"
    yield "cpu.load.slowest.khz", str(slowest)
    yield "cpu.load.cooling", str(cooling)


def cpu_supply() -> str:
    """The regulator cpu0's cpu-supply names, by phandle."""
    wanted = Path("/proc/device-tree/cpus/cpu@0/cpu-supply")
    if not wanted.exists():
        return ""
    phandle = wanted.read_bytes()
    for regulator in glob.glob("/sys/class/regulator/regulator.*"):
        with contextlib.suppress(OSError):
            if Path(f"{regulator}/of_node/phandle").read_bytes() == phandle:
                return regulator
    return ""


# storage.md


def storage() -> Iterator[Line]:
    for ios in sorted(glob.glob("/sys/kernel/debug/mmc*/ios")):
        fields = dict(line.split(":", 1) for line in read(ios).splitlines() if ":" in line)
        timing = fields.get("timing spec", "").strip()
        volts = fields.get("signal voltage", "").strip()
        yield f"mmc.{Path(ios).parent.name}", f"{timing} {volts}"
    errors = [l for l in dmesg() if re.search(r"mmc\d.*(error|timeout|fail)", l, re.I)]
    yield "mmc.errors", f"{len(errors)}: {'; '.join(errors[:3])}" if errors else "0"
    disk = boot_disk()
    kind = read(f"/sys/block/{Path(disk).name}/device/type")
    yield "root.device", f"{disk} {kind or '?'}"
    for device in sorted(glob.glob("/sys/block/mmcblk*/device")):
        if read(f"{device}/type") == "MMC":
            life = read(f"{device}/life_time")
            eol = read(f"{device}/pre_eol_info") or "?"
            yield f"emmc.{Path(device).parent.name}.wear", f"life {life or '?'} pre-eol {eol}"
    usb = [Path(p).parent.parent.name for p in glob.glob("/sys/block/sd*/device/vendor")]
    yield "usb.storage", " ".join(usb) or NONE
    if not have("fio"):
        yield "fio", "no fio"
        return
    path = "/var/tmp/box.fio"
    for name, mode, block in (
        ("seq.read", "read", "1M"),
        ("seq.write", "write", "1M"),
        ("rand.read", "randread", "4k"),
        ("rand.write", "randwrite", "4k"),
    ):
        out = sh(
            f"fio --name={name} --filename={path} --size={PROFILE.fio_mb}M --rw={mode} "
            f"--bs={block} "
            f"--ioengine=libaio --iodepth=32 --direct=1 --runtime={PROFILE.fio_s} --time_based "
            "--output-format=terse",
            timeout=PROFILE.fio_s * 4 + FIO_LAYOUT_S,
        ).split(";")
        reading = mode.endswith("read")
        if len(out) > 49 and out[4] == "0":  # terse field 4: the job's error, 0 for none
            bw, iops = (out[6], out[7]) if reading else (out[47], out[48])
            yield f"fio.{name}", f"{int(bw) / 1024:.1f} MB/s {iops} IOPS"
        else:
            yield f"fio.{name}", f"failed, error {out[4]}" if len(out) > 4 else "failed"
    with contextlib.suppress(OSError):
        os.remove(path)


# network.md


def board_nets(leaf: str) -> list[str]:
    """Interfaces that have leaf in sysfs, a USB adapter's left out: plugged in, not the board's."""
    found = [Path(p).parent for p in glob.glob(f"/sys/class/net/*/{leaf}")]
    return sorted(n.name for n in found if not on_usb(os.path.realpath(f"{n}/device")))


# a PHY's hot receive-detect switch, by a debug build's threshold: under the SoC's temperature,
# then over any it reaches; each switch's log line awaited
PHY_HOT_KNOB = "/sys/module/*/parameters/hot_mc"
PHY_HOT_BELOW_MC = 5000
PHY_HOT_NEVER_MC = 200000
PHY_HOT_WAIT_S = 5


def soc_temp_mc() -> int:
    for zone in glob.glob("/sys/class/thermal/thermal_zone*"):
        if read(f"{zone}/type") == "soc-thermal":
            return int(read(f"{zone}/temp") or 0)
    return 0


def awaited(pattern: str, seen: int) -> float | None:
    """Seconds until a log line past the first seen matches, None at PHY_HOT_WAIT_S."""
    start = time.monotonic()
    while time.monotonic() - start < PHY_HOT_WAIT_S:
        if any(re.search(pattern, line) for line in dmesg()[seen:]):
            return time.monotonic() - start
        time.sleep(0.1)
    return None


def phy_hot(name: str) -> str:
    knobs = glob.glob(PHY_HOT_KNOB)
    if not knobs:
        return "not run: no debug build's knob"
    knob, temp = Path(knobs[0]), soc_temp_mc()
    if not temp:
        return "not run: no soc-thermal zone"
    sh(f"ip link set {name} up")
    saved = knob.read_text().strip()
    try:
        seen = len(dmesg())
        knob.write_text(str(temp - PHY_HOT_BELOW_MC))
        hot = awaited(r"receive detect at 160 mV", seen)
        seen = len(dmesg())
        knob.write_text(str(PHY_HOT_NEVER_MC))
        cool = awaited(r"receive detect at 260 mV", seen)
    finally:
        knob.write_text(saved)
    shown = lambda s: f"{s:.1f} s" if s is not None else "never"
    return f"160 mV at {temp / 1000:.1f} C in {shown(hot)}, back to 260 mV in {shown(cool)}"


def network() -> Iterator[Line]:
    for name in board_nets("device"):
        path = f"/sys/class/net/{name}"
        kind = read(f"{path}/addr_assign_type")
        yield f"addr.{name}", f"{read(f'{path}/address')} type {kind}"
    for name in board_nets("phydev"):
        driver = Path(os.path.realpath(f"/sys/class/net/{name}/phydev/driver")).name
        yield f"eth.{name}.phy", driver
        yield f"eth.{name}.hot", phy_hot(name)
        carrier = read(f"/sys/class/net/{name}/carrier") == "1"
        yield f"eth.{name}.link", (
            f"{read(f'/sys/class/net/{name}/speed')} Mb/s" if carrier else "no cable"
        )
    for wifi in board_nets("wireless"):
        driver = Path(os.path.realpath(f"/sys/class/net/{wifi}/device/driver/module")).name
        modes = MODES.get(driver) if PROFILE.driver_modes else None
        for mode, has_bt in modes or [("", True)]:
            tag = f"wifi.{mode}" if modes else "wifi"
            if modes:
                yield f"{tag}.reload", reload(driver, mode, wifi)
            yield from radio(tag, wifi)
            if has_bt:
                yield from bluetooth(tag.replace("wifi", "bt", 1))
        if modes:  # the box's own mode back, as its modprobe.d sets it
            yield "wifi.restored", reload(driver, "", wifi)
        yield "wifi.reloads", reloads(driver, wifi)
    if not board_nets("wireless"):
        yield from bluetooth("bt")


def throughputs(iperf: str) -> Iterator[Line]:
    """network.md N2, N6, N7: each wired link with a cable and each radio mode, each way, idle
    and under load. Run alone: the iperf3 server takes one box at a time."""
    if not iperf:
        yield "throughput", "not run: no iperf3 server named"
        return
    for name in board_nets("phydev"):
        if read(f"/sys/class/net/{name}/carrier") == "1":
            yield from loaded(f"eth.{name}", iperf, name)
        else:
            yield f"eth.{name}.mbits", "not run: no cable"
    for wifi in board_nets("wireless"):
        driver = Path(os.path.realpath(f"/sys/class/net/{wifi}/device/driver/module")).name
        for mode, _ in MODES.get(driver, [("", True)]):
            tag = f"wifi.{mode}" if driver in MODES else "wifi"
            if driver in MODES:
                yield f"{tag}.reload", reload(driver, mode, wifi)
            yield from loaded(tag, iperf, wifi)
        if driver in MODES:
            yield "wifi.restored", reload(driver, "", wifi)


def loaded(tag: str, iperf: str, interface: str) -> Iterator[Line]:
    """Throughput idle, then with the CPU and the disk busy."""
    yield from throughput(tag, iperf, interface)
    if have("stress-ng"):
        load = subprocess.Popen(
            [
                "stress-ng",
                "--cpu",
                "0",
                "--hdd",
                "1",
                "-t",
                f"{PROFILE.loaded_s}s",
                "-q",
            ],
            cwd="/var/tmp",
        )
        yield from throughput(f"{tag}.loaded", iperf, interface)
        load.wait()


def uptime() -> float:
    """Seconds since boot, the time asleep included, which time.monotonic() leaves out."""
    return float(read("/proc/uptime").split()[0])


def address(interface: str) -> str:
    found = re.search(r"inet ([\d.]+)", sh(f"ip -4 -o addr show {interface}"))
    return found.group(1) if found else ""


def wait_for_address(interface: str, seconds: int = 90) -> bool:
    for _ in range(seconds):
        if address(interface):
            return True
        time.sleep(1)
    return False


def modprobe(*args: str) -> bool:
    try:
        return subprocess.run(["modprobe", *args], capture_output=True, timeout=60).returncode == 0
    except subprocess.TimeoutExpired:
        return False


def unload(driver: str) -> bool:
    """The driver unloaded and gone: a module still loaded would pass any reload after it."""
    return modprobe("-r", driver) and not Path(f"/sys/module/{driver.replace('-', '_')}").exists()


def reload(driver: str, parameters: str, interface: str) -> str:
    """The driver unloaded and loaded with these parameters; seconds until an address is back."""
    if not unload(driver):
        return "unload failed"
    start = time.monotonic()
    if not modprobe(driver, *parameters.split()):
        return "load failed"
    if not wait_for_address(interface):
        return "address lost"
    return f"{parameters or 'default'}: {time.monotonic() - start:.0f} s"


def reloads(driver: str, interface: str) -> str:
    """chip X4: the driver unloaded and loaded again and again, the link back each time."""
    back = 0
    for _ in range(PROFILE.reloads):
        back += unload(driver) and modprobe(driver) and wait_for_address(interface)
    return f"{back}/{PROFILE.reloads} back"


def radio(tag: str, wifi: str) -> Iterator[Line]:
    link = sh(f"iw dev {wifi} link")
    signal = re.search(r"signal: (-?\d+) dBm", link)
    rate = re.search(r"tx bitrate: ([\d.]+ MBit/s[^\n]*)", link)
    dbm, speed = signal.group(1) if signal else "?", rate.group(1) if rate else "?"
    yield f"{tag}.link", f"{dbm} dBm {speed}"
    bands = sorted({b for b in re.findall(r"Band (\d+):", sh("iw list"))})
    yield f"{tag}.bands", " ".join(bands) or NONE
    sh("iw reg set 00")
    time.sleep(2)
    seen = sh(f"iw dev {wifi} scan", timeout=30)
    freqs = [int(float(f)) for f in re.findall(r"freq: ([\d.]+)", seen)]
    five = len([f for f in freqs if f > 4000])
    yield f"{tag}.scan.unset", f"{seen.count('SSID:')} networks, {five} on 5 GHz"
    for region in REGIONS:
        sh(f"iw reg set {region}")
        time.sleep(2)
        got = re.search(r"country (\w+)", sh("iw reg get"))
        country = got.group(1) if got else NONE
        yield f"{tag}.region.{region}", (country if country == region else f"{country}, not taken")
    sh("iw reg set 00")


def busy_wait(command: str, timeout: float) -> str:
    """An iperf3 run, retried while the server serves another box: it takes one at a time."""
    deadline = time.monotonic() + BUSY_WAIT_S
    while True:
        out = sh(f"{command} 2>&1", timeout=timeout)
        if "server is busy" not in out or time.monotonic() > deadline:
            return out
        time.sleep(random.uniform(5, 20))


def throughput(tag: str, server: str, interface: str) -> Iterator[Line]:
    """iperf3 each way through interface alone, the median of three: an access point narrows its
    channel at will, and a box with a cable would otherwise measure the cable."""
    if not have("iperf3"):
        yield f"{tag}.mbits", "no iperf3"
        return
    for way, flag in (("up", ""), ("down", "-R")):
        if not address(interface):
            yield f"{tag}.{way}.mbits", f"failed: no address on {interface}"
            continue
        runs = []
        for _ in range(PROFILE.iperf_runs):
            out = busy_wait(
                f"iperf3 -c {server} --connect-timeout 3000 -t {PROFILE.iperf_s} {flag} "
                f"--bind-dev {interface}",
                timeout=PROFILE.iperf_s + 15,
            )
            found = re.findall(r"([\d.]+) Mbits/sec.*receiver", out)
            if found:
                runs.append(float(found[-1]))
        rate = ""
        if Path(f"/sys/class/net/{interface}/wireless").exists():
            got = re.search(r"tx bitrate: ([\d.]+ MBit/s)", sh(f"iw dev {interface} link"))
            rate = f", tx {got.group(1)}" if got else ""
        median = sorted(runs)[len(runs) // 2] if runs else None
        yield f"{tag}.{way}.mbits", (
            f"{median:.0f}{rate}" if median is not None else f"failed{rate}"
        )


def bluetooth(tag: str) -> Iterator[Line]:
    controllers = sorted(Path(p).name for p in glob.glob("/sys/class/bluetooth/hci*"))
    if not controllers:
        yield tag, NONE
        return
    for hci in controllers:
        info = sh(f"hciconfig {hci}")
        flags = re.search(r"\n\s+(UP[^\n]*|DOWN[^\n]*)", info)
        errors = re.findall(r"errors:(\d+)", info)
        address = re.search(r"BD Address: ([0-9A-F:]+)", info)
        yield f"{tag}.{hci}", (
            f"{address.group(1) if address else '?'} {flags.group(1).strip() if flags else '?'} "
            f"errors {'+'.join(errors) or '?'}"
        )
    if have("btmgmt"):
        found = sh(
            "sleep 25 | timeout 20 stdbuf -oL btmgmt find -l", timeout=30
        )  # it quits at stdin's end; -l: LE-only controllers refuse a dual-mode find
        yield f"{tag}.find", str(len(set(re.findall(r"dev_found: ([0-9A-F:]+)", found))))


# display.md


def display() -> Iterator[Line]:
    for path in sorted(glob.glob("/sys/class/drm/card*-*")):
        yield f"connector.{Path(path).name.split('-', 1)[1]}", read(f"{path}/status")
    formats = sh("drm_info 2>/dev/null") if have("drm_info") else ""
    wanted = re.findall(r"\b(NV12|NV15|P010|YUV420_8BIT|YUV420_10BIT|XR30|AR30)\b", formats)
    yield "planes.formats", " ".join(sorted(set(wanted))) or (
        "no drm_info" if not formats else NONE
    )
    yield "planes.count", str(formats.count("Plane ")) if formats else NONE
    cec = sh("cec-ctl -d /dev/cec0") if have("cec-ctl") else ""
    found = re.search(r"Physical Address\s*:\s*(\S+)", cec)
    yield "cec.address", found.group(1) if found else NONE
    names = sorted(read(p) for p in glob.glob("/sys/class/video4linux/video*/name"))
    yield "video.devices", " ".join(names) or NONE
    fb = [l for l in dmesg() if "frame buffer device" in l]
    yield "console", fb[-1].split(": ", 1)[-1] if fb else NONE
    for connector in sorted(glob.glob("/sys/class/drm/card*-HDMI-A-*")):
        with contextlib.suppress(OSError):
            edid = Path(f"{connector}/edid").read_bytes()
            valid = len(edid) >= 128 and all(
                sum(edid[i : i + 128]) % 256 == 0 for i in range(0, len(edid), 128)
            )
            yield "hdmi.edid", (
                f"{len(edid)} bytes, {'checksums valid' if valid else 'BAD CHECKSUM'}"
                if edid
                else NONE
            )
    elds = [read(f) for f in glob.glob("/proc/asound/card*/eld#*")]
    monitor = [re.search(r"monitor_name[ \t]+(\S.*)", e) for e in elds]
    yield "hdmi.eld", " ".join(m.group(1) for m in monitor if m) or NONE


# display.md H5, H6


def audio() -> Iterator[Line]:
    for card in sorted(glob.glob("/proc/asound/card[0-9]*")):
        number, name = card.removeprefix("/proc/asound/card"), read(f"{card}/id")
        rates = offered_rates(number)
        yield f"audio.{name}.rates", " ".join(map(str, rates)) or NONE
        for rate in rates:
            yield f"audio.{name}.{rate}.2s", rate_seconds(number, rate)
        if FORMAT_RATE in rates:
            for sample in offered_samples(number):
                yield f"audio.{name}.{sample}.2s", rate_seconds(number, FORMAT_RATE, sample)
        most = max_channels(number)
        if "hdmi" in name.lower() and not hdmi_connected():
            yield f"audio.{name}.multichannel", "not run: no HDMI sink to offer channels"
        elif most > 2:
            yield f"audio.{name}.{most}ch.3s", timed_play(number, 48000, most)
        yield f"audio.{name}.disabled", disabled_routes(number)
        jacks = re.findall(
            r"name='([^']*Jack[^']*)'.*?\n.*?\n\s*: values=(\w+)",
            sh(f"amixer -c {number} contents"),
        )
        yield f"audio.{name}.jacks", " ".join(f"{j}={v}" for j, v in jacks) or NONE
        if "hdmi" in name.lower():
            yield f"audio.{name}.hdmi-jack", hdmi_jack(jacks)
            yield f"audio.{name}.hdmi-jack.follows", hdmi_jack_follows(number)


def hdmi_jack(jacks: list[tuple[str, str]]) -> str:
    """An HDMI card's jack beside its connector: on with a sink, off without."""
    if not jacks:
        return "no jack"
    return f"{jacks[0][1]} {'connected' if hdmi_connected() else 'disconnected'}"


def ddr() -> Iterator[Line]:
    """The DDR rate's governor, rate and transitions since boot."""
    found = [
        f"/sys/class/devfreq/{n}" for n in DDR_DEVFREQ if os.path.isdir(f"/sys/class/devfreq/{n}")
    ]
    if not found:
        yield "ddr.governor", "no DDR devfreq"
        return
    yield "ddr.governor", read(f"{found[0]}/governor")
    yield "ddr.rate", read(f"{found[0]}/cur_freq")
    total = re.search(r"Total transition : (\d+)", read(f"{found[0]}/trans_stat"))
    yield "ddr.transitions", total.group(1) if total else NONE


def max_channels(card: str) -> int:
    """The most channels the card's PCM takes, by its hardware parameters."""
    out = sh(f"aplay -D hw:{card},0 --dump-hw-params -d 1 /dev/zero 2>&1", timeout=20)
    found = re.search(r"CHANNELS:\s*\[?\s*\d+\s+(\d+)\]?|CHANNELS:\s*(\d+)", out)
    return int(found.group(1) or found.group(2)) if found else 2


@contextlib.contextmanager
def screen() -> Iterator[None]:
    """A connected HDMI connector for the time: glmark2 asks for one even off-screen, and scans out
    whatever mode the connector has, which costs the GPU memory bandwidth. Where nothing is plugged
    in, a synthetic 1080p60 screen, so every box renders at one size; forced on where the kernel
    takes no EDID override, and back to detecting after."""
    if hdmi_connected():
        yield
        return
    with hdr_sink(hdr_edid(SINKS["SDR"])) as synthetic:
        forced = [] if synthetic else glob.glob("/sys/class/drm/card*-HDMI-A-*/status")
        for status in forced:
            Path(status).write_text("on")
        try:
            yield
        finally:
            for status in forced:
                Path(status).write_text("detect")


def jack_value(card: str) -> str:
    """The card's first jack's state, on or off."""
    found = re.search(
        r"name='[^']*Jack[^']*'.*?\n.*?\n\s*: values=(\w+)",
        sh(f"amixer -c {card} contents"),
    )
    return found.group(1) if found else NONE


def jack_settled(card: str, state: str) -> str:
    """The jack's state once it reads state, or as it reads at JACK_WAIT_S."""
    end = time.monotonic() + JACK_WAIT_S
    while (value := jack_value(card)) != state and time.monotonic() < end:
        time.sleep(JACK_POLL_S)
    return value


def hdmi_jack_follows(card: str) -> str:
    """With no screen attached, the HDMI jack under a synthetic screen, then after it."""
    if hdmi_connected():
        return "not run: a screen is attached"
    with hdr_sink(hdr_edid(SINKS["SDR"])) as stood_in:
        if not stood_in:
            return "not run: no EDID override"
        plugged = jack_settled(card, "on")
    return f"{plugged} with a screen, {jack_settled(card, 'off')} without"


def hdmi_connected() -> bool:
    return any(
        read(f"{c}/status") == "connected" for c in glob.glob("/sys/class/drm/card*-HDMI-A-*")
    )


def offered_samples(card: str) -> list[str]:
    """The PCM sample formats the card's PCM offers, its IEC 958 subframes aside: the datasheet's
    16 to 32 bits."""
    out = subprocess.run(
        ["aplay", "-D", f"hw:{card},0", "--dump-hw-params", "-s", "1", "/dev/zero"],
        capture_output=True,
        text=True,
        check=False,
    )
    found = re.search(r"^FORMAT:\s*(.*)$", out.stderr + out.stdout, re.M)
    return [f for f in found.group(1).split() if f.startswith(("S", "U"))] if found else []


def offered_rates(card: str) -> list[int]:
    """The AUDIO_RATES the card's PCM plays as asked: hw: plays one it lacks at the nearest, with
    only a warning."""
    offered = []
    for rate in AUDIO_RATES:
        cmd = [
            "aplay",
            "-D",
            f"hw:{card},0",
            "-r",
            str(rate),
            "-c",
            "2",
            "-f",
            "S16_LE",
        ]
        out = subprocess.run(
            cmd + ["-s", str(RATE_PROBE_SAMPLES), "/dev/zero"],
            capture_output=True,
            text=True,
            check=False,
        )
        if not out.returncode and "not accurate" not in out.stderr:
            offered.append(rate)
    return offered


def rate_seconds(card: str, rate: int, sample: str = "S16_LE") -> str:
    """How long 2 s of audio at rate takes to play: a 3 s play less a 1 s one, so the silence that
    pads the last period, constant, cancels out."""
    short, long = timed_play(card, rate, 2, 1, sample), timed_play(card, rate, 2, 3, sample)
    if "refused" in (short, long):
        return "refused"
    return f"{float(long) - float(short):.3f}"


def timed_play(
    card: str, rate: int, channels: int, seconds: int = 3, sample: str = "S16_LE"
) -> str:
    start = time.monotonic()
    out = subprocess.run(
        [
            "aplay",
            "-q",
            "-D",
            f"hw:{card},0",
            "-r",
            str(rate),
            "-f",
            sample,
            "-c",
            str(channels),
            "-d",
            str(seconds),
            "/dev/zero",
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    if out.returncode:
        return "refused"
    return f"{time.monotonic() - start:.2f}"


def disabled_routes(card: str) -> str:
    """A route left DISABLED plays at full rate into silence."""
    names, items, off = "", {}, []
    for line in sh(f"amixer -c {card} contents").splitlines():
        if line.startswith("numid="):
            names = line.split("'")[1] if "'" in line else line
            items = {}
        elif "; Item #" in line:
            number, item = line.split("#", 1)[1].split(" ", 1)
            items[number] = item.strip("'")
        elif ": values=" in line and items.get(line.split("=")[-1]) == "DISABLED":
            off.append(names)
    return " ".join(off) or NONE


# display.md H13


def gpu_ladder() -> str:
    """The GPU's devfreq rates, each with its rail's voltage where a regulator supplies the GPU
    alone to scale: system.md S25, read against stock's ladder."""
    found = [d for d in sorted(glob.glob("/sys/class/devfreq/*")) if "gpu" in Path(d).name]
    if not found:
        return "no GPU devfreq"
    dev = found[0]
    rates = read(f"{dev}/available_frequencies").split()
    name = Path(dev).name
    rails = [r for r in glob.glob("/sys/class/regulator/regulator.*") if glob.glob(f"{r}/{name}-*")]
    governor = read(f"{dev}/governor")
    if not rails or "userspace" not in read(f"{dev}/available_governors"):
        return f"{' '.join(str(int(r) // 1000000) for r in rates)} MHz, the rail fixed"
    steps = []
    with contextlib.suppress(OSError):
        Path(f"{dev}/governor").write_text("userspace")
        for rate in rates:
            Path(f"{dev}/userspace/set_freq").write_text(rate)
            time.sleep(0.5)
            steps.append(
                f"{int(rate) // 1000000}@{int(read(f'{rails[0]}/microvolts') or 0) // 1000}"
            )
    Path(f"{dev}/governor").write_text(governor)
    return " ".join(steps) or NONE


def gpu() -> Iterator[Line]:
    yield "gpu.ladder", gpu_ladder()
    if not have("glmark2-es2-drm"):
        yield "glmark2", "no glmark2"
        return
    with screen():
        out = sh(f"glmark2-es2-drm --off-screen {PROFILE.glmark2}", timeout=900)
    for scene, options, fps in re.findall(r"^\[(\w+)\] (.*?): FPS: (\d+)", out, re.MULTILINE):
        yield f"glmark2.{scene}.{options.replace(' ', '_').replace('<default>', 'default')}", fps
    unsupported = re.findall(r"^\[(\w+)\] .*?: Unsupported", out, re.MULTILINE)
    yield "glmark2.unsupported", " ".join(unsupported) or NONE
    score = re.search(r"glmark2 Score: (\d+)", out)
    yield "glmark2.score", score.group(1) if score else "failed"


# input.md


def on_usb(device: str) -> bool:
    """An input under a USB bus: a keyboard or mouse plugged in, not the board's."""
    return re.search(r"/usb\d+/", device) is not None


def input_() -> Iterator[Line]:
    unnamed = []
    for event in sorted(glob.glob("/dev/input/event*")):
        linked = any(
            os.path.realpath(l) == event for l in glob.glob("/dev/input/*") if os.path.islink(l)
        )
        device = os.path.realpath(f"/sys/class/input/{Path(event).name}/device")
        if not linked and not on_usb(device):
            unnamed.append(read(f"/sys/class/input/{Path(event).name}/device/name"))
    yield "input.unnamed", "; ".join(unnamed) or NONE
    for rc in sorted(glob.glob("/sys/class/rc/rc*")):
        driver = Path(os.path.realpath(f"{rc}/device/driver")).name
        if not have("ir-keytable"):
            yield f"ir.{Path(rc).name}", f"{driver}, no ir-keytable"
            continue
        table = sh(f"ir-keytable -r -s {Path(rc).name}") if have("ir-keytable") else ""
        keys = re.findall(r"scancode (0x[0-9a-f]+) = (KEY_\w+)", table)
        digest = hashlib.sha256(" ".join(f"{s}={k}" for s, k in keys).encode()).hexdigest()
        keymap = re.search(r"Default keymap: (\S+)", sh(f"ir-keytable -s {Path(rc).name} 2>&1"))
        yield f"ir.{Path(rc).name}", (
            f"{driver} {keymap.group(1) if keymap else '?'} {len(keys)} keys {digest[:8]}"
        )
    for rc in sorted(glob.glob("/sys/class/rc/rc*")):
        protocols = re.findall(r"\[(\w+)\]", read(f"{rc}/protocols"))
        wake = read(f"{rc}/device/power/wakeup") or "?"
        yield f"ir.{Path(rc).name}.protocols", f"{' '.join(protocols) or NONE}, wake {wake}"
    if enabled(*IR_RECEIVERS):
        yield "ir.node", ("/dev/input/ir-remote" if Path("/dev/input/ir-remote").exists() else NONE)
    yield "ir.tables", remotectl_tables()
    yield "usb.devices", str(len(sh("lsusb").splitlines()))
    controllers = [
        Path(d).name
        for d in glob.glob("/sys/bus/platform/devices/*")
        if re.search(r"usb|ehci|ohci|xhci|dwc|musb", read(f"{d}/of_node/compatible"))
        and read(f"{d}/of_node/status") in ("", "okay", "ok")
        and not Path(f"{d}/driver").exists()
    ]
    yield "usb.controllers.unbound", " ".join(controllers) or NONE
    errors = [
        l
        for l in dmesg()
        if re.search(r"over-current|device descriptor read|unable to enumerate", l)
    ]
    yield "usb.errors", str(len(errors))
    tree = sh("lsusb -t")
    hubs = len(re.findall(r"Class=Hub", tree)) - len(re.findall(r"^/:", tree, re.MULTILINE))
    yield "usb.hubs.external", str(max(hubs, 0))
    yield "usb.speeds", " ".join(sorted(set(re.findall(r"(\d+M)$", tree, re.MULTILINE)))) or NONE
    button = "/dev/input/recovery-button"
    if Path(button).exists():
        caps = read(
            f"/sys/class/input/{Path(os.path.realpath(button)).name}/device/capabilities/key"
        )
        vendor = 0x168  # KEY_VENDOR
        bits = int("".join(f"{int(w, 16):016x}" for w in caps.split()), 16) if caps else 0
        yield "button.recovery", ("KEY_VENDOR" if bits >> vendor & 1 else "lacks KEY_VENDOR")
    else:
        yield "button.recovery", NONE
    yield "leds", " ".join(map(led, sorted(glob.glob("/sys/class/leds/*")))) or NONE
    yield "leds.driven", leds_driven()
    yield "buttons.idle", buttons_idle()


def remotectl_tables() -> str:
    """Rockchip's vendor IR receiver keeps its keymaps in the tree: each remote's user code and a
    digest of its table, so a changed table shows between runs."""
    tables = []
    for compatible in glob.glob("/proc/device-tree/*/compatible"):
        if "remotectl" not in read(compatible):
            continue
        for key in sorted(glob.glob(f"{Path(compatible).parent}/ir_key*")):
            code = Path(f"{key}/rockchip,usercode").read_bytes().hex()[-4:]
            table = Path(f"{key}/rockchip,key_table").read_bytes()
            tables.append(f"{code}:{len(table) // 8}:{hashlib.sha256(table).hexdigest()[:8]}")
    return " ".join(tables) or NONE


def gpio_lines() -> dict[str, str]:
    """debugfs's GPIO lines by consumer: "out hi", "in lo" and so on."""
    lines = {}
    for line in read("/sys/kernel/debug/gpio").splitlines():
        found = re.search(r"\|(\S+)\s*\)?\s+(in|out)\s+(hi|lo)", line)
        if found:
            lines[found.group(1)] = f"{found.group(2)} {found.group(3)}"
    return lines


def leds_driven() -> str:
    """input.md E1, electrically: each GPIO LED driven on and off, its line's level read back from
    the controller; its state and trigger restored after."""
    results = []
    for path in sorted(glob.glob("/sys/class/leds/*")):
        name = Path(path).name
        if name.startswith("input") or name not in gpio_lines():
            continue
        trigger = re.search(r"\[(\S+)\]", read(f"{path}/trigger"))
        brightness = read(f"{path}/brightness")
        levels = []
        for value in ("1", "0"):
            Path(f"{path}/brightness").write_text(value)
            time.sleep(0.2)
            levels.append(gpio_lines().get(name, "?").split()[-1])
        Path(f"{path}/trigger").write_text(trigger.group(1) if trigger else "none")
        Path(f"{path}/brightness").write_text(brightness or "0")
        results.append(f"{name}:{'/'.join(levels)}")
    return " ".join(results) or NONE


def buttons_idle() -> str:
    """input.md R4, R5: each button at rest, no key held: an ADC key's channel above its keys'
    thresholds, a GPIO key's line not active."""
    out = []
    for node in glob.glob("/proc/device-tree/**/compatible", recursive=True):
        compatible = read(node)
        if "adc-keys" in compatible:
            idle = int.from_bytes(
                Path(Path(node).parent / "keyup-threshold-microvolt").read_bytes(),
                "big",
            )
            raw = [read(f) for f in glob.glob("/sys/bus/iio/devices/iio:device*/in_voltage*_raw")]
            out.append(f"adc-keys keyup {idle // 1000} mV, channels {' '.join(raw) or '?'}")
        elif "gpio-keys" in compatible:
            held = [
                c for c, state in gpio_lines().items() if state == "in lo" and "key" in c.lower()
            ]
            out.append(f"gpio-keys held: {' '.join(held) or NONE}")
    return "; ".join(out) or NONE


def led(path: str) -> str:
    """An LED's brightness and the trigger it runs, as name=brightness/trigger."""
    trigger = re.search(r"\[(\S+)\]", read(f"{path}/trigger"))
    return f"{Path(path).name}={read(f'{path}/brightness')}/{trigger.group(1) if trigger else '?'}"


# power.md


def remote_wake() -> str:
    """How many of the box's IR receivers may wake it from sleep, by name: a remote that cannot
    wake a sleeping box strands it, its power key the only way to sleep."""
    receivers = [
        r for r in sorted(glob.glob("/sys/class/rc/rc*")) if "[cec]" not in read(f"{r}/protocols")
    ]
    if not receivers:
        return "no IR receiver"
    armed = [r for r in receivers if read(f"{r}/device/power/wakeup") == "enabled"]
    names = " ".join(
        f"{Path(r).name}:{read(f'{r}/device/power/wakeup') or 'none'}" for r in receivers
    )
    return f"{len(armed)} of {len(receivers)} armed: {names}"


def power(sleep: int) -> Iterator[Line]:
    wakers = [
        Path(root).parent.name
        for root, _, files in os.walk("/sys/devices")
        if root.endswith("/power") and "wakeup" in files and read(f"{root}/wakeup") == "enabled"
    ]
    yield "wake.sources", " ".join(sorted(set(wakers))) or NONE
    yield "sleep.states", read("/sys/power/mem_sleep") or NONE
    yield "wake.remote", remote_wake()
    rtc = read("/sys/class/rtc/rtc0/name")
    yield "rtc", rtc or NONE
    if rtc:
        drift = int(read("/sys/class/rtc/rtc0/since_epoch") or 0) - int(time.time())
        yield "rtc.drift.s", str(drift)
    if sleep <= 0 or not rtc:
        yield "suspend", "not run" if rtc else "no RTC to wake by"
        return
    boot, entered = read("/proc/sys/kernel/random/boot_id"), read(SUSPENDS)
    start = uptime()
    done = subprocess.run(["rtcwake", "-m", "freeze", "-s", str(sleep)], capture_output=True)
    slept = uptime() - start
    same = read("/proc/sys/kernel/random/boot_id") == boot
    after = read(SUSPENDS)
    asleep = (
        done.returncode == 0 and entered.isdigit() and after.isdigit() and int(after) > int(entered)
    )
    yield "suspend.s2idle", (
        f"{'same boot' if same else 'NEW BOOT'}, {'slept' if asleep else 'did not sleep'}, "
        f"{slept:.0f} s for {sleep}"
    )
    yield "suspend.watchdog", read("/sys/class/watchdog/watchdog0/state") or NONE


# system.md S21


def soak(seconds: int, iperf: str) -> Iterator[Line]:
    if seconds <= 0:
        yield "soak", "not run"
        return
    # the step before, a sleep, may leave a radio still rejoining
    if iperf and have("ping") and not reachable(iperf, SOAK_SETTLE_S):
        yield "soak.server", f"failed: {iperf} not answering after {SOAK_SETTLE_S} s"
    before = len(dmesg("err,warn"))
    jobs = [
        [
            "stress-ng",
            "--cpu",
            "0",
            "--vm",
            "1",
            "--vm-bytes",
            "30%",
            "--hdd",
            "1",
            "-t",
            f"{seconds}s",
            "--metrics-brief",
        ]
    ]
    if have("glmark2-es2-drm"):
        jobs.append(
            [
                "sh",
                "-c",
                f"end=$(($(date +%s)+{seconds})); while [ $(date +%s) -lt $end ];"
                " do glmark2-es2-drm --off-screen >/dev/null 2>&1 || exit 1; done",
            ]
        )
    if iperf and have("ping"):  # a ping stream: the iperf3 server takes one client at a time
        jobs.append(["ping", "-q", "-i", "0.01", "-s", "1400", "-w", str(seconds), iperf])
    with screen():
        running = [
            subprocess.Popen(
                j,
                cwd="/var/tmp",
                stdout=subprocess.PIPE,
                stderr=subprocess.DEVNULL,
                text=True,
                start_new_session=True,
            )
            for j in jobs
        ]
        hot = 0.0
        deadline = time.monotonic() + seconds
        while time.monotonic() < deadline:
            time.sleep(min(10, max(0.0, deadline - time.monotonic())))
            hot = max(hot, hottest())
        codes = [ended(job) for job in running]
        outputs = [job.communicate()[0] for job in running]
    loss = re.search(r"([\d.]+)% packet loss", outputs[-1]) if iperf else None
    new = dmesg("err,warn")[before:]
    yield "soak.c", f"{hot:.1f} max over {seconds} s"
    yield "soak.warnings", f"{len(new)}: {'; '.join(new[:3])}" if new else "0"
    yield "soak.jobs", " ".join(str(code) for code in codes)
    yield "soak.cpu.ops", stressor_ops(outputs[0], "cpu")
    if iperf:
        yield "soak.ping.loss", f"{loss.group(1)} %" if loss else "failed"


def stressor_ops(metrics: str, stressor: str) -> str:
    """A stressor's bogo ops from stress-ng's --metrics-brief: the work done, beside its heat."""
    found = re.search(rf"metrc: \[\d+\] {stressor} +(\d+)", metrics)
    return found.group(1) if found else NONE


def reachable(host: str, seconds: int) -> bool:
    """Whether host answers a ping within seconds: a radio back from sleep rejoins first."""
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        answer = subprocess.run(["ping", "-c", "1", "-W", "1", host], capture_output=True)
        if answer.returncode == 0:
            return True
        time.sleep(1)
    return False


def ended(job: subprocess.Popen[str]) -> int:
    """A soak job's exit status: one still running at the deadline, a glmark2 run past it, ran its
    course and is stopped, never left holding the GPU and the display."""
    try:
        return job.wait(timeout=SOAK_GRACE_S)
    except subprocess.TimeoutExpired:
        os.killpg(job.pid, signal.SIGTERM)
        job.wait()
        return 0


def verdict(key: str, value: str) -> str | None:
    """FAIL where a rule's test fails, UNTESTED where the box lacked what the check needs."""
    if value.startswith(("no ", "not run")):
        return "UNTESTED"
    for pattern, passes in RULES:
        if re.fullmatch(pattern, key):
            try:
                return None if passes(value) else "FAIL"
            except (ValueError, IndexError):
                return "FAIL"
    return None


def main() -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--suite", default=",".join(SUITES), help="comma-separated")
    parser.add_argument("--profile", choices=PROFILES, default="default")
    parser.add_argument("--iperf", default="", help="an iperf3 server the box resolves")
    parser.add_argument("--sleep", type=int, help="s2idle seconds; the profile's by default")
    parser.add_argument("--soak", type=int, help="soak seconds; the profile's by default")
    args = parser.parse_args()
    global PROFILE
    PROFILE = PROFILES[args.profile]
    sleep_s = args.sleep or PROFILE.sleep_s
    soak_s = args.soak or PROFILE.soak_s
    suites: dict[str, Callable[[], Iterator[Line]]] = {
        "system": system,
        "cpu": cpu,
        "storage": storage,
        "network": network,
        "throughput": lambda: throughputs(args.iperf),
        "display": display,
        "audio": audio,
        "gpu": gpu,
        "input": input_,
        "power": lambda: power(sleep_s),
        "crypto": crypto_bench,
        "soak": lambda: soak(soak_s, args.iperf),
    }
    failed = False
    for name in args.suite.split(","):
        if name not in suites:
            sys.exit(f"no sub-suite {name}: {', '.join(suites)}")
        for key, value in suites[name]():
            value = value or NONE
            print(f"{key} {value}", flush=True)
            judged = verdict(key, value)
            if judged:
                print(f"{judged} {key}", flush=True)
            failed |= judged == "FAIL"
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
