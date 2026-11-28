"""tools/validate/box.py: soak jobs end with the soak, and each rule fails what it should."""

from __future__ import annotations

import subprocess
import sys
import struct
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools/validate"))
import box  # noqa: E402


class PvtmTest(unittest.TestCase):
    def test_both_kernels_logs_give_the_count_and_level(self) -> None:
        vendor = ["cpu cpu0: bin=0", "cpu cpu0: pvtm=1543", "cpu cpu0: pvtm-volt-sel=4"]
        next2 = [
            "cpu cpu0: pvtm 1533 at 1416000 kHz, 950750 uV",
            "platform ff700000.gpu: pvtm 907 at 800000 kHz, 950750 uV",
            "rockchip-cpufreq-pvtm rockchip-cpufreq-pvtm: gpu pvtm 907: bin L5",
            "rockchip-cpufreq-pvtm rockchip-cpufreq-pvtm: pvtm 1533: bin L4",
        ]
        self.assertEqual(box.pvtm_levels(vendor), {"cpu": "1543 L4"})
        self.assertEqual(box.pvtm_levels(next2), {"cpu": "1533 L4", "gpu": "907 L5"})
        self.assertEqual(box.pvtm_levels(["eth0: link up"]), {})


class SoakJobTest(unittest.TestCase):
    def job(self, script: str) -> subprocess.Popen[str]:
        return subprocess.Popen(["sh", "-c", script], text=True, start_new_session=True)

    def test_a_job_past_the_soak_is_stopped_and_ran_its_course(self) -> None:
        job = self.job("sleep 100")
        with mock.patch.object(box, "SOAK_GRACE_S", 0.2):
            self.assertEqual(box.ended(job), 0)
        self.assertIsNotNone(job.poll())

    def test_a_job_that_failed_keeps_its_status(self) -> None:
        self.assertEqual(box.ended(self.job("exit 3")), 3)


class InputTest(unittest.TestCase):
    def test_a_plugged_in_keyboard_is_not_the_board_s(self) -> None:
        for device, usb in [
            (
                "/sys/devices/platform/soc/5311000.usb/usb4/4-1/4-1:1.0/0003:046D:C534.0001",
                True,
            ),
            (
                "/sys/devices/platform/soc/5100000.usb/musb-hdrc.2.auto/usb1/1-1/1-1:1.1",
                True,
            ),
            ("/sys/devices/platform/gpio-keys", False),
            ("/sys/devices/platform/soc/7040000.ir/rc/rc0", False),
        ]:
            with self.subTest(device=device):
                self.assertEqual(box.on_usb(device), usb)


class NetworkTest(unittest.TestCase):
    def test_a_usb_adapter_is_not_the_board_s(self) -> None:
        devices = {
            "/sys/class/net/end0/device": "/sys/devices/platform/soc/5020000.ethernet",
            "/sys/class/net/wlan0/device": "/sys/devices/platform/soc/4021000.mmc/mmc_host/mmc1",
            "/sys/class/net/enx00e04c/device": "/sys/devices/platform/soc/5200000.usb/usb1/1-1",
        }
        found = [f"{d.rsplit('/', 1)[0]}/phydev" for d in devices]
        with (
            mock.patch.object(box.glob, "glob", return_value=found),
            mock.patch.object(box.os.path, "realpath", side_effect=devices.__getitem__),
        ):
            self.assertEqual(box.board_nets("phydev"), ["end0", "wlan0"])


class AudioRatesTest(unittest.TestCase):
    def test_a_rate_played_at_the_nearest_is_not_offered(self) -> None:
        def aplay(cmd: list[str], **_: object) -> subprocess.CompletedProcess[str]:
            rate = int(cmd[cmd.index("-r") + 1])
            warning = "" if rate in (12000, 48000) else "Warning: rate is not accurate"
            return subprocess.CompletedProcess(cmd, 1 if rate == 8000 else 0, "", warning)

        with mock.patch.object(box.subprocess, "run", side_effect=aplay):
            self.assertEqual(box.offered_rates("0"), [12000, 48000])


