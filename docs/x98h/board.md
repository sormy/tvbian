# x98h — Test report

Board: X98H, Allwinner H618, PCB `Y8927_141_V1.1 23253` (photos in this folder).

**Read this first:** the box has been running **Armbian 26.11.0 (kernel 6.18.63-ophub)**, not
TVBian, and there has been **no serial console and no TV attached** during any of it. Marks below
are evidence from that: hardware facts (RAM, eMMC, radios, GPIO, input) carry over to TVBian; every
line that depends on *our* kernel, providers, packaging or loader is ❓ until the run happens on
TVBian with serial and a screen. Each ✅ says what it rests on.

Kit on hand: SD card, USB stick, USB-TTL (CP2102), phone camera, a TV and an OTG cable. No second
board of this family. The eMMC image is at `backup/x98h-stock.img.zst` locally (1.5 GB, from a
31,268,536,320-byte dump); nothing from `stock/` or `backup/` is in the repo.

## contact

- ✅ **K1** Photos of both sides are in this folder (`pcb-top.jpg`, `pcb-bottom.jpg`); the listing is
  not recorded — bought as "X98H 4+32", silkscreen only.
- ✅ **K2** SoC is **H618**: the vendor tree's `/cpus` and `compatible`, the mainline
  `sun50i-h618-x98h-100mb.dtb` that boots it, and the BOOT0 banner (`PMU: AXP1530`, `DRAM 4096 MB`).
- ✅ **K3** Kind: **board** — a known family (`sunxi-h616`) with known chips (AIC8800), no new chip
  driver needed beyond the BT transport, which is the in-tree `hci_aic8800`.

## identity

- ❓ **L1** No serial was ever attached on this box; the stock Android's log was never captured.
- 🟡 **I1** ID search not done for `Y8927_141_V1.1`; the PCB name and date code are from the
  silkscreen only.
- ✅ **I2** Owner confirmed X98H (bought as such, `4+32` sticker).
- ✅ **I3** Photos of both sides are here. The radio is the **AIC8800** (SDIO Wi-Fi, UART BT); its
  can is visible in `pcb-top.jpg` (`NT18101S` marking next to the shield).
- ❓ **I4** The serial pads are not yet outlined on the photo (not wired at any point).
- 🟡 **I5** Components recorded so far: H618, 4× DDR (1 GB each, 4 GB total), eMMC 29.1 GB,
  AIC8800 radio, AXP1530 PMIC (BOOT0 banner), 2× USB-A + 1× micro-USB, HDMI, AV jack, RJ45
  (100 M), SD slot, 12-pin panel FPC, `Block Light` header. The four NAND-looking packages on the
  top side are the DDR; eMMC is under the shield on the other side (to confirm).
- 🟡 **I6** This file is the section set; the parts above are what we have.
- ✅ **I7** `BOARD_PCB=Y8927_141_V1.1`, `BOARD_DATE=23253` (silkscreen).
- ❓ **I8** No product/box/remote photos taken yet; only the PCB.

## backup

- ✅ **B1** The dump is off the box: `backup/x98h-stock.img.zst`, 1.5 GB, `zstd -t` passes.
- ✅ **B2** Size 31,268,536,320 bytes = `/sys/block/mmcblk2/size × 512` (61,071,360 × 512).
- ❓ **B3** No read over a service mode yet on this box (FEL was never exercised here).
- ❓ **B4** `preserve-sectors` for this board is not written yet.
- ❓ **B5** The factory DRAM-init blob is not carved yet (it is in the first sectors of the dump).
- ❓ **B6** Stock's recovery gestures: not tested on stock Android — the box has never run it during
  this work.

## dump

