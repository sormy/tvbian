# H96 Max M2 Plus: what is left

The board's open items.

- [ ] **A TV at 4K60.** Picture and sound, replugged, the TV remote's mute and volume over CEC.

- [ ] **Serial: find and mark the pads.** Three unpopulated pads on the underside. With a
      multimeter: GND by continuity to the shield, TX by its idle level with the box on, RX the one
      left; the voltage from TX's idle level. Mark them on `board-bottom.jpg`, pin names and voltage,
      then solder a header: the stock boot log, U-Boot, the kernel and the login on serial.

- [ ] **`rk35xx-next`: the combined soak and hours of traffic.** 30 minutes of CPU, RAM, eMMC and
      Wi-Fi load, then hours of Wi-Fi traffic, on 6.12.

- [ ] **A Lima MMU fault at 103 °C**, in one of two 30-minute soaks on 6.1. Repeat the soak and read
      whether it comes back.

- [ ] **The USB 3 root port logs `config error`** with nothing plugged.

- [ ] **`gpu-bus` fails to probe**, no `pvtm` regulator: `vdd_logic` does not follow the GPU clock.
      The DMC floor is 850 mV; the GPU bus wants up to 875 mV at 800 MHz. 900 mV read at idle.

- [ ] **A few days of daily use**, each issue a worklog entry.
