# Desktop worklog

## 2026-11-17 — gaps closed without a box, untested on one

- `tvb-desktop`: a udev rule starts greetd on a DRM hotplug, for a screen plugged in after a
  headless boot.
- `tvb-desktop`: kanshi, now a depend, runs in the greeter and the session and re-applies each
  screen's scale whenever the set of screens changes; wlroots already gives a new screen its
  preferred mode. `scale-outputs` ran only at greeter start and login.

## 2026-11-25 — greetd no longer starts at boot

- On next2 the M2 Plus's greeter, labwc running gtkgreet on VT 7, exited at once: greetd restarted
  it until systemd gave up, and between restarts its greeter took the console's VT, the kernel's
  fbdev client then turning every output off under the display checks.
- `postinst` disables greetd on the first install: the desktop is started by hand while it is
  experimental. The suite's system step fails a display manager enabled at boot (`units.autostart`).
  greetd disabled on the M2 Plus; greetd and gtkgreet purged on the M20 and the H313, left over from
  `tvb-desktop`'s removal.
