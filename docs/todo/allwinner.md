# Allwinner: what is left, every board

- [ ] **H616: deep suspend, parked.** The H616 has no SCPI core, so TF-A needs its own
      `SYSTEM_SUSPEND`: DRAM self-refresh and a wake path from EL3. Large; s2idle meanwhile.

- [ ] **Reboot into FEL from Linux, parked.** Stock writes "boot efex" to `misc` and its U-Boot
      jumps to the boot ROM's FEL; ours needs a flag Linux leaves and our U-Boot reads.
