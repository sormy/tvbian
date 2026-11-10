# USB, remote, buttons, LEDs

## Do

1. **USB**: one device a generation, each on its own path: a USB 3 stick or SSD (`5000M`, `uas`), a
   USB 2 stick (`480M`, `usb-storage`), a keyboard, mouse or receiver (`12M`, HID). Ask for all
   three at once, each said disposable or not. `lsusb -t` first, then each stick under `fio` and
   `stress-ng` together; `fio` sized to the link, 256 MB read and 128 MB write on `480M`, 1 GB on
   `5000M`; raw reads `--readonly`, writes only to a disposable one.
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
- [ ] **U4** Every port under `fio` and `stress-ng` together, stable
- [ ] **U5** 👤 Hotplug on every port
- [ ] **U6** USB 1.1 at `12M`: a keyboard, mouse or receiver enumerates, its inputs appear
- [ ] **R1** `ir-keytable -r` lists every button, against the canonical keymap
- [ ] **R2** 👤 A remote the keymap doc lacks: every button under `evtest`, over IR and over BLE
- [ ] **R3** 👤 The remote cold-boots the box; each button registers or does its job; the recovery
      button reaches the service mode
- [ ] **R4** Every on-board input — IR, CEC, a button — has a name in `/dev/input`, from
      `base/input-names.rules`
- [ ] **R5** A recovery button the kernel sees sends `KEY_VENDOR` on `/dev/input/recovery-button`; a
      FEL or maskrom button only the boot ROM reads is ➖
- [ ] **E1** 👤 The LEDs on, off and asleep match the factory's
