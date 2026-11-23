# Working in this repo

Rules for anyone — human or agent — adding a board or changing this repo. Most have a corpse in
`docs/*/worklog.md` behind them. The procedure itself lives in the docs indexed below.

Notes for agents live here and in the docs, never in a tool's private memory; what can't be public
goes in `AGENTS.local.md` (gitignored).

## What this repo is

Debian with our own kernel, drivers and board packages, not a fork of a distro. Kernel sources and
userspace come from upstream; we carry only what upstream can't know. **Adding a board is data, not
code** — one `boards/<board>/` directory. If a change needs new code per board, the design is wrong.
TVBian is based on Debian; it is never called Debian.

**Boards stay downstream**: no board tree or config goes upstream. Mainline patches are sendable as
they stand: one change each, a `Signed-off-by`, `checkpatch.pl --strict` clean except where the
surrounding code's style wins. Imported and backported code stays as its source wrote it. A fix to a
carried patch not yet upstream is folded into it. Vendor-kernel patches (`linux-rockchip`, the
out-of-tree drivers) have no upstream path, and are written for the least code that is correct on
our boxes. A board's key names its model (`h96max-m20`), never its SoC.

| Tree                | Holds                                                                                          |
| ------------------- | ---------------------------------------------------------------------------------------------- |
| `boards/<board>/`   | `board.conf`, the factory trees, the patches on them and their output, loaders, `package.list` |
| `boards/common/`    | mechanism some boards share, each picking it in its `package.list`                             |
| `base/`             | `tvb-base`: what every box gets, and its `package.list`                                        |
| `firmware/<chip>/`  | a chip's firmware, packaged as `tvb-firmware-<chip>`                                           |
| `docs/<board>/`     | `worklog.md` (history), `dtb.md` (tree changes), `board.md` (usage)                            |
| `docs/<family>/`    | `worklog.md`: the family's work no single box owns                                             |
| `docs/<chip>/`      | `worklog.md`: a Wi-Fi/BT chip's driver work, whatever board carries it                         |
| `stock/<board>/`    | factory evidence: dumps, logs, partition maps                                                  |
| `backup/`           | `<board>-stock.img.xz`, the factory eMMC (gitignored)                                          |
| `patches/<topic>/`  | every patch to an upstream's code, one folder per upstream, with its upstream status           |
| `tools/<tool>/`     | host tools: a build script or our own source; `tools/board/`, the boot-file generators         |
| `keyring/`          | the `apt` repo's public signing key                                                            |
| `kernel/`           | each kernel's pin, config, fragment and patch list, and the step building it                   |
| `build-env/`        | the build environment: one container image every `./build.sh` step runs in                     |
| `modules/`          | each out-of-tree driver: its pin, our patches, the step packaging it per kernel                |
| `uboot/`            | each U-Boot a board package ships, and each FEL loader: pin, defconfig, the step building it   |
| `package/`          | the steps building `tvb-<board>`, `tvb-firmware-<chip>`, `tvb-base` and `tvb-archive-keyring`  |
| `extras/<package>/` | a Debian package we shadow until Debian ships the fix, or an upstream one beside Debian's      |
| `va-driver/`        | our VA-API driver: its source, every backend in one build, the step building `tvb-va-driver`   |
| `session/<name>/`   | a session: Debian's programs as its depends, our defaults for them, `tvb-<name>`               |
| `image/`            | the image step, its package list, and the image's own state: locale, root's first SSH login    |
| `release/`          | the release plan, the signed `apt` repo, and the upload to GitHub                              |
| `site/`             | the public page and the script that builds it                                                  |
| `tests/`            | the scripts' tests, one file a script, run by `./build.sh test` in the build container         |

**Repo files carry no prefix**: each board's `package.list` names where a file installs. A board
directory holds `board.conf`, the tree, the factory idbloader and the maskrom loader,
`package.list`, and firmware only where it is shown to be this board's. **What every box gets lives
in `base/`, mechanism some boards share in `boards/common/`** — a board never keeps its own copy of
a family script. What it may keep is mechanism no other board can use: a unit for hardware only it
has.

