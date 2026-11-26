# x98h — worklog

Dated, newest last. Every entry names the command that showed it.

## 2026-11-23
- **Stock dump taken.** `dd if=/dev/mmcblk2` → 31,268,536,320 bytes (matches
  `/sys/block/mmcblk2/size × 512`), `zstd -1` → 1.5 GB, `zstd -t` passes. Kept in `backup/`.
- Partition table read: 25 partitions, `boot_a` (p5) 64 MB, `vendor_boot_a` (p7) 32 MB,
  `super` (p9) 3 GB, `dtbo_a` (p21) 2 MB, userdata (p25) 25.7 GB f2fs.

## 2026-11-24
- **Reimaged the SD** with `Armbian_26.11.0_allwinner_x98h-100mb_trixie_6.18.63_server_2026.11.14`
  and booted it: `uname -r` = `6.18.63-ophub`.
- **Installed to eMMC** with `armbian-install` (ext4). After `poweroff`, SD removed, it boots on
  its own: `findmnt -no SOURCE /` = `/dev/mmcblk2p2`. The vendor tree was carved the same day:
  `mmcblk2p7` offset 0x1800, 67,554 bytes (`vendor_board.dtb`).

## 2026-11-25
- **5 GHz.** Both SSIDs were in the same netplan profile, so NetworkManager stayed on 2.4 GHz.
  `iw dev wlan0 link` then showed `HUAWEI-hA6U_Plus5`, 5180 MHz, −57 dBm, 175 Mbit/s.
- **Bluetooth.** AIC8800 BT is on **UART1 (PG6–PG9)**, not USB. A serdev child for the in-tree
  `hci_aic8800` driver, with the vendor's GPIO polarities (`enable` PG19 **active-low**,
  `device-wakeup` PG17 **active-high**, `host-wakeup` PG16 **active-low**) and `max-speed=1500000`,
  gives `hci0` `UP RUNNING` and a working scan. With `enable` active-high the driver still logs
  `fw_ready=1` but the controller never registers.
- **IR.** `sunxi-cir` on `rc1`. Power is `0x140` (kernel reports `addr_low<<8 | cmd`; the vendor
  tree's `ir_power_key_code0=0x40`, `ir_addr_code0=0xfe01`). All 30 buttons of the shipped remote
  captured with `ir-keytable -t`.
- **Panel.** SM1628 behind PC2 (data), PC7 (clock), PC12 (strobe); address = segment, data bit =
  digit. Icons share the segment address byte (writing one separately wipes that segment).

## 2026-11-26
- PCB photos pulled from the phone (USB `adb pull`, 35 MB/s) and added here.
- `factory_boot0.bin` carved: sector 16, 128 sectors → 65,536 bytes, starts `eGON.BT0`.
- **Single-picture measurements, for the record:** Wi-Fi 0.54 MB/s to a Wi-Fi peer vs 15 MB/s to a
  wired host from the same radio — a repeater client-to-client path, not the radio's ceiling.
