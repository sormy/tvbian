# TODO

What spans families lives here. An item that needs its own page gets one beside this file, listed
below.

## Open

- [ ] **Every board: the tree's `model` as `Box (Silkscreen Date)`**, in `board.patch` and
      `uboot.patch` alike, built from `BOARD_NAME`, `BOARD_PCB` and `BOARD_DATE`:
      `H96 Max 3518 (3518_ZX_V01 2025-08-18)`, not `H96 Max 3518 3518_ZX_V01`; the date left out
      where the PCB shows none. `BOARD_DATE` is set only on the Tanix TX1 V2.0 today; the 3518's
      (`20250818`) and the 3518D's (`20250401`) are in their docs, the M20's and R69's to be read
      off the PCB photos.

- [ ] **Every board: `dtb.md` beside the patch it explains**, from `docs/<board>/` to
      `boards/<board>/`, and its links followed.

- [ ] **Every board: answer the TV's CEC queries.** The TV asks for the box's power status and gets
      `FEATURE_ABORT`: nothing on the box speaks CEC's follower side. The TV's remote reaches the
      box.

- [ ] **The BLE remote wakes every box from sleep.** Today only IR does; it matters most where there
      is no IR receiver.

- [ ] **A `tools/validate/` test shows decoded AFBC and scaled frames on a plane**, unattended.

- [ ] **Blu-ray 3D plays in 3D on a 3D TV.** Today only its 2D view.

- [ ] **FFmpeg, Kodi and Fuseamp install as `tvb-*` packages**, Fuseamp once it is ready for
      release.

- [ ] **A new kernel or driver is shown not to regress, unattended, on every board it ships to**,
      before it ships.

- [ ] **Every board: the recovery button sends `KEY_VENDOR`.** Mainline's code for a "recovery",
      "update" or "maskrom" button; the Tanix TX1 V2.0 and the H96 Max M2 Plus have it. The others
      keep their factory trees' codes: the R69 and H96 Max 3518 `KEY_VOLUMEUP`, the H96 Max 3518D
      `KEY_F11`. Each change says why in its `board.patch`, and a press under
      `evtest /dev/input/recovery-button` checks it.

- [ ] **Consider: a browser decodes video in hardware.** Debian's Chromium bundles its own FFmpeg
      and Google Chrome links none, so both decode in software here. Firefox loads the system's
      FFmpeg, ours, at run time; else a Chromium built with its V4L2 decoders.

- [ ] **Consider: the console fits each screen plugged after the first.** The kernel's console is
      one framebuffer, sized by the first screen and cloned to every output, so a larger screen
      plugged later shows it small. A userspace console (kmscon) redraws per screen on hot-plug.

- [ ] **Every board: which recovery button it has.** Most boxes expose a U-Boot recovery button, a
      key the bootloader reads and Linux sees, not the SoC's maskrom or FEL strap, which is rarely
      wired out. Each board's README row and `board.md` name it: "Recovery button (U-Boot)", or "→
      Maskrom" where holding it reaches the boot ROM, shown by the boot ROM's USB device.

- [ ] **Every board without an SD slot: our U-Boot boots a USB disk first when one is in**, as an SD
      card does on the boards that have one. A failed update is then undone by plugging in a stick,
      with no hidden button to find. Rockchip's part is in `docs/todo/rk35xx-uboot-usb.md`; on an
      Allwinner board it is the U-Boot conf's `BOOT_PREBOOT`, done on the Tanix.