**A board's tree for a kernel not yet its own lives in a subdirectory**, `boards/<board>/next2/`: a
`board.conf` naming only its DTB bases, links to the factory DTB and its source, and its patch and
output. It replaces the board's own tree once that kernel does.

**A board's version lives in `BOARD_ID` alone**, beside `BOARD_PCB`'s silkscreen, which says it
anyway. `BOARD_NAME` and `BOARD_HOSTNAME` name the model: `tanix-tx1-v2` is `Tanix TX1` at
`tanix-tx1.local`.

**Tools we build, and must:** `dtc` (`./build.sh tool dtc` — vanilla cannot round-trip a vendor blob
with `&label`s) · `rkdeveloptool` (`./build.sh tool rkdeveloptool`) and each board's maskrom loader
(`./build.sh loaders`) · `sunxi-fel` (`./build.sh tool sunxi-fel`) and each board's FEL loader, the
same step · `amlcmd` and `gxlimg` (`./build.sh tool amlcmd`, `./build.sh tool gxlimg` — Amlogic's
own are closed and x86-64 Linux only) · each board's `board.dtb` and `uboot.dts` from its factory
trees (`./build.sh board-dtb <board>`, `./build.sh uboot-dtb <board>`) — or every board's boot files
at once with `./build.sh boards`. **From the host:** a container runtime, on macOS Apple's native
`container`, never Docker · `cc` and `patch` · `fdtput` · `fsck.ext4` (keg-only on Homebrew:
`/opt/homebrew/opt/e2fsprogs/sbin/`) · `xz` · `npx prettier` · `python3` · `mtools` and `mkimage`,
for a board whose image carries a FAT boot partition. **On the box:** `evtest`, `fio`, `stress-ng`,
`iw`, `bluez`.

**Every container and volume a session makes is labelled `project=tvbian`**, as `./build.sh`'s are:
an unlabelled one is stray, deleted once its owner says so.

**`e2tools`** (`./build.sh tool e2tools`) — edit a box's ext4 rootfs on an SD card or USB stick from
a Mac, which cannot mount ext4; the stock one corrupts an image on delete.

## Where things are written down

**This table is the only index.** Docs are independent — each stands alone and none links to
another, so nothing rots when one is rewritten.