class VerdictTest(unittest.TestCase):
    def test_each_rule_fails_what_it_should(self) -> None:
        cases = [
            ("fio.seq.read", "87.8 MB/s 87 IOPS", None),
            ("fio.seq.read", "failed", "FAIL"),
            ("fio.seq.read", "failed, error 5", "FAIL"),
            ("wifi.reload", "default: 3 s", None),
            ("wifi.reload", "unload failed", "FAIL"),
            ("wifi.reload", "address lost", "FAIL"),
            ("wifi.region.DE", "DE", None),
            ("wifi.region.DE", "98, not taken", "FAIL"),
            ("suspend.s2idle", "same boot, slept, 22 s for 20", None),
            ("suspend.s2idle", "same boot, did not sleep, 0 s for 20", "FAIL"),
            ("cpu.load", "failed, stress-ng exit 1", "FAIL"),
            ("soak.jobs", "0 0 0", None),
            ("soak.jobs", "0 1 0", "FAIL"),
            ("wifi.up.mbits", "failed: no address on wlan0", "FAIL"),
            ("fio", "no fio", "UNTESTED"),
            ("soak.server", "failed: plex not answering after 30 s", "FAIL"),
            ("mmc.errors", "0", None),
            ("mmc.errors", "1: mmc2: error -110 whilst initialising MMC card", "FAIL"),
            (
                "usb.hubs.external",
                "1",
                None,
            ),  # a hub plugged in or on the board: the reader judges
            ("ddr.governor", "performance", None),
            ("ddr.governor", "dmc_ondemand", None),
            ("ddr.governor", "simple_ondemand", "FAIL"),
            ("ddr.governor", "no DDR devfreq", "UNTESTED"),
            ("audio.rk3528acodec.12000.2s", "2.001", None),
            ("audio.rk3528acodec.11025.2s", "2.090", "FAIL"),
            ("audio.rk3528acodec.11025.2s", "refused", "FAIL"),
            ("audio.rockchiphdmi.hdmi-jack", "on connected", None),
            ("audio.rockchiphdmi.hdmi-jack", "off disconnected", None),
            ("audio.rockchiphdmi.hdmi-jack", "off connected", "FAIL"),
            ("audio.rockchiphdmi.hdmi-jack", "on disconnected", "FAIL"),
            ("audio.rockchiphdmi.hdmi-jack", "no jack", "UNTESTED"),
            (
                "audio.rockchiphdmi.hdmi-jack.follows",
                "on with a screen, off without",
                None,
            ),
            (
                "audio.rockchiphdmi.hdmi-jack.follows",
                "off with a screen, off without",
                "FAIL",
            ),
            (
                "audio.rockchiphdmi.hdmi-jack.follows",
                "not run: a screen is attached",
                "UNTESTED",
            ),
            ("units.autostart", "none", None),
            ("units.autostart", "greetd.service", "FAIL"),
            ("wake.remote", "1 of 1 armed: rc0:enabled", None),
            ("wake.remote", "0 of 1 armed: rc0:disabled", "FAIL"),
            ("wake.remote", "no IR receiver", "UNTESTED"),
            ("boot.startup", "running", None),
            ("boot.startup", "degraded", "FAIL"),
            ("boot.seconds", "11.438", None),
            ("boot.seconds", "none", "FAIL"),
        ]
        for key, value, expected in cases:
            with self.subTest(key=key, value=value):
                self.assertEqual(box.verdict(key, value), expected)


if __name__ == "__main__":
    unittest.main()


