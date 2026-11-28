# System

The validation files, `system.md` to `input.md`, run on the family's kernel and on its `-next`, the
Test report marking each side by side; a number that differs between them is a finding.

## Do

1. Boot twice, measure the second: the first resizes and runs first-boot setup.
2. Account for `dmesg` line by line: every noisy line is a fault or a wrong level, often in an
   out-of-tree driver. Judge a line by what it says, not its level; demoting it hides it.
3. Ten warm reboots, every device checked after each: an MMC controller can fail its first init
   after a warm reboot.
4. RAM under load, and its read and write bandwidth with `stress-ng --stream 1`, then `4`, against a
   sibling family's. Then the watchdog's two traps, a forced panic and a real hang: the box must
   reset itself each time, because every later phase relies on that to run unattended.
5. **Clocks and rails, against stock's**:
   - the CPU's and GPU's ladders, each rate at the voltage stock uses on this chip;
   - the chip's bin or speed grade, as the stock log names it;
   - the GPU's bus clock, DDR's ladder, and the logic and GPU rails.

   Then watch the scaling happen rather than reading the tables: under load each clock reaches its
   top rate and voltage, idle it falls back, and a block that suspends parks at its lowest rate
   first. A clock or rail below stock's is a gap for the todo page, not a choice.

6. **Heat**: CPU stress, then CPU and GPU together, against the trip points. On some SoCs the GPU
   shares the CPU's rail and heat sink: one box ran 81 °C on CPU stress and 93 °C with the GPU
   added. A stick, or a box with a small heat sink, also gets a 30-minute combined soak (CPU, GPU, a
   4K decode, Wi-Fi and eMMC traffic at once) with every thermal zone logged. Where it throttles or
   shows errors, tune its trip points, OPPs and eMMC, DRAM and Wi-Fi settings, measuring each
   change.

## Bites

- **A vendor's OPP table is not mainline's**: each driver numbers its speed grades in
  `opp-supported-hw` its own way. On the H616, SID `0x5c00` is stock's bit 2 but mainline's bin 4,
  so the factory's masks, copied as they were, ran another grade's rows: 50–70 mV below stock and a
  step higher. Compare the booted ladder with stock's, never the table with the factory's.
- **The reference is the stock firmware, not a vendor kernel**: our vendor 6.12 applies no PVTM bin
  and runs every RK3528 chip at the table's default, below stock's voltage for the low bins. The
  stock log names the bin (`pvtm-volt-sel`) and its clock dump the rates.
- **A clock changed with its power domain off can reset the box**: lima's devfreq left the RK3528's
  GPU at 800 MHz as its domain powered down, and the box reset within 30 s. A `min_freq` written to
  an idle GPU did the same. Two fixes cover it: the OPP table's `opp-suspend` row parks the clock
  before the domain goes down, and devfreq leaves a suspended device's rate until it resumes. If a
  box resets only once a driver goes idle, or after a rate is pinned from sysfs, check both.
- **A DDR rate change can hang the SoC**: on the RK3528 it did, on the vendor kernel and mainline
  alike, both under a second apart and with seconds between changes. Stock never changes the DDR
  rate by load, and neither do we.
- **A boot that grew** is the cheapest signal: a unit waiting on absent hardware, a getty on a
  missing tty, DHCP on an unplugged port.
- **A watchdog has two known traps**: it may count through system sleep (`power.md`), and a timeout
  set above the hardware's maximum fires early or never. To prove it resets the box, take it from
  systemd (`RuntimeWatchdogUSec` 0 over D-Bus), open it from a script at the set timeout, ping once,
  then stop. Stopping PID 1 with `kill -STOP 1` proves nothing, and real-time busy loops are capped
  by the kernel.
- **The watchdog proves PID 1 runs, not the box**: when one CPU is stuck on a bus read, systemd
  keeps pinging from another and the box stays hung; the M20 did this through eight hangs. The
  kernel's soft and hard lockup detectors turn that into a panic, the panic stops the pings, and the
  panic timeout or the watchdog resets the box. The watchdog's timeout must outlast a whole reboot:
  shutdown, the loader, and the boot up to systemd.
