# Backup and a way back

Nothing on the box is written before its whole eMMC is off it and a way back is proven.

## Do

1. **The DRAM-init blob first**, it feeds every service-mode loader:
   - Rockchip: the idbloader, sector 64 for 4096 sectors → `boards/<board>/factory_idbloader.bin`.
     Our loader is built from it, so the first read is through the factory Loader, the one use it is
     fit for: 2 MiB, under its silent 32 MB read cap, twice and identical, a valid IDB header and
     DDR entry. Then our loader, uploaded over Maskrom, reads the same block: identical means it
     reads true, and the full backup rests on it. Its writes are proven later, a write read back
     (`storage.md`);
   - Allwinner: boot0, sector 16 for 128 → `boards/<board>/factory_boot0.bin`, before the first FEL
     read: the FEL loader's DRAM settings come from it;
   - Amlogic: none, the factory U-Boot serves the burning mode itself.
2. **The full image** → `backup/<board>-stock.img.xz`, its size `/sys/block/<dev>/size` × 512.
   Routes, best first: a root shell on serial, the image streamed over the network (`dd | nc`,
   `ssh`), never over serial; the USB service mode, once it has a loader with this board's DRAM
   settings; `adb`, where Android allows it.
3. **What an install never writes**, into the family's `boards/common/preserve-sectors.<family>`,
   one block a line with its note: the unit's MAC, serial and keys (Rockchip: `DVKR` at sector 7168,
   `SSKR` at 8192), the factory DRAM-init stage, and every region TVBian does not use. Never written
   to the eMMC, never shipped.
4. **The way back**: over the service mode, read the first sectors back and compare with the image.
   Each family's service-mode procedure has its own doc, listed in `AGENTS.md`'s index.
5. **Every recovery gesture stock knows**, buttons and remote keys alike, read from the dump into
   `board.md`'s Recovery section, and tried on stock before anything overwrites it.

## Bites

- **A loader's DRAM settings are this board's**, read from its own factory blob, never a sibling's:
  the Tanix TX1's two PCBs differ in four of eight. A wrong DDR blob on the eMMC is unrecoverable
  short of shorting an eMMC line; erasing sector 64 is recoverable.
- **The preserve list keeps the eMMC's DRAM init, not only the unit's keys.** A boot from a card or
  stick never runs the DRAM init an install would write (Rockchip and Amlogic start from the eMMC's
  own, Allwinner from the card's), so an image for a sibling board passes that test and bricks the
  box at its first eMMC boot; boxes sold under shared names make that the expected mistake. What an
  install never writes, it cannot get wrong. Left: a unit whose own SPL cannot load our U-Boot stays
  on that SPL, `ctrl+b` its way back where it has one.
- **A stock chain that cannot run ours is replaced, DRAM init and all.** We build arm64 only, so
  where stock hands off to an AArch32 U-Boot, as Allwinner's does, the install writes our SPL in its
  place. That family's way back must then be the BootROM's own, FEL, not a stage we overwrite.
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
- [ ] **B4** `preserve-sectors` covers the per-unit window, the DRAM-init stage and every unused
      region
- [ ] **B5** The factory DRAM-init blob is carved
- [ ] **B6** Stock's recovery gestures are in `board.md`, each tried on stock
