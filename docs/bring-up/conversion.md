# Vendor-to-mainline conversion

This applies only to a board whose `_SOURCE` base is a vendor kernel and whose `_TARGET` is
mainline. Its factory tree is translated (`trees.md`, `family.md` step 7), and a translation can be
silently wrong. A vendor tree kept on its vendor kernel, or a mainline tree moved to a newer
mainline, skips all of this: its patch is the whole difference, and the box tests it.

The rule for every step: **stock is the source of truth**. The translation restates stock in
mainline's terms and fixes nothing. Measure on the box any fact stock lacks, and override stock only
where the box proves it wrong. Never take facts from an upstream tree for a sibling board: it
describes the revision its author had.

## Do

1. **Translate with the report**: run `translate.py --report` until no token is `unknown`, every
   drop's comment says why it is safe (no driver reads it, the block has none), and every
   `unresolved` is a question for the steps below. A conf refactor must leave every board's tree
   byte-identical.
2. **Answer the questions on the box, not from another tree.** Measure the rail, the bank voltage,
   the GPIO level. On the H616, `PIO_POW_VAL` at `0x0300b348` reads each bank's voltage, one bit per
   bank, 1 for 1.8 V. A patch line that overrides stock names its measurement in a comment.
3. **Semdiff against the last proven tree**: `tools/dtcx/semdiff.py <proven.dtb> <new.dtb>` (for a
   first board, against stock's dtb). Explain every line by the conf, the board's patch or a dtsi
   patch. Anything else is a bug: fix it in the tool, with a test that fails without the fix.
4. **Prove the upstream view**:
   `tools/dtcx/upstream.py --prove board.dtb <source> <target> board.dts` writes the board as
   mainline would and must show no difference from `board.dtb` (`tools/dtcx/README.md` lists what a
   view may leave out). Read its header (the patches the board needs beyond its base kernel, found
   by name, so best-effort) and its size: a block no board fact explains is a bug.
5. **Validate against the bindings** the tree is written for: the tag of the conf's `soc` URL plus
   the kernel conf's binding patches (`tools/dtcx/bindings.py`, then `dt-mk-schema` and
   `dt-validate`). Every finding except the board's own compatible gets a `dt-bindings:` patch,
   listed ahead of the patch that adds the compatible or property, in both confs.
6. **No block described twice**: `tools/dtcx/devices.py board.dtb`. Proof and schemas pass a block
   described twice (a vendor root node and the dtsi's node for one SRAM); merge the two by label.
7. **Deploy so a failure can recover**: a box reachable only over Wi-Fi rolls back to the previous
   tree by itself if the new one brings no network up (a one-shot unit checks for an address three
   minutes in). Then test both kernels, the blocks the change touched (regulator consumers, bank
   modes, MMC timing, the radio), and warm reboots.

## Pitfalls

- **semdiff only reads what it knows.** A reference property not in `references.py` or the base
  compares as numbers: renumbering shows as a change, and a phandle moved to another node can be
  missed (the RK3528's `clk_pin` pointed at `ioc_grf` in its view until the base declared it).
  Disabled blocks and unselected pin groups are not compared. Fix the reader before trusting a line
  it cannot read.
- **A label is a name, not an address.** The M20's vendor `pwm_cd` is at `0x8640`, mainline's at
  `0x8650`; matching by label enabled the wrong block. A vendor unit address can be wrong while its
  `reg` is right: the H616's GIC is `@03020000`, its registers at `0x3021000`.
- **The vendor's template is not the board**: pin groups for blocks the box lacks, remote tables for
  remotes it never shipped with. What nothing selects configures nothing.
- **A property the driver ignores is not worth keeping**: neither the sunxi-cir nor the AXP313
  driver reads `wakeup-source`. Read the driver before keeping a property.
- **A line belongs on its consumer, not on a hog.** The H313's Bluetooth reset and wake lines were
  hogs until its driver took them. A control boot (no hog, no driver) shows what the chip needs: the
  AIC8800 needed neither.
- **Validate against the right kernel's bindings.** 6.18's bindings report gaps in a tree written
  for 7.3 that 7.3 has already closed.
- **A guard's check needs tools the image has**: a rollback guard that used `ping` rolled every box
  back, because the image has no `ping`.
- **An upstream sibling is a different revision**: upstream's Tanix TX1 is the V1.0, with banks PC
  and PG at 1.8 V; the V2.0 runs both at 3.3 V.

## Check

- [ ] **V1** `translate.py --report` lists no `unknown`, and every `unresolved` is answered or
      recorded as open in `dtb.md`
- [ ] **V2** Each override of stock in `board.patch` names the measurement behind it
- [ ] **V3** `semdiff.py` against the last proven tree: every line explained in `dtb.md`
- [ ] **V4** `upstream.py --prove` reports no difference
- [ ] **V5** `dt-validate` against the patched bindings reports nothing but the board compatible
- [ ] **V6** `devices.py` finds no block described twice
- [ ] **V7** `regression.md` on both kernels, with the touched blocks checked
