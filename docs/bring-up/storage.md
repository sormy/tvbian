# Storage

## Do

1. `fio`, fixed so every board compares, in decimal MB/s:

   ```sh
   fio --name=seq  --filename=<file> --rw=read|write         --bs=1M --size=1G   \
       --direct=1 --ioengine=libaio --iodepth=8  --numjobs=1 --runtime=30 --time_based
   fio --name=rand --filename=<file> --rw=randread|randwrite --bs=4k --size=512M \
       --direct=1 --ioengine=libaio --iodepth=32 --numjobs=1 --runtime=30 --time_based
   ```

2. The install cycle, in order: external media and `tvb-install`, or the service mode where the box
   boots none; the eMMC; the service mode on our U-Boot. A new family's also: a write over it, read
   back identical; a full write that boots shows the same, at more risk. Within a family the
   family's proof stands.

## Bites

- **Mainline's eMMC defaults are not stock's**: read stock's boot log and runtime tree for the mode,
  clock and tuning first.
- **An intermittent storage fault needs a count, not a boot**: N boots under stress, errors per boot
  from the serial log. Stress the path that fails: a write hang is not found by a read stress.

- **The service mode on our U-Boot is mandatory on a slotless board**: replacing the factory U-Boot
  can remove the route that reached it.
- **A capability measured before a boot stage was replaced** says nothing after it: re-measure.

## Check

- [ ] **M1** The eMMC under `fio`
- [ ] **M2** The SD card under `fio`
- [ ] **M3** 👤 SD hotplug, in and out
- [ ] **M4** Every speed mode kept survives warm reboots
- [ ] **M5** `tvb-install` puts the image on the eMMC, where the box boots external media
- [ ] **M6** It boots from the eMMC on its own loaders
- [ ] **M7** The per-unit window is byte-identical to the backup
- [ ] **M8** 👤 The service mode enters on our U-Boot
- [ ] **M9** A new family's: it loads the family's loader and reports the eMMC's true size
- [ ] **M10** A new family's: over it, a write reads back identical, or a full write boots
