"""A step's results on the box, judged: its checks, its failures and untested lines, and which of
the failures are known (known.conf) rather than new. Read by regression.py's report on the host and
by onbox.py's gate on the box, so both judge alike."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from fnmatch import fnmatch
from pathlib import Path

from video import FAILING

SKIPPED = "77"  # a step's exit status for nothing to test on this box
TRACEBACK = "Traceback (most recent call last):"
SKIP = "step:"  # known.conf's form for a step not run: step:<name>
NOTHING = "(?!)"  # a pattern no line matches


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
                if record["verdict"] == "skipped":  # a --skip hazard, or past the box: recorded, never run
                    why = f", {record['why']}" if "why" in record else ""
                    found.untested.append(f"video {case}: skipped{why}")
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
            elif " " in line and not line.startswith(("exit ", "#", "NOTE", "RECORD")):
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
    """A failure known and not yet fixed, from known.conf: which boards and kernels, which check;
    or, as step:<name>, a step not run there at all until the fix lands."""

    boards: tuple[str, ...]
    kernels: str
    check: re.Pattern[str]
    reason: str
    step: str = ""

    @staticmethod
    def load(path: Path) -> list[Known]:
        out: list[Known] = []
        for line in path.read_text().splitlines() if path.exists() else []:
            entry, _, reason = line.partition("  # ")
            if not entry.strip() or entry.startswith("#"):
                continue
            boards, kernels, check = entry.split(None, 2)
            step = check.removeprefix(SKIP) if check.startswith(SKIP) else ""
            pattern = re.compile(NOTHING if step else check)
            out.append(Known(tuple(boards.split(",")), kernels, pattern, reason.strip(), step))
        return out

    def on(self, board: str, kernel: str) -> bool:
        return any(fnmatch(board, b) for b in self.boards) and fnmatch(kernel, self.kernels)

    def matches(self, board: str, kernel: str, line: str) -> bool:
        return self.on(board, kernel) and bool(self.check.search(line))


def skipped(known: list[Known], board: str, kernel: str, step: str) -> str | None:
    """Why known.conf keeps a step from running on this board and kernel, if it does."""
    return next((k.reason for k in known if k.step == step and k.on(board, kernel)), None)


def known_reason(known: list[Known], board: str, kernel: str, line: str) -> str | None:
    return next((k.reason for k in known if k.matches(board, kernel, line)), None)


def new_failures(folder: Path, names: list[str], known: list[Known], board: str) -> list[str]:
    """The failures in the steps named, of the kernel whose results folder this is, that
    known.conf does not name."""
    kernel = folder.name
    found = [f"{n}: {f}" for n in names for f in Verdicts.of(folder / f"{n}.txt").fails]
    return [f for f in found if known_reason(known, board, kernel, f) is None]
