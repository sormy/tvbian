"""release/publish.sh's image handoff, with git and gh held local."""

from __future__ import annotations

import os
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


class Publish(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        (self.root / "release").mkdir()
        shutil.copyfile(ROOT / "release/publish.sh", self.root / "release/publish.sh")
        for directory in ("repo", "release", "images"):
            (self.root / "build/out" / directory).mkdir(parents=True)
        (self.root / "build/out/repo/InRelease").write_text("signed repo fixture\n")
        (self.root / "build/out/release/plan").write_text("base base 1 published\n")
        (self.root / "build/out/release/notes.md").write_text("image release fixture\n")
        (self.root / "bin").mkdir()
        self.stub(
            "git",
            """#!/bin/sh
case "$1" in
  rev-parse) echo main ;;
  ls-remote) exit 2 ;;
esac
""",
        )
        self.stub(
            "gh",
            """#!/bin/sh
printf '%s\n' "$*" >>"$COMMAND_LOG"
case "$1 $2" in
  'release view')
    [ "$3" = apt ] && exit 0
    [ "$3" = 2026-11-04 ] && [ "${COLLIDE:-0}" = 1 ] && exit 0
    exit 1 ;;
  'release create') exit "${FAIL_CREATE:-0}" ;;
esac
""",
        )
        self.output = self.root / "github-output"
        self.log = self.root / "commands"

    def stub(self, name: str, body: str) -> None:
        path = self.root / "bin" / name
        path.write_text(body)
        path.chmod(0o755)

    def publish(self, **extra: str) -> subprocess.CompletedProcess[str]:
        env = {
            **os.environ,
            "PATH": f"{self.root / 'bin'}:{os.environ['PATH']}",
            "GITHUB_OUTPUT": str(self.output),
            "COMMAND_LOG": str(self.log),
            **extra,
        }
        return subprocess.run(
            ["bash", "release/publish.sh"],
            cwd=self.root,
            env=env,
            capture_output=True,
            text=True,
        )

    def image(self) -> None:
        (
            self.root / "build/out/images/tvbian-example-trixie-2026-11-04.img.xz"
        ).write_bytes(b"image fixture")

    def test_success_exposes_the_published_tag(self) -> None:
        self.image()
        result = self.publish()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(self.output.read_text(), "tag=2026-11-04\n")
        self.assertIn("release create 2026-11-04 --verify-tag", self.log.read_text())

    def test_second_release_exposes_its_suffix(self) -> None:
        self.image()
        result = self.publish(COLLIDE="1")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(self.output.read_text(), "tag=2026-11-04.2\n")

    def test_failed_upload_exposes_no_tag(self) -> None:
        self.image()
        result = self.publish(FAIL_CREATE="1")
        self.assertNotEqual(result.returncode, 0)
        self.assertFalse(self.output.exists())

    def test_apt_only_publish_exposes_no_tag(self) -> None:
        result = self.publish()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertFalse(self.output.exists())
        self.assertNotIn("release create", self.log.read_text())


if __name__ == "__main__":
    unittest.main()
