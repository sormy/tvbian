# H96 Max M2 Plus: what is left

The board's open items.

- [ ] **A TV at 4K60.** Picture and sound, replugged, the TV remote's mute and volume over CEC.

- [ ] **The serial pins outlined on a PCB photo**, TX · GND · RX named.

- [ ] **`rk35xx-next`: the combined soak and hours of traffic.** 30 minutes of CPU, RAM, eMMC and
      Wi-Fi load, then hours of Wi-Fi traffic, on 6.12.

- [ ] **No Lima MMU fault under the combined soak.** Seen once in three 30-minute soaks on 6.1, at
      103 °C; the other two, to 105 °C and capped at 95 °C, were clean.

- [ ] **The USB 3 root port logs `config error`** with nothing plugged.

- [ ] **`gpu-bus` fails to probe**, no `pvtm` regulator: `vdd_logic` does not follow the GPU clock.
      The DMC floor is 850 mV; the GPU bus wants up to 875 mV at 800 MHz. 900 mV read at idle.

- [ ] **A few days of daily use**, each issue a worklog entry.
