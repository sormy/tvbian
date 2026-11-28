"""A step's results on the box, judged: its checks, its failures and untested lines; and the steps
known.conf keeps from running where they break a box. Read by regression.py's report on the host
and by onbox.py on the box."""

from __future__ import annotations

import json
from dataclasses import dataclass
from fnmatch import fnmatch
from pathlib import Path

from video import FAILING, NOT_RUN

NOT_RUN_REASON = {"skipped": "skipped", "memory": "past this box's memory", "untested": "untested"}

SKIPPED = "77"  # a step's exit status for nothing to test on this box
TRACEBACK = "Traceback (most recent call last):"
SKIP = "step:"  # known.conf's form for a step not run: step:<name>


def crash(path: Path) -> str | None:
    """The exception a step's script died of, its last line; None when it did not crash."""
    lines = path.read_text(errors="replace").splitlines() if path.exists() else []
    if TRACEBACK not in lines:
        return None
    after = lines[lines.index(TRACEBACK) + 1 :]
    raised = [l for l in after if l and not l.startswith((" ", "exit ", "FAIL ")) and ":" in l]
    return raised[-1] if raised else "a traceback"


@dataclass
class Verdicts:
    """A result file's checks: how many ran, and its FAIL and UNTESTED lines with their values."""

    checks: int
    fails: list[str]
    untested: list[str]

    @staticmethod
    def of(path: Path) -> Verdicts:
        if not path.exists():
            return Verdicts(0, [], [])
        lines = path.read_text(errors="replace").splitlines()
        values = dict(line.split(" ", 1) for line in lines if " " in line)
        found = Verdicts(0, [], [])
        for line in lines:
            if line.startswith("{") and '"verdict"' in line:  # video.py's records
                record = json.loads(line)
                case = f"{record.get('suite')} {record.get('codec')} {record.get('size')}"
                if record["verdict"] in NOT_RUN:  # recorded, never run
                    reason = NOT_RUN_REASON[record["verdict"]]
                    why = f", {record['why']}" if "why" in record else ""
                    found.untested.append(f"video {case}: {reason}{why}")
                    continue
                found.checks += 1
                if record["verdict"] in FAILING:  # refused or unoffered: the engine's limit
                    found.fails.append(f"video {case}: {record['verdict']}")
            elif line.startswith("SKIP "):  # a sub-check the box could not run
                found.untested.append(line.removeprefix("SKIP "))
            elif line.startswith(("FAIL ", "UNTESTED ")):
                word, _, rest = line.partition(" ")
                key = rest.split(":")[0].split()[0] if rest else ""
                shown = f"{rest}: {values[key]}" if key in values else rest
                (found.fails if word == "FAIL" else found.untested).append(shown)
            elif " " in line and not line.startswith(("exit ", "#", "NOTE", "RECORD", "PROBE")):
                found.checks += 1
        if why := crash(path):  # the suite's own bug: no check after it ran
            found.fails.insert(0, f"CRASHED: {why}")
        status = next((l.split(" ", 1)[1] for l in reversed(lines) if l.startswith("exit ")), "0")
        last = lines[-2] if len(lines) > 1 else ""
        if status == SKIPPED:  # nothing to test on this box: untested, not failed
            if not found.untested:
                found.untested.append(f"skipped: {last}".strip())
        elif status != "0" and not found.fails:  # it died without saying what failed
            found.fails.append(f"exited {status}: {last}".strip())
        return found


@dataclass(frozen=True)
class Known:
    """A step known to break a box, from known.conf: the boards and kernels it is not run on, and
    why, until the fix lands."""

    boards: tuple[str, ...]
    kernels: str
    step: str
    reason: str

    @staticmethod
    def load(path: Path) -> list[Known]:
        out: list[Known] = []
        for line in path.read_text().splitlines() if path.exists() else []:
            entry, _, reason = line.partition("  # ")
            if not entry.strip() or entry.startswith("#"):
                continue
            boards, kernels, step = entry.split()
            if not step.startswith(SKIP):
                raise ValueError(f"known.conf: not a step:<name> line: {line}")
            out.append(
                Known(tuple(boards.split(",")), kernels, step.removeprefix(SKIP), reason.strip())
            )
        return out

    def on(self, board: str, kernel: str) -> bool:
        return any(fnmatch(board, b) for b in self.boards) and fnmatch(kernel, self.kernels)


def skipped(known: list[Known], board: str, kernel: str, step: str) -> str | None:
    """Why known.conf keeps a step from running on this board and kernel, if it does."""
    return next((k.reason for k in known if k.step == step and k.on(board, kernel)), None)
