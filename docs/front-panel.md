# Front-panel clock

A box whose front-panel display has a driver shows the time on it, whatever the chip: the clock runs
wherever a display named `display` and its colon, `display::colon`, appear under `/sys/class/leds/`.
Settings go in `/etc/default/tvb-front-panel` on the box:

| Setting              | Values                                    | Default         |
| -------------------- | ----------------------------------------- | --------------- |
| `DISPLAY_CLOCK`      | `12h`, `24h`, `off`                       | `24h`           |
| `DISPLAY_BRIGHTNESS` | `1`–`8`                                   | `3`             |
| `DISPLAY_COLON`      | `on`, `off`, `blinking`                   | `blinking`      |
| `DISPLAY_TIMEZONE`   | Zoneinfo name, such as `America/New_York` | System timezone |

The clock picks up a change at the next minute. To apply it now, on the box, as root:

```sh
systemctl start tvb-front-panel.service
```

- The 12-hour clock leaves the leading digit blank for single-digit hours.
- `DISPLAY_CLOCK=off` blanks the digits and the colon.
- A panel with fewer than 8 brightness levels caps `DISPLAY_BRIGHTNESS` at its top one.
- Asleep, the panel is dark. It redraws at once on waking, and when the system clock or time zone is
  set.
