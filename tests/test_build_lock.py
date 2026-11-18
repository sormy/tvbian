"""build.sh's one build at a time: its container carries the work volume's label, and a step refuses
while another holds it. Runs build.sh against a stand-in container runtime and uname, on both hosts:
Apple's container on macOS, podman on Linux.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
HOLDER = "tvb-12345"

# the runtime's calls go to calls.log; `list`/`ps` print the holder, if HOLDER is set
CONTAINER = """#!/bin/sh
echo "$@" >> "$CALLS"
case "$1" in
  list) [ -n "$HOLDER" ] && printf '[{"configuration": {"id": "%s", "labels": {"tvbian.work": "tvb-work"}}}]' "$HOLDER" || echo '[]' ;;
esac
exit 0
"""
PODMAN = """#!/bin/sh
echo "$@" >> "$CALLS"
case "$1" in
  ps) [ -n "$HOLDER" ] && echo "$HOLDER" ;;
esac
exit 0
"""


class BuildLock(unittest.TestCase):
    def run_build(self, host: str, holder: str) -> tuple[subprocess.CompletedProcess[str], str]:
        work = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, work)
        (work / "build-env").mkdir()
        shutil.copy(REPO / "build.sh", work)
        shutil.copy(REPO / "build-env/Containerfile", work / "build-env")
        bin_dir = work / "bin"
        bin_dir.mkdir()
        system, machine = ("Darwin", "arm64") if host == "macos" else ("Linux", "aarch64")
        stubs = {
            "uname": f'#!/bin/sh\n[ "$1" = -m ] && echo {machine} || echo {system}\n',
            "container" if host == "macos" else "podman": CONTAINER if host == "macos" else PODMAN,
        }
        for name, script in stubs.items():
            (bin_dir / name).write_text(script)
            (bin_dir / name).chmod(0o755)
        calls = work / "calls.log"
        env = dict(os.environ, PATH=f"{bin_dir}:{os.environ['PATH']}", CALLS=str(calls))
        env.update(HOLDER=holder, TVB_BUILD_SUITE="trixie")
        done = subprocess.run(
            ["bash", str(work / "build.sh"), "test"], env=env, capture_output=True, text=True
        )
        return done, calls.read_text() if calls.exists() else ""

    def test_refuses_while_the_volume_is_held(self) -> None:
        for host in ("macos", "linux"):
            with self.subTest(host=host):
                done, calls = self.run_build(host, HOLDER)
                self.assertEqual(done.returncode, 1)
                self.assertIn(f"{HOLDER} is building in tvb-work", done.stderr)
                self.assertNotIn("run ", calls)

    def test_runs_labelled_when_free(self) -> None:
        for host in ("macos", "linux"):
            with self.subTest(host=host):
                done, calls = self.run_build(host, "")
                self.assertEqual(done.returncode, 0, done.stderr)
                run = next(line for line in calls.splitlines() if line.startswith("run "))
                self.assertIn("-l project=tvbian -l tvbian.work=tvb-work", run)
                create = next(
                    line for line in calls.splitlines() if line.startswith("volume create")
                )
                self.assertIn("--label project=tvbian", create)


if __name__ == "__main__":
    unittest.main()