- [ ] **Every board: a recovery button with no other use picks the fallback in our U-Boot.** Held at
      power-on: the previous kernel (u-boot-menu's second entry, the one Debian keeps). Held longer:
      U-Boot's boot menu on HDMI, for a USB keyboard. On a board without an SD slot a USB disk needs
      no button: it boots first whenever one is in. Never Android's recovery, which our images do
      not have. The Tanix TX1 V2.0's PH9 was built once this way.

- [ ] **Every board: built outputs made by the build, not committed.** The repo keeps the inputs
      (`factory_*`, `*.patch`) and builds the rest: factory tree → `.dts` → patch → `board.dts` →
      `board.dtb`, and the same for `uboot.dts`, `maskrom_loader.bin` and `fel_loader.bin`. Today
      those outputs are committed beside their inputs, and can drift from them.

- [ ] **Rename `rk35xx` to `rockchip`:** the kernel conf, fragment and packages
      (`linux-image-tvb-rk35xx`, its `-next`), `BOARD_KERNEL`, and `BOARD_FAMILY` split off as its
      own SoC key (`meson-gxl`, `sunxi-h616` beside the kernel's `meson64`, `sunxi64`), the
      `rk35xx-` todo prefix. Installed boxes need the new packages to `Replace` and `Break` the old,
      which the release guard checks.

- [ ] **Docs: user guides apart from developer docs.** The guides a user follows (install, back up,
      restore, first login, the service modes) beside the bring-up, build and reference docs today,
      in one `docs/`. Split them, by folder or by name, so a user never lands in a worklog.

- [ ] **Docs: the cross-references out.** `AGENTS.md` now has docs stand alone; the reference docs
      still name others, the board docs up to five. Each goes: the fact stated where it is needed,
      or the reference dropped.

- [ ] **Docs: the family READMEs, one structure.** The same sections in the same order, each install
      route with its commands: only `README_ROCKCHIP.md` spells out the OTG install today;
      `README_AMLOGIC.md` and `README_ALLWINNER.md` defer or leave steps out.

- [ ] **`tools/dtcx/bases/`: out of `tools/`.** Each `.conf` describes a kernel's or a U-Boot's
      trees, headers and vendor properties: data beside what it describes, not tool code. The
      boards' `BOARD_*_DTB_SOURCE` and `_TARGET` name them.

- [ ] **`./build.sh kernel`: a test kernel under its own release name**, installed beside the
      known-good one so the boot menu keeps a fallback. Kbuild appends `LOCALVERSION` from the
      environment; `run` does not pass it into the container, and the driver packages must follow
      the new release.

- [ ] **`patches/linux-sunxi/`: folders by subsystem.** 255 patches in one list, ours squeezed into
      the gaps of LibreELEC's numbering, `0099` against its `0100`. Split by the files a patch
      touches into `soc/`, `mmc/`, `sound/`, `drm/`, `media/`, `dts/`, numbered per folder, applied
      in that order, a patch spanning two in the later. Origin goes in each folder's README. A
      move-only commit: the patched tree byte-identical before and after.

- [ ] **Every board's Test report has a row for every check, by name**, so a line never run shows.

- [ ] **An AI review on every pull request, against `AGENTS.md`.** A fork PR runs without our
      secrets, so a GitHub App fits: CodeRabbit's open-source plan, free for a public repo and
      rate-limited per developer, pointed at `AGENTS.md`. Gemini Code Assist's free GitHub app is
      reported shut down in July 2026. To think about: the Claude Code action, automatic on the
      maintainer's own PRs and on anyone else's only when the maintainer invokes it by comment,
      since a comment from a maintainer runs with the repo's token and a fork PR does not. ❓
      CodeRabbit's current limits, and the file it reads guidelines from.

- [ ] **The repo restructure.** Folders named for what they hold, every patch in `patches/`, docs
      current or in `research/`: `docs/todo/repo-layout.md`.

- [ ] **`tvb-install`, a first real install.** `boards/common/tvb-install` has reached its prompt on
      the 3518, never past it: the 3518 from its SD to the eMMC, keeping `DVKR`/`SSKR`; the M20
      image from a stick to the eMMC, then back from the eMMC to a stick. Together they test phases
      4 and 5.
- [ ] **Low priority: `tvb-firstlogin`, the first-login wizard.** Until then, `docs/first-login.md`
      gives the commands. Runs once, from `/etc/profile.d/`, at root's first interactive login; Esc
      skips a step; `/var/lib/tvb/firstlogin.done` marks it finished, so an interrupted run starts
      again:
  - a user: `adduser`, added to `sudo`;
  - the timezone: `timedatectl list-timezones` through `fzf`;
  - the locale: `SUPPORTED`'s UTF-8 lines through `fzf`, then `locale-gen`;
  - Wi-Fi, where a Wi-Fi device exists: `nmcli device wifi list` through `fzf`, then
    `nmcli --ask device wifi connect`.
- [ ] **A USB keyboard's keymap on `tty1`:** `console-setup` in the image and a README line, or US
      only.
- [ ] **BTF:** dropped with debug info by `CONFIG_DEBUG_INFO_NONE`, or kept for BPF tools at the
      cost of runner disk.
- [ ] **Gate a kernel that moved** on the validation script passing on one box of its family, or
      keep publishing it automatically.
- [ ] **Sealed TVBian:** image-based A/B updates, an option for any flavour, plain or Kodi. Levels:
      a read-only root, a volatile root, then A/B with `systemd-sysupdate`, two roots plus a data
      partition and a fallback at boot.

- [ ] **`tools/validate/`: one script a component, one runner.** `validate.sh` becomes components
      beside `video.py` (boot, watchdog, Wi-Fi and Bluetooth, storage, USB, HDMI and CEC, audio,
      input, sleep and wake, thermal), each case tied to a line of `docs/bring-up/`'s checks, all on
      `video.py`'s host and box split: JSON out, `report`, `matrix` for a board's `board.md`,
      `compare` as the regression check.

- [ ] **Unattended board enrollment: the goal.** A new box brought up with as few human actions as
      possible: the factory evidence harvested before the wipe, an image matched, bring-up driven
      over serial, and each subsystem proven by an automated check: display, video, audio, Wi-Fi,
      Bluetooth and its remote, input, power, storage.

## Bigger todos

| File                            | Open question                               |
| ------------------------------- | ------------------------------------------- |
| `docs/todo/video.md`            | hardware video: what is left, every SoC     |
| `docs/todo/media-stick.md`      | the universal media stick                   |
| `docs/todo/kodi.md`             | Kodi 22 on our FFmpeg, built on trixie      |
| `docs/todo/extras-upstream.md`  | extras built from an upstream release       |
| `docs/todo/rk35xx.md`           | Rockchip boards, every one                  |
| `docs/todo/rk35xx-boot-log.md`  | boot log cleanup                            |
| `docs/todo/rk35xx-uboot-usb.md` | USB in our U-Boot                           |
| `docs/todo/allwinner.md`        | Allwinner boards, every one                 |
| `docs/todo/amlogic.md`          | Amlogic boards, every one                   |
| `docs/todo/tanix-tx1-v2.md`     | the Tanix TX1 V2.0: what is left            |
| `docs/todo/h96max-m20.md`       | the H96 Max M20: what is left               |
| `docs/todo/h96max-m2-plus.md`   | the H96 Max M2 Plus: what is left           |
| `docs/todo/swt6621s.md`         | the SWT6621S Wi-Fi/BT: what is left         |
| `docs/todo/website.md`          | tvbian.com: one page on GitHub Pages        |
| `docs/todo/repo-layout.md`      | folders, patches, tools and docs, regrouped |
