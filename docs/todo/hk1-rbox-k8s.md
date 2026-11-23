# HK1 RBOX K8S

- [ ] **HDMI picture and sound on vendor 6.1**: a screen attached at boot reads disconnected while
      next2 finds it. The GPIO reads high; the vendor mirrors it into the controller once at probe,
      right after enabling the pin's input, and no edge comes later to correct it.
- [ ] **The GPU's clocks on 6.1 with their measured reason**: both `ACLK_GPU_MALI`, where next2's
      core runs on SCMI.
- [ ] **UART2 the same on both trees**: 6.1 drops its DMA, next2 keeps it.
- [ ] **The analog codec's timing on 6.1**: 3.02 s against 6.12's 2.03 s for a 2 s clip.
- [ ] **USB Ethernet on the SuperSpeed hub** through every warm boot and under load.
- [ ] **Wi-Fi download at 2.4 GHz on next2, every run**: nothing in two of four runs.
- [ ] **The FD650B-S's status icons**, if the panel has them.
- [ ] **Bluetooth flow control on next2**: UART2 muxes no RTS there; the vendor tree's Bluetooth
      node holds `uart2m0_rtsn`.
- [ ] **The SDIO power-off delay at its measured minimum**: 2 s is the only value tried.

## 👤 By hand

- [ ] HDMI on 6.1: unplug and replug the cable with a screen on; does it find the screen.
- [ ] The serial pads' voltage.
- [ ] Pair a BLE remote and a Bluetooth keyboard; each survives a power cycle.
- [ ] On a screen: HDMI sound, glmark2, a 4K60 player, HDR, DDC/CI.
- [ ] Composite picture and analog sound from the AV jack.
- [ ] Ethernet at 10 Mb/s.
- [ ] A fast stick on USB 3 and USB 2; a low-speed keyboard; a keyboard on the OTG port.
- [ ] A UHS card in the SD slot at its UHS mode; out and back in.
- [ ] The factory image restored over OTG.
- [ ] The front panel's brightness set.
