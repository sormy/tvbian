from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools/validate"))
import kexec_once  # noqa: E402

MENU = """default l4
label l0
\tmenu label TVBian 7.3.6-tvb-rk35xx-next2
\tlinux /boot/vmlinuz-7.3.6-tvb-rk35xx-next2
\tinitrd /boot/initrd.img-7.3.6-tvb-rk35xx-next2
\tfdt /usr/lib/tvb/fdt/7.3.6-tvb-rk35xx-next2/board.dtb
\tappend root=UUID=1 rootwait
label l0r
\tmenu label TVBian 7.3.6-tvb-rk35xx-next2 (rescue target)
\tlinux /boot/vmlinuz-7.3.6-tvb-rk35xx-next2
\tappend root=UUID=1 rootwait systemd.unit=rescue.target
label l4
\tlinux /boot/vmlinuz-6.1.172-tvb-rk35xx
"""


class KexecOnceTest(unittest.TestCase):
    def test_the_entry_is_the_kernel_s_and_not_its_recovery_twin(self) -> None:
        lines = kexec_once.entry_of(MENU, "7.3.6-tvb-rk35xx-next2")
        assert lines is not None
        self.assertEqual(lines["append"], "root=UUID=1 rootwait")
        self.assertIsNone(kexec_once.entry_of(MENU, "7.3.7-tvb-rk35xx-next2"))

    def test_the_load_is_kexec_load_with_the_tree_it_is_given(self) -> None:
        lines = kexec_once.entry_of(MENU, "7.3.6-tvb-rk35xx-next2")
        assert lines is not None
        for extra, append in (([], "root=UUID=1 rootwait"), (["ro"], "root=UUID=1 rootwait ro")):
            with self.subTest(extra=extra):
                self.assertEqual(
                    kexec_once.kexec_load_command(lines, Path("/var/tmp/kexec.dtb"), extra),
                    [
                        "kexec",
                        "-c",
                        "-l",
                        "/boot/vmlinuz-7.3.6-tvb-rk35xx-next2",
                        f"--append={append}",
                        "--initrd=/boot/initrd.img-7.3.6-tvb-rk35xx-next2",
                        "--dtb=/var/tmp/kexec.dtb",
                    ],
                )

    def test_the_running_tree_s_memory_serial_and_ethernet_address(self) -> None:
        live = Path(tempfile.mkdtemp())
        (live / "memory-controller").mkdir()  # next2 names a node so; it is no memory
        (live / "memory").mkdir()
        (live / "memory/reg").write_bytes(bytes.fromhex("00000000 00200000 00000000 7fe00000"))
        (live / "serial-number").write_text("6a97e688395beb4d\0")
        for node in ("ethernet@ffbd0000", "ethernet@ffbe0000"):
            (live / node).mkdir()
            (live / node / "local-mac-address").write_bytes(bytes.fromhex("00ef004a43a6"))
        paths = ["/", "/soc", "/soc/ethernet@ffbd0000"]
        self.assertEqual(
            kexec_once.boot_fixups(live, paths),
            [
                ("s", "/memory", "device_type", ["memory"]),
                ("x", "/memory", "reg", ["0x0", "0x200000", "0x0", "0x7fe00000"]),
                ("s", "/", "serial-number", ["6a97e688395beb4d"]),
                ("bx", "/soc/ethernet@ffbd0000", "local-mac-address", "00 ef 00 4a 43 a6".split()),
            ],
        )

    def test_fdtput_takes_its_options_before_the_file(self) -> None:
        self.assertEqual(
            kexec_once.fdtput_command(Path("t.dtb"), "x", "/memory", "reg", ["0x0"]),
            ["fdtput", "-p", "-t", "x", "t.dtb", "/memory", "reg", "0x0"],
        )


if __name__ == "__main__":
    unittest.main()
