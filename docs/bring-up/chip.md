# Chip bring-up

A Wi-Fi, BT or other chip with no driver in the repo. The board lands first, with the chip ❌.

Anywhere from a day to the hardest part of a bring-up. A driver that associates is quick; a fault
that shows only after hours is not: the Seekwave SWT6621S and the AltoBeam ATBM6031 both latch, in
`research/seekwave-tx-latch-bug/` and `research/atbm6031-latch-bug/`, and neither is fixed; their
workarounds took long to build. So the chip lands working, its hard faults scoped, and the study
goes on in `research/`.

## Do

1. A driver, best first: in-tree, the chip vendor's, another board's vendor SDK. None is research.
2. Its firmware from the stock image, as `tvb-firmware-<chip>` from `firmware/<chip>/`; a newer or
   working build wins, the package's `README.md` saying which.
3. Iterate against `network.md`'s Wi-Fi and Bluetooth lines on both kernels.
4. **A fault that needs hours to show** gets a forcing scenario first, the README's procedure for an
   intermittent fault, then its own `research/<chip>-<fault>/`. Its workaround ships as a switch,
   its cost measured, and the chip lands with the fault marked.

## Bites

- **A community patch is read before it is carried**: one here was 5.8 MB, its substance 22 KB, and
  it bound every SDIO device and hardcoded `/tmp` build paths.
- **Reload a module you are connected through** from one detached script that unloads, checks and
  reloads, so a dropped link cannot strand the box.
- **A hardware trade-off is a switch**, a module parameter, never one side left out: the ATBM6031's
  BLE costs Wi-Fi throughput, and the owner decides.
- **A driver's own error paths are read** before a fault is soaked: the vendor's handling of a
  firmware reboot sat commented out beside its log line.

## Check

- [ ] **X1** N5 to N17 pass on the family's kernel
- [ ] **X2** N5 to N17 pass on its `-next`
- [ ] **X3** Any regulatory country can be set
- [ ] **X4** The module loads and unloads cleanly, repeatedly
- [ ] **X5** The firmware's origin is in its package's `README.md`