| Doc                                      | Holds                                                                 |
| ---------------------------------------- | --------------------------------------------------------------------- |
| `docs/bring-up/`                         | bring-up in phases, each do, bites and checks; the run's rules        |
| `docs/first-login.md`                    | a new box's user, timezone, locale and Wi-Fi, by hand                 |
| `docs/mpp.md`                            | reaching the video engines; the codec test commands                   |
| `docs/video-support.md`                  | each SoC's hardware decode, encode and display formats, by codec      |
| `docs/va-driver.md`                      | Debian's programs in hardware; what the VA driver adds                |
| `va-driver/README.md`                    | the VA-API driver: what each engine offers, how VA maps onto it       |
| `va-driver/worklog.md`                   | the VA-API driver's dated history, wrong turns included               |
| `session/<name>/worklog.md`              | a session's dated history                                             |
| `docs/emmc-layout.md`                    | the measured eMMC map: every replicated structure and its sectors     |
| `docs/build.md`                          | `./build.sh`: hosts, steps, outputs, and making a release             |
| `docs/release-checklist.md`              | what a new package needs to build and publish: extras, new steps      |
| `site/README.md`                         | the public page: one HTML file from the repo, deployed on a release   |
| `docs/sources.md`                        | every upstream we build from: what floats, what is pinned, and why    |
| `docs/migrate.md`                        | moving a box off the overlay: in place on Rockchip, or a reinstall    |
| `docs/uboot.md`                          | the bootloader pair: what we build, what stays factory, why           |
| `docs/rockchip-maskrom.md`               | Rockchip's USB service modes: entry, the 32 MiB Loader trap, restore  |
| `docs/amlogic-burning-mode.md`           | the Amlogic burning gadget: entry, backup, restore, the mask ROM      |
| `docs/allwinner-fel.md`                  | Allwinner's FEL: back up, restore, install over USB                   |
| `docs/watchdog.md`                       | the watchdog: checking it, rebooting with it armed, crash records     |
| `docs/hdmi-edid-override.md`             | banning a display mode the panel advertises but nothing should pick   |
| `docs/remote-keymap.md`                  | validating IR and BLE keymaps separately; the `hwdb` override         |
| `docs/front-panel.md`                    | a front-panel display's clock: its settings on the box                |
| `docs/rk3528-line-buffers.md`            | the RK3528's display line buffers: planes per split, the boot setting |
| `research/<experiment>/`                 | dead ends and partial results, kept so nobody re-walks them           |
| `docs/todo/README.md`                    | project-wide items, and the index of every page in `docs/todo/`       |
| `docs/todo/`                             | a page a scope: family, Wi-Fi/BT chip, box, or project-wide topic     |
| `docs/<board>/board.md`                  | that board's identity, measured numbers, known gaps                   |
| `docs/<board>/dtb.md`                    | that board's device-tree changes, tried and reverted ones too         |
| `docs/<board>/worklog*.md`               | dated history, wrong turns included; split by topic once it grows     |
| `docs/<family>/worklog.md`               | a kernel, translator rules, SoC blocks: no single box's work          |
| `docs/<chip>/worklog.md`                 | a Wi-Fi/BT chip's driver, on every board that carries it              |
| `tools/dtcx/README.md`                   | a blob decompiled as its vendor wrote it: named constants, decimal    |
| `tools/amlcmd/README.md`                 | the Amlogic burning-mode client we wrote, and its worklog             |
| `tools/validate/README.md`               | a running box against the bring-up criteria, one script a component   |
| `patches/dtc/README.md`                  | the patched `dtc` that round-trips a vendor blob with `&label`s       |
| `patches/u-boot/README.md`               | U-Boot's pylibfdt build off Linux; the MAC from vendor storage        |
| `patches/arm-trusted-firmware/README.md` | TF-A's BL31 for Allwinner boards: the watchdog reset fix              |
| `patches/rkdeveloptool/README.md`        | the patched `pack`; why the stock one cannot build a usable loader    |
| `patches/e2tools/README.md`              | the patched `e2tools`; why the stock one corrupts an image on delete  |
| `patches/linux-rockchip/README.md`       | the vendor kernel's patches, their PRs, what Rockchip fixed since     |
| `patches/linux-meson/README.md`          | mainline kernel patches for Amlogic boards, on their way upstream     |
| `patches/linux-sunxi/README.md`          | mainline kernel patches for Allwinner boards: the H616 display        |
| `patches/aic8800/README.md`              | the AIC8800 SDIO driver: Radxa's patches, then ours                   |
| `patches/atbm6031/README.md`             | the ATBM6031 SDIO driver: a community 6.18 port, then ours            |
| `patches/tm16xx/README.md`               | the TM16xx front-panel display driver on our kernels                  |
| `patches/seekwave-swt6621s/README.md`    | the H96 Max Wi-Fi driver patches and their PRs                        |
| `patches/mt76-mt7668/README.md`          | mainline mt76 for the MT7668S: what it does, its gaps, its firmware   |
| `patches/btmtksdio-mt7668/README.md`     | mainline Bluetooth for the MT7668S, in-tree                           |
| `patches/mt76x8-mt7668/README.md`        | the vendor MT7668 driver on 6.18: the fallback, not shipped           |
| `patches/meson-dw-hdmi/README.md`        | mainline HDMI for the GXLX2 (S905L3), in-tree                         |
| `patches/meson-codecs/README.md`         | the video decoder in-tree and the encoders beside it on the GXLX2     |
| `patches/gst-plugins-good/README.md`     | VC-1 through V4L2 on GStreamer 1.26.2: the patched plugin, by hand    |
| `patches/mpp/README.md`                  | Rockchip's MPP: its probe a call; IEP2 keeping every field            |
| `patches/ffmpeg/README.md`               | FFmpeg 9.0.2: V4L2 request, mem2mem and Rockchip MPP codecs           |
| `patches/kodi/README.md`                 | Kodi 22 on GBM: handing the screen to another program                 |
| `patches/mesa/README.md`                 | Panfrost fixes on Debian's Mesa, backported from upstream             |
| `patches/gxlimg/README.md`               | the Amlogic boot-image tool, built on macOS                           |
| `keyring/README.md`                      | the archive signing key: fingerprint, secret, rotation                |
| `kernel/regdb-certs/README.md`           | the regulatory database's signing keys our kernels trust              |

