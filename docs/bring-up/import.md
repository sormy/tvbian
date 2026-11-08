# Import bring-up

A board of a family we boot, built from its stock firmware image with no box in hand. Every line
that needs the box stays ❓ until one boots.

## Do

1. **Identify the board** from an owner's PCB photos and a seller or vendor page: the silkscreen
   gives `BOARD_PCB`, the parts give SoC, RAM, eMMC and radio, the case gives the ports. With no
   page, `BOARD_NAME` is the PCB marking.
2. **Tie the image to that board** before creating anything: read the source's whole thread; the
   image's tree must match the photos and the vendor's spec (RAM type, Ethernet PHY, radio bus). An
   owner's boot log or carved tree that matches is the strongest proof.
3. **Unpack it** in scratch, on the host: the loader with its DRAM init, the kernel tree, the U-Boot
   tree and the radio's files, each where its family's image keeps it (below).
4. **Classify the DRAM init** against the SoC vendor's public blobs: equal is the public blob, a few
   bytes off is vendor tuning, no match is the vendor's own build. Note it in the worklog.
5. **Write `board.conf`** from the closest board's, with `BOARD_SUPPORT=not_tested`.
6. **Write the trees**: empty patches, then `./build.sh board-dtb <board>` and `uboot-dtb <board>`;
   apply the family's recipe from the closest board's patch. Per-board rows (names, LEDs, remote,
   radio UART, Ethernet) come from this factory tree, the image's files and the photos, each naming
   its source. A sibling's value is a question, not a row: ask, never guess. Search the tree before
   calling a part absent.
7. **Build**: `./build.sh loader <board>`, `uboot <board>`, `board <board>`, `image <board>`.
8. **Document**: `board.md` with the Test report and the image's source, `dtb.md`, `worklog.md`; the
   board's rows in `README.md` and its family's README, marked ❓.

## Where each family's image keeps it

Rockchip, an `RKFW` image:

| Part                    | Where                                                         |
| ----------------------- | ------------------------------------------------------------- |
| loader                  | `RKFW` header: offset and length at byte 25                   |
| partitions              | the `RKAF` archive after it                                   |
| `factory_board.dtb`     | `boot.img`'s `RSCE` resource, `rk-kernel.dtb`                 |
| `factory_uboot.dtb`     | `uboot.img`, a FIT: its `fdt` image                           |
| `factory_idbloader.bin` | the loader's FlashHead, FlashData, FlashBoot, padded to 2 MiB |
| radio files             | `super.img`, sparse: `vendor`'s `/etc/firmware/`              |
| public DRAM blobs       | rkbin's `bin/rk35/`                                           |

- The loader's entries are RC4 per 512 bytes; the whole buffer through RC4 also starts `RKNS`, then
  garbage.
- Older DRAM inits print `DDR V1.05`, newer `ddr-v1.11`.

Allwinner and Amlogic images are not run yet.

## Bites

- **A download's name is not the board, nor is what its image shares with others**: a DRAM init or a
  tree built on a vendor's evaluation board can sit on several boards. Match the tree to the photos'
  chips.
- **A multi-Wi-Fi image names no chip**: it ships every chip's firmware, and its tree's radio entry
  can be a placeholder. Read the chip from an owner's log, or from the module's marking where it
  reads clearly.
- **An image can be older than the boards in the field.** Its driver and firmware dates against an
  owner's boot log show it; read a chip's revision from that log, not from what the image supports.
- **A node is not a part, a name not a use**: every factory tree enables `sdmmc`, slot or not; a
  `pwr-wifi` LED can be the box's only LED.
- **A calibration file fits the board** when it equals the image's own in every enabled value; a
  vendor's template shared by every box is not evidence either way.
- **Shared tools change only for a tied image.** An unchecked image's quirk is not a reason to widen
  a build script.
- **An image is not a dump**: no per-unit data, MACs or DRAM training.

## Marks

| Line                                        | Mark                       |
| ------------------------------------------- | -------------------------- |
| identity, trees, loader, build              | ✅ where the files show it |
| SoC block identical to a sister's           | 🟡, the sister named       |
| board wiring, per-unit values, anything run | ❓                         |

One fact moves a claim one mark, never from one end to the other.

## Check

- [ ] **P1** The board identified from an owner's photos and a seller or vendor page
- [ ] **P2** The image tied to that board, the evidence recorded
- [ ] **P3** The DRAM init classified
- [ ] **P4** The factory trees decompile with no cell left a number
- [ ] **P5** The recipe applied; every per-board row names its source, or was asked
- [ ] **P6** `loader`, `uboot`, `board` and `image` build
- [ ] **P7** `BOARD_SUPPORT=not_tested`; `board.md` names the image's source
- [ ] **P8** The Test report marks only what the files show; each 🟡 names its sister
