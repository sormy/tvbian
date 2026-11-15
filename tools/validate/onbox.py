#!/usr/bin/env python3
"""The regression suite's run on the box, alone: every kernel of the plan, every step of its
profile, across the reboots the run makes itself. regression.py deploys it and collects after.

    python3 onbox.py step     what tvb-regress.service runs at every boot

plan.json, beside this file, is what to run; state.json, how far it got; results/<kernel>/, what
each step printed, and results/run.log, when. A step that reboots the box (a kernel switch, a
panic, the watchdog, a reboot) records what it began, and the next boot records how it ended.
When the plan is done the boot default comes back, the unit is disabled and results/done is
written.
"""

from __future__ import annotations

import fcntl
import json
import os
import re
import subprocess
import sys
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path

from results import Known, crash, new_failures

HERE = Path(__file__).resolve().parent
RESULTS = HERE / "results"
STATE = HERE / "state.json"
EXTLINUX = Path("/boot/extlinux/extlinux.conf")
PSTORE = Path("/var/lib/systemd/pstore")
UNIT = "tvb-regress.service"
GUARD_UNIT = "tvb-regress-guard.service"
WATCHDOG_WAIT_S = 300  # an unpinged watchdog resets within this, or never will
WDIOC_GETTIMEOUT = 0x80045707
WDIOC_SETTIMEOUT = 0xC0045706
WATCHDOG_TEST_S = 10  # the unpinged watchdog's timeout: systemd's 80 s proves nothing more


@dataclass
class Step:
    name: str
    command: list[str]
    seconds: int
    needs: list[str] = field(default_factory=list)  # steps whose new failures make this one moot


@dataclass
class Plan:
    board: str
    kernels: list[str]
    steps: list[Step]
    reboots: int

    @staticmethod
    def load() -> Plan:
        raw = json.loads((HERE / "plan.json").read_text())
        steps = [Step(**s) for s in raw["steps"]]
        return Plan(raw["board"], raw["kernels"], steps, raw["reboots"])


@dataclass
class Pending:
    """A step that may end in a reboot, as it began."""

    kind: str  # "switch", "panic", "watchdog", "reboot" or "step"
    boot: str
    at: float
    detail: str = ""


@dataclass
class State:
    default: str = ""  # the boot entry before the run, restored after
    kernel: int = 0  # the plan's kernel under test
    steps_done: list[str] = field(default_factory=list)
    reboots_done: int = 0
    recovery: int = 0  # 1: the panic began, 2: the watchdog began
    booted: bool = False  # this run booted the kernel under test, so what it installed is live
    pending: Pending | None = None

    @staticmethod
    def load() -> State:
        if not STATE.exists():
            return State()
        raw = json.loads(STATE.read_text())
        pending = raw.pop("pending", None)
        return State(**raw, pending=Pending(**pending) if pending else None)

    def save(self) -> None:
        STATE.write_text(json.dumps(asdict(self), indent=1))

    def begin(self, kind: str, detail: str = "") -> None:
        self.pending = Pending(kind, boot_id(), time.time(), detail)
        self.save()


def log(line: str) -> None:
    RESULTS.mkdir(parents=True, exist_ok=True)
    with (RESULTS / "run.log").open("a") as f:
        f.write(f"{time.strftime('%H:%M:%S')} {line}\n")


def boot_id() -> str:
    return Path("/proc/sys/kernel/random/boot_id").read_text().strip()


def booted_at() -> float:
    """When this boot began, wall-clock seconds."""
    return time.time() - float(Path("/proc/uptime").read_text().split()[0])


def default_entry() -> str:
    found = re.search(r"^default (\S+)", EXTLINUX.read_text(), re.MULTILINE)
    return found.group(1) if found else ""


def entry_for(release: str) -> str | None:
    """The extlinux entry booting release, not its recovery twin (a label ending in r)."""
    current = ""
    for line in EXTLINUX.read_text().splitlines():
        words = line.split()
        if words[:1] == ["label"]:
            current = words[1]
        elif words[:1] == ["linux"] and words[1].endswith(release) and current[-1:] != "r":
            return current
    return None


def set_default(entry: str) -> None:
    text = re.sub(r"^default .*$", f"default {entry}", EXTLINUX.read_text(), flags=re.MULTILINE)
    EXTLINUX.write_text(text)


def reboot() -> None:
    subprocess.run(["sync"], check=False)
    subprocess.run(["systemctl", "reboot"], check=False)
    time.sleep(600)  # the reboot ends the process