# Standing rules

**A mistake made twice becomes a rule** here, or in `AGENTS.local.md` when it is about the owner's
setup.

## Claims and evidence

Six states, meaning exactly what they say:

- **✅ verified here** — run on this box, with the number or output to show for it.
- **🟡 likely** — not verified here, but something proven backs it and nothing indicates a problem:
  the same mechanism ✅ on a sibling board with no sign the boards differ, or a ✅ layer beneath it
  that we do not touch.
- **❓ never tested** — nobody has looked, and nothing predicts the answer.
- **🟠 works, degraded** — verified here, but measurably short of its siblings or stock.
- **❌ tested and broken.**
- **➖ not present on this box.**

**Verification is per-board.** A shared mechanism earns 🟡. It earns ✅ only from a sister board's
✅ plus a weak check on this board, a sister being identical for that block: the same SoC, chip and
tree node. 🟡 and ❓ are not interchangeable: 🟡 has a reason behind it, ❓ is an unknown.

**A per-board claim names its source**: the file, log line or photo it came from. A sibling's value
or a reading nobody is sure of is a question until this board's own evidence answers it.

**Check before asserting** — read the file, query the box, run the command. A doc is not evidence
about hardware; reconcile against the box. Don't publish a recipe you haven't run, and when a claim
cannot be backed, say so rather than rounding up.

## Documentation

- **Written for people first, AI second.** A reader who knows the field but not this repo follows
  every doc; an agent reads the same words, never a version written only for it.
- **Docs are updated in the same pass as the change.** Work isn't done when the box works; it's done
  when the docs say what the box does. A doc that contradicts the repo is worse than no doc.
- **Docs stand alone: none names another**, by link or in prose, nor explains itself through another
  family's terms. A doc that needs another's fact states it. Exceptions: the index above, the top
  READMEs routing a reader to a family or a guide, a board's own `board.md` for its per-board facts,
  a worklog naming the files it changed, and the bring-up's phases naming each other and the docs
  they update.
- **Checklist IDs live in `docs/bring-up/` alone**: a board's Test report, its worklog, commits and
  messages name what a line checks, since IDs drift.
- **A check is never a todo, unless it waits on a person.** Checks live in `docs/bring-up/`, a hand
  check marked 👤; one a board still waits on is a 👤 item on its todo page until done.
- **A todo goes where its scope is.** `docs/todo/README.md` holds what spans families, and indexes
  the folder: `<family>.md` for what spans a family's boards (`rk35xx`), `<chip>.md` for a Wi-Fi/BT
  chip whatever board carries it (`aic8800`), `<board>.md` for one box, and `<topic>.md` for a
  project-wide item too big for a line. A page grows topics as `<scope>-<topic>.md`. Every page has
  its row in the index. An item says what we want in the end, in a line or two, not how. A finished
  item is removed: the worklog and the commit record it.
- **A todo changed is a todo cross-checked**: the board's `board.md` and `dtb.md`, the READMEs that
  name it, and `tools/validate/known.conf`, whose step skips point at todos and go when they land.
- **An ask made in the middle of other work is a todo first**, to do or to consider, on its page.
  Then back to the work.
- **Worklogs are written as work happens** — dated entries, wrong turns included. They are the raw
  material everything else derives from, and what the next port follows. Beside each, `steering.md`
  logs where the docs or rules steered wrong. A box's results go in its board's worklog; a Wi-Fi/BT
  chip's driver work in its chip's; a feature's, a session or the VA driver, in its own folder; the
  rest no single box owns, in its family's.
- **Narrative lives in `docs/`**, never in scripts, payload files or DTB tables. Those stay terse.
- **Measured numbers live in `docs/<board>/board.md`** — they're per-unit and they decay.
- **The claim, not its proof.** Dates, evidence and the session's narration go in the worklog; a
  table is never restated in prose; a line that fails "do we even need this?" goes.
