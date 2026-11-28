# Allwinner: what is left, every board

- [ ] **A hardware cursor plane on the H616**: a spare UI channel typed cursor, if the mixer has one
      beyond the desktop's and the video's; mainline types every channel primary or overlay.
- [ ] **H616: deep suspend, parked.** The H616 has no SCPI core, so TF-A needs its own
      `SYSTEM_SUSPEND`: DRAM self-refresh and a wake path from EL3. Large; s2idle meanwhile.

- [ ] **Reboot into FEL from Linux, parked.** Stock writes "boot efex" to `misc` and its U-Boot
      jumps to the boot ROM's FEL; ours needs a flag Linux leaves and our U-Boot reads.

- [ ] **H616 SRAM bindings.** `dt-validate` rejects the SRAM sections' compatibles
      (`allwinner,sun50i-h616-ve-sram`, `sun50i-h616-sram-c`) on every H616 board; they need a
      `dt-bindings:` patch.

- [ ] **H616 analog audio on by default.** Line out and the DAC boot muted; the AV jack plays
      nothing until set by hand.

- [ ] **H616 display: `RCQ sync timed out`.** `sun50i-planes` logs it at boot; find the commit that
      misses its window.

- [ ] **H616 on 7.3: a one-CPU lockup resets by the hardware watchdog**, at 16 s, with no lockup
      panic or pstore record; 6.18's soft-lockup detector panics first and keeps the oops.

- [ ] **H616 on 6.18: CEC reads no physical address** where 7.3 reads `1.0.0.0` from the same
      monitor.

- [ ] **`screen.py` at 1080p and 4K whatever the panel**: an EDID override pins the mode, so the
      on-screen GPU check reaches the framebuffer sizes the tiler bug needs.

- [ ] **H616: 4K H.264 and VP8 on the screen**, linear frames as their decoder writes them: count
      underflows and frames shown, then settle the READMEs' "to 4K" mark.
- [ ] **H616: H.264 4K60**: the engine takes 24 ms a 4K picture, a 41 fps ceiling, with linear
      references; stock's `libawh264` has no compressed ones to follow, as H.265 and VP9 had.
- [ ] **VC-1 Main's B pictures on Cedrus** decode exact: SMPTE's SMM0005 gives them at 37 to 58 dB,
      I and P bit-exact, so `0815` refuses a Main sequence with B pictures. Its P pictures use 4MV.