def record(out: Path, name: str, lines: list[str]) -> None:
    out.mkdir(parents=True, exist_ok=True)
    with (out / f"{name}.txt").open("a") as f:
        f.write("\n".join(lines) + "\n")


def run(step: Step, out: Path) -> None:
    """One step's output to out/<name>.txt, killed with its children past its time."""
    out.mkdir(parents=True, exist_ok=True)
    started = time.monotonic()
    with (out / f"{step.name}.txt").open("w") as f:
        process = subprocess.Popen(
            step.command, cwd=HERE, stdout=f, stderr=subprocess.STDOUT, start_new_session=True
        )
        try:
            status = str(process.wait(timeout=step.seconds))
        except subprocess.TimeoutExpired:
            os.killpg(process.pid, 9)
            process.wait()
            status = f"KILLED past {step.seconds} s"
            f.write(f"FAIL {step.name}: {status}\n")
        f.write(f"exit {status}\n")
    log(f"{out.name}: {step.name} exit {status}, {time.monotonic() - started:.0f} s")


def ended(state: State, out: Path) -> None:
    """How the step that rebooted the box ended, now that it is back."""
    pending, state.pending = state.pending, None
    if pending is None:
        return
    gap = booted_at() - pending.at
    new_boot = boot_id() != pending.boot
    if pending.kind == "panic":
        records = len(list(PSTORE.rglob("dmesg*"))) if PSTORE.exists() else 0
        lines = [f"recovery.panic back {gap:.0f} s after it, {records} pstore records"]
        lines += [] if new_boot else ["FAIL recovery.panic: the same boot"]
    elif pending.kind == "watchdog":
        lines = [f"recovery.watchdog {pending.detail}, reset {gap:.0f} s after it went unpinged"]
        late = gap > WATCHDOG_WAIT_S + 120
        lines += [] if new_boot and not late else ["FAIL recovery.watchdog: no timely reset"]
    elif pending.kind == "step":  # it never returned: its output stays, the step is not rerun
        state.steps_done.append(pending.detail)
        how = "the box reset during it" if new_boot else "the run stopped during it"
        record(out, pending.detail, [f"FAIL {pending.detail}: {how}"])
        state.save()
        log(f"{out.name}: {pending.detail} did not return")
        return
    else:  # a reboot
        state.reboots_done += 1
        lines = [f"reboot.{state.reboots_done} back, {gap:.0f} s to boot"]
    record(out, "recovery" if pending.kind != "reboot" else "reboots", lines)
    state.save()
    log(f"{out.name}: {pending.kind} ended, {gap:.0f} s")


def step() -> int:
    plan, state = Plan.load(), State.load()
    if not state.default:
        state.default = default_entry()
    try:
        return run_kernels(plan, state)
    except Crashed as error:  # fail fast: stop the run, say why
        return finish(state, "crashed", str(error))


def run_kernels(plan: Plan, state: State) -> int:
    """Each kernel of the plan booted in turn and its steps run, to the end."""
    while state.kernel < len(plan.kernels):
        release = plan.kernels[state.kernel]
        out = RESULTS / release
        switched = state.pending is not None and state.pending.kind == "switch"
        if switched:
            state.pending = None
        ended(state, out)
        if switched and os.uname().release == release:
            state.booted = True
        if not state.booted:  # booted even when already running it: the install takes effect
            entry = entry_for(release)
            if entry is None or switched:  # no entry, or the guard brought the default back
                log(f"{release}: {'no extlinux entry' if entry is None else 'did not boot'}")
                record(out, "boot", [f"FAIL boot: {release} did not come up"])
                state.kernel += 1
                state.save()
                continue
            state.begin("switch", release)
            set_default(entry)
            log(f"{release}: booting {entry}")
            reboot()
            return 0
        if not carry_on(plan, state, out):
            return 0  # a step rebooted the box; the next boot resumes
        state.kernel, state.steps_done, state.reboots_done, state.recovery, state.booted = (
            state.kernel + 1,
            [],
            0,
            0,
            False,
        )
        state.save()
    return finish(state, "done", "the default back")


class Crashed(Exception):
    """A step's script died of its own bug: every result after it would be the suite's, not the
    box's."""