- **No titles or file names from the owner's media** in docs, patches, commits or messages: a film
  is named by its format, "a 4K24 HEVC Main10 film"; tests use synthetic streams.
- **Short and plain**: docs, instructions and comments, an agent's most of all. Leave out the
  obvious; no flourish. What can be said in half the words is said in half.

## Markdown

- **Pure facts. No poems, no prose, no narrative.** A table or a checklist beats a paragraph. Drop
  anything obvious or inferrable — if a competent reader can work it out, it does not go in.
- **Simple to read**: the point first; short sentences, one idea each; plain words, a term the
  reader needs defined once; a list or a table for anything with parts.
- **Prose value over prose amount: every word earns its place.** Cut relentlessly: a sentence
  restating the one above it, a caveat the command already enforces, an explanation of what the
  reader can see. Length is the symptom; restatement is the disease.
- **One claim per line, backed by the command that shows it — not by your proof that you ran it.**
  "A full pass completes on a full-clock board", never "✅ proven on two boards, spot-verified".
  Dates and evidence belong in `worklog.md`.
- **One command, one line.** The mechanism behind it goes in `docs/todo/` or the patch that
  implements it. Never warn against a command the doc does not give, or defend against a state it
  forbids.
- **Keep a doc around 300 lines** — past that by much, split it or cut it. Two exceptions:
  `docs/<board>/board.md` gets 500, and `worklog.md` has no limit, being append-only history.
- **README is scannable**: no filler, no repeated links, no per-board hardcoding where a pattern
  works. Warnings go in blockquotes. Humour is fine; it must not cost clarity.
- `npx prettier --write` on every markdown file you touch.

## Writing a reference doc

- **One doc, one subject.** Check every block against the title; move what fits only by adjacency.
- **Say where a command runs** — host, box, U-Boot prompt, maskrom. Read in the wrong context, a
  block is a destructive mistake.
- **Blocks in the order they are performed.** "Do this first" under the second block is a bug.
- **Lead with the procedure.** A reference table comes after it, never instead.
- **A table cell is a label, not a sentence.** Markdown is read as source as often as rendered, and
  prettier will not wrap a table: a row past 100 columns is unreadable in the file. Keep cells to a
  few words and put any clause in the prose below.
- **One column, one kind of thing. One row per case.**
- **One name per thing.** Say once that two names mean the same, then pick one.
- **The marker carries the uncertainty.** ❓ already says untested.
- **Never say it twice in two shapes.**
- **Never write ❌ for something nobody tried.** Untried is ❓; reasoned-but-unmeasured is 🟡, with
  the reasoning named.
- **Never enumerate the boards.** State the mechanism and the selector; the per-board answer lives
  in that board's `board.md`.
- **Say "known here"** — never imply a list is exhaustive.
- **A limitation being fixed is current, not permanent.**
- **History belongs in `worklog.md`.** A **date on a claim is evidence, not history**:
  `✅ measured 2026-08-20` belongs.

## Writing a guide

A guide is a procedure a user follows, a README section or a service-mode doc; a reader who has
never seen the box must get through it.

- **Sections by task**: prerequisites, then one per job; a job with an easy and a hard case splits.
- **Prose between the commands**, no numbered steps or bullets; caveats close it as a short list.
- **Generic**: no board's name or numbers, and both hosts, macOS and Linux, wherever they differ.
- **No internals**: how it was built and why lives in comments and the reference docs.
- **No ❓**: what is untested is a todo item, its history the worklog.
- **No magic numbers**: the command reads them from the repo's own files, or a short comment says
  what they are.
- **Each step says what it is for and where it runs**; what is optional says so, and what for.
- **Recommend the safer route** without forbidding the other.

## Commits

**Commit and push only when the owner asks**, after showing the change; never as a step of other
work. A push starts a release.

**Nothing is committed untested**, unless the owner approves it untested. A kernel, tree or driver
change is tested on the box it targets, on every kernel it ships on.

**Release-ready means `docs/bring-up/regression.md` passed**: its unattended run, the extended
profile for a kernel series, and its list of what needs hands, done by the owner. No one suite's
pass stands in for it.

**A title. A paragraph only where it earns its place** — something a reader cannot get from the
diff. The diff is the record; reasoning belongs in the comment, the doc, or the todo it came from.

