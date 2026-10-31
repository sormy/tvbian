# System

The validation files, `system.md` to `input.md`, run on the family's kernel and on its `-next`, the
Test report marking each side by side; a number that differs between them is a finding.

## Do

1. Boot twice, measure the second: the first resizes and runs first-boot setup.
2. Account for `dmesg` line by line: every noisy line is a fault or a wrong level, often in an
   out-of-tree driver. Judge a line by what it says, not its level; demoting it hides it.
3. Ten warm reboots and ten power cycles, every device checked after each: an MMC controller can
   fail its first init after a warm reboot.
4. RAM under load, then the watchdog's two traps, then a forced panic.
5. **Heat**: the factory OPP table, then CPU stress against the trip points. A stick, or a box with
   a small heat sink, also gets a combined soak, CPU, GPU, a 4K decode, Wi-Fi and eMMC traffic at
   once for 30 minutes, every thermal zone logged. Where it throttles or errs, its trip points, OPPs
   and the eMMC, DRAM and Wi-Fi settings are tuned for it, each change measured.

## Bites

- **A boot that grew** is the cheapest signal: a unit waiting on absent hardware, a getty on a
  missing tty, DHCP on an unplugged port.
- **A watchdog has two known traps**: counting through system sleep (`power.md`), and a timeout set
  above the hardware's maximum that fires early or never. To prove it resets: release it from
  systemd (`RuntimeWatchdogUSec` 0 over D-Bus), open it at the set timeout from a script, ping once,
  go quiet. `kill -STOP 1` does nothing, and real-time busy loops are capped.
- **A panic must reboot the box**, and leave its record: `echo c > /proc/sysrq-trigger`, the box
  back on its own, the oops in `/sys/fs/pstore/`, archived by systemd to `/var/lib/systemd/pstore/`.
  The watchdog's reset keeps ramoops; a power cycle loses it. A region that faults is a RAM finding
  first.

- **No userspace bring-up**: no MAC-pinning service, no `hciattach`; a small kernel patch, so `hci0`
  and the addresses exist when the driver probes.
- **A lean image**, close to minimal Debian, and no user preference: a `video=` pin for one monitor
  caps every 4K TV. GitHub caps a release file's size.
- **Heat shows as errors before it shows as throttling**: eMMC CRC errors, Wi-Fi drops, a DRAM fault
  under load. A soak counts them, not only the clock.

## Check

- [ ] **S1** Comes up on the network with no serial attached
- [ ] **S2** U-Boot prints on serial
- [ ] **S3** The kernel prints on serial
- [ ] **S4** A login on serial
- [ ] **S5** The boot on HDMI, as early as it gets
- [ ] **S6** `dmesg` accounted for line by line; tolerated lines named in `board.md`
- [ ] **S7** `systemd-analyze blame` explains every second
- [ ] **S8** The second boot is at or under the recorded time
- [ ] **S9** `/usr/lib/tvb/board-{id,name,pcb}` are right
- [ ] **S10** Every `tvb-*-modules` module is loaded
- [ ] **S11** Ten warm reboots, every device working after each
- [ ] **S12** Ten power cycles, every device working after each
- [ ] **S13** `free -m` is the advertised RAM
- [ ] **S14** `stress-ng --vm --verify` over most of RAM is clean
- [ ] **S15** `journalctl -b | grep "Watchdog running with"` shows the largest timeout its clock
      allows
- [ ] **S16** Pings stopped, the box resets at the set timeout: not at the maximum, not never
- [ ] **S17** A forced panic reboots the box, the oops in `/sys/fs/pstore/`
- [ ] **S18** No userspace service sets an address or attaches a device
- [ ] **S19** The image adds nothing beyond `tvb-base`, the board's packages and their depends
- [ ] **S20** `scaling_available_frequencies` is the factory OPP table
- [ ] **S21** 5 minutes of 4-core `stress-ng` stays under the trip points, not throttled
- [ ] **S22** A stick or small heat sink: the 30-minute combined soak, no throttling, no eMMC, DRAM
      or Wi-Fi error
