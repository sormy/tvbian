# Stock dump

The factory firmware is the board's specification, and the only reference once the box is gone.

## Do

1. **From a shell on stock**, serial, `adb` or `ssh`: a dump carved from the image has no `dmesg` or
   `getprop`. Text files and small binaries fit serial, each `gzip | base64` on the console and its
   SHA-256 checked on the host, a 1 MiB file in about two minutes at 115200.
2. **`stock/<board>/`**:

   | File                                                     | What                                  |
   | -------------------------------------------------------- | ------------------------------------- |
   | `README.md`                                              | how and when; the identity table      |
   | the bootloader stages                                    | idbloader or BL2, TEE/trust, U-Boot   |
   | `board-runtime.dtb`                                      | the tree after U-Boot edited it       |
   | `firmware/`                                              | every chip's and SoC block's firmware |
   | `boot.log`, `dmesg.txt`, `cmdline.txt`                   | the boot, from power-on               |
   | `getprop.txt`, `kernel-config.txt`                       | the build                             |
   | `cpuinfo.txt`, `meminfo.txt`, `iomem.txt`                | the SoC and its memory                |
   | `partitions.txt`, `gpt.bin`, `emmc-identity.txt`         | the eMMC                              |
   | `lsmod.txt`                                              | the vendor's drivers                  |
   | `gpio.txt`, `pinmux.txt`, `regulators.txt`, `clocks.txt` | the wiring state                      |
   | `cpufreq.txt`, `thermal.txt`                             | the factory OPPs and trip points      |
   | `input-devices.txt`, `leds.txt`                          | buttons, remote, LEDs                 |
   | `iw-list.txt`                                            | the Wi-Fi's modes, bands and rates    |

   The README's identity table: product properties, build, kernel version, the SoC's own ID,
   silkscreen.

3. **The factory trees** → `boards/<board>/factory_board.dtb`, and `factory_uboot.dtb` where we
   build U-Boot from it: carved from the image at the `d00dfeed` magic in the boot partition, the
   size in the next four bytes.
4. **The bases**: vendor or mainline and the version of the kernel and U-Boot, from the boot banner,
   `/proc/version` and the binaries' strings, set the `_DTB_SOURCE` bases in `tools/dtcx/bases/`. A
   base's source is the SoC vendor's own repository where it publishes one; else the base says which
   it uses and why. A missing base is written, never routed around.
5. **What differs per unit**, from stock's boot log and runtime tree: RAM size and ranks, the eMMC's
   mode, clock and tuning, the SoC's bin. Each is detected at boot by our loaders, never built in.
6. **The vendor's own matrices**: every codec, profile, depth and largest size from the datasheet or
   user manual, and stock's IR keymaps (factory tree, `usr/keylayout/` on the vendor partition).

## Bites

- **Never take a tree from `/proc/device-tree`**: U-Boot has edited it, even the SoC's `compatible`.
- **The proof a base decodes the blob is not provenance**: never claim the factory tree came from
  the base's source.
- **Odd RAM sizes are known trouble** (1.5 GB, 3 GB): search the DRAM blob's values (`para1`,
  `para2`, `tpr13`) and the size against public reports before the first boot.
- **Kept out of the repo**, `backup/` alone holding them: the per-unit window, DRM and attestation
  keys, secure storage, Wi-Fi credentials, anything naming the owner, a traceable MAC.

## Check

- [ ] **D1** `stock/<board>/` has every file above
- [ ] **D2** Its README's identity table is filled
- [ ] **D3** The factory trees are carved from the image
- [ ] **D4** Nothing kept out is in the repo
- [ ] **D5** The `_SOURCE` bases are named, with versions and their source
- [ ] **D6** The per-unit values are listed in `board.md`, each with how it is detected
- [ ] **D7** The vendor's codec matrix and stock's IR keymaps are recorded
