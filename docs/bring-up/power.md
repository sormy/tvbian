# Power

## Do

1. Sleep and wake, off and on, by each route the box has: wired IR, a power button, a BLE key.
2. Suspend is two rows, `s2idle` and deep (`deep` in `/sys/power/mem_sleep`), each with its wake
   source and its power draw. A missing deep state goes on the todo page with what it needs, such as
   TF-A's `SYSTEM_SUSPEND` or the SCP firmware.
3. Every sleep test runs longer than every timer that could end it: the watchdog's hardware maximum
   and its set timeout.

## Bites

- **Never suspend a box remotely** that has no RTC and no network wake: nothing brings it back.
- **A watchdog may keep counting in `s2idle`**: a sleep longer than its maximum then resets the box,
  which comes back as a fresh boot (compare `boot_id`). If the driver stops the watchdog on suspend
  instead, a box that nothing wakes stays asleep until a power cycle, so test `s2idle` with a hand
  on the plug.
- **Wake on a remote that is not reliable is disabled**, as on the H96 Max 3518D.
- **Meter the bare board**: a USB stick and HDMI move the figure by tenths of a watt.

## Check

- [ ] **W1** 👤 Sleep and wake, off and on, by each route the box has
- [ ] **W2** Every wake route kept is reliable; the rest disabled
- [ ] **W3** Resumed on the remote, it stayed up: no logind double-fire in the journal
- [ ] **W4** `s2idle`, with its wake source, where there is no `deep`
- [ ] **W5** Deep sleep works and wakes on its wake source, or a todo on the board's page says why
      not (`sleep.states`, `wake.remote`)
- [ ] **W6** A suspend longer than the watchdog's maximum and its set timeout resumes the same
      `boot_id`, the timer armed after
- [ ] **W7** The RTC keeps time, or its absence is recorded (`rtc`)
- [ ] **W8** 👤 Optional: power draw in sleep, against idle, for what sleep saves
- [ ] **W9** On a box behind a switchable outlet: a box put to sleep stays asleep, and one powered
      off stays off, until the outlet is power-cycled; it comes back after each (`power.sleep`,
      `power.poweroff`)
