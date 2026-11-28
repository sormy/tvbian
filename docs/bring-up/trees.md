# Device trees

Every board has `factory_board.dts` and `board.patch`, plus `factory_uboot.dts` and `uboot.patch`
where we build U-Boot. No exceptions: a board whose tree is adopted from mainline still has its
patch, targeting mainline's tree.

## Do

1. **Read a finished `factory_board.dts`** of an existing board first, to see what a good decompile
   looks like.
2. Run `./build.sh tool dtc`, then `./build.sh board-dtb <board>` and `uboot-dtb <board>`. This
   decompiles the factory blobs with `tools/dtcx/dtcx.py` against the `_SOURCE` bases. Extend the
   base until only addresses and bitmasks stay hex: interrupts named, vendor quantities in decimal,
   vendor GPIO and reference properties declared.
3. **Copy `factory_board.dts` to `board.dts`, edit it, and diff it into `board.patch`** (the same for
   U-Boot). Never start from the generated `board.dts`: it has no explicit phandles, so a diff
   against the factory tree would delete hundreds of lines. The build regenerates `board.dts` and
   `board.dtb` (committed), drops the explicit phandles and proves the result equal with
   `tools/dtcx/canonical.py`.
   - Where the `_SOURCE` base has a `.translate.conf`, the build first translates the factory tree to
     the target dialect (`factory_board_translated.dts`), and the patch is against that.
   - A change every board on the base needs goes in the `.translate.conf` (`family.md`, step 7,
     checked by `conversion.md`), not in a board's patch.
   - The patch holds only the board's own decisions. Disable a block the board lacks; never delete
     it.
4. **Every property is the factory's value**, or has a one-line comment saying why not. Check any
   value taken from a sibling's mainline tree against the dump, line by line. Change one thing per
   test boot, following the factory, never inventing a third value.
5. **Known grafts.** The closest board's patch shows which nodes to touch, never their values: read
   each value from this board's factory tree, or record it as a question. Never apply another board's
   patch.

   | Graft                                       | Needed for                                     |
   | ------------------------------------------- | ---------------------------------------------- |
   | IR `remote_support_psci` → `1`              | the remote waking the box from off             |
   | GPU: lima `clocks`, `interrupt-names`       | mainline's lima                                |
   | LEDs: labels `power`, `standby`             | the shared LED hooks                           |
   | Recovery button → `KEY_VENDOR`              | a button the kernel sees; not a boot-ROM strap |
   | LEDs: `retain-state-shutdown`, `-suspended` | the hooks, not the LED core, own the LEDs      |
   | sunxi: alias `bluetooth0` on a UART BT node | U-Boot's Bluetooth address                     |
   | `watchdog` → `okay`                         | systemd's `RuntimeWatchdogSec`                 |
   | VOP `esmart_lb_mode` → `02`                 | 4K on Rockchip                                 |
   | `model` → the box's name                    | identity; the factory names the EVB            |
   | CEC: mainline's node, `hdmi-phandle`        | `/dev/cec0`                                    |
   | DDC: `i2c-gpio`, pins muxed to GPIO         | DDC/CI where DDC is on GPIOs (not on H616)     |
   | IOMMU: `iommus` on every factory master     | no page faults at idle                         |
   | SoC or board `compatible`                   | only where a driver or userspace checks it     |

## Pitfalls

- **Stock first.** An unofficial tree for a one-off box carries its own bring-up's mistakes. Use it
  as a hint when something fails; never copy it.
- **An H616's Ethernet PHY is chosen by the SID, not the tree.** Word 0x2c bit 8 set means the AC300
  on MDIO; the factory tree may still describe an AC200 on I2C.
- **Trust the PCB, not the tree.** Factory trees are often an evaluation board's and claim hardware
  the box lacks. Disable a node only on a positive signal (a driver error, a probe reading nothing);
  silence is not absence. Add no graft without a consumer.
- **Nor the listing.** Listings for the same box disagree. A USB port's generation is its
  receptacle's lead count (nine for USB 3) and a SuperSpeed device's link speed.
