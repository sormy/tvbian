# Identity and components

## Do

1. **The board ID** names one hardware design: the sticker's product name, lowercase with dashes,
   the brand where it owns a domain. Search it: if the results mix years, PCBs or SoCs, qualify it
   with a version or PCB revision, `r69-1` not `r69`. The agent proposes it from the sticker,
   silkscreen and photos; the human confirms it before any file is named, since a renamed board is a
   package rename on every installed box.
2. **The case open, every component**, the heat sink lifted where it comes off:

   | Component   | Record                                    |
   | ----------- | ----------------------------------------- |
   | SoC         | the exact part, from its marking          |
   | Wi-Fi/BT    | the chip or module part                   |
   | RAM, eMMC   | part, type, size                          |
   | ports       | every one, unpopulated ones too           |
   | IR receiver | where it is; often behind the front panel |
   | LEDs        | each one and its colour                   |
   | buttons     | the recovery hole, side buttons           |
   | other chips | any MCU, PMIC or Ethernet PHY             |

   The silkscreen's name goes in `BOARD_PCB`, its date in `BOARD_DATE`.

3. **`board.md`**, in this order:

   | Section        | Holds                                                        |
   | -------------- | ------------------------------------------------------------ |
   | Identity       | name, PCB, components, the product and PCB photos            |
   | Serial console | location, pinout and its square pad, level, console and baud |
   | Addresses      | each one and its source                                      |
   | Test report    | every check by name, its mark per kernel, its evidence       |
   | Measured       | the numbers, dated, with what was fitted                     |
   | per component  | how each works on this board                                 |
   | Known gaps     | ❌, ❓, the trade-offs, each scoped                          |
   | Recovery       | this box's way into the service mode, and back               |

4. **The serial pins**, on the open board. TX carries the console out, RX takes keystrokes in;
   reading needs only GND and TX.
   1. GND reads 0 V against exposed metal: a USB, HDMI or Ethernet shell.
   2. The supply pad reads highest, 3.3 V or 5 V; TX and RX a few mV below it.
   3. GND and the box's TX first, to the adapter's RX, which only listens. The candidate that prints
      is TX.
   4. The logger at the family's baud, 1500000 on Rockchip, 115200 on Amlogic and Allwinner, a new
      file per boot, then power-cycle:
      `tio -b <baud> -t -L --log-file build/logs/<board>/<YYYYMMDD-HHMMSS>.log <port>`.
   5. The box's RX last, for a shell: it drives the SoC, so the jumper is set to the SoC's level
      first. Never the supply pad.
   6. Contact held firm: a hook in a plated hole touches only its rim. Noise between clean lines, or
      the adapter dropping off USB, is a loose pin or GND, not the baud.

## Bites

- **One case holds several boards.** A vendor ships look-alike cases with different SoCs; the
  silkscreen names the board, the case does not.

## Check

- [ ] **L1** 👤 Where stock boots with serial attached: its log scrolls there
- [ ] **I1** The ID is searched: every result is this box
- [ ] **I2** The human confirmed the ID
- [ ] **I3** 👤 Photos of both sides of the PCB, the markings readable
- [ ] **I4** 👤 The serial pads outlined on the PCB photo, each pin named (TX, RX, GND) with its
      voltage, where the board has them
- [ ] **I5** Every component is in `board.md`, by part
- [ ] **I6** `board.md` has every section above
- [ ] **I7** `BOARD_PCB` and `BOARD_DATE` are the silkscreen's name and date
