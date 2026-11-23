# System

The validation files, `system.md` to `input.md`, run on the family's kernel and on its `-next`, the
Test report marking each side by side; a number that differs between them is a finding.

## Do

1. Boot twice, measure the second: the first resizes and runs first-boot setup.
2. Account for `dmesg` line by line: every noisy line is a fault or a wrong level, often in an
   out-of-tree driver. Judge a line by what it says, not its level; demoting it hides it.
3. Ten warm reboots, every device checked after each: an MMC controller can fail its first init
   after a warm reboot.
4. RAM under load and its bandwidth, `stress-ng --stream 1`, then `4`, read and write against a
   sibling family's; then the watchdog's two traps, a forced panic, and a real hang: the box resets
   itself each time. It is what every later phase relies on to run unattended.
5. **Clocks and rails, against stock's**: the CPU's and the GPU's ladders, each rate at the voltage
   stock runs it at on this chip, the chip's bin or speed grade as the stock log names it; the GPU's
   bus clock; DDR's ladder; the logic and GPU rails. Then scaling seen, not read: under load each
   reaches its top rate and voltage, idle each falls back, and a block that suspends parks at its
   lowest rate first. A clock or rail short of stock's is a gap in the todo, not a choice.
6. **Heat**: CPU stress, then CPU and GPU together, against the trip points: the GPU shares the
   CPU's rail and heat sink on some SoCs, and a box ran 81 °C on CPU stress and 93 °C with the GPU
   beside it. A stick, or a box with a small heat sink, also gets a combined soak, CPU, GPU, a 4K
   decode, Wi-Fi and eMMC traffic at once for 30 minutes, every thermal zone logged. Where it
   throttles or errs, its trip points, OPPs and the eMMC, DRAM and Wi-Fi settings are tuned for it,
   each change measured.

## Bites

- **A vendor's OPP table is not mainline's**: `opp-supported-hw` numbers speed grades per driver. On
  the H616, SID `0x5c00` is stock's bit 2 and mainline's bin 4; the factory's masks passed through
  ran another grade's rows, 50–70 mV under stock and a step above it. Compare the booted ladder with
  stock's, never the table with the factory's.
- **The reference is the stock firmware, not a vendor kernel**: our vendor 6.12 applies no PVTM bin
  and runs every RK3528 chip at the table's default, below stock's voltage for the low bins. The
  stock log names the bin (`pvtm-volt-sel`) and its clock dump the rates.
- **A clock changed with its power domain off can reset the box**: lima's devfreq left the RK3528's
  GPU at 800 MHz as its domain powered down, and the box reset within 30 s. The OPP table's
  `opp-suspend` row parks it first, and devfreq leaves a suspended device's rate to its resume: a
  `min_freq` written to an idle GPU did the same. A box that resets only once a driver idles, or on
  a rate pinned from sysfs, is checked for both.
- **A boot that grew** is the cheapest signal: a unit waiting on absent hardware, a getty on a
  missing tty, DHCP on an unplugged port.
- **A watchdog has two known traps**: counting through system sleep (`power.md`), and a timeout set
  above the hardware's maximum that fires early or never. To prove it resets: release it from
  systemd (`RuntimeWatchdogUSec` 0 over D-Bus), open it at the set timeout from a script, ping once,
  go quiet. `kill -STOP 1` does nothing, and real-time busy loops are capped.
- **The watchdog proves PID 1 runs, not the box**: a CPU stuck on a bus read leaves systemd pinging
  from another, and the box stays hung, as the M20 did through eight hangs. The kernel's soft and
  hard lockup detectors panic on it; the panic stops the pings, and the panic timeout or the
  watchdog resets the box. Its timeout outlasts a reboot cycle: shutdown, the loader and the boot up
  to systemd.
- **A real hang is `modprobe test_lockup`**, the kernel's own: `disable_preempt=1`, `disable_irq=1`,
  `all_cpus=1`. The RCU stall timeout stays above the soft-lockup threshold.
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
- [ ] **S5** The boot shows on HDMI from the kernel's first lines; before them, only where our
      U-Boot drives the display
- [ ] **S6** `dmesg` accounted for line by line; tolerated lines named in `board.md`
- [ ] **S7** `systemd-analyze blame` explains every second
- [ ] **S8** The second boot is at or under the recorded time
- [ ] **S9** `/usr/lib/tvb/board-{id,name,pcb}` are right
- [ ] **S10** Every `tvb-*-modules` module is loaded
- [ ] **S11** Ten warm reboots, every device working after each
- [ ] **S12** `free -m` is the advertised RAM
- [ ] **S13** `stress-ng --vm --verify` over most of RAM is clean
- [ ] **S14** `journalctl -b | grep "Watchdog running with"` shows the largest timeout its clock
      allows
- [ ] **S15** Pings stopped, the box resets at the set timeout: not at the maximum, not never
- [ ] **S16** A forced panic reboots the box, the oops in `/sys/fs/pstore/`
- [ ] **S17** No userspace service sets an address or attaches a device
- [ ] **S18** The image adds nothing beyond `tvb-base`, the board's packages and their depends
- [ ] **S19** The ladder is stock's: `scaling_available_frequencies` as the dump's `cpufreq.txt`,
      and `vdd-cpu`'s voltage at each step as the factory row stock selects
- [ ] **S20** 5 minutes of 4-core `stress-ng` stays under the trip points, not throttled
- [ ] **S28** 5 minutes of 4-core `stress-ng` beside the GPU at its top rate stays under the trip
      points, `--verify` clean
- [ ] **S21** A stick or small heat sink: the 30-minute combined soak, no throttling, no eMMC, DRAM
      or Wi-Fi error
- [ ] **S22** A CPU stuck on a hung bus read: a lockup panic, the box back by itself
- [ ] **S23** RAM type, clock and bandwidth on one core and four are in `board.md` and the family
      README's Memory table
- [ ] **S24** The chip's PVTM bin or speed grade is the one the stock log names
- [ ] **S25** The GPU's ladder is stock's, each rate at the voltage stock's bin selects, and its bus
      clock at stock's rate
- [ ] **S26** DDR's ladder, and the logic and GPU rails' voltage at each step, are stock's
- [ ] **S27** Scaling, seen: under load the CPU and GPU reach their top rate and voltage, idle they
      return, and the GPU suspends at its lowest rate (`trans_stat`), no driver error