class HdmiJackTest(unittest.TestCase):
    def test_the_jack_is_read_beside_the_connector(self) -> None:
        for jacks, connected, expected in [
            ([], True, "no jack"),
            ([("hdmi-audio-codec.4.auto-jack Jack", "on")], True, "on connected"),
            ([("hdmi-audio-codec.4.auto-jack Jack", "off")], False, "off disconnected"),
        ]:
            with self.subTest(jacks=jacks, connected=connected):
                with mock.patch.object(box, "hdmi_connected", return_value=connected):
                    self.assertEqual(box.hdmi_jack(jacks), expected)


class IommuLinesTest(unittest.TestCase):
    def test_an_iommu_shared_with_its_master_is_left_out(self) -> None:
        interrupts = """           CPU0       CPU1
 24:          0          0     GICv2 127 Level     ff740800.iommu
 37:     153921          0     GICv2 141 Level     ff847e00.iommu, ff840000.vop
 62:          5          0     GICv2 121 Level     gpmmu
 70:        900          0     GICv2 150 Edge      ff8d0000.hdmi
"""
        lines = box.iommu_lines(interrupts)
        self.assertEqual([l.split(":")[0].strip() for l in lines], ["24", "62"])


class StressorOpsTest(unittest.TestCase):
    METRICS = (
        "stress-ng: metrc: [7447] stressor       bogo ops real time  usr time\n"
        "stress-ng: metrc: [7447] cpu                 147      3.46      3.30\n"
        "stress-ng: metrc: [7447] vm                14790      3.04      2.09\n"
    )

    def test_a_stressor_s_bogo_ops(self) -> None:
        for stressor, ops in (("cpu", "147"), ("vm", "14790"), ("hdd", box.NONE)):
            with self.subTest(stressor=stressor):
                self.assertEqual(box.stressor_ops(self.METRICS, stressor), ops)