- ❓ **D1** No shell was ever had on the stock Android, so no `dmesg`/`getprop` set exists.
- ❓ **D2** No family README table (family exists; this board's chip set is not a new family).
- ✅ **D3** The factory tree is carved: `vendor_board.dtb`/`.dts` from `mmcblk2p7` at the
  `d00dfeed` magic (offset 0x1800, 67554 bytes).
- ✅ **D4** Nothing kept out is in the repo: no dump, no log, no MAC.
- ❓ **D5** `_DTB_SOURCE` bases not named — the vendor kernel's version was never read.
- 🟡 **D6** Per-unit values known so far: RAM 4 GB, eMMC 29.1 GB, Wi-Fi MAC `88:00:33:77:32:eb`,
  eth MAC `88:00:33:77:f6:69`, BT MAC `0b:3b:22:ac:88:20` (gadget-generated, changes).
- ✅ **D7** No `stock/` or `backup/` file is in the repo.
- 🟡 **D7b** The remote's 30-key IR set was captured on the box (`ir-keytable -t`); the vendor's
  codec matrix is not recorded yet.

## trees

- ❓ **T1** No `factory_board.dts`/`board.patch`/`factory_uboot.dts`/`uboot.patch` pair yet. The
  vendor U-Boot tree is here decompiled; the Android kernel tree was not extracted (the kernel in
  `boot_a` is a raw arm64 Image with no appended FDT).
- ❓ **T2**–**T12** Not started: every one needs the translated trees, which do not exist yet. The
  two facts that will matter are recorded in the README: the BT UART/GPIO set
  (`uart_index=1`, `bt_rst_n` PG19 active-low, `bt_wake` PG17 high, `bt_hostwake` PG16 low) and the
  panel's three pins (PC2/PC7/PC12).

## storage

- ❓ **M1** eMMC not put under `fio` on this box.
- 🟡 **M2** SD card wrote an image at ~12 MB/s and booted it; no `fio` run.
- ✅ **M3** 👤 SD hotplug worked across many insert/remove cycles during the bring-up (booted from
  SD, then from eMMC with the card removed).
- ❓ **M4** Speed modes not exercised (only the default).
- ❓ **M5** `tvb-install` never ran on this box (Armbian's `armbian-install` did).
- ✅ **M6** It boots from the eMMC on its own loaders: `root=/dev/mmcblk2p2`, SD removed, and it
  came up unattended (Armbian's `armbian-install` wrote the loader). This is the strongest
  storage line and the one a TVBian loader must keep.
- ❓ **M7** Per-unit window byte-identical to the backup: not compared.
- ❓ **M8** Our U-Boot's service mode: not tested (no TVBian loader on the box yet).
- ➖ **M9**, **M10** New-family lines — H618 is not new (sisters: h96max-h313, leffot-h313).
- ❓ **M11** Stock's fastest mode not compared.

## network

- ❓ **N1** Ethernet never brought up (the box has been on Wi-Fi throughout; the 100 M port is
  untested).
- ❓ **N2**, **N3** Not measured.
- ❓ **N4** PHY driver not checked.
- ✅ **N5** Wi-Fi on **2.4 and 5 GHz**, both verified: `HUAWEI-hA6U_Plus` (2462 MHz) and
  `HUAWEI-hA6U_Plus5` (5180 MHz, −57 dBm, 175 Mbit/s PHY). Regulatory domain is **country 00** at
  present.
- 🟡 **N6** Throughput: 0.54 MB/s to a Wi-Fi peer and 15 MB/s to a wired host, but that is the
  repeater's client-to-client path, not the radio's ceiling — see the worklog.
- ❓ **N7**, **N8** Not measured.
- ✅ **N9** With no region set, a scan finds networks (5 GHz included).
- ❓ **N10** `iw reg set` not exercised.
- ✅ **N11** BT `hci0` **UP RUNNING**, `errors:0` — after the serdev overlay (see the README).
- ✅ **N12** `btmgmt find` / `bluetoothctl scan on` lists devices (found the TV and a sibling board).
- ❓ **N13**, **N14** The bundled remote has not been paired over BT; BLE wake is untested.
- 🟡 **N15** Addresses: Wi-Fi and eth MACs are the board's (`88:00:33:77:32:eb`,
  `88:00:33:77:f6:69`) and the Wi-Fi one survived the eMMC migration; the BT address is
  gadget-generated and changes with the board's boot.
- ❓ **N16**–**N22** Not checked.
- ❓ **N23** Ethernet hotplug not tested.

## input

- ❓ **U1**–**U6** USB not exercised beyond using a stick on another box; no `lsusb -t`, no `fio`.
- ✅ **R1** `ir-keytable -r` lists the shipped remote's buttons: 30 keys mapped, power `0x140`
  (vendor code 0x40/addr 0xfe01 collapsed to `addr_low<<8 | cmd`).
- ✅ **R2** 👤 Every button on the shipped remote was pressed and captured (`ir-keytable -t`), so the
  keymap is measured, not guessed.
- ❓ **R3** The remote cold-booting the box is untested (no IR wake source: the `sunxi-cir` device
  exposes no wakeup capability, so this is a scoped to-do).
- 🟡 **R4** `/dev/input/event1` is the `sunxi-ir` device; the vendor tree also wires a recovery
  button (`sunxi-bt`/`btlpm` aside, `ir_power_key_code*` covers the remote).
- ❓ **R5** No `recovery-button` device seen.
- ❓ **E1** LEDs: the `Block Light` header exists; nothing driven yet.

## display

- ❓ **H1**–**H4** HDMI never used for output (headless); Armbian's log shows the HDMI connector
  forced on, which is not a check.
- ❓ **H5**–**H12** Audio/CEC/DDC/AV/S-PDIF untested.
- 🟡 **H13** GPU: **Mali-G31 via panfrost**, `/dev/dri/renderD128` present, GLES 3.1, and a GLES
  reprojection shader ran at 23 ms/frame. No `glmark2` suite run.
- ❓ **H14**–**H22** Not started.
- 🟡 Panel: 4-digit SM1628 on PC2/PC7/PC12 (data/clock/stb), driven from userspace during
  bring-up; address = segment, data bit = digit (`a=addr0 b=2 c=4 d=6 e=8 f=10 g=12`, digits
  bits 7→4, icons on bit 3). The node for the in-tree `tm1628` driver is what replaces that.

## system

- ✅ **S1** Comes up on the network unattended, no serial attached (Wi-Fi, static `.46`).
- ❓ **S2**, **S3**, **S4** No serial console on this box at any point.
- ❓ **S5** HDMI boot messages untested.
- 🟡 **S6** `dmesg` was read for the BT and GPU issues; not accounted line by line.
- ❓ **S7**, **S8** Not measured.
- ❓ **S9** `/usr/lib/tvb/board-*` do not exist (no TVBian on the box yet).
- ❓ **S10** No `tvb-*-modules` present.
- ❓ **S11** Ten warm reboots not run.
- ✅ **S12** `free -m` shows 3,911 MB — the 4 GB the board has.
- ❓ **S13** No `stress-ng --vm --verify`.
- ❓ **S14**, **S15** No TVBian watchdog; Armbian's is not the same mechanism.
- ❓ **S16** No `pstore`/`ramoops` check.
- ❓ **S17**–**S27** Not started (all kernel/image side).
- 🟡 **S23** RAM is 4 GB; type/clock not read.

## video

- 🟡 **C1**–**C8** The decoder exists: `/dev/video1` (`cedrus-dec`) is present and registered; no
  clip has been decoded through it.
- ❓ **C9**–**C12** Not started. The vendor matrix is not recorded.
- Note: this box showed **one** video node; the sibling h96max exposes `cedrus-dec` *and*
  `cedrus-enc`, so an encoder may depend on the tree, not the silicon.

## power

- ❓ **W1**–**W8** Untested. The box has no exposed power button; `systemctl poweroff` halts and the
  vendor loader keeps the rail up (observed on the sibling).

## conversion

- ❓ **V1**–**V8** Not started; there is no translated tree yet.

## boot

- ❓ **O1**, **O2** Service mode not exercised on this box.
- ✅ **O3** 👤 The image boots from an SD card with the eMMC untouched — done repeatedly before the
  eMMC install.
- ❓ **O4** USB stick boot not tried.
- ✅ **O5** It comes up on the network and takes `ssh` (key auth as root).
- ➖ **O6** Rockchip line.
- ❓ **O7**, **O8**, **O9** TVBian-side, not started.

## finish

- ❓ **Q1**–**Q7** Not started; this report is the beginning of that pass, not the end.

## Known gaps

1. **No serial console** on this box so far — blocks L1, S2–S5, B3, M8, and the whole of `trees`/
   `conversion`.
2. **No stock Android shell** — blocks D1, D2, the codec matrix, and the vendor runtime trees.
3. **No TV/monitor attached** during the work — blocks display, audio, CEC, DDC.
4. **TVBian has never run on this box** — every `tvb-*`, provider, loader and packaging line is ❓
   by definition.
5. **The eMMC loader is Armbian's**, not ours: it boots (M6 ✅) but proves nothing about TVBian's
   loader.

## What the next session needs

Serial on the UART pads (TX/RX/GND by the AV jack, 3.3 V, 115200), a TV on HDMI, and a TVBian
build for `sunxi-h616` with this board's tree. With those, `identity` → `dump` → `trees` →
`conversion` → `boot` is the order that unblocks the rest.
