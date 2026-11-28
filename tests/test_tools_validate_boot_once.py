from __future__ import annotations

import subprocess
import sys
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools/validate"))
import boot_once  # noqa: E402

MENU = """default l2
label l0
\tmenu label TVBian 7.3.6-tvb-rk35xx-next2
\tlinux /boot/vmlinuz-7.3.6-tvb-rk35xx-next2
label l2
\tmenu label TVBian 6.1.172-tvb-rk35xx
\tlinux /boot/vmlinuz-6.1.172-tvb-rk35xx
"""


class BootOnceTest(unittest.TestCase):
    def test_a_release_is_found_by_its_kernel_line(self) -> None:
        for release, label in [
            ("7.3.6-tvb-rk35xx-next2", "l0"),
            ("6.1.172-tvb-rk35xx", "l2"),
            ("7.3.6-tvb-rk35xx", None),
        ]:
            with self.subTest(release=release):
                self.assertEqual(boot_once.label_of(MENU, release), label)

    def test_the_default_moves_and_every_label_stays(self) -> None:
        out = boot_once.with_default(MENU, "l0")
        self.assertIn("default l0\n", out)
        self.assertEqual(out.replace("default l0", "default l2"), MENU)

    def test_a_menu_without_a_default_is_refused(self) -> None:
        with self.assertRaises(ValueError):
            boot_once.with_default(MENU.replace("default l2\n", ""), "l0")

    def test_the_initramfs_hook_is_valid_shell_and_resolves_the_root_device(self) -> None:
        script = boot_once.HOOK_SCRIPT
        result = subprocess.run(["sh", "-n"], input=script, text=True, capture_output=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn(". /scripts/functions\n", script)
        self.assertIn('$(resolve_device "$ROOT")', script)
        self.assertIn('$(get_fstype "$dev")', script)

    def test_the_hook_replaces_the_menu_atomically(self) -> None:
        script = boot_once.HOOK_SCRIPT
        self.assertIn('menu="$root/boot/extlinux/extlinux.conf"', script)
        self.assertRegex(script, r'> "\$menu\.new" && sync &&\s+mv "\$menu\.new" "\$menu"')
        self.assertNotRegex(
            script, r""">\s*["']?(?:\$\{?menu\}?|[^\s;"']*extlinux\.conf)(?=["'\s;&]|$)"""
        )

    def test_install_removes_the_old_hook(self) -> None:
        release = "7.3.6-tvb-rk35xx-next2"
        with (
            mock.patch.object(sys, "argv", ["boot_once.py", release]),
            mock.patch.object(boot_once, "MENU") as menu,
            mock.patch.object(boot_once, "STATE"),
            mock.patch.object(boot_once, "OLD_HOOK") as old_hook,
            mock.patch.object(boot_once, "HOOK") as hook,
            mock.patch.object(boot_once, "write_atomically"),
            mock.patch.object(boot_once.subprocess, "run"),
            mock.patch.object(boot_once.os, "sync"),
            mock.patch("builtins.print"),
        ):
            menu.read_text.return_value = MENU
            boot_once.main()
        old_hook.unlink.assert_called_once_with(missing_ok=True)
        hook.write_text.assert_called_once_with(boot_once.HOOK_SCRIPT)


if __name__ == "__main__":
    unittest.main()
