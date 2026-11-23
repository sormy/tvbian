# HK1 RBOX K8S

- [ ] **HDMI picture and sound on vendor 6.1**: the HPD GPIO reads high, the PHY's HPD bit low, so
      the driver reports no sink, EDID or modes.
- [ ] **USB Ethernet on the SuperSpeed hub** through every warm boot and under load.
- [ ] **Wi-Fi download at 2.4 GHz on next2, every run**: nothing in two of four runs.
- [ ] **The FD650B-S's status icons**, if the panel has them.
- [ ] **Bluetooth flow control on next2**: UART2 muxes no RTS there; the vendor tree's Bluetooth
      node holds `uart2m0_rtsn`.
- [ ] **The SDIO power-off delay at its measured minimum**: 2 s is the only value tried.

## 👤 By hand

- [ ] Pair a BLE remote and a Bluetooth keyboard; each survives a power cycle.
- [ ] On a screen: HDMI sound, glmark2, a 4K60 player, HDR, DDC/CI.
- [ ] Composite picture and analog sound from the AV jack.
- [ ] Ethernet at 10 Mb/s.
- [ ] A fast stick on USB 3 and USB 2; a low-speed keyboard; a keyboard on the OTG port.
- [ ] A UHS card in the SD slot at its UHS mode; out and back in.
- [ ] The factory image restored over OTG.
- [ ] The front panel's brightness set.
