# First contact

The human may know only what the shop called the box. Ask for actions, not facts: whatever the box
can show, the agent reads off it. Say what each action is for.

## Do

1. 👤 Ask for the product listing URL first. Read its model, selected variant where visible, ports
   and accessories. Ask only for photos that resolve what the listing cannot show: the delivered
   unit, its label or accessories. Keep the URL and photos in `docs/<board>/` once the ID is agreed.
2. **Ask: a serial adapter, and the pins found?** `identity.md`'s serial steps, then stock Android
   booted with the console attached: often a root shell. Take `dump.md`'s small files there and
   then.
3. **Else ask: an OTG cable?** A USB-A male-to-male cable from the OTG port to the host, the
   recovery button held while the box powers up: the USB service mode. Its vendor ID, in `lsusb` or
   `system_profiler SPUSBDataType`, names the family: `2207` Rockchip, `1b8e` Amlogic, `1f3a`
   Allwinner.
4. **No cable to hand: the network**, on the few boxes whose stock listens for `adb` on TCP: try
   `adb connect <ip>:5555`, then `adb root`. A `userdebug` build with `ro.adb.secure` 0 gives a root
   shell, and `dump.md`'s files come over it.
5. **Last, Android's UI**: Developer options, debugging, `adb`. TV firmware often hides them.
6. Read the SoC, decide the kind (the table in `README.md`), and tell the human what comes next.

## Bites

- **The name lies.** A box labelled "H96 Max H313", branded LEFFOT, is an RK3518; vendors keep a
  model name, a case and a web page across chip changes, and clones copy all three.
- **A listing describes the offer, not the delivered hardware.** An inaccessible listing needs its
  title and selected variant from the human; it does not require a full photo set.
- **Android lies too.** Spoofed firmware reports more RAM, storage and a faster SoC. The SoC is read
  where Android cannot reach: the service mode's vendor ID, or the `compatible` of the factory tree
  carved from the eMMC.
- **Serial and OTG both connected, no DC.** Most boxes run from OTG alone; DC beside OTG can
  backfeed one supply into the other.

## Check

- [ ] **K1** 👤 Listing URL or product photos recorded; delivered-unit ambiguities resolved
- [ ] **K2** The SoC, read from the service mode or the factory tree
- [ ] **K3** The kind decided and told to the human
