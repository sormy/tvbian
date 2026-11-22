# Desktop worklog

## 2026-11-17 — gaps closed without a box, untested on one

- `tvb-desktop`: a udev rule starts greetd on a DRM hotplug, for a screen plugged in after a
  headless boot.
- `tvb-desktop`: kanshi, now a depend, runs in the greeter and the session and re-applies each
  screen's scale whenever the set of screens changes; wlroots already gives a new screen its
  preferred mode. `scale-outputs` ran only at greeter start and login.
