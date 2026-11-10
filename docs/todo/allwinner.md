# Allwinner: what is left, every board

- [ ] **H616: deep suspend, parked.** The H616 has no SCPI core, so TF-A needs its own
      `SYSTEM_SUSPEND`: DRAM self-refresh and a wake path from EL3. Large; s2idle meanwhile.

- [ ] **Reboot into FEL from Linux, parked.** Stock writes "boot efex" to `misc` and its U-Boot
      jumps to the boot ROM's FEL; ours needs a flag Linux leaves and our U-Boot reads.
- [ ] **H616 analog audio on by default.** Line out and the DAC boot muted; the AV jack plays
      nothing until set by hand.
- [ ] **H616 display: `RCQ sync timed out`.** `sun50i-planes` logs it at boot; find the commit that
      misses its window.
- [ ] **H616: a long `s2idle` resets.** 100 s of `s2idle` ends in a reset with no pstore record,
      though `0092` stops `sunxi_wdt` in suspend; 20 s resumes. Find what fires.
- [ ] **H616 on 7.3: a one-CPU lockup resets by the hardware watchdog**, at 16 s, with no lockup
      panic or pstore record; 6.18's soft-lockup detector panics first and keeps the oops.
- [ ] **H616 on 6.18: CEC reads no physical address** where 7.3 reads `1.0.0.0` from the same
      monitor.
