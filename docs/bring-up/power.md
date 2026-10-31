# Power

## Do

1. Sleep and wake, off and on, by each route the box has: wired IR, a power button, a BLE key.
2. Suspend is two rows, `s2idle` and deep (`deep` in `/sys/power/mem_sleep`), each with its wake
   source and its draw. A missing deep state is a scoped to-do: TF-A's `SYSTEM_SUSPEND`, the SCP
   firmware.
3. Every sleep test runs longer than every timer that could end it: the watchdog's hardware maximum
   and its set timeout.

## Bites

- **Never suspend a box remotely** that has no RTC and no network wake: nothing brings it back.
- **A watchdog counts in `s2idle`**: a sleep past its maximum resets the box, and comes back as a
  fresh boot. Compare `boot_id`.
- **Wake on a remote that is not reliable is disabled**, as on the H96 Max 3518D.
- **Meter the bare board**: a USB stick and HDMI move the figure by tenths of a watt.

## Check

- [ ] **W1** 👤 Sleep and wake by each route the box has
- [ ] **W2** 👤 Off and on by each route the box has
- [ ] **W3** Every wake route kept is reliable; the rest disabled
- [ ] **W4** 👤 Resumed on the remote, it stays up: no logind double-fire
- [ ] **W5** `s2idle`, with its wake source
- [ ] **W6** Deep, with its wake source, or a scoped to-do
- [ ] **W7** A suspend longer than the watchdog's maximum and its set timeout resumes the same
      `boot_id`, the timer armed after
- [ ] **W8** The RTC keeps time, or its absence is recorded
- [ ] **W9** 👤 Where sleep works: draw at idle, suspended and off, on the bare board
