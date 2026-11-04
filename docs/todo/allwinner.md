# Allwinner: what is left, every board

- [ ] **H616: deep suspend.** The H616 has no SCPI core, so TF-A needs its own `SYSTEM_SUSPEND`:
      DRAM self-refresh and a wake path from EL3. Large; s2idle meanwhile.

- [ ] **Reboot into FEL from Linux, parked.** Stock writes "boot efex" to `misc` and its U-Boot
      jumps to the boot ROM's FEL; ours needs a flag Linux leaves and our U-Boot reads.

- [ ] **H616: a TCON rate the HDMI clock cannot divide.** 640x480 at 59.94: the TCON takes 453 MHz /
      18 for 25.167 MHz, the HDMI clock's divider stops at 16 and it falls to `pll-video2`, 24.750
      MHz. The TCON's rate should be one the HDMI clock reaches from the same PLL.
