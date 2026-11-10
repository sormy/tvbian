# H96 Max H313 steering

## 2026-11-08 — board record delayed

- Kind: agent.
- Found by: owner.
- Cost: owner requested the board doc after supplying hardware details.
- Fix: created `board.md` and `worklog.md`; record supplied facts as they arrive.

## 2026-11-08 — extracted root lacked merged-/usr links

- Kind: tooling.
- Found by: offline `modprobe --show-depends` check.
- Cost: one failed dependency check; no hardware boot attempted.
- Fix: normalize `bin`, `sbin` and `lib` links after package extraction; run a dynamic executable
  and resolve the USB controller's module dependencies before archiving the diagnostic root.

## 2026-11-08 — use SD for kernel bring-up

- Kind: agent.
- Found by: owner.
- Cost: diagnostic initramfs preparation and a three-minute FEL upload that timed out.
- Reversed: first-kernel boot through FEL despite the delivered box having an SD slot.
- Fix: use SD when available; FEL remains for identification, backup and recovery. Updated
  `docs/bring-up/boot.md`; removed the untested RAM-boot helper from this change.

## 2026-11-08 — kernel omitted Ethernet providers

- Kind: agent.
- Found by: owner, then deferred-probe and kernel-config checks.
- Cost: failed Ethernet access; Wi-Fi setup provided a working way in.
- Fix: check enabled clock/reset providers against selected kernel drivers before the first image.
  PWM and AC200 PHY-control modules are under test; image build alone did not cover them.

## 2026-11-08 — experimental manifest dropped existing fragments

- Kind: agent.
- Found by: three host build failures, then inspection of the complete kernel configuration.
- Cost: three failed builds; no live Ethernet module test reached.
- Reversed: treating the resulting configuration errors as new kernel incompatibilities.
- Fix: preserve `kernel/sunxi64-next.fragment` when adding an experimental fragment. It already
  handles the panic-option types, NTFS3 dependency and AC200 module-name conflict.
- Status: manifest corrected; another build awaits the owner's go-ahead after the three-failure
  stop.

## 2026-11-08 — first Ethernet success remains unexplained

- Kind: agent.
- Found by: owner asking how Ethernet worked during the first boot.
- Cost: one clarification; the earlier connection and loss remain unaccounted for.
- Fix: distinguish the current deferred probe from the historical connection. Inspect the earlier
  boot's kernel and NetworkManager records before assigning a cause to the first drop.

## 2026-11-08 — EPHY variant taken from the factory tree

- Kind: agent.
- Found by: AC200 I2C timeout after the clock resolved, then the SID readout.
- Cost: one kernel build and a live module test on the wrong companion.
- Reversed: describing an AC200 because the factory tree names one; the vendor kernel picks AC200 or
  AC300 at run time.
- Fix: on an H616-family box, read SID 0x2c before writing the EPHY: bit 8 set means AC300 on MDIO.

## 2026-11-08 — defconfig symbols that no patch defines

- Kind: agent.
- Found by: the EPHY chain's deferred probe, then the kernel's resolved config.
- Cost: no Ethernet on the first image.
- Fix: check that each symbol a tree node needs appears in the built kernel's config, not only in
  the defconfig.

## 2026-11-08 — the tree copied a sibling's values

- Kind: agent.
- Found by: an audit of `board.dts` against this unit's factory tree.
- Cost: the EPHY on the 1.8 V rail, the SD detect without its pull-up, comments naming the Tanix
  TX1's remote and rails.
- Fix: check every value a sibling's tree supplies against this unit's factory tree before the first
  image.

## 2026-11-08 — the EPHY drivers as modules

- Kind: agent.
- Found by: a reboot without Ethernet, `EMAC reset timeout`.
- Cost: one lost boot; the first boot had won the race.
- Fix: a driver whose clock the MAC's reset needs is built in.

## 2026-11-08 — composite on mainline timing with vendor tables

- Kind: agent.
- Found by: the owner, black lines between picture lines.
- Cost: a dozen live register tests, the owner watching.
- Reversed: Allwinner's encoder tables kept, mainline's interlaced CRTC timing kept beside them.
- Fix: port a vendor sequence whole, its timing and clocks with its tables, read from the BSP first.

## 2026-11-08 — the owner asked to test what the source answers

- Kind: agent.
- Found by: owner.
- Cost: one ask, refused: boot stock Android to hear its channel order.
- Fix: read stock's driver source first; ask only for what no read can show.

## 2026-11-08 — addresses had no match check

- Kind: docs.
- Found by: owner, the label's MAC against the box's.
- Cost: the first images shipped SID-derived addresses while the label's sat in secure storage.
- Fix: `docs/bring-up/network.md` ranks the factory store as the label's copy; N21 checks it.

## 2026-11-08 — a conf edit failed inside a background build

- Kind: agent.
- Found by: no `hci0`; the module had no `aicsemi,aic8800-bt` alias.
- Cost: one kernel build and an install without the patch.
- Fix: edit and check a conf in its own step, then build; a background command hides the edit's
  failure.

## 2026-11-08 — reboots waited on by uptime or ping

- Kind: agent.
- Found by: owner, a panic test reported as "no reboot" after the box was back.
- Cost: three reboot tests misread: a wait passed before shutdown, a ping loop missed the outage, an
  uptime window let the wait hang.
- Fix: read the boot ID before the reboot, then wait until it differs.

## 2026-11-09 — input names marked ❌ for USB HID

The check names internal devices only, those hard to trace; a USB device has `by-id` and `by-path`
already. The checklist said every `event*`; it now says on-board inputs.

## 2026-11-09 — USB 2.0 marked ✅ from a 12M receiver

The input phase asks for a USB 2 stick before it starts; the run skipped the ask and let a 1.1
device stand for 480M. A row's ✅ needs the device the check names.

## 2026-11-09 — glmark2 41–42 marked 🟠 and left

The image ships no Mesa; `glmark2-es2-drm` pulled in Debian's, our repo carrying none yet. The
number was taken on it and not compared with the sibling's 121 or with `patches/mesa/README.md`,
which records 42 → 121 on this SoC. A low number is a question until a sibling's figure explains it.

## 2026-11-09 — the trees phase said to start from the closest board's patch

- Kind: doc.
- Found by: the owner, after the 2026-11-08 audit.
- Cost: the Tanix TX1's OPPs, rails, remote and recovery key carried into this tree whole.
- Fix: `trees.md` takes only the list of nodes from a sibling's patch, each value from this board's
  factory tree, and checks that no value traces only to another board's tree.

## 2026-11-09 — the eMMC left at the tree's cautious DDR52

- Kind: doc.
- Found by: the owner.
- Cost: the eMMC at 75.5 MB/s, stock's HS200 and HS400 never tried; the SD and SDIO alike.
- Fix: the storage phase brings every MMC bus to stock's fastest mode, or records the error that
  stopped it.