class CryptoBenchTest(unittest.TestCase):
    PROC = "\n\n".join(
        "\n".join(f"{k:<12} : {v}" for k, v in block.items())
        for block in (
            {
                "name": "cbc(aes)",
                "driver": "cbc-aes-rk2",
                "priority": "300",
                "selftest": "passed",
                "internal": "no",
                "type": "skcipher",
                "min keysize": "16",
                "ivsize": "16",
            },
            {
                "name": "cbc(aes)",
                "driver": "cbc-aes-ce",
                "priority": "300",
                "selftest": "passed",
                "internal": "no",
                "type": "skcipher",
                "min keysize": "16",
                "ivsize": "16",
            },
            {
                "name": "ofb(sm4)",
                "driver": "ofb-sm4-rk2",
                "priority": "300",
                "selftest": "passed",
                "internal": "no",
                "type": "skcipher",
                "min keysize": "16",
                "ivsize": "16",
            },
            {
                "name": "sm4",
                "driver": "sm4-generic",
                "priority": "100",
                "selftest": "passed",
                "internal": "no",
                "type": "cipher",
            },
            {
                "name": "sha256",
                "driver": "rk2-sha256",
                "priority": "300",
                "selftest": "unknown",
                "internal": "no",
                "type": "ahash",
                "digestsize": "32",
            },
            {
                "name": "__cbc(aes)",
                "driver": "__cbc-aes-ce",
                "priority": "300",
                "selftest": "passed",
                "internal": "yes",
                "type": "skcipher",
            },
        )
    )

    def test_only_self_tested_callable_algorithms_in_order(self) -> None:
        drivers = [a.driver for a in box.crypto_algs(self.PROC)]
        self.assertEqual(drivers, ["cbc-aes-rk2", "cbc-aes-ce", "ofb-sm4-rk2", "sm4-generic"])

    def test_a_tie_goes_to_the_newest(self) -> None:
        algs = box.crypto_algs(self.PROC)
        self.assertEqual(box.default_driver(algs, "cbc(aes)"), "cbc-aes-rk2")

    def test_a_mode_only_the_engine_lists_meets_the_cpu_s_cipher(self) -> None:
        algs = box.crypto_algs(self.PROC)
        for name, drivers in (
            ("cbc(aes)", ["cbc-aes-rk2", "cbc-aes-ce"]),
            ("ofb(sm4)", ["ofb-sm4-rk2", "ofb(sm4-generic)"]),
        ):
            with self.subTest(name=name):
                self.assertEqual([a.driver for a in box.contenders(algs, name)], drivers)

    CIPHER_LOG = [
        "tcrypt: testing speed of multibuffer cbc-aes-ce (cbc-aes-ce) encryption",
        "tcrypt: test 3 (128 bit key, 256 byte blocks): 1261144 operations in 1 seconds "
        "(322852864 bytes)",
        "tcrypt: test 6 (128 bit key, 4096 byte blocks): 191896 operations in 1 seconds "
        "(786006016 bytes)",
        "tcrypt: testing speed of multibuffer cbc-aes-ce (cbc-aes-ce) decryption",
        "tcrypt: test 6 (128 bit key, 4096 byte blocks): 254360 operations in 1 seconds "
        "(1041858560 bytes)",
    ]
    HASH_LOG = [
        "tcrypt: test  5 (  256 byte blocks,  256 bytes per update,   1 updates):  "
        "811000 opers/sec, 207616000 bytes/sec",
        "tcrypt: test 15 ( 4096 byte blocks,  256 bytes per update,  16 updates):  "
        "60000 opers/sec, 245760000 bytes/sec",
        "tcrypt: test 16 ( 4096 byte blocks, 4096 bytes per update,   1 updates):  "
        "70000 opers/sec, 286720000 bytes/sec",
    ]

    def test_the_idle_temperature_is_read_once_it_stops_falling(self) -> None:
        for readings, expected in (
            ([53.3, 51.6, 49.9, 48.1, 48.1, 48.1, 48.1, 48.1, 48.1, 48.1], (48.1, 90)),
            ([44.4] * 8, (44.4, 60)),
            ([60.0 - n for n in range(40)], (30.0, 300)),
        ):
            with self.subTest(first=readings[0]):
                temps = iter(readings)
                self.assertEqual(box.cooled(lambda: next(temps), lambda _: None), expected)

    def test_an_untimed_size_names_tcrypt_s_failure(self) -> None:
        for log, why in (
            (
                ["[  9.1] tcrypt: encryption() failed flags=0"],
                "tcrypt: encryption() failed flags=0",
            ),
            (self.CIPHER_LOG, "no failure logged"),
        ):
            with self.subTest(why=why):
                self.assertEqual(box.tcrypt_failure(log), why)

    def test_tcrypt_rates_encryption_and_one_update_hashes(self) -> None:
        for log, kind, rates in (
            (self.CIPHER_LOG, "skcipher", {256: 322.852864, 4096: 786.006016}),
            (self.HASH_LOG, "ahash", {256: 207.616, 4096: 286.72}),
            (["tcrypt: hashing failed ret=-110"], "ahash", {}),
        ):
            with self.subTest(kind=kind, rates=rates):
                self.assertEqual(box.tcrypt_rates(log, kind), rates)

    def test_a_run_s_lines_follow_its_last_marker(self) -> None:
        log = ["old", "box.py tcrypt x 1", "a", "box.py tcrypt x 2", "b", "c"]
        self.assertEqual(box.after_marker(log, "box.py tcrypt x 2"), ["b", "c"])
        self.assertEqual(box.after_marker(log[:2], "box.py tcrypt x 2"), [])

    def test_the_engine_must_fail_as_provoked_then_run(self) -> None:
        for value, judged in (
            ("provoked: failed, next: 250", None),
            ("provoked: failed, next: failed", "FAIL"),
            ("provoked: not failed, next: 250", "FAIL"),
            ("not run: no debug build's knob", "UNTESTED"),
        ):
            with self.subTest(value=value):
                self.assertEqual(box.verdict("crypto.recovery.wedge", value), judged)

    def test_the_default_must_be_the_fastest(self) -> None:
        key = "crypto.bench.cbc(aes)"
        for value, judged in (
            (
                "cbc-aes-ce 900/1100, cbc-aes-rk2 200/800 MB/s; default cbc-aes-rk2, "
                "fastest cbc-aes-ce",
                "FAIL",
            ),
            ("cbc-aes-ce 900/1100 MB/s; default cbc-aes-ce, fastest cbc-aes-ce", None),
        ):
            with self.subTest(value=value):
                self.assertEqual(box.verdict(key, value), judged)


