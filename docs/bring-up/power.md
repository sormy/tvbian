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
- **A watchdog may count in `s2idle`**: a sleep past its maximum then resets the box, back as a
  fresh boot; compare `boot_id`. One whose driver stops it on suspend does not, and a box nothing
  wakes then stays asleep until a power cycle: test `s2idle` with a hand on the plug.
- **Wake on a remote that is not reliable is disabled**, as on the H96 Max 3518D.
- **Meter the bare board**: a USB stick and HDMI move the figure by tenths of a watt.

## Check

- [ ] **W1** 👤 Sleep and wake, off and on, by each route the box has
- [ ] **W2** Every wake route kept is reliable; the rest disabled
- [ ] **W3** Resumed on the remote, it stayed up: no logind double-fire in the journal
- [ ] **W4** `s2idle`, with its wake source, where there is no `deep`
- [ ] **W5** Deep, with its wake source, or a scoped to-do
- [ ] **W6** A suspend longer than the watchdog's maximum and its set timeout resumes the same
      `boot_id`, the timer armed after
- [ ] **W7** The RTC keeps time, or its absence is recorded
- [ ] **W8** 👤 Optional: power draw in sleep, against idle, for what sleep saves
