"""The checks only a power switch makes safe, run from the host once a box's on-box run has ended:
asleep, a box stays asleep; powered off, it stays off. Neither needs a wake source: the switch
ends each hold and brings the box back, so a box that never wakes costs a power cycle, not a run.
`regression.py run --power-switch` runs them."""

from __future__ import annotations

import shlex
import subprocess
import time
from dataclasses import dataclass
from typing import Callable, Protocol

# a box answering within this after the command went down on its own: it never slept, or a
# watchdog brought it back; long enough for the hardware watchdog's ~90 s and its own boot
HOLD_S = {"sleep": 180, "poweroff": 300}
COMMANDS = {"sleep": "systemctl suspend", "poweroff": "systemctl poweroff"}
POLL_S = 15
SETTLE_S = 10  # the command's own shutdown, before the hold is timed
OFF_S = 5  # the outlet off, for the box to lose its power
BOOT_S = 300  # a box back from the switch's power cycle within this, or a failure
STARTUP_S = 300  # how long a just-booted box's startup may take before a test asks anything of it
BOOT_ONCE_S = 180  # boot_once.py's initramfs, which a box just up builds slower than an idle one
BOOT_ONCE = "/var/lib/tvb-regress/boot_once.py"
BOARD_ID = "/usr/lib/tvb/board-id"
RESULTS = "/var/lib/tvb-regress/results"


class Remote(Protocol):
    def raw(
        self, command: str, stdin: bytes = b"", seconds: float = ..., check: bool = ...
    ) -> bytes: ...


@dataclass
class PowerSwitch:
    """A box and the command that switches its outlet, `{state}` filled with on or off."""

    board: str
    box: Remote
    command: str
    sleep: Callable[[float], None] = time.sleep

    def switch(self, state: str) -> None:
        subprocess.run(
            self.command.format(state=state), shell=True, check=True, capture_output=True
        )

    def answers(self, kernel: str = "") -> bool:
        """Whether the box answers as this board, on kernel where one is named."""
        try:
            said = self.box.raw(f"cat {BOARD_ID}; uname -r", seconds=15, check=True).decode()
        except ConnectionError:
            return False
        lines = said.split()
        return bool(lines) and lines[0] == self.board and (not kernel or kernel in lines[1:])

    def wait_back(self, kernel: str = "") -> bool:
        waited = 0
        while waited < BOOT_S:
            if self.answers(kernel):
                return True
            self.sleep(POLL_S)
            waited += POLL_S
        return False

    def cycle(self) -> bool:
        """The outlet off and on, the box back on whatever it boots by default."""
        self.switch("off")
        self.sleep(OFF_S)
        self.switch("on")
        return self.wait_back()

    def hold(self, test: str, kernel: str) -> list[str]:
        """kernel booted once, then the test's command: the box must stay silent the whole hold."""
        self.started()
        # boot_once.py rebuilds the kernel's initramfs: cut short, it leaves no reboot and a torn file
        self.box.raw(f"python3 {BOOT_ONCE} {shlex.quote(kernel)}", seconds=BOOT_ONCE_S, check=True)
        self.box.raw("systemctl reboot", seconds=15)
        self.sleep(SETTLE_S)
        if not self.wait_back(kernel):
            return [f"UNTESTED power.{test}: {kernel} did not boot", *self.recover(test)]
        self.started()
        self.box.raw(f"(sleep 2; {COMMANDS[test]}) >/dev/null 2>&1 &", seconds=15)
        self.sleep(SETTLE_S)
        silent = 0
        while silent < HOLD_S[test]:
            if self.answers():
                return [f"FAIL power.{test}: back on its own {silent + SETTLE_S} s after it"]
            self.sleep(POLL_S)
            silent += POLL_S
        return [f"power.{test} held {silent + SETTLE_S} s", *self.recover(test)]

    def started(self) -> None:
        """Startup finished: a box answers ssh before it, and a reboot or a sleep asked then is lost."""
        self.box.raw("systemctl is-system-running --wait", seconds=STARTUP_S)

    def recover(self, test: str) -> list[str]:
        return (
            [] if self.cycle() else [f"FAIL power.{test}: no boot after the switch's power cycle"]
        )

    def run(self, kernels: list[str]) -> dict[str, list[str]]:
        """Each kernel's lines, sleep then poweroff."""
        return {
            kernel: [line for test in COMMANDS for line in self.hold(test, kernel)]
            for kernel in kernels
        }

    def record(self, results: dict[str, list[str]]) -> None:
        """Each kernel's lines into its results folder on the box, collected with the rest."""
        for kernel, lines in results.items():
            text = "".join(f"{line}\n" for line in lines)
            path = shlex.quote(f"{RESULTS}/{kernel}/power-switch.txt")
            self.box.raw(f"sudo -n tee {path} >/dev/null", stdin=text.encode(), check=True)