- **Kernel arguments go in `BOARD_CMDLINE`**, never `/chosen/bootargs`: U-Boot replaces the tree's
  with `extlinux.conf`'s.
- **Sizes come from the hardware, not the tree.** U-Boot writes the RAM it found into the memory
  node's `reg` and nothing else. A factory `linux,usable-memory` overrides it and caps every unit at
  its size: drop it (the M20 had one).
- **Allwinner's legacy pin groups** (`allwinner,pins`, `function`, `drive`, `pull`) work in Linux but
  U-Boot silently ignores them. Translate them to `pins`, `function`, `drive-strength`
  ((n + 1) × 10 mA) and `bias-*`.
- **Linux applies only the `default` pin state** (plus the few a driver asks for, like `sleep` or
  `clk-gate`). Vendors name states for their own drivers (Amlogic's `sdio_all_pins`), so none gets
  applied and only what the bootloader muxed works. Rename the state the driver selects at probe to
  `default`.
- **Power management does not port 1:1.** The M20's factory tree suspends through Amlogic's
  `aml_pm`, which mainline lacks. Rewrite it, try the candidates, keep the best-measured one.
- **The upstream view's base is the board the vendor built on, as the factory tree names it.** The
  root compatible names either the template (`rockchip,rk3518-evb1-ddr4-v10`,
  `rockchip,rk3528-evb2-ddr3-v10`) or just the SoC (`allwinner,h616`, `amlogic, Gxl`); the base is
  that reference board's file or the SoC dtsi. The base conf's `soc` sets the default, and a board's
  `BOARD_KERNEL_DTB_BASE` overrides it.
  - A template's name says nothing about its RAM: every box here names a DDR4 EVB, but none is DDR4
    (the M2 Plus is DDR3; the 3518, 3518D and R69-1 are LPDDR3). DRAM belongs to the loader, not the
    tree.
  - Only when the named template is not upstream, measure with `upstream.py --soc` (smallest proven
    view wins), and only among the SoC vendor's EVB, demo and reference boards. Never pick a retail
    board: its maintainer keeps editing it, and every edit leaks into our view. In practice no other
    vendor board beat the named template by more than a few lines.
- **Stock is the source of truth, not upstream.** Measure on the box any fact stock lacks, and
  override stock only where the box proves it wrong. An upstream tree describes the hardware revision
  its author had: upstream's Tanix TX1 is the V1.0, with banks PC and PG at 1.8 V; our V2.0 runs both
  at 3.3 V, and measuring that found the bug in stock's ALDO1 on the eMMC. On the H616, `PIO_POW_VAL`
  (`0x0300b348`) reads each bank's voltage, one bit per bank, 1 for 1.8 V.
- **The watchdog cannot be disarmed once opened** and keeps counting across a soft reboot. Read its
  clock before trusting a timeout.

## Check

- [ ] **T1** `factory_board.dts` and `board.patch` exist, plus `factory_uboot.dts` and `uboot.patch`
      where we build U-Boot
- [ ] **T2** The decompile names interrupts and leaves only addresses and bitmasks in hex
- [ ] **T3** Every changed property is the factory's, or says why not
- [ ] **T4** Each disabled node's hunk is marked `NOT FITTED`, with its signal
- [ ] **T5** The IOMMU's line in `/proc/interrupts` stays still at idle
- [ ] **T6** `dtb.md` records every change, reverted ones included
- [ ] **T7** The suspend setup is the best-measured candidate; the others are in `dtb.md`
- [ ] **T8** The booted memory node holds U-Boot's `reg` and no `linux,usable-memory`
- [ ] **T9** No value in `board.patch` traces only to another board's tree
- [ ] **T10** `/chosen` holds no `bootargs`
- [ ] **T11** On sunxi, `bluetooth0` names the tree's Bluetooth node, where it has one
- [ ] **T12** Each pin bank's supply holds the voltage the bank measures on the box
