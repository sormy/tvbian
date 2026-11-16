#!/usr/bin/env python3
"""A running box against the bring-up criteria, unattended: one sub-suite a bring-up phase.

On the box, as root, Python's standard library only; regression.py copies it there and runs it
detached, as a sub-suite may reload the Wi-Fi driver the session rides on:

    python3 box.py [--suite system,storage,...] [--iperf HOST] [--sleep SECONDS] [--soak SECONDS]

Every line is "key value"; a missing tool or device is a value, never a gap. The sub-suites, in
order, each named after the bring-up doc it measures:

    system     identity, boot, log, modules, devices, firmware, packages, kernel baseline, RAM
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
import glob
import hashlib
import os
import random
import re
import shutil
import signal
import subprocess
import sys
import time
from collections.abc import Callable, Iterator
from dataclasses import dataclass
from pathlib import Path

Line = tuple[str, str]
NONE = "none"
# Wi-Fi drivers with more than one mode: the module parameters to load each with, and whether
# Bluetooth, which rides on the Wi-Fi firmware, exists in it
MODES: dict[str, list[tuple[str, bool]]] = {
    "atbm6031": [("wifi_bt_comb=0", False), ("wifi_bt_comb=1", True)]
}
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
}
# tree nodes that never get a driver of their own: register banks, buses' QoS, the arch timer
DRIVERLESS = ("syscon", "qos", "timer", "opp-", "psci", "shmem", "debug")
# a SoC's crypto engine, not the CPU's instructions (the -ce drivers alone)
CRYPTO_ENGINE = r"sun8i-ce|^rk|meson|gxl-crypto"
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
    "soak",
)
# what passes, by key: a line no rule names is a measurement, compared run to run
EMPTY = ("none", "0")
RULES: list[tuple[str, Callable[[str], bool]]] = [
    (
        r"units\.failed|dmesg\.deferred|modules\.missing|drivers\.unbound|firmware\.failed"
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
    (r"hwrng", lambda v: v == "none" or int(v.split(": ")[1].split()[0]) >= 200),
    (r"emmc\..*\.wear", lambda v: v.endswith("pre-eol 0x01")),
    (r"eth\..*\.phy", lambda v: "Generic" not in v),
    (r".*\.reload|wifi\.restored", lambda v: v.endswith(" s")),
    (r"wifi\.reloads", lambda v: v.split("/")[0] == v.split("/")[1].split()[0]),
    (r".*\.region\.\w+", lambda v: not v.endswith("not taken")),  # N10: iw reg get shows it
    (r".*\.scan\.unset", lambda v: not v.startswith("0 ")),
    (r".*\.mbits", lambda v: v[:1].isdigit()),
    (r"fio\..*", lambda v: v[:1].isdigit()),
    (r"cpu\.load|soak\.server", lambda v: not v.startswith("failed")),
    (r"bt.*\.hci\d+", lambda v: "UP RUNNING" in v and set(v.split("errors ")[1]) <= {"0", "+"}),
    (r"bt.*\.find", lambda v: v != "0"),
    (r"audio\..*\.3s", lambda v: v != "refused" and 2.9 <= float(v) <= 3.3),
    (r"glmark2\.score", lambda v: v.isdigit()),
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
]
TAINT_STAGING, TAINT_OOT, TAINT_UNSIGNED = 1 << 10, 1 << 12, 1 << 13
SETTLE_PERCENT = 8
SUSPENDS = "/sys/power/suspend_stats/success"  # the kernel's count of system sleeps entered
SOAK_SETTLE_S = 30  # how long the soak waits for the server: a radio rejoining after sleep
SOAK_GRACE_S = 15  # past the soak's end, how long a job may take to finish on its own
FIO_LAYOUT_S = 120  # fio writes its file first: 512 MB on a slow SD card takes most of this
BUSY_WAIT_S = 900  # how long a box waits for the iperf3 server other boxes are using


@dataclass(frozen=True)
class Profile:
    """How long each check runs: short while working, minutes; default for every change, under
    30 minutes for both kernels; extended for a release, as long as bring-up's own checks."""

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
    yield "temp.idle.c", f"{hottest():.1f}"
    yield "boot.seconds", sh("systemd-analyze | grep -oE '= [0-9.]+s' | tr -d '= s'") or NONE
    blame = sh("systemd-analyze blame").splitlines()
    yield "boot.slowest", " ".join(blame[0].split()) if blame else NONE
    yield "units.failed", sh("systemctl --failed --no-legend --plain | awk '{print $1}' | xargs")
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
    unsigned (E) modules. Anything left, a warning or an oops among them, is a failure."""
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


def hwrng() -> str:
    current = read("/sys/class/misc/hw_random/rng_current")
    if not current or current == "none":
        return NONE
    with contextlib.suppress(OSError), open("/dev/hwrng", "rb") as f:
        data = f.read(4096)
        return f"{current}: {len(set(data))} distinct bytes of {len(data)}"
    return f"{current}: unreadable"


def iommu_irqs() -> str:
    """The IOMMU's interrupt count over 10 s at idle: one still firing is a fault storm."""

    def count() -> int:
        lines = [l for l in read("/proc/interrupts").splitlines() if "iommu" in l.lower()]
        return sum(int(x) for l in lines for x in l.split()[1:] if x.isdigit())

    before = count()
    time.sleep(PROFILE.iommu_s)
    return str(count() - before)


