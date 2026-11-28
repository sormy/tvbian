# Import bring-up

A board built from its stock firmware image with no box in hand, beside a similar board already
here. The riskiest route: no box boots its image before an owner does, so a wrong tree, loader or
DRAM init reaches a box unseen. It has no validation of its own: an owner's report is all that
comes, and it is coarse, the box boots or not, Wi-Fi works or not. Each report fills only the lines
it names; the rest stay ❓. Reserve `BOARD_SUPPORT=not_tested` for an import with no hardware test
run.

## Do

1. **Identify the board** from an owner's PCB photos and a seller or vendor page: the silkscreen
   gives `BOARD_PCB`, the parts give SoC, RAM, eMMC and radio, the case gives the ports. With no
   page, `BOARD_NAME` is the PCB marking. If the name is also used for other PCBs, add the PCB or a
   version to the ID, unless the human decides otherwise. Settle the ID before naming any file:
   renaming it later renames the package on every box.
2. **Tie the image to that board** before creating anything: read the source's whole thread; the
   image's tree must match the photos and the vendor's spec (RAM type, Ethernet PHY, radio bus). An
   owner's boot log or carved tree that matches is the strongest proof.
3. **Unpack it** in scratch, on the host: the loader with its DRAM init, the kernel tree, the U-Boot
   tree and the radio's files, each where its family's image keeps it (below). Take every file from
   one image: the newest one that matches the box. An owner's dump only confirms the match.
4. **Classify the DRAM init** against the SoC vendor's public blobs: equal is the public blob, a few
   bytes off is vendor tuning, no match is the vendor's own build. Note it in the worklog.
5. **Write `board.conf`** from the closest board's, with `BOARD_SUPPORT=not_tested`.
6. **Write the trees**: empty patches, then `./build.sh board-dtb <board>` and `uboot-dtb <board>`;
   apply the family's recipe from the closest board's patch. Per-board rows (names, LEDs, remote,
   radio UART, Ethernet) come from this factory tree, the image's files and the photos, each naming
   its source. A sibling's value is a question, not a row: ask, never guess. Search the tree and the
   image's settings files before calling a part absent. If no `dtcx` base reads this vendor's
   kernel, add the base and its translation first (`trees.md`, `family.md` step 7). A remote's
   keymap uses `docs/remote-keymap.md`'s canonical keys.
7. **Build**: `./build.sh loader <board>`, `uboot <board>`, `board <board>`, `image <board>`.
8. **Review before it ships**, a second pass over everything the image writes: every hunk of the
   patches read against this factory tree, every per-board row against its named source, the loader
   and DRAM init the image's own. Run `conversion.md`'s checks that need no box: V1, and V3 to V6.
   If an owner runs another tree on the box, compare it with ours by `semdiff` and explain each
   difference. The owner approves the import before a release carries it.
9. **Document**: `board.md` with `identity.md`'s sections, the Test report and the image's source;
   `dtb.md` and `worklog.md`; the board's rows in `README.md` and its family's README, marked ❓.
   Each open question goes on the board's todo page as one step an owner can do, booted from the
   image on an SD card.

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

Allwinner, a PhoenixSuit `IMAGEWTY` image, unencrypted where it starts `IMAGEWTY` in clear:

| Part                 | Where                                                                 |
| -------------------- | --------------------------------------------------------------------- |
| items                | a 1 KiB header, then a 1 KiB entry each: name, length, offset         |
| `factory_board.dtb`  | `sunxi.fex`: the kernel's tree, which U-Boot also reads               |
| `factory_boot0.bin`  | `boot0_sdcard.fex`; a box's eMMC copy adds what boot0 trained         |
| DRAM tables          | `sys_config.fex`: `[dram_para]`, `[dram_paraN]`, `[dram_select_para]` |
| PMIC boot voltages   | `sys_config.fex` `[power_sply]`, 1000000 + mV                         |
| recovery key         | `sys_config.fex` `[key_boot_recovery]`, where the tree has none       |
| remote keymap        | `super.fex` `system_a`: `/system/usr/keylayout/customer_ir_<addr>.kl` |
| kernel               | `boot.fex`'s banner; `vmlinux.fex`, bzip2 over a tar of the vmlinux   |
| radio files          | `super.fex`, Android sparse: `vendor_a`'s `/etc/firmware/`            |
| public DRAM settings | U-Boot's sunxi DRAM defconfigs                                        |

- An entry's name is at byte 0x24, its length at 0x12c, its offset at 0x134; the count is the
  header's word at 0x3c.
- `vmlinux.fex` is the vendor kernel with its symbols. `llvm-objdump` shows what its drivers do,
  such as how it picks the CPU's speed bin or drives a front panel.
- The remote's layout file is named after its NEC address, the vendor tree's `ir_addr_code`. It
  covers every remote the vendor ships on that address, so it has more keys than one remote.
- `[dram_select_para]` picks a table by strap pins; which one a box runs is what its eMMC copy
  trained, and an image may change one table and not the others.

Amlogic images are not run yet.

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
- **A forum's dump can be carved from the vendor image**: hash its tree against the image's before
  taking it as the box's.
- **An image is not a dump**: no per-unit data, MACs or DRAM training.
- **Several images of one box differ.** Compare their trees, ignoring phandles, and their DRAM
  settings. Use the newest image that matches an owner's dump, and take every file from it.
- **An owner's pull request made for another distribution's kernel can't be merged.** Its tree uses
  that kernel's drivers. Keep its photos, dumps and measurements, and compare its tree with ours.
- **Sellers reuse photos of similar models.** Use a listing photo only if the case shows the board's
  name and the ports match the PCB. The front panel's icons can differ between listings.
- **Check the DRAM voltage when the family has not had this RAM type before.** Our U-Boot's
  defconfig is another board's. A DDR3 box left at LPDDR3's 1.2 V does not start.
- **Allwinner's 5.4 trees leave the PMIC rails at their full range.** Its U-Boot sets them from
  `sys_config`, but mainline's MMC driver may raise a 1.8 V I/O rail to 3.3 V. Fix each rail to the
  voltage `sys_config` gives it.

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
- [ ] **P9** `conversion.md`'s V1 and V3 to V6 pass; any owner's tree is compared and explained
- [ ] **P10** Each open question is one owner step on the board's todo page