- **A real hang is `modprobe test_lockup`**, the kernel's own: `disable_preempt=1`, `disable_irq=1`,
  `all_cpus=1`. The RCU stall timeout stays above the soft-lockup threshold.
- **A panic must reboot the box and leave a record**: after `echo c > /proc/sysrq-trigger` the box
  comes back on its own, with the oops in `/sys/fs/pstore/`, which systemd archives to
  `/var/lib/systemd/pstore/`. A watchdog reset keeps the ramoops region; a power cycle loses it. If
  the region itself faults, suspect the RAM first.

- **No userspace bring-up**: no MAC-pinning service and no `hciattach`. A small kernel patch does it
  instead, so `hci0` and the addresses exist as soon as the driver probes.
- **A lean image**, close to minimal Debian; GitHub caps a release file's size.
- **No user preferences in the image**: a `video=` pin for one monitor caps every 4K TV.
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
- [ ] **S8** The second boot is at or under the recorded time (`boot.seconds`)
- [ ] **S9** `/usr/lib/tvb/board-{id,name,pcb}` are right (`identity.id`, `identity.name`,
      `identity.pcb`)
- [ ] **S10** Every `tvb-*-modules` module is loaded
- [ ] **S11** Ten warm reboots, every device working after each (`reboot.<n>`)
- [ ] **S12** `free -m` is the advertised RAM
- [ ] **S13** `stress-ng --vm --verify` over most of RAM is clean
- [ ] **S14** `journalctl -b | grep "Watchdog running with"` shows the largest timeout its clock
      allows
- [ ] **S15** Pings stopped, the box resets at the set timeout: not at the maximum, not never
      (`recovery.watchdog`)
- [ ] **S16** A forced panic reboots the box, the oops in `/sys/fs/pstore/` (`recovery.panic`)
- [ ] **S17** No userspace service sets an address or attaches a device (`addresses.assigned`)
- [ ] **S18** The image adds nothing beyond `tvb-base`, the board's packages and their depends
- [ ] **S19** The ladder is stock's: `scaling_available_frequencies` as the dump's `cpufreq.txt`,
      and `vdd-cpu`'s voltage at each step as the factory row stock selects
- [ ] **S20** 5 minutes of 4-core `stress-ng` stays under the trip points, not throttled
- [ ] **S28** 5 minutes of 4-core `stress-ng` beside the GPU at its top rate stays under the trip
      points, `--verify` clean
- [ ] **S21** A stick or small heat sink: the 30-minute combined soak, no throttling, no eMMC, DRAM
      or Wi-Fi error (`soak.c`, `soak.warnings`)
- [ ] **S22** A CPU stuck on a hung bus read: a lockup panic, the box back by itself
- [ ] **S23** RAM type, clock and bandwidth on one core and four are in `board.md` and the family
      README's Memory table
- [ ] **S24** The chip's PVTM bin or speed grade is the one the stock log names (`pvtm.cpu`,
      `pvtm.gpu`)
- [ ] **S25** The GPU's ladder is stock's, each rate at the voltage stock's bin selects, and its bus
      clock at stock's rate (`gpu.ladder`)
- [ ] **S26** DDR's ladder, and the logic and GPU rails' voltage at each step, are stock's
      (`ddr.rate`, `ddr.governor`)
- [ ] **S27** Scaling, seen: under load the CPU and GPU reach their top rate and voltage, idle they
      return, and the GPU suspends at its lowest rate (`trans_stat`), no driver error
- [ ] **S29** DDR's rate held as stock holds it, never scaled by polled load (`ddr.governor`)
- [ ] **S30** Every option in the SoC's datasheet is listed as working or not, and the list matches
      the datasheet and the board's `board.md` (`probe.py`)
- [ ] **S31** No display manager starts at boot (`units.autostart`); one would take the screen from
      the display checks mid-run
- [ ] **S32** Each crypto algorithm an engine serves passes its self-test (`crypto.selftests`). The
      one the kernel picks is the fastest at 4 KiB, engine or CPU (`crypto.bench.<algorithm>`).
      After a hash is made to time out or wedge the engine, the next one runs (`crypto.recovery.*`,
      in a debug build). An engine's RSA signs with fresh keys, every signature verified, at a rate
      shown beside the CPU's (`crypto.rsa.<driver>`)
