# H96 Max RK3528 steering

## 2026-11-07: an import built on the wrong image, its rows guessed

- **Kind**: `agent`.
- **Found by**: the human, three times: the LED, the 1000 Mbit Ethernet, the flip-flop.
- **Cost**: a board directory, trees, a loader, a package and an image built on unchecked inputs;
  the human's corrections.
- **What went wrong**, in order:
  1. The image was taken from ophub #2404's issue body, the owner's first recovery link, without
     reading the thread. The owner wrote later that it was "for the H96MAX m1", and posted the M2's
     own ROM from H96.
  2. The board directory was built before the image's tree was checked against the photos and H96's
     spec: DDR3 and a 100 Mbit `gmac0` against DDR4 and an RTL8211F on `gmac1`.
  3. Per-board rows were guessed into `board.dts`: the factory's `pwr-wifi` LED read as the radio's
     power, the Ethernet taken as the M2 Plus's.
  4. A shared DDR banner and tree with `RK3528_DDR3_8X4_V12` was reported as the M2's identity.
  5. One fact, the missing `gmac1`, swung the claim from "the M2's, 🟡" to "unrelated to the M2",
     overstated both ways.
  6. `tools/board/build-loader.sh` was widened to take the unchecked image's older DDR banner.
- **Fix**, in `docs/bring-up/import.md`: read the source's whole thread before taking a file; check
  the image's tree against the photos and the vendor's spec (RAM type, Ethernet PHY, radio) before
  any board directory exists; ask the human for a row the evidence does not settle; a single fact
  moves a claim one mark, not across. `aedc2fe`, `81f1cf9`.
- **Outcome**: the board is the H96 Max RK3528, neither the M1 nor the M2.

## 2026-11-08: rows from siblings and misreadings, before the image was read

- **Kind**: `agent`.
- **Found by**: the human, asking whether Bluetooth runs over serdev, and doubting the module's
  marking.
- **Cost**: three questions from the human; docs corrected twice.
- **What**: Bluetooth on `uart2` serdev was written as fact from the R69-1 before the image's
  `bt_vendor.conf` was read; it held. The radio was written into the worklog and the inventory as an
  AIC8800D80 from a photo neither person could read; it held, shown later by the stock boot log. The
  tree was said to describe no front display, unsearched: its `fd655_dev` node was there. An `sdmmc`
  node at `okay` was argued as evidence of a slot, yet every factory tree here has one.
- **Repeat**: the 2026-11-07 entry's guessed rows, again.
- **Fix**: an `AGENTS.md` rule: a per-board claim names its source; a sibling's value or an unsure
  reading is a question until the board's own evidence answers it. `81f1cf9`.

## 2026-11-08: the seller's image is older than the board's stock

- **Kind**: `missing`.
- **Found by**: the agent, reading the owner's stock boot log for the radio's revision.
- **What**: BOXPUT's image (2023-06-30) carries a 2023 AIC driver and a 1,811-B calibration file;
  the board's own stock (`RZX.V01.20240924`) a 2024 driver and 2,683 B. Kernel tree and DDR init
  match. Nothing in `docs/bring-up/import.md` warned that an image may lag the boards in the field.
- **Fix**: `docs/bring-up/import.md`: the image's driver and firmware dates against an owner's boot
  log; a chip's revision is read from the board's own log, never from what an image supports.
  `81f1cf9`.

## 2026-11-08: a doc and a gate rule that overclaim

- **Kind**: `wrong`.
- **Found by**: the agent.
- **What**: `firmware/aic8800/README.md` said radxa's set covers "every revision and variant"; it
  has no AIC8800D80 U01 set. The import gate asks for Wi-Fi calibration from the board's own dump,
  yet the R69-1 ships radxa's file: its stock, this image's and radxa's apply the same values, AIC's
  template, every other section disabled.
- **Fix**: the README corrected, `c5d80d9`. The import bite: a file equal to the image's own in
  every enabled value, `81f1cf9`.

## 2026-11-08: a failed edit still wrote

- **Kind**: `tooling`.
- **Found by**: the agent, a duplicate worklog entry.
- **What**: a shell step ran an append after the edit before it had failed, the two on separate
  lines rather than joined by `&&`.
- **Fix**: none in the docs; it happened once. Dependent steps joined by `&&`.