def missing_modules() -> str:
    packages = sh("dpkg-query -W -f '${Package}\\n' 'tvb-*-modules-*'").split()
    files = sh(f"dpkg -L {' '.join(packages)}").splitlines() if packages else []
    wanted = {Path(f).name.removesuffix(".ko") for f in files if f.endswith(".ko")}
    loaded = {line.split()[0] for line in read("/proc/modules").splitlines()}
    return " ".join(sorted(wanted - loaded)) or NONE


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
    out = sh(f"stress-ng --stream {workers} -t {PROFILE.stream_s}s --metrics 2>&1", timeout=60)
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
    while load.poll() is None:
        time.sleep(5)
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


def network() -> Iterator[Line]:
    for name in board_nets("device"):
        path = f"/sys/class/net/{name}"
        kind = read(f"{path}/addr_assign_type")
        yield f"addr.{name}", f"{read(f'{path}/address')} type {kind}"
    for name in board_nets("phydev"):
        driver = Path(os.path.realpath(f"/sys/class/net/{name}/phydev/driver")).name
        yield f"eth.{name}.phy", driver
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
            ["stress-ng", "--cpu", "0", "--hdd", "1", "-t", f"{PROFILE.loaded_s}s", "-q"],
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
        yield f"{tag}.region.{region}", country if country == region else f"{country}, not taken"
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
        yield f"{tag}.{way}.mbits", f"{median:.0f}{rate}" if median is not None else f"failed{rate}"


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
        for rate in (44100, 48000):
            yield f"audio.{name}.{rate}.3s", timed_play(number, rate, 2)
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


def max_channels(card: str) -> int:
    """The most channels the card's PCM takes, by its hardware parameters."""
    out = sh(f"aplay -D hw:{card},0 --dump-hw-params -d 1 /dev/zero 2>&1", timeout=20)
    found = re.search(r"CHANNELS:\s*\[?\s*\d+\s+(\d+)\]?|CHANNELS:\s*(\d+)", out)
    return int(found.group(1) or found.group(2)) if found else 2


@contextlib.contextmanager
def screen() -> Iterator[None]:
    """A connected HDMI connector for the time: glmark2 asks for one even off-screen. Forced on
    where nothing is plugged in, and back to detecting after."""
    forced = [] if hdmi_connected() else glob.glob("/sys/class/drm/card*-HDMI-A-*/status")
    for status in forced:
        Path(status).write_text("on")
    try:
        yield
    finally:
        for status in forced:
            Path(status).write_text("detect")


def hdmi_connected() -> bool:
    return any(
        read(f"{c}/status") == "connected" for c in glob.glob("/sys/class/drm/card*-HDMI-A-*")
    )


def timed_play(card: str, rate: int, channels: int) -> str:
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
            "S16_LE",
            "-c",
            str(channels),
            "-d",
            "3",
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


def gpu() -> Iterator[Line]:
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
        yield "ir.node", "/dev/input/ir-remote" if Path("/dev/input/ir-remote").exists() else NONE
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
        yield "button.recovery", "KEY_VENDOR" if bits >> vendor & 1 else "lacks KEY_VENDOR"
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
                Path(Path(node).parent / "keyup-threshold-microvolt").read_bytes(), "big"
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


def power(sleep: int) -> Iterator[Line]:
    wakers = [
        Path(root).parent.name
        for root, _, files in os.walk("/sys/devices")
        if root.endswith("/power") and "wakeup" in files and read(f"{root}/wakeup") == "enabled"
    ]
    yield "wake.sources", " ".join(sorted(set(wakers))) or NONE
    yield "sleep.states", read("/sys/power/mem_sleep") or NONE
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
            "-q",
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
    if iperf:
        yield "soak.ping.loss", f"{loss.group(1)} %" if loss else "failed"


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
    parser.add_argument(
        "--sleep", type=int, default=120, help="s2idle seconds: past the watchdog's 80 s (W6)"
    )
    parser.add_argument("--soak", type=int, default=1800, help="soak seconds")
    args = parser.parse_args()
    global PROFILE
    PROFILE = PROFILES[args.profile]
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
        "power": lambda: power(args.sleep),
        "soak": lambda: soak(args.soak, args.iperf),
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
