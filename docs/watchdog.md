# The watchdog

Every box arms its SoC's hardware watchdog at boot: systemd opens `/dev/watchdog0` and pings it. A
hang that stops the pings resets the box, and the kernel's last log survives the reset in
`/var/lib/systemd/pstore/`.

## Check it

On the box:

```sh
wdctl                                       # the timeout the hardware runs, and who holds it
journalctl -b | grep 'Watchdog running'     # systemd's view of the same
```

The timeout asked for is `RuntimeWatchdogSec` in
`/usr/lib/systemd/system.conf.d/zz-tvb-watchdog.conf`. The driver rounds it to a step its hardware
has, no higher than its maximum, and systemd pings at half of what it got.

## Reboot with it armed

Once armed, the watchdog cannot be stopped, and its count runs on through a soft reboot: the
shutdown and the next boot together must finish inside one window, or the hardware resets the box
during boot. On some boxes that reset leaves the box dark until its power is pulled. Reboot a box
remotely only where someone can reach its power.

Sleep depends on the driver. One that stops the count in suspend starts it full on resume, so a box
sleeps as long as it likes; one that does not resets a box asleep past its window. The board's
`board.md` says which, once tested.

## Read a crash

| In pstore           | Means                                                           |
| ------------------- | --------------------------------------------------------------- |
| `dmesg-ramoops-N`   | a panic or oops: the kernel's last log                          |
| `console-ramoops-N` | the boot before's console, kept on any warm reboot; not a crash |

## Turn it off

On the box, `RuntimeWatchdogSec=off` in the same drop-in, then:

```sh
systemctl daemon-reexec
```

Nothing then resets a hung box. Keeping it on, and rebooting only where the power is in reach, is
the better trade.