**Sweep the staged diff before committing**: every hunk belongs to the commit's one change, and no
name, path or claim it touches is left stale elsewhere in the repo.

## Code

**Follow a trusted upstream's releases; pin only what is unmaintained or risky.** Mainline Linux on
kernel.org and a vendor's kernel on the vendor's own GitHub account are trusted and float; work from
any other tree is a carried patch. `docs/sources.md` lists each source and why.

**A `kernel/*.conf` lists every patch and fragment it applies, one path a line**: no loops, globs,
`$(…)` or `${…}`. A `-next` conf sources its base for the rest. Where a patch comes from is its
directory's README, never its path.

**All code is clean, readable and maintainable**, read top to bottom by a human. Settings first,
named: paths, versions, URLs, limits. One step a line, each stage a named function; logic that needs
decoding gets a name. No literal buried in a command. Shell runs steps; once a script parses,
compares or builds data, that part is Python.

**A board's tree is translated from its own factory tree, never copied from a sibling's.** Another
board's `board.patch` shows which nodes need work, never their values: each value is read from this
factory tree, or it is a question. A sibling's patch applied whole carries its rails, clocks, keys
and OPPs onto hardware that does not have them.

**What the translator can do reliably, it does.** A vendor node with a mainline counterpart is a
translation rule in `tools/dtcx/bases/`, never a hand edit in each board's patch; the patch holds
only what no vendor node carries, such as a panel's digit map.

**Nothing from a vendor tree is discarded blindly.** A dropped node, property or pin state names
what it did on the vendor kernel and the evidence mainline needs no counterpart: the driver that
reads it, or a runtime diff, vendor against mainline on one box, of pin mux, GPIOs, regulators and
clocks. Each difference is a question until explained. A translation rule that ignores a node is
presumed a bug, not the norm: a vendor node that did something on the vendor kernel needs its
mainline counterpart.

**A tree keeps what its vendor tree enables, and fixes no size the hardware varies.** A vendor ships
one tree across a board's revisions (a 100M and a 1000M Ethernet, more RAM, a bigger eMMC), so a
block enabled with nothing attached stays enabled, and RAM and storage sizes come from U-Boot and
the card, never the tree. The exception is a vendor node that does harm, a pin taken from another
block or a hang: the board's patch disables it, with that reason.

**U-Boot handles the SoC and vendor storage only**: it may set the SoC's Ethernet address and pass
vendor-storage entries on; a radio's address belongs to that radio's driver.

**A driver refuses what it cannot show** rather than show garbage: an atomic check that fails is a
player's cue to take another route; a picture that breaks is not.

**A driver's limit is the hardware's, measured**: a size or rate cap is set only where the hardware
fails past it, and its patch names the test that shows it, at the limit and one step past.

**Kernel code never needs a reboot to recover**: no implementation may leave a block, a bus or the
box wedged. A job that times out or faults resets its block and that block's IOMMU, and the next job
runs; a case whose recovery is not written is refused instead. A block that stays wedged until a
reboot is a bug, and a reload or reboot is the test of a recovery, never the recovery. A busy
block's CRU reset is pulsed only inside the PMU's idle request, as the vendor does: pulsed under a
core on the bus, it hangs the SoC past its watchdog.

Less code is better. Communicate through names, not comments: comment a non-obvious _why_ only,
never what the code already says, and keep it shorter than the code it explains. One responsibility
per script.

**A device tree's comment is one line**, on a line its patch changes: the board's reason. What dtcx
or a base's translation writes needs none.

## Reach for the lowest layer that can express it

1. **Device tree** — it describes hardware, needs no code, and survives every userspace and init
   change. SoC identity, node enablement, pin routing, LED names, clocks.
2. **udev rule** — device-triggered policy: permissions, names, symlinks. Fires when the device
   appears, so it needs no ordering. The VPU node permissions are here. **A MAC address is not
   settable this way**: `/sys/class/net/*/address` is read-only, so `ATTR{address}=` cannot work.
   The layer-2 mechanism for addresses is a systemd `.link` file, applied by the `net_setup_link`
   builtin — and it takes a literal value, so a computed address has to be written into a generated
   `.link` rather than derived at event time.
