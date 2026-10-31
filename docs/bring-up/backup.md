# Backup and a way back

Nothing on the box is written before its whole eMMC is off it and a way back is proven.

## Do

1. **The DRAM-init blob first**, it feeds every service-mode loader:
   - Rockchip: the idbloader, sector 64 for 4096 sectors → `boards/<board>/factory_idbloader.bin`;
   - Allwinner: boot0, sector 16 for 128 → `boards/<board>/factory_boot0.bin`, before the first FEL
     read: the FEL loader's DRAM settings come from it;
   - Amlogic: none, the factory U-Boot serves the burning mode itself.
2. **The full image** → `backup/<board>-stock.img.xz`, its size `/sys/block/<dev>/size` × 512.
   Routes, best first: a root shell on serial, the image streamed over the network (`dd | nc`,
   `ssh`), never over serial; the USB service mode, once it has a loader with this board's DRAM
   settings; `adb`, where Android allows it.
3. **The per-unit window**, the unit's MAC, serial and keys (Rockchip: `DVKR` at sector 7168, `SSKR`
   at 8192), into `boards/<board>/preserve-sectors`: never written, never shipped.
4. **The way back**: over the service mode, read the first sectors back and compare with the image.
   Each family's service-mode procedure has its own doc, listed in `AGENTS.md`'s index.
5. **Every recovery gesture stock knows**, buttons and remote keys alike, read from the dump into
   `board.md`'s Recovery section, and tried on stock before anything overwrites it.

## Bites

- **A loader's DRAM settings are this board's**, read from its own factory blob, never a sibling's:
  the Tanix TX1's two PCBs differ in four of eight. A wrong DDR blob on the eMMC is unrecoverable
  short of shorting an eMMC line; erasing sector 64 is recoverable.
- **macOS mounts and writes** every FAT partition a service mode exposes as a disk (`.fseventsd`):
  unmount it at once. Raw reads and writes run as one `sudo` command; with no terminal, `sudo -A`
  with an `osascript` askpass. On macOS, `/dev/diskNsM` takes small writes where `/dev/rdiskNsM`
  fails.
- **A route without `sudo` beats one with it**: fastboot to write and DFU to read run from user
  space; a mass-storage mode asks the human for a password on every attach.

## Check

- [ ] **B1** The backup is off the box
- [ ] **B2** Its size matches the eMMC's
- [ ] **B3** 👤 A read over the service mode matches it
- [ ] **B4** `preserve-sectors` covers the per-unit window
- [ ] **B5** The factory DRAM-init blob is carved
- [ ] **B6** Stock's recovery gestures are in `board.md`, each tried on stock
