# USB, remote, buttons, LEDs

## Do

1. **USB**: `lsusb -t` first, then every port with a disk faster than its link under `fio` and
   `stress-ng` together; `fio` sized to the link, 256 MB read and 128 MB write on `480M`, 1 GB on
   `5000M`; raw reads `--readonly`, writes to a file on its filesystem.
2. **IR, before any key is pressed**: `ir-keytable -s rcN -p all -t` decodes with no keymap; stock's
   tree (Allwinner `ir_addr_codeN`, Rockchip `ir_key`) and the vendor's `usr/keylayout/` name the
   codes; grep mainline's `drivers/media/rc/keymaps/` for one captured scancode. After a cold boot,
   `ir-keytable -r` lists every button against the canonical keymap in `docs/remote-keymap.md`.
3. **The human's presses**, last: under `evtest`, saying the order; each button's icon seen, on the
   remote or a photo, before its key is chosen.

## Bites

- **A stick is another board's image until `lsblk -f` says not.**
- **USB 3 is judged by its BOS capability**, not `bcdUSB`, the device plugged straight in.
- **The keymap lives in one layer**: a keymap the tree names, never one corrected by `hwdb`, which
  `ir-keytable -a` undoes at every add. A built-in IR driver probes before the rootfs and finds no
  keymap: build it as a module.
- **A bound node is the receiver, not the remote**: IR is ✅ only on key events.
- **A name in a message is not an icon**: "rewind" was `|<<`.

## Check

- [ ] **U1** `lsusb -t`: no USB 2 hub in the way
- [ ] **U2** USB 3 judged by its BOS capability, at `5000M` on `uas`
- [ ] **U3** USB 2 at `480M`, a stick in at power-on enumerating as one plugged in after does
- [ ] **U4** 👤 Every port under `fio` and `stress-ng` together, stable
- [ ] **U5** 👤 Hotplug on every port
- [ ] **R1** `ir-keytable -r` lists every button, against the canonical keymap
- [ ] **R2** 👤 IR produces the canonical keymap under `evtest`
- [ ] **R3** 👤 BLE produces the canonical keymap
- [ ] **R4** 👤 The remote cold-boots the box from off
- [ ] **R5** 👤 Each button registers as input, or does its job at power-on
- [ ] **R6** 👤 The recovery button reaches the service mode
- [ ] **R7** Every `/dev/input/event*` has a name in `/dev/input`, from `base/input-names.rules`
- [ ] **E1** 👤 The LEDs' on state matches the factory's
- [ ] **E2** 👤 The off state matches the factory's
- [ ] **E3** 👤 The suspended state matches the factory's