3. **systemd unit or hook** — last resort, for behaviour the layers below cannot express. The
   poweroff/suspend LED transitions are here, because DT can turn one LED _off_ at shutdown but
   nothing in DT turns another _on_.

**Do not split one behaviour across layers.** Half in the tree and half in a script is worse than
either alone: the two can fight (the LED core's `LED_CORE_SUSPENDRESUME` versus a sleep hook), and
the next reader must find both. If the lower layer can only do part of it, do all of it in the
higher one and record why.

## Hardware

**Not sure how the hardware behaves? Check the vendor tree first**: `factory_board.dts`, then the
vendor kernel's driver for that node. It shows what the vendor configured and relied on, before a
guess, a test or another board's tree.

- **The first login asks for a new root password**: the image ships `1234`, expired. With a network,
  copy an SSH key into `/root/.ssh/authorized_keys` over serial once, and the rest of bring-up runs
  as `ssh root@<BOARD_HOSTNAME>.local`.
- **Test everything unattended, and fast.** Synthetic EDIDs, emulators and writeback stand in for
  screens and people; a suite fails fast and runs in minutes.
- **A test waits on events, each wait bounded by a timeout, not on sleeps**: a socket appearing, a
  page's beacon, a frame shown, a process exiting. A fixed sleep is too long on a quiet box and too
  short on a busy one; the timeout only ends a hang, and says which wait hung.
- **Bring-up and fixes run unattended.** Exhaust the box's readback, the repo and `backup/` before
  asking a person to look, listen or plug in. Make the ask one step, and add the test it shows is
  missing. When the ask is timed, a person watching or acting soon after the agent starts something
  (a button held through a reboot), start only on their word that they are ready.
- **`/dev/mem`: only the offsets the driver uses, while its device is runtime-active**; a domain
  reported on can still have the block's clock gated, and anything else hangs or resets the box.
- **A box without a screen gets one in software for a display test**: a panel's EDID
  (`tools/validate/edid-boe-2256x1504.bin`, the M2 Plus's) into
  `/sys/kernel/debug/dri/0/<connector>/edid_override` and `on` into its `force`, written with
  `printf`: the kernel refuses `echo`'s newline. `reset` and `unspecified` undo both. A result on a
  connector whose `status` reads `disconnected` proves nothing: check it first.
- **A box's `/tmp` is RAM**: big files go to `/var/tmp`; remove what you wrote.
- **A `cma=` in `BOARD_CMDLINE`, where the tree's pool is wrong, covers the worst case**, the
  largest uncompressed picture, a seek, a resolution change and the interface up, plus a margin,
  measured with `/sys/kernel/debug/cma/*/used`. A decoder behind an IOMMU uses none.
- **Tests use our FFmpeg**, built on the host; nothing builds on a box.
- **Over SSH, stop a process by its exact name (`pkill -x`) or PID.** `pkill -f` matches the SSH
  session's own command line and kills it.
- `mmcblk` numbering is **not stable** across images or boots. Identify the eMMC by its
  `boot0`/`boot1` companions, an SD or SDIO host by its controller,
  `/sys/devices/platform/<controller>/mmc_host/mmc*`, never by a remembered number.
- **After any refactor, rebuild the image and diff every payload file against a pre-change build.**
  Comment-level differences only, unless the change is deliberately a rename — and a path moving
  between packages needs `Replaces` and `Breaks`, which the release guard checks.
- These boxes are daily drivers. Say what you're about to do to them, prefer `--no-reboot` plus an
  explicit reboot you can watch, and keep a known-good DTB where one file copy restores it.
- **When a box won't boot after a DTB change:** power off, pull the SD (if it boots from eMMC, boot
  an SD instead), mount its rootfs on the host and `e2cp` the known-good `board.dtb` back. The boot
  loader reads `/usr/lib/tvb/board.dtb`, the one copy, or `board-next2.dtb` for a next2 kernel, each
  through its kernel's link in `/usr/lib/tvb/fdt/`. On serial the two failure shapes differ: a
  silent stop is a hang, a repeating U-Boot banner is a reset loop.
