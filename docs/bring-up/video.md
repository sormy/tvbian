# Video

What the box is sold for (4K60, HDR, 8K) names the pipeline that must work end to end, decoder to
screen in a player, before any one stage is judged.

## Do

1. **The vendor's matrix first** (`dump.md`): every codec, profile, depth and largest size, decode
   and encode, and HDR (HDR10, HLG, HDR10+, Dolby Vision) as a stream decoded and as a signal sent.
2. **The engine**, measured by `tools/validate/video.py` through FFmpeg, as Kodi uses it: every
   codec at every size of its ladder against FFmpeg's software decode, the decoder's own downscale,
   and every encoder's output decoded back. Its `matrix` output becomes the board's table in
   `board.md` and the chip's column in `docs/video-support.md`.
3. **Read the vendor's stack before writing ours**: its display driver and its player's decoder
   setup, the format it sends, what does the scaling, the clocks, the limits it checks. Ours does
   the same unless a measurement shows something better.
4. **Played in a player**, video with its audio, judged by eye and ear: the human's one step.

## Bites

- **Memory bandwidth can be the bottleneck**: decode, scaling and scanout share one bus. A rate that
  falls with resolution, or 8K that decodes but will not play, is checked against the board's Memory
  row before the codec is blamed.
- **Capability by doing.** A plane's formats are proven by `drmModeAddFB2WithModifiers` and a
  TEST_ONLY atomic commit, never a tool's listing: `modetest`'s list misdecodes here.

- **Real time is per codec, through the player's path**: on the H616, scaled 4K H.264 dropped a
  quarter of its pictures while HEVC kept up. An engine that stays busy between pictures is waiting
  on memory: check the reference frame layout before the clock.
- **At 4K60 memory is the limit**: the handover to the display must keep up, not only the decoder.
  On LPDDR3 or a 32-bit bus a 4K60 claim stands on AFBC.
- **A fault must leave the engine usable**: every clip past each limit is followed by a supported
  clip, checked against the software decode. When a job hangs, hits a corrupt stream or times out,
  the driver resets the engine and its IOMMU, and the next clip decodes without a reboot. Test a
  size on a freshly booted engine before calling it a limit.
- **A cap is the hardware's, measured**: a size or rate limit is set only where the engine fails
  past it. Run both the limit, which passes, and one step past, which fails, and name the test in
  the patch. A cap copied from another driver or a datasheet is a question.
- **Interlaced streams are their own codecs**: field-coded and MBAFF H.264, interlaced MPEG-2 and
  VC-1 take paths progressive clips never touch. An MBAFF regression here passed every progressive
  test. MPEG-2, MPEG-4 Part 2, H.263 and VC-1 are compared by PSNR: their IDCT is not bit-exact, and
  FFmpeg's own IDCTs disagree on one clip.
- **A picture read back on the CPU runs at memory speed**: a converter, a scaler or a thumbnailer
  maps decoded pictures, and an uncached buffer took 99 ms a 4K picture here against 24 ms cached.
- **Test as a normal user**: the nodes ship `0600`, and root hides a missing udev rule.
- **Ancient and regional codecs** (RealVideo, AVS) are worth little effort. ffmpeg patches that
  validate or fix a codec live in `patches/ffmpeg/`.
- **AVS, AVS+ and AVS2 are skipped on a mainline kernel**: Linux has no stateless controls for them,
  so C1 passes without them there; on a vendor kernel MPP decodes them.

## Check

- [ ] **C1** `video.py` decode passes every codec the vendor's matrix lists, at its largest size
- [ ] **C2** Every encoder's output decodes back to its source (`video.py` `encode`)
- [ ] **C3** The decoder's downscale, where it has one, works at each ratio it offers; asked for a
      smaller picture than it can make, it gives the smallest it can (`video.py` `scale`)
- [ ] **C4** 👤 A 4K film plays smooth in a player, its audio with it
- [ ] **C5** Where the decoder writes AFBC: 8- and 10-bit frames, decoder to plane (`video.py`
      `afbc`)
- [ ] **C6** The decoder's scaled picture, decoder to plane (`video.py` `scale`)
- [ ] **C7** After a clip past each limit, a supported one still decodes right (`video.py` `decode`
      reruns the largest passing size after the failures, and marks it `flaky` if it no longer
      passes)
- [ ] **C8** The board's matrix is in `board.md`, its chip's column in `docs/video-support.md`
- [ ] **C9** On each engine, after a job forced to time out and one forced to fault on the IOMMU,
      the next clip decodes right without a reboot (`video.py` `failure`, using the driver's
      `fail_next_job` in a `TVB_BUILD_DEBUG=1` kernel)
- [ ] **C10** Each size or rate cap: the limit decodes, one step past is refused, both recorded
      (`video.py` `decode`, its largest passing size and what refused past it)
- [ ] **C11** Interlaced clips, field and MBAFF H.264 and interlaced MPEG-2 and VC-1, against the
      software decode, by PSNR where the IDCT is not bit-exact (`video.py` `deinterlace`,
      `conformance`)
- [ ] **C12** A decoded 4K picture read back on the CPU at memory speed, cached and uncached timed
      (`video.py` `readback`, `readback_mbs`)
- [ ] **C13** A request the driver must refuse, such as a header that would hang the engine or an
      encode past its limits, fails with an error without starting the engine, and the kernel log
      stays quiet (`video.py` `refusal`)
- [ ] **C14** Each mem2mem converter copies a frame exactly at 1:1, and scales it near FFmpeg's
      (`video.py` `convert`)
- [ ] **C15** A clip damaged mid-stream decodes on as far as the software decoder goes, the kernel
      log quiet (`video.py` conceal)
- [ ] **C16** Each source layout the encoder lists codes near its own picture, RGB on the range its
      stream header states (`video.py` input)
- [ ] **C17** The deinterlacer gives the same frames when run twice on the same input; its
      one-frame-per-input control returns one frame per job, from the first field; FFmpeg's
      `deinterlace_v4l2m2m=rate=frame` comes close to bwdif's one frame per input (`video.py`
      `fields`, `deinterlace`)
