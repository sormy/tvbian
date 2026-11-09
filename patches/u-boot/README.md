# u-boot — patches on mainline

Six patches on mainline U-Boot. `uboot/rk3528.conf` applies `0003`, target code, to every RK3528
board's build; `uboot/sunxi-h616.conf` applies `0004`–`0006` to the H616 boards'. `0001` and `0002`
are in `scripts/dtc/pylibfdt`, which `binman` needs and which assumes a Linux host: they built the
FIT on macOS, and the build now runs in the container, so nothing applies them. They are kept to
send upstream.

| Patch  | Fixes                                                                           |
| ------ | ------------------------------------------------------------------------------- |
| `0001` | two Python 2 calls in `libfdt.i_shipped` that swig 4.3+ no longer papers over   |
| `0002` | a hardcoded `-shared`, where Mach-O needs `-bundle -undefined dynamic_lookup`   |
| `0003` | Ethernet on the `cpuid`-derived address instead of vendor storage's `LAN_MAC`   |
| `0004` | H616: two 3/4-populated ranks mapped contiguous, sized at boot                  |
| `0005` | sunxi: Ethernet and Wi-Fi on secure storage's `mac` and `wifi_mac`, not the SID |
| `0006` | sunxi: the Bluetooth address on the tree's `bluetooth0` alias                   |

`libfdt.i_shipped` guards every other Python 2 call behind `PY_VERSION_HEX`; these two were missed.
swig ≤ 4.2 emitted compatibility defines that hid them, and 4.3 dropped Python 2 along with the
defines, so the generated wrapper calls `PyString_FromString` and `PyInt_AsLong` into a Python 3
header. Debian's swig is 4.1.0, which is why a container build never sees it.

A Python extension resolves its interpreter symbols when loaded. ELF links that with `-shared`;
Mach-O leaves every `Py*` symbol undefined unless told to look them up dynamically. Python reports
the right flags in `sysconfig`, and the Makefile overrides them with a literal `-shared`.

`0001` and `0002` are upstream bugs, not local workarounds, and are written to send as-is.

`0003` reads the store the way Rockchip's kernel does: four 64 KiB copies from sector 7168, the
highest `version` whose `version2` matches, then item 3, six bytes per GMAC. Mainline has no
vendor-storage reader, so `rockchip_setup_macaddr()` derived every address from the `cpuid`.

`0004`: 1.5 GB LPDDR3 boards carry two ranks, each 3/4 populated. With the chip select above the row
bits, rank 0's missing quarter is a hole at `0x70000000`, and the 3/4 probe at `0xa0000000` hits
rank 1 and reports 2 GiB. The chip select moves under the two top row bits: the hole goes to the
end, the probe finds it, and the SPL reports `DRAM: 1536 MiB` with no cap.

`0005` reads Allwinner's secure storage on the eMMC, its index at sector 12288, CRC32-checked: `mac`
goes on `ethernet0`, `wifi_mac` on `ethernet1`, and `bdaddr` is the Wi-Fi's plus one. A missing item
keeps the SID's address. `0006` puts `bdaddr` on the node `bluetooth0` names.
