# Device trees

Every board has `factory_board.dts` + `board.patch`, and `factory_uboot.dts` + `uboot.patch` where
we build U-Boot from it. No exception, adoption included: adopting mainline's tree for an officially
supported board means the patch targets mainline's tree.

## Do

1. **Read a finished `factory_board.dts`** of an existing board first, to see what a decompile
   should look like.
2. `./build.sh tool dtc`, then `./build.sh board-dtb <board>` and `uboot-dtb <board>`: the factory
   blobs decompiled by `tools/dtcx/dtcx.py` against the `_SOURCE` bases. Extend the base until only
   addresses and bitmasks stay hex: interrupts named, the vendor's quantities decimal, its gpio and
   reference properties declared.
3. **Edit a copy as `board.dts`**, diff it into `board.patch` (`uboot.patch` alike); the build
   regenerates `board.dts` and `board.dtb`, which is committed.
4. **Every property is the factory's value**, or carries a comment saying why not. A value from a
   sibling's mainline tree is checked against the dump, line by line. One change per test boot,
   following the factory, never a third value.
5. **Grafts known here**, starting from the closest board's patch:

   | Graft                                       | Needed by                                   |
   | ------------------------------------------- | ------------------------------------------- |
   | IR `remote_support_psci` → `1`              | the remote waking the box from off          |
   | GPU: lima `clocks`, `interrupt-names`       | mainline's lima                             |
   | LEDs: labels `power`, `standby`             | the shared LED hooks                        |
   | LEDs: `retain-state-shutdown`, `-suspended` | the hooks, not the LED core, own the LEDs   |
   | `watchdog` → `okay`                         | systemd's `RuntimeWatchdogSec`              |
   | VOP `esmart_lb_mode` → `02`                 | 4K on Rockchip                              |
   | `model` → the box's name                    | identity; the factory names the EVB         |
   | CEC: mainline's node, `hdmi-phandle`        | `/dev/cec0`                                 |
   | DDC: `i2c-gpio`, pins muxed to GPIO         | DDC/CI; unmuxed, the EDID reads empty       |
   | IOMMU: `iommus` on every master the factory | no page faults at idle                      |
   | SoC or board `compatible`                   | only where a driver or userspace keys on it |

## Bites

- **Stock first.** An unofficial tree for a one-off box carries its bring-up's issues: a hint when
  something fails, never copied.
- **Trust the PCB over the tree.** A factory tree is often an evaluation board's: it claims hardware
  the box lacks. Disabling a node needs a positive signal, a driver error or a probe reading
  nothing; silence is not absence. No graft without a consumer.
- **Allwinner's legacy pin groups** (`allwinner,pins`, `function`, `drive`, `pull`) are read by
  Linux and skipped by U-Boot without a word: translate them to `pins`, `function`, `drive-strength`
  ((n + 1) × 10 mA) and `bias-*`.
- **Power management does not copy 1:1** from vendor to mainline: the M20's factory tree suspends
  through Amlogic's `aml_pm`, which mainline lacks. Rewrite it, try the candidates, keep the one
  that measures best.
- **The watchdog cannot be disarmed once opened** and counts across a soft reboot: read its clock
  before trusting a timeout.

## Check

- [ ] **T1** `factory_board.dts` and `board.patch` exist, and `factory_uboot.dts` and `uboot.patch`
      where we build U-Boot
- [ ] **T2** The decompile names interrupts and keeps only addresses and bitmasks hex
- [ ] **T3** Every changed property is the factory's, or says why not
- [ ] **T4** Each disabled node's hunk is marked `NOT FITTED`, with its signal
- [ ] **T5** The IOMMU's line in `/proc/interrupts` stays still at idle
- [ ] **T6** `dtb.md` records every change, reverted ones too
- [ ] **T7** The suspend setup is the best-measured candidate, the others in `dtb.md`