def finish(state: State, marker: str, why: str) -> int:
    """The run over, done or crashed: the default boot back, the units off, the marker the host
    waits for."""
    set_default(state.default)
    subprocess.run(["systemctl", "disable", UNIT, GUARD_UNIT], check=False)
    (RESULTS / marker).write_text(f"{time.strftime('%Y-%m-%d %H:%M:%S')} {why}\n")
    log(f"{marker}: {why}")
    reboot()
    return 0


def carry_on(plan: Plan, state: State, out: Path) -> bool:
    """The kernel's steps not yet done; False when one rebooted the box."""
    for item in plan.steps:
        if item.name in state.steps_done:
            continue
        if item.name == "recovery":
            while state.recovery < 2:
                if recover(state, out):
                    return False
        elif item.name == "reboots":
            if state.reboots_done < plan.reboots:
                state.begin("reboot")
                reboot()
                return False
        elif blocked := new_failures(out, item.needs, Known.load(HERE / "known.conf"), plan.board):
            # an expensive step on a box already failing in new ways measures nothing worth its time
            reason = f"not run, new failures before it: {'; '.join(blocked[:3])}"
            record(out, item.name, [f"{item.name} {reason}", f"UNTESTED {item.name}"])
            log(f"{out.name}: {item.name} {reason}")
        else:
            state.begin("step", item.name)
            run(item, out)
            state.pending = None
            if why := crash(out / f"{item.name}.txt"):
                state.save()
                raise Crashed(f"{out.name}: {item.name}: {why}")
        state.steps_done.append(item.name)
        state.save()
    return True


def recover(state: State, out: Path) -> bool:
    """system.md S16, then S15: a panic, then an unpinged watchdog, each ended by the reboot it
    makes. True while a reboot is on its way; a watchdog that never resets is written as a
    failure here, and the run goes on."""
    state.recovery += 1
    os.sync()  # each makes the kernel stop dead: what is not on disk is lost
    if state.recovery == 1:
        state.begin("panic")
        Path("/proc/sys/kernel/sysrq").write_text("1")
        time.sleep(2)
        Path("/proc/sysrq-trigger").write_text("c")
        time.sleep(60)  # the panic ends the process
        return True
    held, fd = take_watchdog()
    if fd is None:
        record(out, "recovery", [f"recovery.watchdog {held}", "FAIL recovery.watchdog"])
        state.save()
        return False
    state.begin("watchdog", held)
    time.sleep(WATCHDOG_WAIT_S)
    record(out, "recovery", [f"recovery.watchdog {held}", "FAIL recovery.watchdog: no reset"])
    state.pending = None
    state.save()
    give_back_watchdog(fd)
    return False


def give_back_watchdog(fd: int) -> None:
    """The watchdog closed with its magic character, which stops it, and handed back to
    systemd."""
    os.write(fd, b"V")
    os.close(fd)
    manager = ["org.freedesktop.systemd1", "/org/freedesktop/systemd1"]
    held = ["org.freedesktop.systemd1.Manager", "RuntimeWatchdogUSec", "t", "80000000"]
    subprocess.run(["busctl", "set-property", *manager, *held], check=False)


def rollback() -> int:
    """The boot guard's way back: the default before the run, and a reboot."""
    state = State.load()
    if state.default:
        set_default(state.default)
        log("rollback: no network on this kernel, the default back")
        reboot()
    return 0


def take_watchdog() -> tuple[str, int | None]:
    """The watchdog from systemd, opened and left unpinged: "armed <seconds> s" and its file, or
    why not."""
    manager = ["org.freedesktop.systemd1", "/org/freedesktop/systemd1"]
    release = ["org.freedesktop.systemd1.Manager", "RuntimeWatchdogUSec", "t", "0"]
    subprocess.run(["busctl", "set-property", *manager, *release], check=False)
    time.sleep(1)
    try:
        fd = os.open("/dev/watchdog0", os.O_WRONLY)
    except OSError as error:
        return f"refused: {error.strerror}", None
    os.write(fd, b"1")
    fcntl.ioctl(fd, WDIOC_SETTIMEOUT, WATCHDOG_TEST_S.to_bytes(4, "little"))
    seconds = int.from_bytes(fcntl.ioctl(fd, WDIOC_GETTIMEOUT, b"\0" * 4), "little")
    return f"armed {seconds} s", fd


if __name__ == "__main__":
    commands = {"step": step, "rollback": rollback}
    sys.exit(commands[sys.argv[1]]() if sys.argv[1:] and sys.argv[1] in commands else 2)
