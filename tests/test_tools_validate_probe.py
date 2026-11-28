"""tools/validate/probe.py: the parts that read the kernel's answers."""

from __future__ import annotations

import struct
import sys
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools/validate"))
import display  # noqa: E402
import probe  # noqa: E402

CRYPTO = """name         : sha256
driver       : sha256-ce
module       : kernel

name         : cbc(aes)
driver       : cbc(aes-ce)
module       : kernel

name         : ecb(aes)
driver       : ecb-aes-rk
module       : kernel

name         : stdrng
driver       : drbg_nopr_hmac_sha256
module       : kernel
"""


class CryptoTest(unittest.TestCase):
    def probe(self, text: str) -> tuple[str, bool, str]:
        with mock.patch.object(probe, "read", return_value=text):
            return next(probe.crypto())

    def test_an_engine_driver_is_found_beside_the_cpu_and_software(self) -> None:
        self.assertEqual(self.probe(CRYPTO), ("crypto engine", True, "ecb-aes-rk: ecb(aes)"))

    def test_only_cpu_and_software_is_no_engine(self) -> None:
        name, works, _ = self.probe(CRYPTO.split("\n\nname         : ecb")[0])
        self.assertFalse(works)


class ModifiersTest(unittest.TestCase):
    def test_the_in_formats_blob_gives_each_modifier(self) -> None:
        mods = [0, 0x0800000000000001]
        header = struct.pack("<6I", 1, 0, 1, 24, len(mods), 32) + struct.pack("<I4x", 0x34325258)
        blob = header + b"".join(struct.pack("<QI4xQ", 1, 0, m) for m in mods)
        box = SimpleNamespace(drm=SimpleNamespace(getblob=lambda _: blob))
        self.assertEqual(display.Box.modifiers(box, {"IN_FORMATS": (1, 5, None)}), mods)

    def test_no_in_formats_is_no_modifier(self) -> None:
        self.assertEqual(display.Box.modifiers(SimpleNamespace(), {}), [])


class AudioTest(unittest.TestCase):
    def test_a_rate_played_at_the_nearest_is_not_taken(self) -> None:
        def run(cmd: list[str], timeout: float = 20) -> tuple[int, str]:
            if "--dump-hw-params" in cmd:
                return 0, "CHANNELS: [2 8]"
            rate = int(cmd[cmd.index("-r") + 1])
            return 0, "" if rate in (44100, 48000) else "Warning: rate is not accurate"

        pcms = [("hw:0,0", "playback", "hdmi")]
        with (
            mock.patch.object(probe, "run", run),
            mock.patch.object(probe, "pcms", return_value=pcms),
        ):
            line = next(probe.audio())
        want = ("hdmi playback (hw:0,0)", True, "channels [2 8], rates 44100 48000")
        self.assertEqual(line, want)


if __name__ == "__main__":
    unittest.main()