class HdmiJackFollowsTest(unittest.TestCase):
    def test_a_connected_screen_skips_the_synthetic_sink(self) -> None:
        with (
            mock.patch.object(box, "hdmi_connected", return_value=True),
            mock.patch.object(box, "hdr_sink") as sink,
        ):
            self.assertEqual(box.hdmi_jack_follows("0"), "not run: a screen is attached")
        sink.assert_not_called()

    def test_the_jack_follows_the_synthetic_sink(self) -> None:
        key = "audio.rockchiphdmi.hdmi-jack.follows"
        for inside, verdict in [("on", None), ("off", "FAIL")]:
            with (
                self.subTest(inside=inside),
                mock.patch.object(box, "hdmi_connected", return_value=False),
                mock.patch.object(box, "hdr_sink") as sink,
                mock.patch.object(box, "jack_settled", side_effect=[inside, "off"]) as settled,
            ):
                calls = mock.Mock()
                context = sink.return_value
                context.__enter__.return_value = True
                calls.attach_mock(context, "sink")
                calls.attach_mock(settled, "jack")
                result = box.hdmi_jack_follows("0")
                self.assertEqual(result, f"{inside} with a screen, off without")
                self.assertEqual(box.verdict(key, result), verdict)
                self.assertEqual(
                    calls.mock_calls,
                    [
                        mock.call.sink.__enter__(),
                        mock.call.jack("0", "on"),
                        mock.call.sink.__exit__(None, None, None),
                        mock.call.jack("0", "off"),
                    ],
                )


class CryptoRsaTest(unittest.TestCase):
    def test_a_priority_and_a_delete_message(self) -> None:
        update = box.crypto_msg("rsa-rk2", 300)
        length, kind, flags = struct.unpack_from("IHH", update)
        self.assertEqual((length, kind, flags), (len(update), box.CRYPTO_MSG_UPDATEALG, 5))
        self.assertEqual(update[16 + 64 : 16 + 64 + 7], b"rsa-rk2")
        self.assertEqual(struct.unpack_from("HHI", update, len(update) - 8), (8, 1, 300))
        delete = box.crypto_msg("pkcs1(rsa-generic,sha256)", None)
        self.assertEqual(struct.unpack_from("H", delete, 4)[0], box.CRYPTO_MSG_DELALG)
        self.assertEqual(len(delete), 16 + 3 * 64 + 16)

    def test_every_key_verified_passes(self) -> None:
        for verified, judged in (({1024: 4, 2048: 4, 4096: 4}, True), ({1024: 4, 2048: 3}, False)):
            with self.subTest(verified=verified):
                line = box.rsa_line(verified, 23.5, 28.8, "pkcs1(rsa-rk2,sha256)")
                self.assertEqual(box.rsa_all_verified(line), judged)
                self.assertIn("2048 bits 23.5/s, the CPU's 28.8/s", line)
        self.assertFalse(box.rsa_all_verified("not run: no openssl"))


class PhyHotTest(unittest.TestCase):
    def test_judged_on_both_switches(self) -> None:
        judge = next(f for k, f in box.RULES if k.startswith(r"eth\..*\.hot"))
        for value, ok in (
            ("160 mV at 45.6 C in 0.9 s, back to 260 mV in 1.0 s", True),
            ("160 mV at 45.6 C in never, back to 260 mV in 1.0 s", False),
            ("not run: no debug build's knob", True),
        ):
            with self.subTest(value=value):
                self.assertEqual(judge(value), ok)
