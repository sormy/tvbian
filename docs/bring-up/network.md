# Network

## Do

1. Ethernet at every link speed, at line rate, idle and under 4-core load, with `iperf3`.
2. Wi-Fi on every band, idle and under CPU and I/O load, then hours associated under traffic.
   Station mode is the bar; access point and Wi-Fi Direct are the vendor's parity, each against the
   interface modes stock's `iw list` shows.
3. Bluetooth: the controller up, a scan, the bundled remote paired.
4. Every address read at its source. Ask the owner for the printed one, usually Ethernet's, or
   Wi-Fi's on a box without; unattended, its check waits in the board's todo.

## Bites

- **`ssh` is no throughput test**: its encryption is CPU load.
- **A latch is a link that does not come back**: re-measure at once and after 60 s idle, and record
  what clears it: reassociate, reload, reboot. Then where the interrupts land: `smp_affinity`,
  `rps_cpus`, bus-thread priorities, each shipped as board data with its measurement.
- **Count the drops**, not only the throughput: `CTRL-EVENT-DISCONNECTED` in the journal over the
  soak, each outage timed to `CTRL-EVENT-CONNECTED`, filtered by the journal's own time
  (`journalctl --since`), never by parsing `dmesg`.
- **Conditions match before kernels are compared**: a quiet box, the link rate in the result, the
  median of three runs.

- **Addresses, best first**: the chip's eFUSE; the label, or the factory store holding it; the
  chip's ID; the SoC's. Random is the bug. Bluetooth is the Wi-Fi's plus one where nothing holds its
  own.
- **An eFUSE may hold an address per mode**: the label names the station's.
- **BLE wake needs the BT driver to set `hdev->wakeup`**, or only IR wakes the box.

## Check

- [ ] **N1** Ethernet at every link speed
- [ ] **N2** Ethernet at line rate, idle
- [ ] **N3** Ethernet at line rate under 4-core load
- [ ] **N4** The Ethernet PHY's driver is the vendor's, not Generic
- [ ] **N5** Wi-Fi on every band, the regulatory domain named
- [ ] **N6** Wi-Fi throughput, idle
- [ ] **N7** Wi-Fi throughput under CPU and I/O load
- [ ] **N8** Hours under traffic: no drop in the journal, then `iperf3` at the healthy rate
- [ ] **N9** With no region set, a scan finds networks
- [ ] **N10** `iw reg set <country>`, then `iw reg get` shows it
- [ ] **N11** BT: `hci0` `UP RUNNING`, `errors:0`
- [ ] **N12** `btmgmt find` lists devices
- [ ] **N13** 👤 The bundled remote pairs, and stays paired across a reboot
- [ ] **N14** 👤 The remote wakes the box over BLE: ❌ on every board so far, scoped in
      `docs/todo/README.md`
- [ ] **N15** Every address is stable across reboots and an eMMC migration
- [ ] **N16** Every address is the unit's own, shown by a read
- [ ] **N17** Per-unit firmware (EEPROM, calibration, NVRAM) is named for the board
- [ ] **N18** Access point mode serves a client, where stock offers it, or a scoped to-do; once a
      chip
- [ ] **N19** Wi-Fi Direct connects to a peer, where stock offers it, or a scoped to-do; once a chip
- [ ] **N20** `iw list`'s interface modes match stock's; once a chip
- [ ] **N21** Each address comes from the best source the box has
- [ ] **N22** 👤 The printed address is in use on its interface
